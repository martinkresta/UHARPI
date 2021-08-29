#include <wiringPi.h>
#include <wiringSerial.h>
#include <iostream>
#include "BMS.h"
using namespace std;

#define BMS_PORT	"/dev/ttyACM0"



void PrintData(BMS bms)
{
	cout << "******************************************" << endl;
	cout << "BATTERY PACK STATUS" << endl << endl;

	cout << "Voltage: 		" << bms.TotalVoltageV() << "V" <<endl;
	cout << "SOC: 			" << bms.SOC() << "%" <<endl;
	cout << "Charging:		" << bms.ChargingA() << "A" <<endl;
	cout << "Discharging: 		" << bms.DischargingA() << "A" <<endl;
	cout << "Energy:	 		" << bms.AvailableEnergyKwh() << "kWh" <<endl;
	
	
	cout<< endl << endl << "Cells:" << endl;
	cout<< "#	Voltage[V]	Temperature[C]" <<endl;
	
	int i;
	for (i=0;i<NUM_OF_CELLS;i++)
	{
		cout<< (i+1) << "	" << bms.Cell(i).Voltage << "		" << bms.Cell(i).Temp << endl;
	}
}


int main()
{
	BMS bms;
	int sp;  // bms serial port handler
	int i;
	int recLength;
	char data[200];
	char input;
	
	wiringPiSetupGpio();
	
	sp = serialOpen(BMS_PORT, 57600);
	

	serialPutchar(sp,0x11);
	delay(1000);
	recLength = serialDataAvail(sp);
	if (recLength > 4)
	{
		for (i=0;i<recLength;i++)
		{
			data[i] = serialGetchar(sp);
		}
		bms.BMS_SetPackInfo(data);
	}
	serialFlush(sp);

	while (1)
	{
		serialPutchar(sp,0x12);	
		delay(1000);
		recLength = serialDataAvail(sp);
		if (recLength > 4)
		{
			for (i=0;i<recLength;i++)
			{
				data[i] = serialGetchar(sp);
			}
		}
		serialFlush(sp);
		bms.BMS_SetLiveData(data);
		

		serialPutchar(sp,0x13);	
		delay(1000);
		recLength = serialDataAvail(sp);
		if (recLength > 4)
		{
			for (i=0;i<recLength;i++)
			{
				data[i] = serialGetchar(sp);
			}
		}
		serialFlush(sp);
		bms.BMS_SetCellData(data);
		
	  PrintData(bms);
		
    cout << "creating JSON.."  << endl;
    
		bms.CreateJson();
		delay(1000);	
		
	}
	serialClose(sp);
	return 0;
}






