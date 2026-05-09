#ifndef LOG_H
#define LOG_H

#include <string>

using namespace std;


#define LOGFILE_FULLPATH	"/home/pi/Web/log.txt"

class LOG
{
	// private variables
private:  

    // TBD
    
// public getters
public:  
    

//private methods
private:
    
std::string getSourceName(unsigned char nodeId);
std::string getEventName(unsigned char eventId);
// public methods
public:

   void LOG_InsertMsg(unsigned char data[]);



};

#endif