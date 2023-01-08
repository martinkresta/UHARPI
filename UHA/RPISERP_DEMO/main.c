// Application for testing rpiserp library for linux deviece

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
#include <fcntl.h>
#include "rpiserp.h"


#define UART_DEVICE     "/dev/ttyACM0"

void main(void)
{

    RPISERP_Init(UART_DEVICE);

    // configure the NUCLEO to send more often
    sPacket tx;
    tx.id = 0x180;
    tx.dlc = 4;
    tx.data[0] = 0xBB;
    tx.data[1] = 0x00;
    tx.data[2] = 0x00;
    RPISERP_SendPacket(&tx);

    RPISERP_Start();

    while(tx.data[2] < 10)
    {

        // just process the RecInterface buffer and printout the received packets

        while (0 != RPISERP_GetNumOfRxPackets())
        {
            sPacket rxPacket;
            printf("\n\n available Rx packets: %d ", RPISERP_GetNumOfRxPackets());

            RPISERP_GetRxPacket(&rxPacket);

            printf("\n ID: %d  | DLC: %d  |  Data: ", rxPacket.id, rxPacket.dlc);
            for(int i = 0; i < RPISERP_MAX_DATA_LENGTH; i++)
            {
                printf("%03d ", rxPacket.data[i]);
            }

        }

        // send loopback test
         tx.data[1] ++;
         tx.data[2] ++;
         RPISERP_SendPacket(&tx);

        printf(" \n Sending data bytes: %d, %d", tx.data[1], tx.data[2]);

        usleep(30000);  // 30 msecond sleep
        

    }

    RPISERP_Stop();

}