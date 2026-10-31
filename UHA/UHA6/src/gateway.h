// UhaGate6 main object: single-threaded poll() loop over the serial port, a timerfd tick
// and a signalfd (SIGTERM/SIGINT). Idle CPU ~0 %, no shared buffers between threads.
#ifndef UHA6_GATEWAY_H
#define UHA6_GATEWAY_H

#include <cstdint>
#include <ctime>
#include <string>

#include "config.h"
#include "rpiserp.h"
#include "serial_link.h"
#include "uha_vars.h"

class Gateway
{
public:
    explicit Gateway(const Config& cfg);
    int run();   // returns process exit code

private:
    struct NodeInfo
    {
        time_t lastSeenUnix = 0;
        double lastSeenMono = -1;
        uint64_t messages = 0;
        std::string lastEvent;
    };

    void onTick();
    void onSerialReadable(short revents);
    void onPacket(const RpiPacket& packet);
    void openLink();
    void linkLost(const std::string& reason);
    bool sendPacket(uint16_t id, const uint8_t* data, uint8_t length);
    void sendRtc();
    void appendEventLog(const uint8_t data[8]);
    void writeOutputs();
    bool writeFile(const char* name, const std::string& content);
    std::string buildStatusJson(time_t nowUnix, double nowMono);
    void periodicReports(double nowMono);

    Config mCfg;
    SerialLink mLink;
    RpiserpParser mParser;

    short mVars[NUM_OF_VARS] = {0};
    time_t mVarRxUnix[NUM_OF_VARS] = {0};
    double mVarRxMono[NUM_OF_VARS];
    uint32_t mVarCount[NUM_OF_VARS] = {0};
    NodeInfo mNodes[256];

    // counters (since start)
    uint64_t mVarPackets = 0, mLogPackets = 0, mUnknownIds = 0, mMalformed = 0, mOutOfRangeVars = 0;
    uint64_t mTxPackets = 0, mTxErrors = 0, mRtcSent = 0, mReconnects = 0;
    uint64_t mWriteErrors = 0, mEventLogErrors = 0;

    // link state
    double mStartMono = 0;
    time_t mStartUnix = 0;
    double mLinkChangeMono = 0;
    time_t mLinkChangeUnix = 0;
    double mNextReopenMono = 0;
    double mLastPacketMono = -1;
    bool mReceiving = false;          // got a packet since link up / since the last silence warning
    bool mSilenceWarned = false;
    bool mHadLink = false;
    std::string mLastOpenError;
    double mLastOpenErrorLogMono = -1e9;
    unsigned mOpenAttempts = 0;
    long mLastRtcSlot = -1;

    // report bookkeeping
    double mNextErrorSummaryMono = 0;
    double mNextHourlyMono = 0;
    uint64_t mReportedChecksumErrors = 0, mReportedLengthErrors = 0;
    uint64_t mReportedWriteErrors = 0, mReportedEventLogErrors = 0, mReportedTxErrors = 0;
};

#endif
