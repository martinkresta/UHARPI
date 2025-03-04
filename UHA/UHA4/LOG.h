#ifndef LOG_H
#define LOG_H

#include <string.h>


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
    static std::string getSourceName(unsigned char nodeId);
    static std::string getEventName(unsigned char eventId);
	
// public methods
public:

   void LOG_InsertMsg(unsigned char data[]);


};

#endif