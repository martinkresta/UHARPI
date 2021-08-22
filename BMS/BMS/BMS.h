
#ifndef BMS_H
#define BMS_H


#define NUM_OF_CELLS	16	
#define JSON_FULLPATH	"/home/pi/Web/bms.json"

struct sCell
{
  double Voltage;
  double Temp;
};

class BMS 
{
	// private variables
private:  

	int mNumOfCells;
    double mTotalVoltageV;
    double mMinCellVoltageV;
    double mMaxCellVoltageV;
    double mBalanceCellVoltageV;
    double mCapacityKwh;
    double mChargingA;
    double mDischargingA;
    int mSOC;
    double mTodayChargingKwh;
    double mTodayDischargingKwh;
    double mTotalChargingKwh;
    double mTotalDischargingKwh;
    double mAvailableEnergyKwh;
    
    sCell Cells[NUM_OF_CELLS];
    
// public getters
public:  
	int NumOfCells(){return mNumOfCells;}
    double TotalVoltageV(){return mTotalVoltageV;}
    double MinCellVoltageV(){return mMinCellVoltageV;}
    double MaxCellVoltageV(){return mMaxCellVoltageV;}
    double BalanceCellVoltageV(){return mBalanceCellVoltageV;}
    double CapacityKwh(){return mCapacityKwh;}
    double ChargingA(){return mChargingA;}
    double DischargingA(){return mDischargingA;}
    int SOC(){return mSOC;}
    double TodayChargingKwh(){return mTodayChargingKwh;}
    double TodayDischargingKwh(){return mTodayDischargingKwh;}
    double TotalChargingKwh(){return mTotalChargingKwh;}
    double TotalDischargingKwh(){return mTotalDischargingKwh;}
    double AvailableEnergyKwh(){return mAvailableEnergyKwh;}
    sCell Cell(int i);

//private methods
private:

	double Convert32ToDouble(char* data, int i);
	double Convert16ToDouble(char* data, int i);
	
// public methods
public:

    void BMS_SetPackInfo(char* data);
    void BMS_SetLiveData(char* data);
    void BMS_SetCellData(char* data);
    void CreateJson(void);

};


#endif // BMS_H
