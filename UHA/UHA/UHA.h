

#ifndef UHA_H
#define UHA_H



#define COM_BUFLEN	10

#define  VAR_BAT_SOC  10
#define  VAR_BAT_VOLTAGE_V10  11
#define  VAR_LOAD_A10  12
#define  VAR_CHARGING_A10  13


#define  CMD_RPI_VAR_VALUE  0x50
#define  CMD_RPI_RTC_SYNC  0x51


#define  CMD_TM_VAR_VALUE  	0x221


class UHA
{
	// private variables
private:  

    int mSp;  // bms serial port handler
    int i;
    int recLength;
    char txData[COM_BUFLEN];
    char rxData[COM_BUFLEN];
    char input;

    short mVars[255];
    
// public getters
public:  

//private methods
private:

    void TransmitMesssage(void);
    void CreateJson(void);
	
// public methods
public:

   void UHA_Init(void);
   void UHA_DeInit(void);
   void UHA_SendValues(void);
   void UHA_ProcessMessage(void);
   void UHA_SendRTC(void);

};


#endif 