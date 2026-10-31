// Logging to journald via stdout with syslog level prefixes (<3>, <4>, <6>, <7>).
// journald parses the prefix (SyslogLevelPrefix=yes is the default), no libsystemd needed.
// When stdout is a terminal, a timestamp and a level letter are printed instead.
#ifndef UHA6_LOG_H
#define UHA6_LOG_H

enum class LogLevel { Error = 3, Warning = 4, Info = 6, Debug = 7 };

void log_init(bool verbose);
void log_msg(LogLevel level, const char* fmt, ...) __attribute__((format(printf, 2, 3)));

#define LOG_E(...) log_msg(LogLevel::Error, __VA_ARGS__)
#define LOG_W(...) log_msg(LogLevel::Warning, __VA_ARGS__)
#define LOG_I(...) log_msg(LogLevel::Info, __VA_ARGS__)
#define LOG_D(...) log_msg(LogLevel::Debug, __VA_ARGS__)

#endif
