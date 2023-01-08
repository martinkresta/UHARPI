/* Moduel RPISERP.h  - implementing a simple serial protocol between RPI and UHA devices (STM32 CPUs)*/



#ifndef RPISERP_H
#define RPISERP_H


#include <stdbool.h>

#define  MSG_START_B1							0x7F
#define  MSG_START_B2							0xAA

#define RPISERP_BUFLEN	20

#define RPISERP_RX_RAW_BUFLEN   1000

#define RPISERP_RX_PACKETS_CAPACITY 200
#define RPISERP_MAX_DATA_LENGTH     8 
#define RPISERP_ID_LENGTH           2

//#define REC_DBG_PRINT   

typedef struct 
{
    unsigned short id;
    unsigned char data[RPISERP_MAX_DATA_LENGTH];
}sPacket;

typedef struct 
{
    bool enable;       // enable/disable the receiver
    int port;          // file descriptor of the serial port
    int recPackets;    // number of receivede packets (oveflows if MAX_INT_32)
    int writeIndex;    // index where next received packet will be written 
    int readIndex;     // index of next pacekt to be processed by the application
    int buffSize;      // capacity of pacekets buffer
    sPacket* packets;  // buffer with received packets
}sReceiverIface;

#endif