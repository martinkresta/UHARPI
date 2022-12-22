

//#include "rpiserp.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <termios.h>
#include <unistd.h>
#include <fcntl.h>

#define UART_DEVICE     "/dev/ttyACM0"

struct termios t_vcp;

int fd_vcp; /* File descriptor for the port */

unsigned char buff[1000];

int rxlen;

// Init and open the serial port
void main(void)
{

    printf(" \n*** RPISERP 1.5 *** \n" ); 

    //fd_vcp = open(UART_DEVICE, O_RDWR | O_NOCTTY | O_NDELAY);
    fd_vcp = open(UART_DEVICE, O_RDWR | O_NOCTTY);
    if (fd_vcp == -1)
    {
        printf("Cannot open port \n");
    }

    //fcntl(fd_vcp, F_SETFL, FNDELAY);

    tcgetattr(fd_vcp, &t_vcp);
	
    cfsetispeed(&t_vcp, B57600);
    cfsetospeed(&t_vcp, B57600);
    //cfsetspeed(&t_vcp, B115200);

    cfmakeraw(&t_vcp);
    //t_vcp.c_cflag = CS8 | CREAD;
    //t_vcp.c_iflag = IGNPAR | ICRNL;
    t_vcp.c_cc[VMIN] = 14;
    t_vcp.c_cc[VTIME] = 1;

    if(tcsetattr(fd_vcp,TCSANOW, &t_vcp))
    {
        printf(" \nError setting atributes \n" );        
    }

    while(1)
    {
        rxlen = read(fd_vcp, buff,1000);
        if(rxlen > 0)
        {
            buff[rxlen] = 0;  // string termination
           // printf("\n RecBytes: %d  |    %s", rxlen, buff);
            printf("\n RecBytes: %d  |  ", rxlen);
            for(int i = 0; i < rxlen; i++)
            {
                printf("%02X ", buff[i]);
            }
            printf ("");
        }

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