

#include "rpiserp.h"

#include <wiringPi.h>
#include <wiringSerial.h>
#include <iostream>
#include <stdio.h>
#include <stdlib.h>


// Init and open the serial port
void RPISERP::RPISERP_Init(void)
{
	mSp = serialOpen(UHA_PORT, 57600);
   // mSp = serialOpen(UHA_PORT, 19200);
    txData[0] = (CMD_RPI_VAR_VALUE >> 8) & 0xFF;
    txData[1] = CMD_RPI_VAR_VALUE & 0xFF;

    for (int i = 0; i < 256; i++)
    {
        mVars[i] = 0;
    }
}


void RPISERP::RPISERP_Deinit(void)
{
  // TBD
}

void RPISERP::RPISERP_StartReceiver(void)
{
    while(1)
    {

    }

}


void RPISERP::RPISERP_SendTelegram(void)
{
    // TBD
}