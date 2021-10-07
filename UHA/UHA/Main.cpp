#include <wiringPi.h>
#include <wiringSerial.h>
#include <iostream>
#include "UHA.h"
#include "time.h"
using namespace std;


#define UHA_PERIOD			1000

#define ONE_SECOND			1000



int main()
{
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

	time_t lastUnixTime = 0;
	time_t unixTime = 0;
	struct tm lastTime;
	
	
	wiringPiSetupSys();
	wiringPiSetupGpio();

	uha.UHA_Init();
	


	while (1)
	{

		if (millis() > lastUhaUpdate + UHA_PERIOD )
		{
			lastUhaUpdate = millis();
			// Send values to UHA 
			cout << "Sending data to UHA:"  << lastUhaUpdate << endl;
			uha.UHA_SendValues();


			// check real time
			time(&unixTime);
			struct tm* now = localtime(&unixTime);
			if (now->tm_min != lastTime.tm_min)
			{
				// every minute
				uha.UHA_SendRTC();
			}
			if (now->tm_hour != lastTime.tm_hour)
			{
				// every hour
				uha.UHA_SendRTC();
			}
			if (now->tm_mday != lastTime.tm_mday)
			{
				// every day
			}

			lastTime = *now;

		}

		uha.UHA_ProcessMessage();
		
	}
	uha.UHA_DeInit();
	return 0;
}






