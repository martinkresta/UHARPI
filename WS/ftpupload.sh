#!/bin/sh

HOST='sonami.cz'
USER='sonami.cz'
PASSWD='cas928FM'
FILEtoPut='/home/pi/Web/bms.json' 
Destination='bms.json'

echo $HOST

ftp -n $HOST <<END_SCRIPT 
quote USER $USER
quote PASS $PASSWD

passive

put $FILEtoPut $Destination

quit
echo "done"
END_SCRIPT
exit 0



