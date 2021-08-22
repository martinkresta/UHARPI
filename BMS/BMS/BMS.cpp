

/// <summary>
/// Class for storing the data of the Battery pack received from BMS
/// </summary>
#include <stdio.h>
#include <iostream>
#include <time.h>
#include "BMS.h"
#include "cJSON.h"
using namespace std;


    sCell BMS::Cell(int i)
    {
      if (i < NUM_OF_CELLS)
      {
        return Cells[i];
      }
      return Cells[0];
    }

    /// Sets the pack info variables
    void BMS::BMS_SetPackInfo(char* data)
    {
      mCapacityKwh = Convert32ToDouble(data, 0);
      mMinCellVoltageV = Convert32ToDouble(data, 4);
      mMaxCellVoltageV = Convert32ToDouble(data, 8);
      mBalanceCellVoltageV = Convert32ToDouble(data, 12);
      mNumOfCells = data[16];
     // Cells = new sCell[NUM_OF_CELLS];
    }



    /// Sets the live data
    void BMS::BMS_SetLiveData(char* data)
    {
      mTotalVoltageV = Convert32ToDouble(data, 0);
      mChargingA = Convert32ToDouble(data, 4);
      mDischargingA = Convert32ToDouble(data, 8);
      mTodayChargingKwh = Convert32ToDouble(data, 12);
      mTodayDischargingKwh = Convert32ToDouble(data, 16);
      mAvailableEnergyKwh = Convert32ToDouble(data, 20);
      mTotalChargingKwh = Convert32ToDouble(data, 24) * 1000;
      mTotalDischargingKwh = Convert32ToDouble(data, 28) * 1000;
      mSOC = data[33];
    }


    /// Sets the data of all cells
    void BMS::BMS_SetCellData(char* data)
    {
      int i;
      for (i = 0; i < NUM_OF_CELLS; i++)
      {
        Cells[i].Voltage = Convert16ToDouble(data, i * 4);
        Cells[i].Temp = Convert16ToDouble(data, (i * 4) + 2) * 1000;
      }
    }


    double BMS::Convert32ToDouble(char* data, int i)
    {
      double res = 0;
      int tmp = (data[i] << 0)| (data[i+1] << 8)| (data[i+2] << 16)| (data[i+3] << 24);
      res = tmp / 1000.0;
      return res;
    }

    double BMS::Convert16ToDouble(char* data, int i)
    {
      double res = 0;
      short int tmp = (data[i] << 0) | (data[i + 1] << 8);
      res = tmp / 1000.0;
      return res;
    }
    
    
    // creates json file from the BMS object
void BMS::CreateJson(void)
{
  int i;
  double sum = 0;
  int AvgTempC = 0;

  // calculate data that are not directly received from BMS
  int SunPowerW = (int)(mChargingA * mTotalVoltageV);
  int SunPowerPct = (int)(SunPowerW / 1100) * 100;
  double BattCurrentA = (mChargingA - mDischargingA);
	int LoadPowerW = (int)(mDischargingA * mTotalVoltageV);	
	int LoadPowerPct = (int)(LoadPowerW / 3000) * 100;
	double TodayDiffKwh = (mTodayChargingKwh - mTodayDischargingKwh);

  int Time = (int)time(NULL);

  
  for (i=0;i<NUM_OF_CELLS-1;i++)
  {
    sum += Cells[i].Temp; 
  }	
  AvgTempC = (int)((sum/15.0)+0.5); 
  
  cJSON *Bms = cJSON_CreateObject();
  cJSON *PackInfo = cJSON_CreateObject();
  cJSON *LiveData = cJSON_CreateObject();
  cJSON *CellsJson = cJSON_CreateArray();
  
  
  cJSON_AddItemToObject(PackInfo, "CapacityKwh", cJSON_CreateNumber(mCapacityKwh));
  cJSON_AddItemToObject(PackInfo, "MinCellVoltageV", cJSON_CreateNumber(mMinCellVoltageV));
  cJSON_AddItemToObject(PackInfo, "MaxCellVoltageV", cJSON_CreateNumber(mMaxCellVoltageV));
  cJSON_AddItemToObject(PackInfo, "BalanceCellVoltageV", cJSON_CreateNumber(mBalanceCellVoltageV));
  cJSON_AddItemToObject(PackInfo, "NumOfCells", cJSON_CreateNumber(mNumOfCells));
  cJSON_AddItemToObject(Bms, "BatteryPackInfo", PackInfo);
  
  cJSON_AddItemToObject(LiveData, "SunPowerW", cJSON_CreateNumber(SunPowerW));
  cJSON_AddItemToObject(LiveData, "TotalVoltageV", cJSON_CreateNumber(mTotalVoltageV));
  cJSON_AddItemToObject(LiveData, "ChargingA", cJSON_CreateNumber(mChargingA));
  cJSON_AddItemToObject(LiveData, "DischargingA", cJSON_CreateNumber(mDischargingA));
  cJSON_AddItemToObject(LiveData, "TodayChargingKwh", cJSON_CreateNumber(mTodayChargingKwh));
  cJSON_AddItemToObject(LiveData, "TodayDischargingKwh", cJSON_CreateNumber(mTodayDischargingKwh));
  cJSON_AddItemToObject(LiveData, "AvailableEnergyKwh", cJSON_CreateNumber(mAvailableEnergyKwh));
  cJSON_AddItemToObject(LiveData, "TotalChargingKwh", cJSON_CreateNumber(mTotalChargingKwh));
  cJSON_AddItemToObject(LiveData, "TotalDischargingKwh", cJSON_CreateNumber(mTotalDischargingKwh));
  cJSON_AddItemToObject(LiveData, "SocPct", cJSON_CreateNumber(mSOC));
  cJSON_AddItemToObject(LiveData, "TemperatureC", cJSON_CreateNumber(AvgTempC));
  cJSON_AddItemToObject(LiveData, "SunPowerPct", cJSON_CreateNumber(SunPowerPct));
  cJSON_AddItemToObject(LiveData, "BattCurrentA", cJSON_CreateNumber(BattCurrentA));
  cJSON_AddItemToObject(LiveData, "LoadPowerW", cJSON_CreateNumber(LoadPowerW));
  cJSON_AddItemToObject(LiveData, "LoadPowerPct", cJSON_CreateNumber(LoadPowerPct));
  cJSON_AddItemToObject(LiveData, "TodayDiffKwh", cJSON_CreateNumber(TodayDiffKwh));
  cJSON_AddItemToObject(LiveData, "UnixTime", cJSON_CreateNumber(Time));

  cJSON_AddItemToObject(Bms,"LiveData", LiveData);
  
  for (i=0;i<NUM_OF_CELLS;i++)
  {
    cJSON *Cell = cJSON_CreateObject();
    cJSON_AddItemToObject(Cell, "VoltageV", cJSON_CreateNumber(Cells[i].Voltage));
    cJSON_AddItemToObject(Cell, "TemperatureC", cJSON_CreateNumber(Cells[i].Temp));
    cJSON_AddItemToArray(CellsJson, Cell);
  }	

  
  cJSON_AddItemToObject(Bms,"Cells",CellsJson);
  
  cout << "saving file BMS.json"  << endl;
  
	FILE* fh = fopen(JSON_FULLPATH, "w");
	fprintf(fh, cJSON_Print(Bms));
	fclose(fh);
  cJSON_Delete(Bms);
}

