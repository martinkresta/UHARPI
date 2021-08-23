#!/bin/sh
$HOST='sonami.cz'
$USER='sonami.cz'
$PASSWD='cas928FM'
$FILEtoPut='bms.json'

ftp -n $HOST <<END_SCRIPT
quote USER $USER
quote PASS $PASSWD

put $FILEtoPut

quit
END_SCRIPT
exit 0


