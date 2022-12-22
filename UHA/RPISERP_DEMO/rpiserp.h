/* Moduel RPISERP.h  - implementing a simple serial protocol between RPI and UHA devices (STM32 CPUs)*/



#ifndef RPISERP_H
#define RPISERP_H


#define  MSG_START_B1							0x7F
#define  MSG_START_B2							0xAA

#define RPISERP_BUFLEN	20

#define RPISERP_RX_RAW_BUFLEN   1000

class RPISERP
{
	// private variables
private:  

    int mSp;  // bms serial port handler
    int i;
    int recLength;
    char txData[RPISERP_BUFLEN];
    char rxData[RPISERP_RX_RAW_BUFLEN];
    char input;
    
// public getters
public:  

//private methods
private:

    void TransmitMesssage(void);
	
// public methods
public:

   void RPISERP_Init(void);
   void RPISERP_Deinit(void);
   void RPISERP_StartReceiver(void);
   void RPISERP_SendTelegram(void);


};

#endif