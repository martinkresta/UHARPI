#include "config.h"

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <getopt.h>

static void usage(const char* prog)
{
    printf("Usage: %s [options]\n"
           "  -c, --config FILE        key=value config file (keys = long option names)\n"
           "  -p, --port PATH          serial port (default /dev/ttyUSB0)\n"
           "  -o, --out-dir DIR        folder for uha.json, bms.json, uha_status.json (default /home/pi/Web)\n"
           "  -l, --log-file PATH      node event log (default /home/pi/Web/log.txt)\n"
           "      --json-period-ms N   JSON write period (default 1000)\n"
           "      --rtc-period-s N     RTC sync period (default 60)\n"
           "      --reopen-s N         serial reopen retry period (default 5)\n"
           "      --silence-warn-s N   warn after N s without packets (default 60)\n"
           "      --error-summary-s N  checksum error summary period (default 600)\n"
           "  -v, --verbose            debug log\n"
           "  -h, --help\n", prog);
}

static bool to_int(const std::string& s, int minValue, int& out)
{
    char* end = nullptr;
    long v = strtol(s.c_str(), &end, 10);
    if (s.empty() || *end != '\0' || v < minValue || v > 86400000) return false;
    out = (int)v;
    return true;
}

static bool set_value(Config& cfg, const std::string& key, const std::string& value)
{
    if (key == "port") cfg.port = value;
    else if (key == "out-dir") cfg.outDir = value;
    else if (key == "log-file") cfg.logFile = value;
    else if (key == "json-period-ms") return to_int(value, 100, cfg.jsonPeriodMs);
    else if (key == "rtc-period-s") return to_int(value, 1, cfg.rtcPeriodS);
    else if (key == "reopen-s") return to_int(value, 1, cfg.reopenS);
    else if (key == "silence-warn-s") return to_int(value, 1, cfg.silenceWarnS);
    else if (key == "error-summary-s") return to_int(value, 1, cfg.errorSummaryS);
    else if (key == "verbose") cfg.verbose = (value == "1" || value == "true" || value == "yes");
    else return false;
    return true;
}

static std::string trim(const std::string& s)
{
    size_t b = s.find_first_not_of(" \t\r\n");
    if (b == std::string::npos) return "";
    size_t e = s.find_last_not_of(" \t\r\n");
    return s.substr(b, e - b + 1);
}

static bool load_file(Config& cfg, const std::string& path)
{
    std::ifstream in(path);
    if (!in)
    {
        fprintf(stderr, "Cannot read config file %s\n", path.c_str());
        return false;
    }
    std::string line;
    int lineNo = 0;
    while (std::getline(in, line))
    {
        lineNo++;
        line = trim(line);
        if (line.empty() || line[0] == '#') continue;
        size_t eq = line.find('=');
        if (eq == std::string::npos || !set_value(cfg, trim(line.substr(0, eq)), trim(line.substr(eq + 1))))
        {
            fprintf(stderr, "%s:%d: invalid line: %s\n", path.c_str(), lineNo, line.c_str());
            return false;
        }
    }
    return true;
}

int config_parse(int argc, char** argv, Config& cfg)
{
    static const struct option options[] = {
        {"config", required_argument, nullptr, 'c'},
        {"port", required_argument, nullptr, 'p'},
        {"out-dir", required_argument, nullptr, 'o'},
        {"log-file", required_argument, nullptr, 'l'},
        {"json-period-ms", required_argument, nullptr, 1},
        {"rtc-period-s", required_argument, nullptr, 2},
        {"reopen-s", required_argument, nullptr, 3},
        {"silence-warn-s", required_argument, nullptr, 4},
        {"error-summary-s", required_argument, nullptr, 5},
        {"verbose", no_argument, nullptr, 'v'},
        {"help", no_argument, nullptr, 'h'},
        {nullptr, 0, nullptr, 0}};

    // pass 1: only the config file, so command line options override it
    for (int i = 1; i < argc; i++)
    {
        std::string a = argv[i];
        if ((a == "-c" || a == "--config") && i + 1 < argc) cfg.configFile = argv[i + 1];
        else if (a.rfind("--config=", 0) == 0) cfg.configFile = a.substr(9);
    }
    if (!cfg.configFile.empty() && !load_file(cfg, cfg.configFile)) return 2;

    int opt, index;
    while ((opt = getopt_long(argc, argv, "c:p:o:l:vh", options, &index)) != -1)
    {
        switch (opt)
        {
            case 'c': break;
            case 'h': usage(argv[0]); return 0;
            case 'v': cfg.verbose = true; break;
            case '?': usage(argv[0]); return 2;
            default:
            {
                const char* key = (opt == 'p') ? "port" : (opt == 'o') ? "out-dir"
                                : (opt == 'l') ? "log-file" : options[index].name;
                if (!set_value(cfg, key, optarg))
                {
                    fprintf(stderr, "Invalid value for --%s: %s\n", key, optarg);
                    return 2;
                }
            }
        }
    }
    if (optind < argc)
    {
        fprintf(stderr, "Unexpected argument: %s\n", argv[optind]);
        return 2;
    }
    return -1;
}

std::string config_describe(const Config& cfg)
{
    char text[600];
    snprintf(text, sizeof(text),
             "config=%s port=%s out-dir=%s log-file=%s json-period-ms=%d rtc-period-s=%d "
             "reopen-s=%d silence-warn-s=%d error-summary-s=%d verbose=%d",
             cfg.configFile.empty() ? "(none)" : cfg.configFile.c_str(), cfg.port.c_str(),
             cfg.outDir.c_str(), cfg.logFile.c_str(), cfg.jsonPeriodMs, cfg.rtcPeriodS,
             cfg.reopenS, cfg.silenceWarnS, cfg.errorSummaryS, cfg.verbose ? 1 : 0);
    return text;
}
