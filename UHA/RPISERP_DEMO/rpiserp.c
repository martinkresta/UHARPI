


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

#define UART_DEVICE     "/dev/ttyACM0"

struct termios t_vcp;

int fd_vcp; /* File descriptor for the port */

int bitrate_counter = 0;

unsigned char buff[1000];
unsigned char Ibuff[1000];   // intermediate buffer
unsigned char txBuff[] = {0x7F, 0xAA, 0x03, 0xBB, 0x00, 0x00, 0xCC};

int rxlen;


sPacket RxPackets[RPISERP_RX_PACKETS_CAPACITY];

sReceiverIface mRecIface;

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
char Checksum(char* data, char length)
{
  char i,chsum;
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
        usleep(1000);  // 1 msecond sleep
        rxlen = read(fd_vcp, &(stream[writeIdx]),RPISERP_RX_RAW_BUFLEN-writeIdx);
        if(rxlen > 0)
        {
            // adjust write index for next read
            writeIdx += rxlen;
        
            processIdx = 0;  // allways start processing from the first byte in the stream buffer
            // parse the stream
            cont = true;
            idx = processIdx;
            #ifdef REC_DBG_PRINT
            printf(" \n Receiver: entering while loop with %d bytes (%d new) \n", writeIdx, rxlen);
            #endif
            while ( cont == true)
            {
                remainingBytes = writeIdx - idx;
                
               // printf(" \n Receiver: idx: %d | remaining: %d : writeIdx : %d  \n", idx, remainingBytes, writeIdx);
               validPacket = false;

                if(stream[idx] == MSG_START_B1 && stream[idx+1] == MSG_START_B2)
                {  // detected start sequence of the packet
                   packetLength = stream[idx+2];
                   #ifdef REC_DBG_PRINT
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
                     chsum = chsum & 0xFF;
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
                            memset(pckt->data,0,RPISERP_MAX_DATA_LENGTH);   // reset data to zero
                            memcpy(pckt->data,&(stream[idx+5]),packetLength - 2); // copy data without id
                            // increment the writeindex
                            interface->writeIndex++;
                            if(interface->writeIndex >= interface->buffSize) interface->writeIndex = 0;
                            // increment the idx
                            idx += packetLength + 4;
                            if(idx >= RPISERP_RX_RAW_BUFLEN) idx -= RPISERP_RX_RAW_BUFLEN;
                            #ifdef REC_DBG_PRINT
                            printf(" \n Receiver: complete packet %d stored  \n", interface->recPackets);
                            #endif

                        }
                        else  
                        {
                            // too long messages are discarded - considered as invalid
                            validPacket = false;
                            #ifdef REC_DBG_PRINT
                            printf(" \n Receiver: ERROR: too long packet  \n");
                            #endif
                            idx ++;
                        }
                     }
                     else  // invalid checksum
                     {
                        validPacket = false;
                        #ifdef REC_DBG_PRINT
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
                     #ifdef REC_DBG_PRINT
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
                    #ifdef REC_DBG_PRINT
                    printf("\n Receiver: leaving the while loop with all bytes processed");
                    #endif
                    writeIdx = 0;
                    continue;
                } 
            }

        }

    }
}


// Init and open the serial port
void main(void)
{

    pthread_t RecThread_handle;

    printf(" \n*** RPISERP 2.0 *** \n" ); 

    //fd_vcp = open(UART_DEVICE, O_RDWR | O_NOCTTY | O_NDELAY);
    fd_vcp = open(UART_DEVICE, O_RDWR | O_NOCTTY);
    if (fd_vcp == -1)
    {
        printf("Cannot open port \n");
    }

    //fcntl(fd_vcp, F_SETFL, FNDELAY);

    tcgetattr(fd_vcp, &t_vcp);
	
    //cfsetispeed(&t_vcp, B57600);
    //cfsetospeed(&t_vcp, B57600);
    cfsetspeed(&t_vcp, B115200);

    cfmakeraw(&t_vcp);
    //t_vcp.c_cflag = CS8 | CREAD;
    //t_vcp.c_iflag = IGNPAR | ICRNL;
    t_vcp.c_cc[VMIN] = 14;
    t_vcp.c_cc[VTIME] = 1;

    if(tcsetattr(fd_vcp,TCSANOW, &t_vcp))
    {
        printf(" \nError setting atributes \n" );        
    }

    // configure the NUCLEO to send more often
    write(fd_vcp, txBuff, 7);

    InitReceiverInterface();

    // setting the higher priority for the Receiver theread
    int rc;
    pthread_attr_t attr;
    struct sched_param param;

    rc = pthread_attr_init (&attr);
    rc = pthread_attr_getschedparam (&attr, &param);
    printf( "\n The default priority was : %d", (param.sched_priority));
    (param.sched_priority)+=10;
    printf( "\n New priority is : %d", (param.sched_priority));
    rc = pthread_attr_setschedparam (&attr, &param);
    // check RC ? 

    pthread_create(&RecThread_handle, &attr, Thread_Receiver, (void*)&mRecIface);
    printf(" \nThe receiver thread was started \n" );

    while(1)
    {

        // just process the RecInterface buffer and printout the received packets

        while (mRecIface.readIndex != mRecIface.writeIndex)
        {
            bitrate_counter++;
            printf("\n ID: %d  |  Data: ", mRecIface.packets[mRecIface.readIndex].id);
            for(int i = 0; i < RPISERP_MAX_DATA_LENGTH; i++)
            {
                printf("%03d ", mRecIface.packets[mRecIface.readIndex].data[i]);
            }
            printf("  | ri: %d | wi: %d \n", mRecIface.readIndex, mRecIface.writeIndex);

            mRecIface.readIndex++;
            if(mRecIface.readIndex >= mRecIface.buffSize) mRecIface.readIndex = 0;

        }

        // send loopback test
        txBuff[4] ++;
        txBuff[5] ++;
        write(fd_vcp, txBuff, 7);

        printf(" \n Sending data bytes: %d, %d", txBuff[4], txBuff[5]);

        printf("\n message counter : %d",bitrate_counter);
        usleep(1000);  // 10 msecond sleep
        

    }

    close(fd_vcp);

}


void RPISERP_Deinit(void)
{
  // TBD
}


// this hould run in separate thread. It will put complete received messages to the global buffer
void RPISERP_StartReceiver(void)
{

   
}


void RPISERP_SendTelegram(void)
{
    // TBD
}