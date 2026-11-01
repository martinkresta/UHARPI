#include "event_log.h"

#include <cstdio>

const char* event_node_name(uint8_t nodeId)
{
    switch (nodeId)
    {
        case 1: return "IOBOARD_D";
        case 2: return "IOBOARD_U";
        case 3: return "TECHM";
        case 4: return "ELECON";
        case 5: return "RECU";
        case 6: return "EVSE";
        case 7: return "ELECON_D";   // Elecon Dilna
        default: return "UNKNOWN";
    }
}

const char* event_type_name(uint8_t eventId)
{
    switch (eventId)
    {
        case 0: return "STARTUP";
        case 1: return "ERROR";
        case 2: return "LOG";
        case 3: return "STATUS";
        default: return "UNKNOWN_EVENT";
    }
}

std::string event_format_line(const uint8_t data[8], const struct tm& lt)
{
    char line[160];
    snprintf(line, sizeof(line), "%02d.%02d.%d %02d:%02d:%02d %s %s %d %d %d %d %d %d\n",
             lt.tm_mday, lt.tm_mon + 1, lt.tm_year + 1900, lt.tm_hour, lt.tm_min, lt.tm_sec,
             event_node_name(data[0]), event_type_name(data[1]),
             data[2], data[3], data[4], data[5], data[6], data[7]);
    return line;
}
