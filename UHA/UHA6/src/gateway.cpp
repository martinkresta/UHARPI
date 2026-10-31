#include "gateway.h"

#include <cerrno>
#include <climits>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <poll.h>
#include <sys/signalfd.h>
#include <sys/stat.h>
#include <sys/timerfd.h>
#include <unistd.h>

#include "cJSON.h"
#include "event_log.h"
#include "log.h"
#include "outputs.h"

#define UHAGATE6_VERSION "6.0.0"

struct VarName
{
    int id;
    const char* name;
};
static const VarName kVarNames[] = {
#include "var_names.inc"
};

static double mono_now()
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

static long rss_kb()
{
    long pages = 0, resident = 0;
    FILE* f = fopen("/proc/self/statm", "r");
    if (f == nullptr) return -1;
    if (fscanf(f, "%ld %ld", &pages, &resident) != 2) resident = -1;
    fclose(f);
    return resident < 0 ? -1 : resident * (sysconf(_SC_PAGESIZE) / 1024);
}

Gateway::Gateway(const Config& cfg) : mCfg(cfg), mLink(cfg.port)
{
    for (double& t : mVarRxMono) t = -1;
}

// ---------------------------------------------------------------------------------------------
// main loop

int Gateway::run()
{
    mStartMono = mono_now();
    mStartUnix = time(nullptr);
    mLinkChangeMono = mStartMono;
    mLinkChangeUnix = mStartUnix;
    mNextErrorSummaryMono = mStartMono + mCfg.errorSummaryS;
    mNextHourlyMono = mStartMono + 3600;

    LOG_I("UhaGate6 %s starting (pid %d)", UHAGATE6_VERSION, (int)getpid());
    LOG_I("%s", config_describe(mCfg).c_str());
    if (access(mCfg.outDir.c_str(), W_OK) != 0)
        LOG_E("output folder %s is not writable: %s", mCfg.outDir.c_str(), strerror(errno));

    signal(SIGPIPE, SIG_IGN);
    sigset_t mask;
    sigemptyset(&mask);
    sigaddset(&mask, SIGINT);
    sigaddset(&mask, SIGTERM);
    sigaddset(&mask, SIGHUP);
    sigprocmask(SIG_BLOCK, &mask, nullptr);
    int sigFd = signalfd(-1, &mask, SFD_CLOEXEC | SFD_NONBLOCK);
    int timerFd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC | TFD_NONBLOCK);
    if (sigFd < 0 || timerFd < 0)
    {
        LOG_E("cannot create signalfd/timerfd: %s", strerror(errno));
        return 1;
    }
    struct itimerspec period = {};
    period.it_interval.tv_sec = mCfg.jsonPeriodMs / 1000;
    period.it_interval.tv_nsec = (mCfg.jsonPeriodMs % 1000) * 1000000L;
    period.it_value = period.it_interval;
    timerfd_settime(timerFd, 0, &period, nullptr);

    openLink();

    int exitCode = 0;
    bool running = true;
    while (running)
    {
        struct pollfd fds[3];
        fds[0] = {sigFd, POLLIN, 0};
        fds[1] = {timerFd, POLLIN, 0};
        nfds_t count = 2;
        if (mLink.isOpen())
        {
            fds[2] = {mLink.fd(), POLLIN, 0};
            count = 3;
        }

        if (poll(fds, count, -1) < 0)
        {
            if (errno == EINTR) continue;
            LOG_E("poll failed: %s", strerror(errno));
            exitCode = 1;
            break;
        }

        if (count == 3 && fds[2].revents != 0) onSerialReadable(fds[2].revents);

        if (fds[1].revents & POLLIN)
        {
            uint64_t expirations;
            if (read(timerFd, &expirations, sizeof(expirations)) == sizeof(expirations)) onTick();
        }

        if (fds[0].revents & POLLIN)
        {
            struct signalfd_siginfo si;
            while (read(sigFd, &si, sizeof(si)) == sizeof(si))
            {
                if (si.ssi_signo == SIGHUP)
                {
                    LOG_I("SIGHUP ignored (restart the service to reload the config)");
                    continue;
                }
                LOG_I("stopping on signal %s", strsignal(si.ssi_signo));
                running = false;
            }
        }
    }

    mLink.close();
    close(timerFd);
    close(sigFd);
    LOG_I("UhaGate6 stopped");
    return exitCode;
}

void Gateway::onTick()
{
    const double now = mono_now();
    const time_t nowUnix = time(nullptr);

    if (!mLink.isOpen() && now >= mNextReopenMono) openLink();

    writeOutputs();

    // RTC sync: on every change of the period slot (period 60 s = every minute change, as in UHA5)
    const long slot = (long)(nowUnix / mCfg.rtcPeriodS);
    if (slot != mLastRtcSlot)
    {
        mLastRtcSlot = slot;
        if (mLink.isOpen()) sendRtc();
    }

    // link open but silent
    if (mLink.isOpen() && !mSilenceWarned)
    {
        const double ref = mReceiving ? mLastPacketMono : mLinkChangeMono;
        if (now - ref > mCfg.silenceWarnS)
        {
            LOG_W("serial link open but no packets for %d s", mCfg.silenceWarnS);
            mSilenceWarned = true;
            mReceiving = false;
        }
    }

    periodicReports(now);
}

// ---------------------------------------------------------------------------------------------
// serial link

void Gateway::openLink()
{
    const double now = mono_now();
    mOpenAttempts++;
    if (mLink.open())
    {
        if (mHadLink)
        {
            mReconnects++;
            LOG_I("serial link up again: %s (down %.0f s, %u attempts)", mLink.path().c_str(),
                  now - mLinkChangeMono, mOpenAttempts);
        }
        else
        {
            LOG_I("serial link up: %s", mLink.path().c_str());
        }
        mHadLink = true;
        mOpenAttempts = 0;
        mLastOpenError.clear();
        mLinkChangeMono = now;
        mLinkChangeUnix = time(nullptr);
        mReceiving = false;
        mSilenceWarned = false;
        mParser.reset();

        // nodes get the time right away instead of waiting for the next minute
        mLastRtcSlot = (long)(time(nullptr) / mCfg.rtcPeriodS);
        sendRtc();
        return;
    }

    mNextReopenMono = now + mCfg.reopenS;
    if (mLink.lastError() != mLastOpenError || now - mLastOpenErrorLogMono >= 600)
    {
        LOG_W("cannot open serial port %s: %s (retrying every %d s)", mLink.path().c_str(),
              mLink.lastError().c_str(), mCfg.reopenS);
        mLastOpenError = mLink.lastError();
        mLastOpenErrorLogMono = now;
    }
}

void Gateway::linkLost(const std::string& reason)
{
    if (!mLink.isOpen()) return;
    const double now = mono_now();
    LOG_W("serial link lost: %s (was up %.0f s)", reason.c_str(), now - mLinkChangeMono);
    mLink.close();
    mParser.reset();
    mLinkChangeMono = now;
    mLinkChangeUnix = time(nullptr);
    mNextReopenMono = now + mCfg.reopenS;
    mReceiving = false;
    mSilenceWarned = false;
    mLastOpenError.clear();
}

void Gateway::onSerialReadable(short revents)
{
    if (revents & POLLIN)
    {
        uint8_t buf[512];
        for (int i = 0; i < 16 && mLink.isOpen(); i++)
        {
            ssize_t n = mLink.read(buf, sizeof(buf));
            if (n < 0)
            {
                linkLost(mLink.lastError());
                return;
            }
            if (n == 0) return;
            mParser.feed(buf, (size_t)n, [this](const RpiPacket& p) { onPacket(p); });
        }
        return;
    }
    if (revents & (POLLHUP | POLLERR | POLLNVAL))
        linkLost((revents & POLLHUP) ? "hang-up (device disconnected)" : "poll error");
}

void Gateway::onPacket(const RpiPacket& packet)
{
    const double now = mono_now();
    if (!mReceiving)
    {
        if (mSilenceWarned)
            LOG_I("receiving data again after %.0f s",
                  now - (mLastPacketMono > mLinkChangeMono ? mLastPacketMono : mLinkChangeMono));
        else
            LOG_I("receiving data");
        mReceiving = true;
        mSilenceWarned = false;
    }
    mLastPacketMono = now;

    if (packet.id == CMD_TM_VAR_VALUE)
    {
        mVarPackets++;
        if (packet.dlc < 4)
        {
            mMalformed++;
            return;
        }
        const int varId = (packet.data[0] << 8) + packet.data[1];
        const short value = (short)((packet.data[2] << 8) | packet.data[3]);
        LOG_D("var %d = %d", varId, value);
        if (varId < NUM_OF_VARS)
        {
            mVars[varId] = value;
            mVarRxUnix[varId] = time(nullptr);
            mVarRxMono[varId] = now;
            mVarCount[varId]++;
        }
        else
        {
            mOutOfRangeVars++;
        }
    }
    else if (packet.id == CMD_LOG_MSG)
    {
        mLogPackets++;
        NodeInfo& node = mNodes[packet.data[0]];
        node.lastSeenUnix = time(nullptr);
        node.lastSeenMono = now;
        node.messages++;
        node.lastEvent = event_type_name(packet.data[1]);
        appendEventLog(packet.data);
    }
    else
    {
        mUnknownIds++;
        LOG_D("unknown packet id 0x%03X dlc %d", packet.id, packet.dlc);
    }
}

bool Gateway::sendPacket(uint16_t id, const uint8_t* data, uint8_t length)
{
    RpiPacket packet;
    packet.id = id;
    packet.dlc = length;
    memcpy(packet.data, data, length);
    uint8_t frame[RPISERP_MAX_FRAME];
    const size_t frameLength = rpiserp_encode(packet, frame);
    if (frameLength == 0) return false;

    const int rc = mLink.write(frame, frameLength);
    if (rc == 1)
    {
        mTxPackets++;
        return true;
    }
    mTxErrors++;
    if (rc < 0) linkLost(mLink.lastError());
    return false;
}

// Identical to UHA5 UHA_SendRTC(): 4 bytes big-endian local time = unix + 1 h (+1 h in DST).
void Gateway::sendRtc()
{
    const time_t unixtime = time(nullptr);
    struct tm now;
    localtime_r(&unixtime, &now);

    unsigned int localunixtime = (unsigned int)(unixtime + 3600);   // +1 hour time zone offset
    if (now.tm_isdst > 0) localunixtime += 3600;

    uint8_t txData[4];
    txData[0] = (localunixtime >> 24) & 0xFF;
    txData[1] = (localunixtime >> 16) & 0xFF;
    txData[2] = (localunixtime >> 8) & 0xFF;
    txData[3] = localunixtime & 0xFF;
    if (sendPacket(CMD_RPI_RTC_SYNC, txData, 4))
    {
        mRtcSent++;
        LOG_I("RTC sync sent: %02d.%02d.%d %02d:%02d:%02d (%s time)", now.tm_mday, now.tm_mon + 1,
              now.tm_year + 1900, now.tm_hour, now.tm_min, now.tm_sec, now.tm_isdst > 0 ? "summer" : "winter");
    }
    else
    {
        LOG_W("RTC sync not sent: %s", mLink.lastError().c_str());
    }
}

// ---------------------------------------------------------------------------------------------
// outputs

void Gateway::appendEventLog(const uint8_t data[8])
{
    const time_t now = time(nullptr);
    struct tm lt;
    localtime_r(&now, &lt);
    const std::string line = event_format_line(data, lt);
    LOG_I("node event: %.*s", (int)line.size() - 21, line.c_str() + 20);   // without timestamp and '\n'

    int fd = open(mCfg.logFile.c_str(), O_WRONLY | O_APPEND | O_CREAT | O_CLOEXEC, 0644);
    if (fd < 0 || write(fd, line.data(), line.size()) != (ssize_t)line.size())
    {
        mEventLogErrors++;
        if (mEventLogErrors == mReportedEventLogErrors + 1)
            LOG_E("cannot append to %s: %s", mCfg.logFile.c_str(), strerror(errno));
    }
    if (fd >= 0) close(fd);
}

void Gateway::writeOutputs()
{
    const int Time = (int)time(nullptr);
    writeFile("uha.json", build_uha_json(mVars, Time));
    writeFile("bms.json", build_bms_json(mVars, Time));
    writeFile("uha_status.json", buildStatusJson(Time, mono_now()));
}

// Atomic replace: write <target>.tmp in the same folder, then rename() over the target.
// If the output path is a symlink (tmpfs setup), the file it points to is replaced, not the link.
bool Gateway::writeFile(const char* name, const std::string& content)
{
    std::string path = mCfg.outDir + "/" + name;
    struct stat st;
    if (lstat(path.c_str(), &st) == 0 && S_ISLNK(st.st_mode))
    {
        char target[PATH_MAX];
        ssize_t n = readlink(path.c_str(), target, sizeof(target) - 1);
        if (n > 0)
        {
            target[n] = '\0';
            path = (target[0] == '/') ? std::string(target) : mCfg.outDir + "/" + target;
        }
    }
    const std::string tmp = path + ".tmp";

    const char* failed = nullptr;
    int fd = -1;
    if (content.empty()) failed = "JSON build failed";
    else if ((fd = open(tmp.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644)) < 0) failed = "open";
    else
    {
        fchmod(fd, 0644);
        if (write(fd, content.data(), content.size()) != (ssize_t)content.size()) failed = "write";
        if (close(fd) != 0 && failed == nullptr) failed = "close";
        if (failed == nullptr && rename(tmp.c_str(), path.c_str()) != 0) failed = "rename";
        if (failed != nullptr) unlink(tmp.c_str());
    }
    if (failed == nullptr) return true;

    mWriteErrors++;
    if (mWriteErrors == mReportedWriteErrors + 1)
        LOG_E("cannot write %s: %s: %s", path.c_str(), failed, strerror(errno));
    return false;
}

std::string Gateway::buildStatusJson(time_t nowUnix, double nowMono)
{
    const RpiParserStats& ps = mParser.stats();
    cJSON* root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "Version", UHAGATE6_VERSION);
    cJSON_AddNumberToObject(root, "UnixTime", (double)nowUnix);
    cJSON_AddNumberToObject(root, "StartUnix", (double)mStartUnix);
    cJSON_AddNumberToObject(root, "UptimeS", (double)(long)(nowMono - mStartMono));

    cJSON* link = cJSON_AddObjectToObject(root, "Link");
    cJSON_AddStringToObject(link, "Port", mLink.path().c_str());
    cJSON_AddStringToObject(link, "State", !mLink.isOpen() ? "down" : mReceiving ? "up" : "silent");
    cJSON_AddNumberToObject(link, "SinceUnix", (double)mLinkChangeUnix);
    cJSON_AddNumberToObject(link, "Reconnects", (double)mReconnects);
    if (mLastPacketMono >= 0) cJSON_AddNumberToObject(link, "LastPacketAgeS", (double)(long)(nowMono - mLastPacketMono));
    else cJSON_AddNullToObject(link, "LastPacketAgeS");
    if (!mLink.isOpen() && !mLastOpenError.empty()) cJSON_AddStringToObject(link, "LastError", mLastOpenError.c_str());

    cJSON* counters = cJSON_AddObjectToObject(root, "Counters");
    cJSON_AddNumberToObject(counters, "RxBytes", (double)ps.rxBytes);
    cJSON_AddNumberToObject(counters, "RxPackets", (double)ps.packets);
    cJSON_AddNumberToObject(counters, "VarPackets", (double)mVarPackets);
    cJSON_AddNumberToObject(counters, "LogPackets", (double)mLogPackets);
    cJSON_AddNumberToObject(counters, "UnknownIds", (double)mUnknownIds);
    cJSON_AddNumberToObject(counters, "Malformed", (double)mMalformed);
    cJSON_AddNumberToObject(counters, "OutOfRangeVarIds", (double)mOutOfRangeVars);
    cJSON_AddNumberToObject(counters, "ChecksumErrors", (double)ps.checksumErrors);
    cJSON_AddNumberToObject(counters, "LengthErrors", (double)ps.lengthErrors);
    cJSON_AddNumberToObject(counters, "DiscardedBytes", (double)ps.discardedBytes);
    cJSON_AddNumberToObject(counters, "TxPackets", (double)mTxPackets);
    cJSON_AddNumberToObject(counters, "TxErrors", (double)mTxErrors);
    cJSON_AddNumberToObject(counters, "RtcSyncSent", (double)mRtcSent);
    cJSON_AddNumberToObject(counters, "WriteErrors", (double)mWriteErrors);
    cJSON_AddNumberToObject(counters, "EventLogErrors", (double)mEventLogErrors);
    cJSON_AddNumberToObject(counters, "RssKb", (double)rss_kb());

    // every known VAR_* plus any other id that was received
    bool named[NUM_OF_VARS] = {false};
    cJSON* vars = cJSON_AddObjectToObject(root, "Vars");
    auto addVar = [&](const char* name, int id) {
        cJSON* v = cJSON_AddObjectToObject(vars, name);
        cJSON_AddNumberToObject(v, "Id", id);
        cJSON_AddNumberToObject(v, "Value", mVars[id]);
        if (mVarCount[id] > 0)
        {
            cJSON_AddNumberToObject(v, "AgeS", (double)(long)(nowMono - mVarRxMono[id]));
            cJSON_AddNumberToObject(v, "LastRxUnix", (double)mVarRxUnix[id]);
        }
        else
        {
            cJSON_AddNullToObject(v, "AgeS");
            cJSON_AddNullToObject(v, "LastRxUnix");
        }
        cJSON_AddNumberToObject(v, "Count", mVarCount[id]);
    };
    for (const VarName& vn : kVarNames)
    {
        named[vn.id] = true;
        addVar(vn.name, vn.id);
    }
    for (int id = 0; id < NUM_OF_VARS; id++)
    {
        if (named[id] || mVarCount[id] == 0) continue;
        char name[16];
        snprintf(name, sizeof(name), "ID_%d", id);
        addVar(name, id);
    }

    // nodes are only identified in log messages (0x620 byte 0); 0x221 carries no node id
    cJSON* nodes = cJSON_AddObjectToObject(root, "Nodes");
    for (int id = 0; id < 256; id++)
    {
        const NodeInfo& n = mNodes[id];
        const char* name = event_node_name((uint8_t)id);
        const bool known = strcmp(name, "UNKNOWN") != 0;
        if (!known && n.messages == 0) continue;
        char unknownName[16];
        if (!known)
        {
            snprintf(unknownName, sizeof(unknownName), "NODE_%d", id);
            name = unknownName;
        }
        cJSON* node = cJSON_AddObjectToObject(nodes, name);
        cJSON_AddNumberToObject(node, "Id", id);
        if (n.messages > 0)
        {
            cJSON_AddNumberToObject(node, "LastSeenUnix", (double)n.lastSeenUnix);
            cJSON_AddNumberToObject(node, "AgeS", (double)(long)(nowMono - n.lastSeenMono));
            cJSON_AddStringToObject(node, "LastEvent", n.lastEvent.c_str());
        }
        else
        {
            cJSON_AddNullToObject(node, "LastSeenUnix");
            cJSON_AddNullToObject(node, "AgeS");
        }
        cJSON_AddNumberToObject(node, "LogMessages", (double)n.messages);
    }

    std::string text;
    char* printed = cJSON_Print(root);
    if (printed != nullptr)
    {
        text = printed;
        cJSON_free(printed);
    }
    cJSON_Delete(root);
    return text;
}

void Gateway::periodicReports(double now)
{
    if (now >= mNextErrorSummaryMono)
    {
        mNextErrorSummaryMono = now + mCfg.errorSummaryS;
        const RpiParserStats& ps = mParser.stats();
        const uint64_t chk = ps.checksumErrors - mReportedChecksumErrors;
        const uint64_t len = ps.lengthErrors - mReportedLengthErrors;
        if (chk > 0 || len > 0)
            LOG_W("serial errors in last %d s: %llu checksum, %llu length", mCfg.errorSummaryS,
                  (unsigned long long)chk, (unsigned long long)len);
        if (mWriteErrors > mReportedWriteErrors)
            LOG_E("output write errors in last %d s: %llu", mCfg.errorSummaryS,
                  (unsigned long long)(mWriteErrors - mReportedWriteErrors));
        if (mEventLogErrors > mReportedEventLogErrors)
            LOG_E("log.txt write errors in last %d s: %llu", mCfg.errorSummaryS,
                  (unsigned long long)(mEventLogErrors - mReportedEventLogErrors));
        if (mTxErrors > mReportedTxErrors)
            LOG_W("serial transmit errors in last %d s: %llu", mCfg.errorSummaryS,
                  (unsigned long long)(mTxErrors - mReportedTxErrors));
        mReportedChecksumErrors = ps.checksumErrors;
        mReportedLengthErrors = ps.lengthErrors;
        mReportedWriteErrors = mWriteErrors;
        mReportedEventLogErrors = mEventLogErrors;
        mReportedTxErrors = mTxErrors;
    }

    if (now >= mNextHourlyMono)
    {
        mNextHourlyMono = now + 3600;
        int seen = 0;
        for (int id = 0; id < NUM_OF_VARS; id++)
            if (mVarCount[id] > 0) seen++;
        const RpiParserStats& ps = mParser.stats();
        LOG_I("hourly: link %s, packets %llu, vars seen %d, checksum errors %llu, reconnects %llu, "
              "RTC syncs %llu, RSS %ld kB",
              mLink.isOpen() ? "up" : "down", (unsigned long long)ps.packets, seen,
              (unsigned long long)ps.checksumErrors, (unsigned long long)mReconnects,
              (unsigned long long)mRtcSent, rss_kb());
    }
}
