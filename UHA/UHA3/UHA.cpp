
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
    for (int i = 0; i < NUM_OF_VARS; i++)
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
 /* int SunPowerW = (int)(mVars[VAR_MPPT_SOLAR_POWER_W]);
  int SunPowerPct = (int)(SunPowerW / 5400) * 100;
  double BattCurrentA = mVars[VAR_BAT_CURRENT_A10];
	int LoadPowerW = (int)(mVars[VAR_LOAD_W]);	
	int LoadPowerPct = (int)(LoadPowerW / 8000) * 100;
	double TodayDiffKwh = (mVars[VAR_MPPT_YIELD_TODAY_10WH]*10 - mVars[VAR_CONS_TODAY_WH]);*/

  int SunPowerW = (int)(mVars[VAR_SOLAR_POWER_W]);
  int SunPowerPct = (int)(SunPowerW / 11200) * 100;
  double BattCurrentA = mVars[VAR_BAT_CURRENT_A10];
  double BattPowerW = mVars[VAR_BAT_POWER_W];
	int LoadPowerW = (int)(mVars[VAR_LOAD_W]);	
	int LoadPowerPct = (int)(LoadPowerW / 8000) * 100;
	double TodayDiffKwh = (mVars[VAR_SOLAR_ENERGY_TODAY_10WH]*10 - mVars[VAR_CONS_TODAY_WH]);   // WH! 
  double totalCharging = (mVars[VAR_AXPERT_BAT_CHARGING_A]  +  mVars[VAR_MPPT_BAT_CURRENT_A10]);

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
 // cJSON_AddItemToObject(LiveData, "ChargingA", cJSON_CreateNumber(mVars[VAR_CHARGING_A10]/10.0));
  cJSON_AddItemToObject(LiveData, "ChargingA", cJSON_CreateNumber(totalCharging));
  cJSON_AddItemToObject(LiveData, "DischargingA", cJSON_CreateNumber(mVars[VAR_LOAD_A100]/100.0));
  cJSON_AddItemToObject(LiveData, "DischargingA", 0);
  cJSON_AddItemToObject(LiveData, "TodayChargingKwh", cJSON_CreateNumber(mVars[VAR_MPPT_YIELD_TODAY_10WH]/100.0));
  cJSON_AddItemToObject(LiveData, "TodayDischargingKwh", cJSON_CreateNumber(mVars[VAR_CONS_TODAY_WH]/1000.0));
  cJSON_AddItemToObject(LiveData, "AvailableEnergyKwh", cJSON_CreateNumber(mVars[VAR_BAT_ENERGY_WH]/1000.0));
  cJSON_AddItemToObject(LiveData, "TotalChargingKwh", 0);
  cJSON_AddItemToObject(LiveData, "TotalDischargingKwh",0);
  cJSON_AddItemToObject(LiveData, "SocPct", cJSON_CreateNumber(mVars[VAR_BAT_SOC]));
  cJSON_AddItemToObject(LiveData, "TemperatureC", cJSON_CreateNumber(mVars[VAR_BMS2_CELL4_C]));
  cJSON_AddItemToObject(LiveData, "SunPowerPct", cJSON_CreateNumber(SunPowerPct));
  cJSON_AddItemToObject(LiveData, "BattCurrentA", cJSON_CreateNumber(mVars[VAR_BAT_CURRENT_A10]/10.0));
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
  
  cout << "saving file BSM.json"  << endl;
  
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

      if ((cmd == CMD_TM_VAR_VALUE) && (varId < NUM_OF_VARS))  // variable value received
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


cJSON_AddItemToObject(Uha, "VAR_SOLAR_POWER_W", cJSON_CreateNumber(mVars[VAR_SOLAR_POWER_W]));
cJSON_AddItemToObject(Uha, "VAR_SOLAR_ENERGY_TODAY_10WH", cJSON_CreateNumber(mVars[VAR_SOLAR_ENERGY_TODAY_10WH]));
cJSON_AddItemToObject(Uha, "VAR_BAT_SOC", cJSON_CreateNumber(mVars[VAR_BAT_SOC]));
cJSON_AddItemToObject(Uha, "VAR_BAT_VOLTAGE_V10", cJSON_CreateNumber(mVars[VAR_BAT_VOLTAGE_V10]));
cJSON_AddItemToObject(Uha, "VAR_LOAD_A100", cJSON_CreateNumber(mVars[VAR_LOAD_A100]));
cJSON_AddItemToObject(Uha, "VAR_CHARGING_A10", cJSON_CreateNumber(mVars[VAR_CHARGING_A10]));
cJSON_AddItemToObject(Uha, "VAR_BAT_CURRENT_A10", cJSON_CreateNumber(mVars[VAR_BAT_CURRENT_A10]));
cJSON_AddItemToObject(Uha, "VAR_CONS_TODAY_WH", cJSON_CreateNumber(mVars[VAR_CONS_TODAY_WH]));
cJSON_AddItemToObject(Uha, "VAR_BAT_ENERGY_WH", cJSON_CreateNumber(mVars[VAR_BAT_ENERGY_WH]));
cJSON_AddItemToObject(Uha, "VAR_LOAD_W", cJSON_CreateNumber(mVars[VAR_LOAD_W]));
cJSON_AddItemToObject(Uha, "VAR_BAT_POWER_W", cJSON_CreateNumber(mVars[VAR_BAT_POWER_W]));

cJSON_AddItemToObject(Uha, "VAR_POW_AC300_W", cJSON_CreateNumber(mVars[VAR_POW_AC300_W]));
cJSON_AddItemToObject(Uha, "VAR_POW_AC3KW_W", cJSON_CreateNumber(mVars[VAR_POW_AC3KW_W]));
cJSON_AddItemToObject(Uha, "VAR_POW_AC5KW_W", cJSON_CreateNumber(mVars[VAR_POW_AC5KW_W]));
cJSON_AddItemToObject(Uha, "VAR_POW_FRIDGE_W", cJSON_CreateNumber(mVars[VAR_POW_FRIDGE_W]));
cJSON_AddItemToObject(Uha, "VAR_POW_KITCHEN_W", cJSON_CreateNumber(mVars[VAR_POW_KITCHEN_W]));
cJSON_AddItemToObject(Uha, "VAR_POW_WASCHMACHINE_W", cJSON_CreateNumber(mVars[VAR_POW_WASCHMACHINE_W]));
cJSON_AddItemToObject(Uha, "VAR_POW_OTHER_W", cJSON_CreateNumber(mVars[VAR_POW_OTHER_W]));
cJSON_AddItemToObject(Uha, "VAR_POW_TECHM_W", cJSON_CreateNumber(mVars[VAR_POW_TECHM_W]));
cJSON_AddItemToObject(Uha, "VAR_POW_KITCHEN_A_W", cJSON_CreateNumber(mVars[VAR_POW_KITCHEN_A_W]));
cJSON_AddItemToObject(Uha, "VAR_POW_KITCHEN_B_W", cJSON_CreateNumber(mVars[VAR_POW_KITCHEN_B_W]));
cJSON_AddItemToObject(Uha, "VAR_POW_AXPERT_W", cJSON_CreateNumber(mVars[VAR_POW_AXPERT_W]));
cJSON_AddItemToObject(Uha, "VAR_POW_EVSE_W", cJSON_CreateNumber(mVars[VAR_POW_EVSE_W]));
cJSON_AddItemToObject(Uha, "VAR_POW_WS_HEATING_W", cJSON_CreateNumber(mVars[VAR_POW_WS_HEATING_W]));

cJSON_AddItemToObject(Uha, "VAR_CONS_AC300_WH", cJSON_CreateNumber(mVars[VAR_CONS_AC300_WH]));
cJSON_AddItemToObject(Uha, "VAR_CONS_AC3KW_WH", cJSON_CreateNumber(mVars[VAR_CONS_AC3KW_WH]));
cJSON_AddItemToObject(Uha, "VAR_CONS_AC5KW_WH", cJSON_CreateNumber(mVars[VAR_CONS_AC5KW_WH]));
cJSON_AddItemToObject(Uha, "VAR_CONS_FRIDGE_WH", cJSON_CreateNumber(mVars[VAR_CONS_FRIDGE_WH]));
cJSON_AddItemToObject(Uha, "VAR_CONS_KITCHEN_WH", cJSON_CreateNumber(mVars[VAR_CONS_KITCHEN_WH]));
cJSON_AddItemToObject(Uha, "VAR_CONS_WASCHMACHINE_WH", cJSON_CreateNumber(mVars[VAR_CONS_WASCHMACHINE_WH]));
cJSON_AddItemToObject(Uha, "VAR_CONS_OTHER_WH", cJSON_CreateNumber(mVars[VAR_CONS_OTHER_WH]));
cJSON_AddItemToObject(Uha, "VAR_CONS_TECHM_WH", cJSON_CreateNumber(mVars[VAR_CONS_TECHM_WH]));
cJSON_AddItemToObject(Uha, "VAR_CONS_KITCHEN_A_WH", cJSON_CreateNumber(mVars[VAR_CONS_KITCHEN_A_WH]));
cJSON_AddItemToObject(Uha, "VAR_CONS_KITCHEN_B_WH", cJSON_CreateNumber(mVars[VAR_CONS_KITCHEN_B_WH]));
cJSON_AddItemToObject(Uha, "VAR_CONS_AXPERT_WH", cJSON_CreateNumber(mVars[VAR_CONS_AXPERT_WH]));
cJSON_AddItemToObject(Uha, "VAR_CONS_EVSE_WH", cJSON_CreateNumber(mVars[VAR_CONS_EVSE_WH]));
cJSON_AddItemToObject(Uha, "VAR_CONS_WS_HEATING_WH", cJSON_CreateNumber(mVars[VAR_CONS_WS_HEATING_WH]));

cJSON_AddItemToObject(Uha, "VAR_EL_HEATER_STATUS", cJSON_CreateNumber(mVars[VAR_EL_HEATER_STATUS]));
cJSON_AddItemToObject(Uha, "VAR_EL_HEATER_POWER", cJSON_CreateNumber(mVars[VAR_EL_HEATER_POWER]));
cJSON_AddItemToObject(Uha, "VAR_EL_HEATER_CURRENT", cJSON_CreateNumber(mVars[VAR_EL_HEATER_CURRENT]));
cJSON_AddItemToObject(Uha, "VAR_EL_HEATER_CONS", cJSON_CreateNumber(mVars[VAR_EL_HEATER_CONS]));

cJSON_AddItemToObject(Uha, "VAR_HEAT_TOTAL_WH", cJSON_CreateNumber(mVars[VAR_HEAT_TOTAL_WH]));
cJSON_AddItemToObject(Uha, "VAR_HEAT_HEATING_WH", cJSON_CreateNumber(mVars[VAR_HEAT_HEATING_WH]));

cJSON_AddItemToObject(Uha, "VAR_BOILER_POWER", cJSON_CreateNumber(mVars[VAR_BOILER_POWER]));
cJSON_AddItemToObject(Uha, "VAR_BOILER_HEAT", cJSON_CreateNumber(mVars[VAR_BOILER_HEAT]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_BOILER", cJSON_CreateNumber(mVars[VAR_TEMP_BOILER]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_BOILER_IN", cJSON_CreateNumber(mVars[VAR_TEMP_BOILER_IN]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_BOILER_OUT", cJSON_CreateNumber(mVars[VAR_TEMP_BOILER_OUT]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_IN_H", cJSON_CreateNumber(mVars[VAR_TEMP_TANK_IN_H]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_OUT_H", cJSON_CreateNumber(mVars[VAR_TEMP_TANK_OUT_H]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_1", cJSON_CreateNumber(mVars[VAR_TEMP_TANK_1]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_2", cJSON_CreateNumber(mVars[VAR_TEMP_TANK_2]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_3", cJSON_CreateNumber(mVars[VAR_TEMP_TANK_3]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_4", cJSON_CreateNumber(mVars[VAR_TEMP_TANK_4]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_5", cJSON_CreateNumber(mVars[VAR_TEMP_TANK_5]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_6", cJSON_CreateNumber(mVars[VAR_TEMP_TANK_6]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_WALL_IN", cJSON_CreateNumber(mVars[VAR_TEMP_WALL_IN]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_WALL_OUT", cJSON_CreateNumber(mVars[VAR_TEMP_WALL_OUT]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_BOILER_EXHAUST", cJSON_CreateNumber(mVars[VAR_TEMP_BOILER_EXHAUST]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_RAD_H", cJSON_CreateNumber(mVars[VAR_TEMP_RAD_H]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_RAD_C", cJSON_CreateNumber(mVars[VAR_TEMP_RAD_C]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_IN_C", cJSON_CreateNumber(mVars[VAR_TEMP_TANK_IN_C]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_TANK_OUT_C", cJSON_CreateNumber(mVars[VAR_TEMP_TANK_OUT_C]));


cJSON_AddItemToObject(Uha, "VAR_TEMP_DOWNSTAIRS", cJSON_CreateNumber(mVars[VAR_TEMP_DOWNSTAIRS]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_OFFICE", cJSON_CreateNumber(mVars[VAR_TEMP_OFFICE]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_KIDROOM", cJSON_CreateNumber(mVars[VAR_TEMP_KIDROOM]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_OUTSIDE", cJSON_CreateNumber(mVars[VAR_TEMP_OUTSIDE]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_DILNA", cJSON_CreateNumber(mVars[VAR_TEMP_DILNA]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_AKUPACK1", cJSON_CreateNumber(mVars[VAR_TEMP_AKUPACK1]));

cJSON_AddItemToObject(Uha, "VAR_SHUNT_PCK1_CURRENT_A100", cJSON_CreateNumber(mVars[VAR_SHUNT_PCK1_CURRENT_A100]));
cJSON_AddItemToObject(Uha, "VAR_SHUNT_PCK2_CURRENT_A100", cJSON_CreateNumber(mVars[VAR_SHUNT_PCK2_CURRENT_A100]));

cJSON_AddItemToObject(Uha, "VAR_BMS1_SOC", cJSON_CreateNumber(mVars[VAR_BMS1_SOC]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CURRENT_A10", cJSON_CreateNumber(mVars[VAR_BMS1_CURRENT_A10]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_VOLTAGE_V10", cJSON_CreateNumber(mVars[VAR_BMS1_VOLTAGE_V10]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_ENERGY_STORED_WH", cJSON_CreateNumber(mVars[VAR_BMS1_ENERGY_STORED_WH]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_TODAY_ENERGY_WH", cJSON_CreateNumber(mVars[VAR_BMS1_TODAY_ENERGY_WH]));

cJSON_AddItemToObject(Uha, "VAR_BMS2_SOC", cJSON_CreateNumber(mVars[VAR_BMS2_SOC]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CURRENT_A10", cJSON_CreateNumber(mVars[VAR_BMS2_CURRENT_A10]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_VOLTAGE_V10", cJSON_CreateNumber(mVars[VAR_BMS2_VOLTAGE_V10]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_ENERGY_STORED_WH", cJSON_CreateNumber(mVars[VAR_BMS2_ENERGY_STORED_WH]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_TODAY_ENERGY_WH", cJSON_CreateNumber(mVars[VAR_BMS2_TODAY_ENERGY_WH]));

cJSON_AddItemToObject(Uha, "VAR_MPPT_BAT_CURRENT_A10", cJSON_CreateNumber(mVars[VAR_MPPT_BAT_CURRENT_A10]));
cJSON_AddItemToObject(Uha, "VAR_MPPT_BAT_VOLTAGE_V100", cJSON_CreateNumber(mVars[VAR_MPPT_BAT_VOLTAGE_V100]));
cJSON_AddItemToObject(Uha, "VAR_MPPT_YIELD_TODAY_10WH", cJSON_CreateNumber(mVars[VAR_MPPT_YIELD_TODAY_10WH]));
cJSON_AddItemToObject(Uha, "VAR_MPPT_MAX_TODAY_W", cJSON_CreateNumber(mVars[VAR_MPPT_MAX_TODAY_W]));
cJSON_AddItemToObject(Uha, "VAR_MPPT_SOLAR_POWER_W", cJSON_CreateNumber(mVars[VAR_MPPT_SOLAR_POWER_W]));
cJSON_AddItemToObject(Uha, "VAR_MPPT_SOLAR_VOLTAGE_V100", cJSON_CreateNumber(mVars[VAR_MPPT_SOLAR_VOLTAGE_V100]));
cJSON_AddItemToObject(Uha, "VAR_MPPT_SOLAR_CURRENT_A10", cJSON_CreateNumber(mVars[VAR_MPPT_SOLAR_CURRENT_A10]));
cJSON_AddItemToObject(Uha, "VAR_MPPT_SOLAR_MAX_VOLTAGE_V100", cJSON_CreateNumber(mVars[VAR_MPPT_SOLAR_MAX_VOLTAGE_V100]));
cJSON_AddItemToObject(Uha, "VAR_MPPT_MAX_BAT_CURRENT_A10", cJSON_CreateNumber(mVars[VAR_MPPT_MAX_BAT_CURRENT_A10]));
cJSON_AddItemToObject(Uha, "VAR_MPPT_ENERGY_TODAY_WH", cJSON_CreateNumber(mVars[VAR_MPPT_ENERGY_TODAY_WH]));


cJSON_AddItemToObject(Uha, "VAR_AXPERT_TEMP_C", cJSON_CreateNumber(mVars[VAR_AXPERT_TEMP_C]));
cJSON_AddItemToObject(Uha, "VAR_AXPERT_AC_POWER_W", cJSON_CreateNumber(mVars[VAR_AXPERT_AC_POWER_W]));
//cJSON_AddItemToObject(Uha, "VAR_AXPERT_BAT_CHARGING_A", cJSON_CreateNumber(mVars[VAR_AXPERT_BAT_CHARGING_A]));
//cJSON_AddItemToObject(Uha, "VAR_AXPERT_BAT_DISCHARGING_A", cJSON_CreateNumber(mVars[VAR_AXPERT_BAT_DISCHARGING_A]));
cJSON_AddItemToObject(Uha, "VAR_AXPERT_BAT_VOLTAGE_V10", cJSON_CreateNumber(mVars[VAR_AXPERT_BAT_VOLTAGE_V10]));
cJSON_AddItemToObject(Uha, "VAR_AXPERT_PVS1_W", cJSON_CreateNumber(mVars[VAR_AXPERT_PVS1_W]));
cJSON_AddItemToObject(Uha, "VAR_AXPERT_PVS1_V10", cJSON_CreateNumber(mVars[VAR_AXPERT_PVS1_V10]));
cJSON_AddItemToObject(Uha, "VAR_AXPERT_PVS1_A10", cJSON_CreateNumber(mVars[VAR_AXPERT_PVS1_A10]));
cJSON_AddItemToObject(Uha, "VAR_AXPERT_PVS2_W", cJSON_CreateNumber(mVars[VAR_AXPERT_PVS2_W]));
cJSON_AddItemToObject(Uha, "VAR_AXPERT_PVS2_V10", cJSON_CreateNumber(mVars[VAR_AXPERT_PVS2_V10]));
cJSON_AddItemToObject(Uha, "VAR_AXPERT_PVS2_A10", cJSON_CreateNumber(mVars[VAR_AXPERT_PVS2_A10]));

cJSON_AddItemToObject(Uha, "VAR_AXPERT_BAT_POWER_W", cJSON_CreateNumber(mVars[VAR_AXPERT_BAT_POWER_W]));
cJSON_AddItemToObject(Uha, "VAR_AXPERT_BAT_CURRENT_A", cJSON_CreateNumber(mVars[VAR_AXPERT_BAT_CURRENT_A]));
cJSON_AddItemToObject(Uha, "VAR_AXPERT_SOLAR_W", cJSON_CreateNumber(mVars[VAR_AXPERT_SOLAR_W]));
cJSON_AddItemToObject(Uha, "VAR_AXPERT_ENERGY_TODAY_WH", cJSON_CreateNumber(mVars[VAR_AXPERT_ENERGY_TODAY_WH]));
cJSON_AddItemToObject(Uha, "VAR_AXPERT_LOAD_W", cJSON_CreateNumber(mVars[VAR_AXPERT_LOAD_W]));
//cJSON_AddItemToObject(Uha, "VAR_AXPERT_DISCHARGING_W", cJSON_CreateNumber(mVars[VAR_AXPERT_DISCHARGING_W]));


cJSON_AddItemToObject(Uha, "VAR_TEMP_RECU_FC", cJSON_CreateNumber(mVars[VAR_TEMP_RECU_FC]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_RECU_FH", cJSON_CreateNumber(mVars[VAR_TEMP_RECU_FH]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_RECU_WH", cJSON_CreateNumber(mVars[VAR_TEMP_RECU_WH]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_RECU_WC", cJSON_CreateNumber(mVars[VAR_TEMP_RECU_WC]));
cJSON_AddItemToObject(Uha, "VAR_RH_RECU_FH", cJSON_CreateNumber(mVars[VAR_RH_RECU_FH]));
cJSON_AddItemToObject(Uha, "VAR_RH_RECU_WH", cJSON_CreateNumber(mVars[VAR_RH_RECU_WH]));
cJSON_AddItemToObject(Uha, "VAR_CO2_RECU", cJSON_CreateNumber(mVars[VAR_CO2_RECU]));
cJSON_AddItemToObject(Uha, "VAR_DP_RECU_F", cJSON_CreateNumber(mVars[VAR_DP_RECU_F]));
cJSON_AddItemToObject(Uha, "VAR_DP_RECU_W", cJSON_CreateNumber(mVars[VAR_DP_RECU_W]));
cJSON_AddItemToObject(Uha, "VAR_RECU_FAN_F", cJSON_CreateNumber(mVars[VAR_RECU_FAN_F]));
cJSON_AddItemToObject(Uha, "VAR_RECU_FAN_W", cJSON_CreateNumber(mVars[VAR_RECU_FAN_W]));
cJSON_AddItemToObject(Uha, "VAR_CURR_RECU_A", cJSON_CreateNumber(mVars[VAR_CURR_RECU_A]));

cJSON_AddItemToObject(Uha, "VAR_STRG1_SOC", cJSON_CreateNumber(mVars[VAR_STRG1_SOC]));
cJSON_AddItemToObject(Uha, "VAR_STRG1_POWER_W", cJSON_CreateNumber(mVars[VAR_STRG1_POWER_W]));
cJSON_AddItemToObject(Uha, "VAR_STRG1_CURRENT_A10", cJSON_CreateNumber(mVars[VAR_STRG1_CURRENT_A10]));
cJSON_AddItemToObject(Uha, "VAR_STRG1_ENERGY_WH", cJSON_CreateNumber(mVars[VAR_STRG1_ENERGY_WH]));
cJSON_AddItemToObject(Uha, "VAR_STRG1_OPT_CHARGING_A", cJSON_CreateNumber(mVars[VAR_STRG1_OPT_CHARGING_A]));
cJSON_AddItemToObject(Uha, "VAR_STRG1_CAPACITY_AH", cJSON_CreateNumber(mVars[VAR_STRG1_CAPACITY_AH]));
cJSON_AddItemToObject(Uha, "VAR_STRG1_BALANCED_TODAY", cJSON_CreateNumber(mVars[VAR_STRG1_BALANCED_TODAY]));
cJSON_AddItemToObject(Uha, "VAR_STRG1_VOLTAGE_V10", cJSON_CreateNumber(mVars[VAR_STRG1_VOLTAGE_V10]));
cJSON_AddItemToObject(Uha, "VAR_LLOAD1_POWER_W", cJSON_CreateNumber(mVars[VAR_LLOAD1_POWER_W]));
cJSON_AddItemToObject(Uha, "VAR_LLOAD1_CONS_WH", cJSON_CreateNumber(mVars[VAR_LLOAD1_CONS_WH]));
cJSON_AddItemToObject(Uha, "VAR_LPV1_POWER_W", cJSON_CreateNumber(mVars[VAR_LPV1_POWER_W]));
cJSON_AddItemToObject(Uha, "VAR_LPV1_PROD_WH", cJSON_CreateNumber(mVars[VAR_LPV1_PROD_WH]));
/*cJSON_AddItemToObject(Uha, "VAR_LPV1_S1_POWER_W", cJSON_CreateNumber(mVars[VAR_LPV1_S1_POWER_W]));
cJSON_AddItemToObject(Uha, "VAR_LPV1_S1_CURRENT_A10", cJSON_CreateNumber(mVars[VAR_LPV1_S1_CURRENT_A10]));
cJSON_AddItemToObject(Uha, "VAR_LPV1_S1_VOLTAGE_V", cJSON_CreateNumber(mVars[VAR_LPV1_S1_VOLTAGE_V]));
cJSON_AddItemToObject(Uha, "VAR_LPV1_S2_POWER_W", cJSON_CreateNumber(mVars[VAR_LPV1_S2_POWER_W]));
cJSON_AddItemToObject(Uha, "VAR_LPV1_S2_CURRENT_A10", cJSON_CreateNumber(mVars[VAR_LPV1_S2_CURRENT_A10]));
cJSON_AddItemToObject(Uha, "VAR_LPV1_S2_VOLTAGE_V", cJSON_CreateNumber(mVars[VAR_LPV1_S2_VOLTAGE_V]));*/


cJSON_AddItemToObject(Uha, "VAR_STRG2_SOC", cJSON_CreateNumber(mVars[VAR_STRG2_SOC]));
cJSON_AddItemToObject(Uha, "VAR_STRG2_POWER_W", cJSON_CreateNumber(mVars[VAR_STRG2_POWER_W]));
cJSON_AddItemToObject(Uha, "VAR_STRG2_CURRENT_A10", cJSON_CreateNumber(mVars[VAR_STRG2_CURRENT_A10]));
cJSON_AddItemToObject(Uha, "VAR_STRG2_ENERGY_WH", cJSON_CreateNumber(mVars[VAR_STRG2_ENERGY_WH]));
cJSON_AddItemToObject(Uha, "VAR_STRG2_OPT_CHARGING_A", cJSON_CreateNumber(mVars[VAR_STRG2_OPT_CHARGING_A]));
cJSON_AddItemToObject(Uha, "VAR_STRG2_CAPACITY_AH", cJSON_CreateNumber(mVars[VAR_STRG2_CAPACITY_AH]));
cJSON_AddItemToObject(Uha, "VAR_STRG2_BALANCED_TODAY", cJSON_CreateNumber(mVars[VAR_STRG2_BALANCED_TODAY]));
cJSON_AddItemToObject(Uha, "VAR_STRG2_VOLTAGE_V10", cJSON_CreateNumber(mVars[VAR_STRG2_VOLTAGE_V10]));
cJSON_AddItemToObject(Uha, "VAR_LLOAD2_POWER_W", cJSON_CreateNumber(mVars[VAR_LLOAD2_POWER_W]));
cJSON_AddItemToObject(Uha, "VAR_LLOAD2_CONS_WH", cJSON_CreateNumber(mVars[VAR_LLOAD2_CONS_WH]));
cJSON_AddItemToObject(Uha, "VAR_LPV2_POWER_W", cJSON_CreateNumber(mVars[VAR_LPV2_POWER_W]));
cJSON_AddItemToObject(Uha, "VAR_LPV2_PROD_WH", cJSON_CreateNumber(mVars[VAR_LPV2_PROD_WH]));


/*cJSON_AddItemToObject(Uha, "VAR_LPV2_S1_POWER_W", cJSON_CreateNumber(mVars[VAR_LPV2_S1_POWER_W]));
cJSON_AddItemToObject(Uha, "VAR_LPV2_S1_CURRENT_A20", cJSON_CreateNumber(mVars[VAR_LPV2_S1_CURRENT_A20]));
cJSON_AddItemToObject(Uha, "VAR_LPV2_S1_VOLTAGE_V", cJSON_CreateNumber(mVars[VAR_LPV2_S1_VOLTAGE_V]));
cJSON_AddItemToObject(Uha, "VAR_LPV2_S2_POWER_W", cJSON_CreateNumber(mVars[VAR_LPV2_S2_POWER_W]));
cJSON_AddItemToObject(Uha, "VAR_LPV2_S2_CURRENT_A20", cJSON_CreateNumber(mVars[VAR_LPV2_S2_CURRENT_A20]));
cJSON_AddItemToObject(Uha, "VAR_LPV2_S2_VOLTAGE_V", cJSON_CreateNumber(mVars[VAR_LPV2_S2_VOLTAGE_V]));*/


/*cJSON_AddItemToObject(Uha, "VAR_LVDC_VDIFF_V100", cJSON_CreateNumber(mVars[VAR_LVDC_VDIFF_V100]));
cJSON_AddItemToObject(Uha, "VAR_LVDC_VDIFF_MAX", cJSON_CreateNumber(mVars[VAR_LVDC_VDIFF_MAX]));
cJSON_AddItemToObject(Uha, "VAR_LVDC_CURRENT_A", cJSON_CreateNumber(mVars[VAR_LVDC_CURRENT_A]));
cJSON_AddItemToObject(Uha, "VAR_LVDC_LOSS_W", cJSON_CreateNumber(mVars[VAR_LVDC_LOSS_W]));
cJSON_AddItemToObject(Uha, "VAR_LVDC_LOSS_CONS_WH", cJSON_CreateNumber(mVars[VAR_LVDC_LOSS_CONS_WH]));*/

cJSON_AddItemToObject(Uha, "VAR_METEO_WIND_BURST", cJSON_CreateNumber(mVars[VAR_METEO_WIND_BURST]));
cJSON_AddItemToObject(Uha, "VAR_METEO_WIND_AVG", cJSON_CreateNumber(mVars[VAR_METEO_WIND_AVG]));
cJSON_AddItemToObject(Uha, "VAR_METEO_WIND_POW", cJSON_CreateNumber(mVars[VAR_METEO_WIND_POW]));
cJSON_AddItemToObject(Uha, "VAR_METEO_WIND_ENERGY", cJSON_CreateNumber(mVars[VAR_METEO_WIND_ENERGY]));


cJSON_AddItemToObject(Uha, "VAR_TEMP_TECHM_BOARD", cJSON_CreateNumber(mVars[VAR_TEMP_TECHM_BOARD]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_IOBOARD_D", cJSON_CreateNumber(mVars[VAR_TEMP_IOBOARD_D]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_IOBOARD_U", cJSON_CreateNumber(mVars[VAR_TEMP_IOBOARD_U]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_ELECON_BOARD", cJSON_CreateNumber(mVars[VAR_TEMP_ELECON_BOARD]));
cJSON_AddItemToObject(Uha, "VAR_TEMP_BOARD_ELECON_D", cJSON_CreateNumber(mVars[VAR_TEMP_BOARD_ELECON_D]));

cJSON_AddItemToObject(Uha, "VAR_FLOW_COLD", cJSON_CreateNumber(mVars[VAR_FLOW_COLD]));
cJSON_AddItemToObject(Uha, "VAR_FLOW_HOT", cJSON_CreateNumber(mVars[VAR_FLOW_HOT]));
cJSON_AddItemToObject(Uha, "VAR_CONS_COLD", cJSON_CreateNumber(mVars[VAR_CONS_COLD]));
cJSON_AddItemToObject(Uha, "VAR_CONS_HOT", cJSON_CreateNumber(mVars[VAR_CONS_HOT]));

cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL1_MV", cJSON_CreateNumber(mVars[VAR_BMS1_CELL1_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL2_MV", cJSON_CreateNumber(mVars[VAR_BMS1_CELL2_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL3_MV", cJSON_CreateNumber(mVars[VAR_BMS1_CELL3_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL4_MV", cJSON_CreateNumber(mVars[VAR_BMS1_CELL4_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL5_MV", cJSON_CreateNumber(mVars[VAR_BMS1_CELL5_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL6_MV", cJSON_CreateNumber(mVars[VAR_BMS1_CELL6_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL7_MV", cJSON_CreateNumber(mVars[VAR_BMS1_CELL7_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL8_MV", cJSON_CreateNumber(mVars[VAR_BMS1_CELL8_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL9_MV", cJSON_CreateNumber(mVars[VAR_BMS1_CELL9_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL10_MV", cJSON_CreateNumber(mVars[VAR_BMS1_CELL10_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL11_MV", cJSON_CreateNumber(mVars[VAR_BMS1_CELL11_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL12_MV", cJSON_CreateNumber(mVars[VAR_BMS1_CELL12_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL13_MV", cJSON_CreateNumber(mVars[VAR_BMS1_CELL13_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL14_MV", cJSON_CreateNumber(mVars[VAR_BMS1_CELL14_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL15_MV", cJSON_CreateNumber(mVars[VAR_BMS1_CELL15_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL16_MV", cJSON_CreateNumber(mVars[VAR_BMS1_CELL16_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL1_C", cJSON_CreateNumber(mVars[VAR_BMS1_CELL1_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL2_C", cJSON_CreateNumber(mVars[VAR_BMS1_CELL2_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL3_C", cJSON_CreateNumber(mVars[VAR_BMS1_CELL3_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL4_C", cJSON_CreateNumber(mVars[VAR_BMS1_CELL4_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL5_C", cJSON_CreateNumber(mVars[VAR_BMS1_CELL5_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL6_C", cJSON_CreateNumber(mVars[VAR_BMS1_CELL6_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL7_C", cJSON_CreateNumber(mVars[VAR_BMS1_CELL7_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL8_C", cJSON_CreateNumber(mVars[VAR_BMS1_CELL8_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL9_C", cJSON_CreateNumber(mVars[VAR_BMS1_CELL9_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL10_C", cJSON_CreateNumber(mVars[VAR_BMS1_CELL10_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL11_C", cJSON_CreateNumber(mVars[VAR_BMS1_CELL11_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL12_C", cJSON_CreateNumber(mVars[VAR_BMS1_CELL12_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL13_C", cJSON_CreateNumber(mVars[VAR_BMS1_CELL13_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL14_C", cJSON_CreateNumber(mVars[VAR_BMS1_CELL14_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL15_C", cJSON_CreateNumber(mVars[VAR_BMS1_CELL15_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS1_CELL16_C", cJSON_CreateNumber(mVars[VAR_BMS1_CELL16_C]));

cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL1_MV", cJSON_CreateNumber(mVars[VAR_BMS2_CELL1_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL2_MV", cJSON_CreateNumber(mVars[VAR_BMS2_CELL2_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL3_MV", cJSON_CreateNumber(mVars[VAR_BMS2_CELL3_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL4_MV", cJSON_CreateNumber(mVars[VAR_BMS2_CELL4_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL5_MV", cJSON_CreateNumber(mVars[VAR_BMS2_CELL5_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL6_MV", cJSON_CreateNumber(mVars[VAR_BMS2_CELL6_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL7_MV", cJSON_CreateNumber(mVars[VAR_BMS2_CELL7_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL8_MV", cJSON_CreateNumber(mVars[VAR_BMS2_CELL8_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL9_MV", cJSON_CreateNumber(mVars[VAR_BMS2_CELL9_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL10_MV", cJSON_CreateNumber(mVars[VAR_BMS2_CELL10_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL11_MV", cJSON_CreateNumber(mVars[VAR_BMS2_CELL11_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL12_MV", cJSON_CreateNumber(mVars[VAR_BMS2_CELL12_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL13_MV", cJSON_CreateNumber(mVars[VAR_BMS2_CELL13_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL14_MV", cJSON_CreateNumber(mVars[VAR_BMS2_CELL14_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL15_MV", cJSON_CreateNumber(mVars[VAR_BMS2_CELL15_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL16_MV", cJSON_CreateNumber(mVars[VAR_BMS2_CELL16_MV]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL1_C", cJSON_CreateNumber(mVars[VAR_BMS2_CELL1_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL2_C", cJSON_CreateNumber(mVars[VAR_BMS2_CELL2_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL3_C", cJSON_CreateNumber(mVars[VAR_BMS2_CELL3_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL4_C", cJSON_CreateNumber(mVars[VAR_BMS2_CELL4_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL5_C", cJSON_CreateNumber(mVars[VAR_BMS2_CELL5_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL6_C", cJSON_CreateNumber(mVars[VAR_BMS2_CELL6_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL7_C", cJSON_CreateNumber(mVars[VAR_BMS2_CELL7_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL8_C", cJSON_CreateNumber(mVars[VAR_BMS2_CELL8_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL9_C", cJSON_CreateNumber(mVars[VAR_BMS2_CELL9_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL10_C", cJSON_CreateNumber(mVars[VAR_BMS2_CELL10_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL11_C", cJSON_CreateNumber(mVars[VAR_BMS2_CELL11_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL12_C", cJSON_CreateNumber(mVars[VAR_BMS2_CELL12_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL13_C", cJSON_CreateNumber(mVars[VAR_BMS2_CELL13_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL14_C", cJSON_CreateNumber(mVars[VAR_BMS2_CELL14_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL15_C", cJSON_CreateNumber(mVars[VAR_BMS2_CELL15_C]));
cJSON_AddItemToObject(Uha, "VAR_BMS2_CELL16_C", cJSON_CreateNumber(mVars[VAR_BMS2_CELL16_C]));





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