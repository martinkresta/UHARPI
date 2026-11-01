
#include <iostream>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "UHA.h"
#include "cJSON.h"

extern "C" {
  #include "rpiserp.h"
}

using namespace std;

#define UHA_PORT	"/dev/ttyUSB0"
#define UHA_JSON_FULLPATH	"/home/pi/Web/uha.json"
#define BMS_JSON_FULLPATH	"/home/pi/Web/bms.json"



// Init and open the serial port
void UHA::UHA_Init(void)
{
    for (int i = 0; i < 256; i++)
    {
        mVars[i] = 0;
    }
	  RPISERP_Init((unsigned char*)UHA_PORT);
    RPISERP_Start();   
}

void UHA::UHA_DeInit(void)
{
    RPISERP_Stop();
}

void UHA::UHA_SendValues(void)
{

    // get values from the bms.json file
    char* buffer;
    long size;
    unsigned char txData[8];

    FILE* fh = fopen(BMS_JSON_FULLPATH, "r");
    if(fh == NULL)
    {
      cout << "Input file not found" << endl;
      return ;     
    }
    fseek(fh, 0, SEEK_END);
    size = ftell(fh);
    rewind(fh);

    buffer = (char*)malloc(sizeof(char) * size); 
    if (buffer == NULL)
    {
      cout << "Memory error" << endl;
      return ; 
    }
    fread(buffer, 1, size, fh);
    fclose(fh);

    cJSON *Bms = cJSON_Parse(buffer);
    if (Bms == NULL)
    {
      cout << "JSON parse error" << endl;
      return ; 
    }
    cJSON *BmsLiveData = cJSON_GetObjectItemCaseSensitive(Bms,"LiveData");
    if (BmsLiveData == NULL)
    {
      cout << "JSON parse error livedata" << endl;
      return ; 
    }


    short Soc = (short)cJSON_GetNumberValue(cJSON_GetObjectItem(BmsLiveData,"SocPct"));
    short Charg = (short)(cJSON_GetNumberValue(cJSON_GetObjectItem(BmsLiveData,"ChargingA")) * 10);
    short DisCharg = (short)(cJSON_GetNumberValue(cJSON_GetObjectItem(BmsLiveData,"DischargingA")) * 10);
    short Vbat = (short)(cJSON_GetNumberValue(cJSON_GetObjectItem(BmsLiveData,"TotalVoltageV")) * 10);

    cJSON_Delete(Bms);

    free(buffer);
    // compose the uart message
    // SOC
    SendVariable(VAR_BAT_SOC, Soc); 
    //delay(20);
 
     // Charging
    SendVariable(VAR_CHARGING_A10, Charg); 
    //delay(20);

    // Discharging
    SendVariable(VAR_LOAD_A100, DisCharg);
   // delay(20);

    // VBAT
    SendVariable(VAR_BAT_VOLTAGE_V10, Vbat);
    //delay(20);

    // Heartbeat
    txData[0] = 0x01;
    SendPacket(0x704,txData,1);

    cout << "Data sent: SOC = " << Soc <<" | Charg = " << Charg <<" | Discharg = " << DisCharg << endl; 
    // also create json
    CreateJson();
    
}


void UHA::UHA_CreateUhaJson(void)
{
  CreateJson();
}

void UHA::UHA_CreateBmsJson(void)
{
   int i;
  double sum = 0;
  int AvgTempC = 0;

  // calculate data that are not directly received from BMS
  int SunPowerW = (int)(mVars[VAR_MPPT_SOLAR_POWER_W]);
  int SunPowerPct = (int)(SunPowerW / 5400) * 100;
  double BattCurrentA = mVars[VAR_BAT_CURRENT_A10];
	int LoadPowerW = (int)(mVars[VAR_LOAD_W]);	
	int LoadPowerPct = (int)(LoadPowerW / 8000) * 100;
	double TodayDiffKwh = (mVars[VAR_MPPT_YIELD_TODAY_10WH]*10 - mVars[VAR_CONS_TODAY_WH]);

  int Time = (int)time(NULL);

  
  cJSON *Bms = cJSON_CreateObject();
  cJSON *PackInfo = cJSON_CreateObject();
  cJSON *LiveData = cJSON_CreateObject();
  cJSON *CellsJson = cJSON_CreateArray();
  
  
  cJSON_AddItemToObject(PackInfo, "CapacityKwh", cJSON_CreateNumber(16));
  cJSON_AddItemToObject(PackInfo, "MinCellVoltageV", cJSON_CreateNumber(3));
  cJSON_AddItemToObject(PackInfo, "MaxCellVoltageV", cJSON_CreateNumber(3.6));
  cJSON_AddItemToObject(PackInfo, "BalanceCellVoltageV", cJSON_CreateNumber(3.5));
  cJSON_AddItemToObject(PackInfo, "NumOfCells", cJSON_CreateNumber(16));
  cJSON_AddItemToObject(Bms, "BatteryPackInfo", PackInfo);
  
  cJSON_AddItemToObject(LiveData, "SunPowerW", cJSON_CreateNumber(SunPowerW));
  cJSON_AddItemToObject(LiveData, "TotalVoltageV", cJSON_CreateNumber(mVars[VAR_BAT_VOLTAGE_V10]/10.0));
  cJSON_AddItemToObject(LiveData, "ChargingA", cJSON_CreateNumber(mVars[VAR_CHARGING_A10]/10.0));
  cJSON_AddItemToObject(LiveData, "DischargingA", cJSON_CreateNumber(mVars[VAR_LOAD_A100]/100.0));
  cJSON_AddItemToObject(LiveData, "TodayChargingKwh", cJSON_CreateNumber(mVars[VAR_MPPT_YIELD_TODAY_10WH]/100.0));
  cJSON_AddItemToObject(LiveData, "TodayDischargingKwh", cJSON_CreateNumber(mVars[VAR_CONS_TODAY_WH]/1000.0));
  cJSON_AddItemToObject(LiveData, "AvailableEnergyKwh", cJSON_CreateNumber(mVars[VAR_BAT_ENERGY_WH]/1000.0));
 // cJSON_AddItemToObject(LiveData, "TotalChargingKwh", cJSON_CreateNumber(mVars[]));
  //cJSON_AddItemToObject(LiveData, "TotalDischargingKwh", cJSON_CreateNumber(mVars[]));
  cJSON_AddItemToObject(LiveData, "SocPct", cJSON_CreateNumber(mVars[VAR_BAT_SOC]));
  cJSON_AddItemToObject(LiveData, "TemperatureC", cJSON_CreateNumber(mVars[VAR_BMS2_CELL4_C]));
  cJSON_AddItemToObject(LiveData, "SunPowerPct", cJSON_CreateNumber(SunPowerPct));
  cJSON_AddItemToObject(LiveData, "BattCurrentA", cJSON_CreateNumber(mVars[VAR_SHUNT_CURRENT_A100]/100.0));
  cJSON_AddItemToObject(LiveData, "LoadCurrentA", cJSON_CreateNumber(mVars[VAR_LOAD_A100]/100.0));
  cJSON_AddItemToObject(LiveData, "LoadPowerW", cJSON_CreateNumber(mVars[VAR_LOAD_W]));
  cJSON_AddItemToObject(LiveData, "LoadPowerPct", cJSON_CreateNumber(LoadPowerPct));
  cJSON_AddItemToObject(LiveData, "TodayDiffKwh", cJSON_CreateNumber(TodayDiffKwh));
  cJSON_AddItemToObject(LiveData, "UnixTime", cJSON_CreateNumber(Time));

  cJSON_AddItemToObject(Bms,"LiveData", LiveData);
  
  cout << "filling cells in json."  << endl;
  
  for (i=0;i<16;i++)
  {
    cJSON *Cell = cJSON_CreateObject();
    cJSON_AddItemToObject(Cell, "VoltageV", cJSON_CreateNumber(mVars[i + VAR_BMS1_CELL1_MV]/1000.0));
    cJSON_AddItemToObject(Cell, "TemperatureC", cJSON_CreateNumber(mVars[i + VAR_BMS1_CELL1_C]));
    cJSON_AddItemToArray(CellsJson, Cell);
  }	

  
  cJSON_AddItemToObject(Bms,"Cells",CellsJson);
  
  cout << "saving file.."  << endl;
  
	FILE* fh = fopen(BMS_JSON_FULLPATH, "w");
	fprintf(fh, cJSON_Print(Bms));
	fclose(fh);
  cJSON_Delete(Bms);
}


void UHA::UHA_ProcessMessage(void)
{
  int cmd, varId,value;
  sPacket rxPacket;

  // process all messages available in the RPISERP rx buffer
  while (0 != RPISERP_GetNumOfRxPackets())
  {
      //printf("\n\n available Rx packets: %d ", RPISERP_GetNumOfRxPackets());
      

      RPISERP_GetRxPacket(&rxPacket);

      cmd = rxPacket.id;
      varId = (rxPacket.data[0] << 8) + rxPacket.data[1];
      value = (rxPacket.data[2] << 8) + rxPacket.data[3];

      cout << "Received packetid: " << rxPacket.id << " | varID: " << varId << " | value: " << value << endl;

      if ((cmd == CMD_TM_VAR_VALUE) && (varId < 256))  // variable value received
      {
          mVars[varId] = value;	  // store the variable
      }
  } 
}

void UHA::UHA_SendRTC(void)
{
    long int unixtime = (long int)time(NULL);
    struct tm* now = localtime(&unixtime);
    unsigned char txData[8];

    unsigned int localunixtime = unixtime + 3600;  // +1Hour Time zone offset
    if(now->tm_isdst > 0)
    {
      localunixtime += 3600; 
      cout << "Summer time" << endl;
    }
    else
    {
      cout << "Winter time" << endl;
    }

    txData[0] = (localunixtime >> 24) & 0xFF;
    txData[1] = (localunixtime >> 16) & 0xFF;
    txData[2] = (localunixtime >> 8) & 0xFF;
    txData[3] = localunixtime & 0xFF;
    SendPacket(CMD_RPI_RTC_SYNC, txData, 4);

    cout << "RTC Sync sent.." << endl;
}


void UHA::SendVariable(short int var, short int value)
{
  unsigned char payload[4];

  payload[0] = (var >> 8) & 0xFF;
  payload[1] = var & 0xFF;
  payload[2] = (value >> 8) & 0xFF;
  payload[3] = value & 0xFF;
  SendPacket(CMD_RPI_VAR_VALUE,payload, 4);
}

void UHA::SendPacket(short int id, unsigned char* data, unsigned char length)
{
  if (length > 8) return;  // too long data
  sPacket txPacket;
  txPacket.id = id;
  txPacket.dlc = length;
  memcpy(txPacket.data, data, length);
  RPISERP_SendPacket(&txPacket);
}

void UHA::CreateJson(void)
{
  int i;

  int Time = (int)time(NULL);
  
  cJSON *Uha = cJSON_CreateObject();


      cJSON_AddItemToObject(Uha, "VAR_BAT_SOC", cJSON_CreateNumber(mVars[10]));
      cJSON_AddItemToObject(Uha, "VAR_BAT_VOLTAGE_V10", cJSON_CreateNumber(mVars[11]));
      cJSON_AddItemToObject(Uha, "VAR_LOAD_A100", cJSON_CreateNumber(mVars[12]));
      cJSON_AddItemToObject(Uha, "VAR_CHARGING_A10", cJSON_CreateNumber(mVars[13]));
      cJSON_AddItemToObject(Uha, "VAR_BAT_CURRENT_A10", cJSON_CreateNumber(mVars[14]));
      cJSON_AddItemToObject(Uha, "VAR_CONS_TODAY_WH", cJSON_CreateNumber(mVars[15]));
      cJSON_AddItemToObject(Uha, "VAR_BAT_ENERGY_WH", cJSON_CreateNumber(mVars[16]));
      cJSON_AddItemToObject(Uha, "VAR_LOAD_W", cJSON_CreateNumber(mVars[17]));
      cJSON_AddItemToObject(Uha, "VAR_SHUNT_CURRENT_A100", cJSON_CreateNumber(mVars[50]));


      cJSON_AddItemToObject(Uha, "VAR_BMS1_SOC", cJSON_CreateNumber(mVars[20]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CURRENT_A10", cJSON_CreateNumber(mVars[21]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_VOLTAGE_V10", cJSON_CreateNumber(mVars[22]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_ENERGY_STORED_WH", cJSON_CreateNumber(mVars[23]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_TODAY_ENERGY_WH", cJSON_CreateNumber(mVars[24]));

      cJSON_AddItemToObject(Uha, "VAR_BMS2_SOC", cJSON_CreateNumber(mVars[30]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CURRENT_A10", cJSON_CreateNumber(mVars[31]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_VOLTAGE_V10", cJSON_CreateNumber(mVars[32]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_ENERGY_STORED_WH", cJSON_CreateNumber(mVars[33]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_TODAY_ENERGY_WH", cJSON_CreateNumber(mVars[34]));

      cJSON_AddItemToObject(Uha, "VAR_MPPT_BAT_CURRENT_A10", cJSON_CreateNumber(mVars[40]));
      cJSON_AddItemToObject(Uha, "VAR_MPPT_BAT_VOLTAGE_V100", cJSON_CreateNumber(mVars[41]));
      cJSON_AddItemToObject(Uha, "VAR_MPPT_YIELD_TODAY_10WH", cJSON_CreateNumber(mVars[42]));
      cJSON_AddItemToObject(Uha, "VAR_MPPT_MAX_TODAY_W", cJSON_CreateNumber(mVars[43]));
      cJSON_AddItemToObject(Uha, "VAR_MPPT_SOLAR_POWER_W", cJSON_CreateNumber(mVars[44]));
      cJSON_AddItemToObject(Uha, "VAR_MPPT_SOLAR_VOLTAGE_V100", cJSON_CreateNumber(mVars[45]));
      cJSON_AddItemToObject(Uha, "VAR_MPPT_SOLAR_CURRENT_A10", cJSON_CreateNumber(mVars[46]));
      cJSON_AddItemToObject(Uha, "VAR_MPPT_SOLAR_MAX_VOLTAGE_V100", cJSON_CreateNumber(mVars[47]));
      cJSON_AddItemToObject(Uha, "VAR_MPPT_MAX_BAT_CURRENT_A10", cJSON_CreateNumber(mVars[48]));

      cJSON_AddItemToObject(Uha, "VAR_EL_HEATER_STATUS", cJSON_CreateNumber(mVars[80]));
      cJSON_AddItemToObject(Uha, "VAR_EL_HEATER_POWER", cJSON_CreateNumber(mVars[81]));
      cJSON_AddItemToObject(Uha, "VAR_EL_HEATER_CURRENT", cJSON_CreateNumber(mVars[82]));
      cJSON_AddItemToObject(Uha, "VAR_EL_HEATER_CONS", cJSON_CreateNumber(mVars[83]));

      cJSON_AddItemToObject(Uha, "VAR_HEAT_TOTAL_WH", cJSON_CreateNumber(mVars[85]));
      cJSON_AddItemToObject(Uha, "VAR_HEAT_HEATING_WH", cJSON_CreateNumber(mVars[86]));


      cJSON_AddItemToObject(Uha, "VAR_FLOW_COLD", cJSON_CreateNumber(mVars[90]));
      cJSON_AddItemToObject(Uha, "VAR_FLOW_HOT", cJSON_CreateNumber(mVars[91]));
      cJSON_AddItemToObject(Uha, "VAR_CONS_COLD", cJSON_CreateNumber(mVars[92]));
      cJSON_AddItemToObject(Uha, "VAR_CONS_HOT", cJSON_CreateNumber(mVars[93]));

      cJSON_AddItemToObject(Uha, "VAR_BOILER_POWER", cJSON_CreateNumber(mVars[98]));
      cJSON_AddItemToObject(Uha, "VAR_BOILER_HEAT", cJSON_CreateNumber(mVars[99]));
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
      cJSON_AddItemToObject(Uha, "VAR_TEMP_OFFICE", cJSON_CreateNumber(mVars[125]));
      cJSON_AddItemToObject(Uha, "VAR_TEMP_KIDROOM", cJSON_CreateNumber(mVars[126]));
      cJSON_AddItemToObject(Uha, "VAR_TEMP_OUTSIDE", cJSON_CreateNumber(mVars[127]));

      cJSON_AddItemToObject(Uha, "VAR_CONS_AC300_WH", cJSON_CreateNumber(mVars[60]));
      cJSON_AddItemToObject(Uha, "VAR_CONS_AC3KW_WH", cJSON_CreateNumber(mVars[61]));
      cJSON_AddItemToObject(Uha, "VAR_CONS_AC5KW_WH", cJSON_CreateNumber(mVars[62]));
      cJSON_AddItemToObject(Uha, "VAR_CONS_FRIDGE_WH", cJSON_CreateNumber(mVars[63]));
      cJSON_AddItemToObject(Uha, "VAR_CONS_KITCHEN_WH", cJSON_CreateNumber(mVars[64]));
      cJSON_AddItemToObject(Uha, "VAR_CONS_WASCHMACHINE_WH", cJSON_CreateNumber(mVars[65]));
      cJSON_AddItemToObject(Uha, "VAR_CONS_OTHER_WH", cJSON_CreateNumber(mVars[66]));
      cJSON_AddItemToObject(Uha, "VAR_CONS_TECHM_WH", cJSON_CreateNumber(mVars[67]));


      cJSON_AddItemToObject(Uha, "VAR_POW_AC300_W", cJSON_CreateNumber(mVars[70]));
      cJSON_AddItemToObject(Uha, "VAR_POW_AC3KW_W", cJSON_CreateNumber(mVars[71]));
      cJSON_AddItemToObject(Uha, "VAR_POW_AC5KW_W", cJSON_CreateNumber(mVars[72]));
      cJSON_AddItemToObject(Uha, "VAR_POW_FRIDGE_W", cJSON_CreateNumber(mVars[73]));
      cJSON_AddItemToObject(Uha, "VAR_POW_KITCHEN_W", cJSON_CreateNumber(mVars[74]));
      cJSON_AddItemToObject(Uha, "VAR_POW_WASCHMACHINE_W", cJSON_CreateNumber(mVars[75]));
      cJSON_AddItemToObject(Uha, "VAR_POW_OTHER_W", cJSON_CreateNumber(mVars[76]));
      cJSON_AddItemToObject(Uha, "VAR_POW_TECHM_W", cJSON_CreateNumber(mVars[77]));


      cJSON_AddItemToObject(Uha, "VAR_TEMP_RECU_FC", cJSON_CreateNumber(mVars[128]));
      cJSON_AddItemToObject(Uha, "VAR_TEMP_RECU_FH", cJSON_CreateNumber(mVars[129]));
      cJSON_AddItemToObject(Uha, "VAR_TEMP_RECU_WH", cJSON_CreateNumber(mVars[130]));
      cJSON_AddItemToObject(Uha, "VAR_TEMP_RECU_WC", cJSON_CreateNumber(mVars[131]));
      cJSON_AddItemToObject(Uha, "VAR_RH_RECU_FH", cJSON_CreateNumber(mVars[132]));
      cJSON_AddItemToObject(Uha, "VAR_RH_RECU_WH", cJSON_CreateNumber(mVars[133]));

      cJSON_AddItemToObject(Uha, "VAR_CO2_RECU", cJSON_CreateNumber(mVars[137]));
      cJSON_AddItemToObject(Uha, "VAR_DP_RECU_F", cJSON_CreateNumber(mVars[138]));
      cJSON_AddItemToObject(Uha, "VAR_DP_RECU_W", cJSON_CreateNumber(mVars[139]));
      cJSON_AddItemToObject(Uha, "VAR_RECU_FAN_F", cJSON_CreateNumber(mVars[140]));
      cJSON_AddItemToObject(Uha, "VAR_RECU_FAN_W", cJSON_CreateNumber(mVars[141]));
      cJSON_AddItemToObject(Uha, "VAR_CURR_RECU_A", cJSON_CreateNumber(mVars[142]));


      cJSON_AddItemToObject(Uha, "VAR_METEO_WIND_BURST", cJSON_CreateNumber(mVars[161]));
      cJSON_AddItemToObject(Uha, "VAR_METEO_WIND_AVG", cJSON_CreateNumber(mVars[162]));
      cJSON_AddItemToObject(Uha, "VAR_METEO_WIND_POW", cJSON_CreateNumber(mVars[163]));
      cJSON_AddItemToObject(Uha, "VAR_METEO_WIND_ENERGY", cJSON_CreateNumber(mVars[164]));

      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL1_MV", cJSON_CreateNumber(mVars[180]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL2_MV", cJSON_CreateNumber(mVars[181]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL3_MV", cJSON_CreateNumber(mVars[182]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL4_MV", cJSON_CreateNumber(mVars[183]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL5_MV", cJSON_CreateNumber(mVars[184]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL6_MV", cJSON_CreateNumber(mVars[185]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL7_MV", cJSON_CreateNumber(mVars[186]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL8_MV", cJSON_CreateNumber(mVars[187]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL9_MV", cJSON_CreateNumber(mVars[188]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL10_MV", cJSON_CreateNumber(mVars[189]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL11_MV", cJSON_CreateNumber(mVars[190]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL12_MV", cJSON_CreateNumber(mVars[191]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL13_MV", cJSON_CreateNumber(mVars[192]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL14_MV", cJSON_CreateNumber(mVars[193]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL15_MV", cJSON_CreateNumber(mVars[194]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL16_MV", cJSON_CreateNumber(mVars[195]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL1_C", cJSON_CreateNumber(mVars[196]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL2_C", cJSON_CreateNumber(mVars[197]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL3_C", cJSON_CreateNumber(mVars[198]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL4_C", cJSON_CreateNumber(mVars[199]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL5_C", cJSON_CreateNumber(mVars[200]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL6_C", cJSON_CreateNumber(mVars[201]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL7_C", cJSON_CreateNumber(mVars[202]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL8_C", cJSON_CreateNumber(mVars[203]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL9_C", cJSON_CreateNumber(mVars[204]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL10_C", cJSON_CreateNumber(mVars[205]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL11_C", cJSON_CreateNumber(mVars[206]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL12_C", cJSON_CreateNumber(mVars[207]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL13_C", cJSON_CreateNumber(mVars[208]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL14_C", cJSON_CreateNumber(mVars[209]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL15_C", cJSON_CreateNumber(mVars[210]));
      cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL16_C", cJSON_CreateNumber(mVars[211]));

      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL1_MV", cJSON_CreateNumber(mVars[220]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL2_MV", cJSON_CreateNumber(mVars[221]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL3_MV", cJSON_CreateNumber(mVars[222]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL4_MV", cJSON_CreateNumber(mVars[223]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL5_MV", cJSON_CreateNumber(mVars[224]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL6_MV", cJSON_CreateNumber(mVars[225]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL7_MV", cJSON_CreateNumber(mVars[226]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL8_MV", cJSON_CreateNumber(mVars[227]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL9_MV", cJSON_CreateNumber(mVars[228]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL10_MV", cJSON_CreateNumber(mVars[229]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL11_MV", cJSON_CreateNumber(mVars[230]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL12_MV", cJSON_CreateNumber(mVars[231]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL13_MV", cJSON_CreateNumber(mVars[232]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL14_MV", cJSON_CreateNumber(mVars[233]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL15_MV", cJSON_CreateNumber(mVars[234]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL16_MV", cJSON_CreateNumber(mVars[235]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL1_C", cJSON_CreateNumber(mVars[236]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL2_C", cJSON_CreateNumber(mVars[237]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL3_C", cJSON_CreateNumber(mVars[238]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL4_C", cJSON_CreateNumber(mVars[239]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL5_C", cJSON_CreateNumber(mVars[240]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL6_C", cJSON_CreateNumber(mVars[241]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL7_C", cJSON_CreateNumber(mVars[242]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL8_C", cJSON_CreateNumber(mVars[243]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL9_C", cJSON_CreateNumber(mVars[244]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL10_C", cJSON_CreateNumber(mVars[245]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL11_C", cJSON_CreateNumber(mVars[246]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL12_C", cJSON_CreateNumber(mVars[247]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL13_C", cJSON_CreateNumber(mVars[248]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL14_C", cJSON_CreateNumber(mVars[249]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL15_C", cJSON_CreateNumber(mVars[250]));
      cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL16_C", cJSON_CreateNumber(mVars[251]));

    cJSON_AddItemToObject(Uha, "UnixTime", cJSON_CreateNumber(Time));



  
  cout << "saving file UHA.json"  << endl;
  
	FILE* fh = fopen(UHA_JSON_FULLPATH, "w");
  if (fh == NULL)
  {
    cout << "Error opening file UHA.json " << endl; 
  }
  else
  {
	  fprintf(fh, cJSON_Print(Uha));
	  fclose(fh);
    cout << "File UHA.json writen and closed " << endl; 
  }
  
  cJSON_Delete(Uha);
  return;
}