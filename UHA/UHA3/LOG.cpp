
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "UHA.h"
#include "cJSON.h"
#include "LOG.h"
#include <iostream>
#include <fstream>
#include <iomanip>
#include <ctime>
#include <map>


using namespace std;


// Define node ID mappings
#define NODEID_IOBOARD_D      1
#define NODEID_IOBOARD_U      2
#define NODEID_TECHM          3
#define NODEID_ELECON         4
#define NODEID_RECU           5
#define NODEID_EVSE           6
#define NODEID_ELECON_D       7 // Elecon Dilna

// Define event types
typedef enum {
    eleStartup,
    eleError,
    eleLog,
    eleStatus
} eLogEvent;


/// @brief Constructor
void LOG::LOG(void)
{

}



#define LOGFILE_FULLPATH "/home/pi/Web/log.txt"

void LOG_InsertMsg(unsigned char data[]) {
    std::ofstream file(LOGFILE_FULLPATH, std::ios::app);

    if (!file) {
        std::cerr << "Error: Unable to open or create the log file!" << std::endl;
        return;
    }

    // Get the current timestamp
    std::time_t now = std::time(nullptr);
    std::tm* localTime = std::localtime(&now);

    // Write timestamp in format dd.mm.yyyy hh:mm:ss
    file << std::setfill('0') 
         << std::setw(2) << localTime->tm_mday << "."
         << std::setw(2) << (localTime->tm_mon + 1) << "."
         << (localTime->tm_year + 1900) << " "
         << std::setw(2) << localTime->tm_hour << ":"
         << std::setw(2) << localTime->tm_min << ":"
         << std::setw(2) << localTime->tm_sec << " ";

    // Write source as text
    file << getSourceName(data[0]) << " ";

    // Write event as text
    file << getEventName(data[1]) << " ";

    // Write the remaining 6 data fields
    for (int i = 2; i < 8; ++i) {
        file << static_cast<int>(data[i]);
        if (i < 7) file << " "; // Separate columns with a space
    }

    file << std::endl; // Newline for the next log entry
    file.close();
    std::cout << "Log entry added successfully." << std::endl;
}


// Function to get the source name from the node ID
std::string LOG::getSourceName(unsigned char nodeId) {
    static const std::map<unsigned char, std::string> nodeMap = {
        {NODEID_IOBOARD_D, "IOBOARD_D"},
        {NODEID_IOBOARD_U, "IOBOARD_U"},
        {NODEID_TECHM, "TECHM"},
        {NODEID_ELECON, "ELECON"},
        {NODEID_RECU, "RECU"},
        {NODEID_EVSE, "EVSE"},
        {NODEID_ELECON_D, "ELECON_D"}
    };

    auto it = nodeMap.find(nodeId);
    return (it != nodeMap.end()) ? it->second : "UNKNOWN";
}

// Function to get the event name from the event ID
std::string LOG::getEventName(unsigned char eventId) {
    static const std::map<unsigned char, std::string> eventMap = {
        {eleStartup, "STARTUP"},
        {eleError, "ERROR"},
        {eleLog, "LOG"},
        {eleStatus, "STATUS"}
    };

    auto it = eventMap.find(eventId);
    return (it != eventMap.end()) ? it->second : "UNKNOWN_EVENT";
}

