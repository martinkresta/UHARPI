

//#include "rpiserp.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <termios.h>
#include <unistd.h>
#include <fcntl.h>
#include <pthread.h>
#include "rpiserp.h"

#define UART_DEVICE     "/dev/ttyACM1"

struct termios t_vcp;

int fd_vcp; /* File descriptor for the port */

unsigned char buff[1000];
unsigned char txBuff[] = {0x7F, 0xAA, 0x03, 2, 0x00, 0x00, 0xCC};

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
  return chsum;
}


// the receiver thread
// reads continuously the serial port and parses the byte stream to locate a valid packets
void* Thread_Receiver(void *iface)
{

    unsigned char stream[1000]; // stream of received bytes
    int writeIdx = 0;
    int processIdx =0;
    int rxlen, idx;
    bool validPacket = false;
    bool cont = true;
    char packetLength;
    int remainingBytes;
    sPacket* pckt;

    sReceiverIface* interface = (sReceiverIface*) iface;
    while(interface->enable)
    {
        rxlen = read(fd_vcp, &(stream[writeIdx]),1000);
        if(rxlen > 0)
        {
            // adjust write index for next read
            writeIdx += rxlen;
            if(writeIdx >= 1000) writeIdx -=1000;

            // parse the stream
            cont = true;
            idx = processIdx;
            while ( cont == true)
            {
                remainingBytes = writeIdx - idx;
                if(idx >= writeIdx) remainingBytes = writeIdx + 1000 - idx;

                if(stream[idx] == MSG_START_B1 && stream[idx+1] == MSG_START_B2)
                {  // detected start sequence of the packet
                   packetLength = stream[idx+2];

                   // check if enough data was received
                   if(remainingBytes >= (packetLength + 4))  // header + len + chsum = 4
                   {
                     // validate the checksum
                     if( stream[idx + packetLength + 3] == Checksum(&(stream[idx]), packetLength + 3))
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
                            if(idx >= 1000) idx -= 1000;

                        }
                        else  
                        {
                            // too long messages are discarded - considered as invalid
                            validPacket = false;
                        }
                     }
                     else  // invalid checksum
                     {
                        validPacket = false;
                     }

                   }
                   else   // not enough data to parse entire packet
                   {
                     cont = false;  // skip the parsing for now and wait for mor data
                   }
                 
                }

                if(validPacket == false) // no packet found, move to next byte
                {
                    idx ++;
                    if(idx >= 1000) idx = 0;
                }
                else
                {
                    // do nothing. the idx was already incremented, when packet was detected
 
                }
            }

            processIdx = idx;


/*

            buff[rxlen] = 0;  // string termination
           // printf("\n RecBytes: %d  |    %s", rxlen, buff);
            printf("\n RecBytes: %d  |  ", rxlen);
            for(int i = 0; i < rxlen; i++)
            {
                printf("%02X ", buff[i]);
            }
            printf (" ");

            */
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

    write(fd_vcp, txBuff, 7);

    InitReceiverInterface();
    pthread_create(&RecThread_handle, NULL, Thread_Receiver, (void*)&mRecIface);
    printf(" \nThe receiver thread was started \n" );

    while(1)
    {

        // just process the RecInterface buffer and printout the received packets

        while (mRecIface.readIndex != mRecIface.writeIndex)
        {
            printf("\n ID: %d  |  Data: ", mRecIface.packets[mRecIface.readIndex].id);
            for(int i = 0; i < RPISERP_MAX_DATA_LENGTH; i++)
            {
                printf("%02X ", mRecIface.packets[mRecIface.readIndex].data[i]);
            }
            printf("  | ri: %d | wi: %d \n", mRecIface.readIndex, mRecIface.writeIndex);

            mRecIface.writeIndex++;
        }




        usleep(1000000);  // 1second sleep
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