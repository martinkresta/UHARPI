
#include <iostream>
#include "UHA.h"
#include "time.h"
using namespace std;


#define UHA_PERIOD			1000

#define ONE_SECOND			1000

long getTimeMs()
{
    struct timespec t;
    //clock_gettime(CLOCK_REALTIME, &t);
    clock_gettime(1, &t);
    return (long)t.tv_sec * 1000 + (long)t.tv_nsec/1000000;
}



int main()
{
	UHA uha;

	int LiveDataReading = 0;
	int CellDataReading = 0;
	float lastUhaUpdate = 0;

	time_t lastUnixTime = 0;
	time_t unixTime = 0;
	struct tm lastTime;

	uha.UHA_Init();
	


	while (1)
	{
		//cout << "TimeMS : "<< getTimeMs() << endl;
		if (getTimeMs() > lastUhaUpdate + UHA_PERIOD )
		{
			cout << "TimeMS : "<< getTimeMs() << endl;
			lastUhaUpdate = getTimeMs();

			uha.UHA_CreateUhaJson();
			uha.UHA_CreateBmsJson();

			// Send values to UHA 
			//	uha.UHA_SendValues();

			// check real time
			time(&unixTime);
			struct tm* now = localtime(&unixTime);
			if (now->tm_min != lastTime.tm_min)
			{
				// every minute
				cout << "Sending RTC" << endl;
				uha.UHA_SendRTC();
			}
			if (now->tm_hour != lastTime.tm_hour)
			{
				// every hour
			}
			if (now->tm_mday != lastTime.tm_mday)
			{
				// every day
			}

			lastTime = *now;

		}

		//cout << "Processing msgs" << endl;
		uha.UHA_ProcessMessage();
		//cout << "Messages processed" << endl;
		
	}
	uha.UHA_DeInit();
	return 0;
}






