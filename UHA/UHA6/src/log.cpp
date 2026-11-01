#include "log.h"

#include <cstdarg>
#include <cstdio>
#include <ctime>
#include <unistd.h>

static bool sVerbose = false;
static bool sTerminal = false;

void log_init(bool verbose)
{
    sVerbose = verbose;
    sTerminal = isatty(STDOUT_FILENO);
    setvbuf(stdout, nullptr, _IOLBF, 0);
}

void log_msg(LogLevel level, const char* fmt, ...)
{
    if (level == LogLevel::Debug && !sVerbose) return;

    char text[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(text, sizeof(text), fmt, ap);
    va_end(ap);

    if (sTerminal)
    {
        static const char letters[] = "???EW?ID";
        time_t now = time(nullptr);
        struct tm lt;
        localtime_r(&now, &lt);
        char stamp[16];
        strftime(stamp, sizeof(stamp), "%H:%M:%S", &lt);
        printf("%s %c %s\n", stamp, letters[(int)level], text);
    }
    else
    {
        printf("<%d>%s\n", (int)level, text);
    }
}
