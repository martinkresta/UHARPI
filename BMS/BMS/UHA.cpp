#include <wiringPi.h>
#include <wiringSerial.h>
#include <iostream>
using namespace std;

#define UHA_PORT	"/dev/ttyUSB0"
#define UHA_JSON_FULLPATH	"/home/pi/Web/uha.json"


#include "UHA.h"
#include "BMS.h"
#include "cJSON.h"



//void TransmitMesssage(void);

// Init and open the serial port
void UHA::UHA_Init(BMS* bms)
{
    mBms = bms;
  //  wiringPiSetupGpio();	
	mSp = serialOpen(UHA_PORT, 57600);
    txData[0] = (CMD_RPI_VAR_VALUE >> 8) & 0xFF;
    txData[1] = CMD_RPI_VAR_VALUE & 0xFF;

    for (int i = 0; i < 256; i++)
    {
        mVars[i] = 0;
    }
}

void UHA::UHA_DeInit(void)
{
    serialClose(mSp);    
}

void UHA::UHA_SendValues(void)
{
    // get values from the BMS.h

    short Soc = (short)mBms->SOC();
    short Charg = (short)(mBms->ChargingA() * 10);
    short DisCharg = (short)(mBms->DischargingA() * 10);
    short Vbat = (short)(mBms->TotalVoltageV() * 10);

    // compose the uart message
    // SOC
    txData[0] = (CMD_RPI_VAR_VALUE >> 8) & 0xFF;
    txData[1] = CMD_RPI_VAR_VALUE & 0xFF;
    txData[2] = (VAR_BAT_SOC >> 8) & 0xFF;
    txData[3] = VAR_BAT_SOC & 0xFF;
    txData[4] = (Soc >> 8) & 0xFF;
    txData[5] = Soc & 0xFF;
    TransmitMesssage();  
    delay(20);
 
     // Charging
    txData[0] = (CMD_RPI_VAR_VALUE >> 8) & 0xFF;
    txData[1] = CMD_RPI_VAR_VALUE & 0xFF;
    txData[2] = (VAR_CHARGING_A10 >> 8) & 0xFF;
    txData[3] = VAR_CHARGING_A10 & 0xFF;
    txData[4] = (Charg >> 8) & 0xFF;
    txData[5] = Charg & 0xFF;
    TransmitMesssage(); 
    delay(20);

    // Discharging
    txData[0] = (CMD_RPI_VAR_VALUE >> 8) & 0xFF;
    txData[1] = CMD_RPI_VAR_VALUE & 0xFF;
    txData[2] = (VAR_LOAD_A10 >> 8) & 0xFF;
    txData[3] = VAR_LOAD_A10 & 0xFF;
    txData[4] = (DisCharg >> 8) & 0xFF;
    txData[5] = DisCharg & 0xFF;
    TransmitMesssage(); 
    delay(20);

    // VBAT
    txData[0] = (CMD_RPI_VAR_VALUE >> 8) & 0xFF;
    txData[1] = CMD_RPI_VAR_VALUE & 0xFF;
    txData[2] = (VAR_BAT_VOLTAGE_V10 >> 8) & 0xFF;
    txData[3] = VAR_BAT_VOLTAGE_V10 & 0xFF;
    txData[4] = (Vbat >> 8) & 0xFF;
    txData[5] = Vbat & 0xFF;
    TransmitMesssage(); 
    delay(20);

    // Heartbeat
    txData[0] = (0x704 >> 8) & 0xFF;
    txData[1] = 0x704 & 0xFF;
    txData[2] = 0x01;
    TransmitMesssage(); 
    // also create json
    CreateJson();
    
}

void UHA::UHA_ProcessMessage(void)
{
   int cmd, varId,value;
   int recLength = serialDataAvail(mSp);
   
    if (recLength >= COM_BUFLEN)
    {
        // complete message recived
        for (i=0;i<recLength;i++)
        {
            rxData[i] = serialGetchar(mSp);
        }

        // decode meseage
        cmd = (rxData[0] << 8) + rxData[1];
        varId = (rxData[2] << 8) + rxData[3];
        value = (rxData[4] << 8) + rxData[5];
        if (cmd == CMD_TM_VAR_VALUE && varId < 256)
        {
            mVars[varId] = value;	        
        }
        cout << "Cmd: 	    " << cmd <<endl;
        cout << "VarId: 	" << varId <<endl;
	    cout << "value: 	" << value <<endl;
        cout << "------------------------------" << endl;
        //serialFlush(mSp);
    }
    else
    {
       // cout << "Reclength: 	" << recLength <<endl;
    }
   
    
}



void UHA::TransmitMesssage(void)
{
 int i;
 for (i = 0; i < COM_BUFLEN; i++)
 {
    serialPutchar(mSp,txData[i]);	    
 }

}

void UHA::CreateJson(void)
{
  int i;

  int Time = (int)time(NULL);
  
  cJSON *Uha = cJSON_CreateObject();

    cJSON_AddItemToObject(Uha, "VAR_BAT_SOC", cJSON_CreateNumber(mVars[10]));
    cJSON_AddItemToObject(Uha, "VAR_BAT_VOLTAGE_V10", cJSON_CreateNumber(mVars[11]));
    cJSON_AddItemToObject(Uha, "VAR_LOAD_A10", cJSON_CreateNumber(mVars[12]));
    cJSON_AddItemToObject(Uha, "VAR_CHARGING_A10", cJSON_CreateNumber(mVars[13]));


    cJSON_AddItemToObject(Uha, "VAR_EL_HEATER_STATUS", cJSON_CreateNumber(mVars[80]));
    cJSON_AddItemToObject(Uha, "VAR_EL_HEATER_POWER", cJSON_CreateNumber(mVars[81]));
    cJSON_AddItemToObject(Uha, "VAR_EL_HEATER_CURRENT", cJSON_CreateNumber(mVars[82]));
    cJSON_AddItemToObject(Uha, "VAR_EL_HEATER_CONS", cJSON_CreateNumber(mVars[83]));


    cJSON_AddItemToObject(Uha, "VAR_FLOW_COLD", cJSON_CreateNumber(mVars[90]));
    cJSON_AddItemToObject(Uha, "VAR_FLOW_HOT", cJSON_CreateNumber(mVars[91]));
    cJSON_AddItemToObject(Uha, "VAR_CONS_COLD", cJSON_CreateNumber(mVars[92]));
    cJSON_AddItemToObject(Uha, "VAR_CONS_HOT", cJSON_CreateNumber(mVars[93]));


    cJSON_AddItemToObject(Uha, "VAR_TEMP_BOILER", cJSON_CreateNumber(mVars[100]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_BOILER_IN", cJSON_CreateNumber(mVars[101]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_BOILER_OUT", cJSON_CreateNumber(mVars[102]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_IN_H", cJSON_CreateNumber(mVars[103]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_OUT_H", cJSON_CreateNumber(mVars[104]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_1", cJSON_CreateNumber(mVars[105]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_2", cJSON_CreateNumber(mVars[106]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_3", cJSON_CreateNumber(mVars[107]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_4", cJSON_CreateNumber(mVars[108]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_5", cJSON_CreateNumber(mVars[109]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_6", cJSON_CreateNumber(mVars[110]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_WALL_IN", cJSON_CreateNumber(mVars[111]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_WALL_OUT", cJSON_CreateNumber(mVars[112]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_BOILER_EXHAUST", cJSON_CreateNumber(mVars[113]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_RAD_H", cJSON_CreateNumber(mVars[114]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_RAD_C", cJSON_CreateNumber(mVars[115]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_IN_C", cJSON_CreateNumber(mVars[116]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_OUT_C", cJSON_CreateNumber(mVars[117]));


    cJSON_AddItemToObject(Uha, "VAR_TEMP_TECHM_BOARD", cJSON_CreateNumber(mVars[120]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_IOBOARD_D", cJSON_CreateNumber(mVars[121]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_IOBOARD_U", cJSON_CreateNumber(mVars[122]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_ELECON_BOARD", cJSON_CreateNumber(mVars[123]));
    cJSON_AddItemToObject(Uha, "VAR_TEMP_DOWNSTAIRS", cJSON_CreateNumber(mVars[124]));

    cJSON_AddItemToObject(Uha, "UnixTime", cJSON_CreateNumber(Time));



  
  cout << "saving file UHA.json"  << endl;
  
	FILE* fh = fopen(UHA_JSON_FULLPATH, "w");
	fprintf(fh, cJSON_Print(Uha));
	fclose(fh);
  cJSON_Delete(Uha);
}