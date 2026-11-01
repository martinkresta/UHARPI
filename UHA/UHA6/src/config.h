// Configuration: defaults = UhaGate5 behaviour, then optional key=value file, then command line.
#ifndef UHA6_CONFIG_H
#define UHA6_CONFIG_H

#include <string>

struct Config
{
    std::string configFile;
    std::string port = "/dev/ttyUSB0";
    std::string outDir = "/home/pi/Web";             // uha.json, bms.json, uha_status.json
    std::string logFile = "/home/pi/Web/log.txt";    // node log messages
    int jsonPeriodMs = 1000;
    int rtcPeriodS = 60;          // RTC sync on every change of (unix time / rtcPeriodS)
    int reopenS = 5;              // retry period while the serial port is missing
    int silenceWarnS = 60;        // warn when the link is open but no packet arrived for this long
    int errorSummaryS = 600;      // period of the checksum/length error summary
    bool verbose = false;         // debug log (every received packet)
};

// Returns -1 to continue, otherwise the process exit code (help printed or error).
int config_parse(int argc, char** argv, Config& cfg);
std::string config_describe(const Config& cfg);

#endif
