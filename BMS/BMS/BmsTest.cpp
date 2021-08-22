#include <wiringPi.h>
#include <wiringSerial.h>
#include <iostream>
#include "BMS.h"
#include "UHA.h"
using namespace std;

#define BMS_PORT	"/dev/ttyACM0"

#define LIVE_DATA_PERIOD	4000
#define CELL_DATA_PERIOD	4000
#define READ_DELAY          1000

#define UHA_PERIOD			3000

// Prints BMS data to console
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
	UHA uha;
	int sp;  // bms serial port handler
	int i;
	int recLength;
	char data[200];
	char input;

	int lastLiveData = 0;
	int lastCellData = 2000;
	int LiveDataReading = 0;
	int CellDataReading = 0;
	int lastUhaUpdate = 0;
	
	wiringPiSetupSys();
	wiringPiSetupGpio();
	
	sp = serialOpen(BMS_PORT, 57600);

	uha.UHA_Init(&bms);
	

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
		// read live values from BMS
		if ((millis() > (lastLiveData + LIVE_DATA_PERIOD)) && !LiveDataReading)
		{
			lastLiveData = millis();
			serialPutchar(sp,0x12);	
			LiveDataReading = 1;
			cout << "Live data request."  << endl;
		}
		if ((millis() > (lastLiveData + READ_DELAY)) && LiveDataReading)
		{
			LiveDataReading = 0;
			recLength = serialDataAvail(sp);
			if (recLength > 4)
			{
				for (i=0;i<recLength;i++)
				{
					data[i] = serialGetchar(sp);
				}
				cout << "Live data processed"  << endl;
			}
			serialFlush(sp);
			bms.BMS_SetLiveData(data);
		}
		
		
		// read cell data from BMS
		if ((millis() > (lastCellData + LIVE_DATA_PERIOD)) && !CellDataReading)
		{
			lastCellData = millis();
			serialPutchar(sp,0x13);	
			CellDataReading = 1;
			cout << "Cell data request."  << endl;
		}
		if ((millis() > (lastCellData + READ_DELAY)) && CellDataReading)
		{
			CellDataReading = 0;
			recLength = serialDataAvail(sp);
			if (recLength > 4)
			{
				for (i=0;i<recLength;i++)
				{
					data[i] = serialGetchar(sp);
				}
				cout << "Cell data processed"  << endl;
			}
			serialFlush(sp);
			bms.BMS_SetCellData(data);


			// print data
			PrintData(bms);	
			bms.CreateJson();

		//	cout << "Sending data to UHA.."  << endl;
		//	uha.UHA_SendValues();
		}

		if (millis() > lastUhaUpdate + UHA_PERIOD )
		{
			lastUhaUpdate = millis();
			// Send values to UHA 
			cout << "Sending data to UHA.."  << endl;
			uha.UHA_SendValues();
		}

		uha.UHA_ProcessMessage();
		
	}
	uha.UHA_DeInit();
	serialClose(sp);
	return 0;
}






