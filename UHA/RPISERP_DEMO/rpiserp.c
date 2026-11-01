


#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <termios.h>
#include <unistd.h>
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include "rpiserp.h"




// global variables
static struct termios t_vcp;            // handle for serial port configuration
static pthread_t RecThread_handle;    // receiver thread handle
static sReceiverIface mRecIface;  // interface with receiver thread
static int fd_vcp;                     // handle for serial port read/write access
static sPacket RxPackets[RPISERP_RX_PACKETS_CAPACITY];  // buffer with received packets (validated)


static unsigned char Ibuff[1000];   // intermediate buffer

// default initialization of receiver thread interface structure
void InitReceiverInterface(void)
{
    mRecIface.buffSize = RPISERP_RX_PACKETS_CAPACITY;
    mRecIface.port = fd_vcp;
    mRecIface.packets = RxPackets;
    mRecIface.readIndex = 0;
    mRecIface.writeIndex = 0;
    mRecIface.recPackets = 0;
    mRecIface.enable = true;  
}

// calculate the 8bit checksum over a byte array with length 0-255 bytes
unsigned char Checksum(char* data, char length)
{
  unsigned char i,chsum;
  chsum = 0;
  for(i = 0;i < length; i++)
  {
    chsum += data[i];
  }
  return (chsum & 0xFF);
}


// the receiver thread
// reads continuously the serial port and parses the byte stream to locate a valid packets
void* Thread_Receiver(void *iface)
{

    unsigned char stream[RPISERP_RX_RAW_BUFLEN]; // stream of received bytes
    int writeIdx = 0;
    int processIdx =0;
    int rxlen, idx;
    bool validPacket = false;
    bool cont = true;
    unsigned char packetLength;
    int remainingBytes;
    unsigned char chsum;
    sPacket* pckt;

    sReceiverIface* interface = (sReceiverIface*) iface;
    while(interface->enable)
    {
        #ifdef RPISERP_DBG_PRINT
         printf(" \n Receiver: receiver thread enabled , %d\n", interface->enable);
        #endif
        // read data from port
        rxlen = read(fd_vcp, &(stream[writeIdx]),RPISERP_RX_RAW_BUFLEN-writeIdx);
        if(rxlen > 0)
        {
            // adjust write index for next read
            writeIdx += rxlen;
        
            processIdx = 0;  // allways start processing from the first byte in the stream buffer
            // parse the stream
            cont = true;
            idx = processIdx;
            #ifdef RPISERP_DBG_PRINT
            printf(" \n Receiver: entering while loop with %d bytes (%d new) \n", writeIdx, rxlen);
            #endif
            while ( cont == true && interface->enable)
            {
                remainingBytes = writeIdx - idx;
                
               // printf(" \n Receiver: idx: %d | remaining: %d : writeIdx : %d  \n", idx, remainingBytes, writeIdx);
               validPacket = false;

                if(stream[idx] == MSG_START_B1 && stream[idx+1] == MSG_START_B2)
                {  // detected start sequence of the packet
                   packetLength = stream[idx+2];
                   #ifdef RPISERP_DBG_PRINT
                   printf(" \n Receiver: found packet start at index %d with length of %d bytes \n", idx, packetLength);
                   #endif

                   if(packetLength > RPISERP_ID_LENGTH + RPISERP_MAX_DATA_LENGTH)
                   {
                        // ERROR packet length, The detectend packet start should be discarded
                   }

                   // check if enough data was received
                   if(remainingBytes >= (packetLength + 4))  // header + len + chsum = 4
                   {
                     // validate the checksum
                     chsum = Checksum(&(stream[idx]), packetLength + 3);
                     if( stream[idx + packetLength + 3] == chsum)
                     {
                        // checksum is valid, insert the packet to the application buffer
                        
                        if(packetLength <= RPISERP_ID_LENGTH + RPISERP_MAX_DATA_LENGTH)
                        {

                            // length is valid
                            validPacket = true;
                            interface->recPackets++;
                            pckt = &(interface->packets[interface->writeIndex]); // pointer to new packet
                            pckt->id = (unsigned short)(stream[idx+3]) * 256 + stream[idx+4];
                            pckt->dlc = (unsigned char) (packetLength - 2);
                            memset(pckt->data,0,RPISERP_MAX_DATA_LENGTH);   // reset data to zero
                            memcpy(pckt->data,&(stream[idx+5]),packetLength - 2); // copy data without id
                            // increment the writeindex
                            interface->writeIndex++;
                            if(interface->writeIndex >= interface->buffSize) interface->writeIndex = 0;
                            // increment the idx
                            idx += packetLength + 4;
                            if(idx >= RPISERP_RX_RAW_BUFLEN) idx -= RPISERP_RX_RAW_BUFLEN;
                            #ifdef RPISERP_DBG_PRINT
                            printf(" \n Receiver: complete packet %d stored  \n", interface->recPackets);
                            #endif

                        }
                        else  
                        {
                            // too long messages are discarded - considered as invalid
                            validPacket = false;
                            #ifdef RPISERP_DBG_PRINT
                            printf(" \n Receiver: ERROR: too long packet  \n");
                            #endif
                            idx ++;
                        }
                     }
                     else  // invalid checksum
                     {
                        validPacket = false;
                        #ifdef RPISERP_DBG_PRINT
                        printf(" \n Receiver: ERROR: invalid checksum  \n");
                            printf("\n Receiver: Corrupted frame: ");
                            for(int i = 0; i < packetLength + 4; i++)
                            {
                             printf("%02X ", stream[idx+i]);
                            }
                            printf("\n Receiver: Received checksum : %02X", stream[idx + packetLength + 3]);
                            printf("\n Receiver: Calculated checksum : %02X", chsum);
                        #endif
                        idx ++;
                     }

                   }
                   else   // not enough data to parse entire packet
                   { 
                     // copy the remaining unprocessed data to the begining of the stream buffer and adjust the write index,
                     // so the next recived data willl be placed just after this unprocessed data.
                     // we have to use temporary intermediate buffer, because the source and destination data may overlap
                     memcpy(Ibuff, &(stream[idx]), remainingBytes);
                     memcpy(stream, Ibuff, remainingBytes);   // copy to the beggining of stream which will be processed next time
                     writeIdx = remainingBytes;  // adjust the writeIdx
                     #ifdef RPISERP_DBG_PRINT
                     printf("\n Receiver: leaving the while loop with %d remaining bytes, idx = %d" , remainingBytes, idx);
                     #endif
                     cont = false;  // skip the parsing for now and wait for more data
                     continue;
                   }
                 
                }
                else
                {
                    idx ++;
                    
                }

                if(idx >= writeIdx-1)
                {
                    cont = false;
                    #ifdef RPISERP_DBG_PRINT
                    printf("\n Receiver: leaving the while loop with all bytes processed");
                    #endif
                    writeIdx = 0;
                    continue;
                } 
            }

            #ifdef RPISERP_DBG_PRINT
                //printf(" \n Receiver: leaving the parsing loop\n");
            #endif
        }

        #ifdef RPISERP_DBG_PRINT
        // printf(" \n Receiver: left the parsing loop\n");
        #endif
    }

    printf(" \n Receiver: receiver thread finishing...\n");
    return NULL;
}



void RPISERP_Init(unsigned char* port)
{
    #ifdef RPISERP_DBG_PRINT   
    printf(" \n*** RPISERP 2.0 *** \n" ); 
    printf(" \nInitialization of RPISERP module ... ");
    #endif
    
    fd_vcp = open(port, O_RDWR | O_NOCTTY);
    if (fd_vcp == -1)
    {
        #ifdef RPISERP_DBG_PRINT 
        printf("\nCannot open serial device %s\n", port);
        perror("\nCannot open serial devic");
        #endif
    }


    tcgetattr(fd_vcp, &t_vcp);	
    cfsetspeed(&t_vcp, B115200);
    cfmakeraw(&t_vcp);
    t_vcp.c_cc[VMIN] = 14;
    t_vcp.c_cc[VTIME] = 1;

    if(tcsetattr(fd_vcp,TCSANOW, &t_vcp))
    {
        #ifdef RPISERP_DBG_PRINT 
        printf(" \nError setting atributes \n" );   
        perror(" \nError setting atributes \n" ); 
        #endif     
    }
}

void RPISERP_Start(void)
{
    InitReceiverInterface();

    // setting the higher priority for the Receiver thread
    int rc;
    pthread_attr_t attr;
    struct sched_param param;

    rc = pthread_attr_init (&attr);
    rc = pthread_attr_getschedparam (&attr, &param);
       (param.sched_priority)+=10;
    rc = pthread_attr_setschedparam (&attr, &param);
    // check RC ? 

    pthread_create(&RecThread_handle, &attr, Thread_Receiver, (void*)&mRecIface);
   // pthread_create(&RecThread_handle, NULL, Thread_Receiver, (void*)&mRecIface);
    #ifdef RPISERP_DBG_PRINT
    printf(" \nThe receiver thread was started \n" );
    #endif
}

void RPISERP_Stop(void)
{
    //  kill the rec thread
    #ifdef RPISERP_DBG_PRINT
    printf(" \n Stopping the receiver thread... \n" );
    #endif
    mRecIface.enable = false;
    
    // TODO: pthread_join never returns !  the recevier thread does not terminate.  ?? inverstigate why
    // pthread_join(RecThread_handle, NULL); 
    // close the serial port
    close(fd_vcp);
    #ifdef RPISERP_DBG_PRINT
    printf(" \n Receiver thread terminated and serial port closed \n" );
    #endif
}

void RPISERP_SendPacket(sPacket* packet)
{
    // check the input
    if(packet->dlc > RPISERP_MAX_DATA_LENGTH)
    {
        #ifdef RPISERP_DBG_PRINT 
        printf("/n Invalid Tx packet length!");
        #endif
        return;
    }
    // compose the packet
    unsigned char txBuff[RPISERP_MAX_DATA_LENGTH + RPISERP_ID_LENGTH + 4];
    txBuff[0] = MSG_START_B1;
    txBuff[1] = MSG_START_B2;
    txBuff[2] = packet->dlc;

    memcpy(&(txBuff[3]), packet->data, packet->dlc);
    txBuff[packet->dlc + 3] = Checksum(txBuff, packet->dlc + 3);

    // send the complete packet to the serial port
    write(fd_vcp, txBuff, packet->dlc + 4);
    
}

int RPISERP_GetNumOfRxPackets(void)
{
    if(mRecIface.readIndex == mRecIface.writeIndex)
    {
        return 0;
    }
    else
    {
        if(mRecIface.readIndex < mRecIface.writeIndex)
        {
            return mRecIface.writeIndex - mRecIface.readIndex;
        }
        else
        {
            return mRecIface.writeIndex + mRecIface.buffSize - mRecIface.readIndex;
        }
    }

}

int RPISERP_GetRxPacket(sPacket* packet)
{
    packet->id = mRecIface.packets[mRecIface.readIndex].id;
    packet->dlc = mRecIface.packets[mRecIface.readIndex].dlc;
    memcpy(&(packet->data), &(mRecIface.packets[mRecIface.readIndex].data), packet->dlc);

    mRecIface.readIndex++;
    if(mRecIface.readIndex >= mRecIface.buffSize) mRecIface.readIndex = 0;
}