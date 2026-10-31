// Node log messages (CMD_LOG_MSG 0x620) -> log.txt, same line format as UHA5 LOG.cpp:
// "dd.mm.yyyy hh:mm:ss NODE EVENT d2 d3 d4 d5 d6 d7"
#ifndef UHA6_EVENT_LOG_H
#define UHA6_EVENT_LOG_H

#include <cstdint>
#include <ctime>
#include <string>

const char* event_node_name(uint8_t nodeId);    // "UNKNOWN" if not known
const char* event_type_name(uint8_t eventId);   // "UNKNOWN_EVENT" if not known

// Formatted line including the trailing '\n'.
std::string event_format_line(const uint8_t data[8], const struct tm& localTime);

#endif
