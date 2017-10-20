#!/usr/bin/bash
username=one
password=potrzebie
serveraddr='localhost'
serverport=2001
progname=example.muf

helpmessage=\
"Usage: progloader -filename [-progname <name>] [-username <name>] [-password <password>] [-serverport <port>] [-serveraddr <addr>] \n
Purpose: loads a program into a muck server from a local file\n
If progname isn't specified, then the script looks for a line in the source file matching '((( filename: <name> )))' and sets the destination program to that.\n
The program does assume that the server is using telnet, and does not allow for alternative protocols at this point."
echo "$serveraddr"

# echo $#
for ((n=0;n<=$#;n+=1))
do
	# echo $n
	extrainc=1
	currarg="${!n}"
	nextindex=$((n+1))
	nextarg="${!nextindex}"
	# echo $currarg
	if [[ $currarg = "-port" ]]
	then
		serverport = $nextarg
	elif [[ $currarg = "-serveraddr" ]] ; then
		serveraddr=$nextarg
	elif [[ $currarg = "-progname" ]]; then
		progname=$nextarg
	elif [[ $currarg = "-username" ]]; then
		username=$nextarg
	elif [[ $currarg = "-filename" ]]; then
		filename=$nextarg
        progname=`grep $filename -Pe "\(\(\( filename: .+ \)\)\)" | cut -f 3 -d' '`
	elif [[ $currarg = "-password" ]]; then
		password=$nextarg
    elif [[ $currarg = '-help' ]]; then
        echo -e $helpmessage
        exit
	else
		extrainc=0
	fi
	if [[ $extrainc = 1 ]] 
	then
		n=$((n + 1))
	fi
done
echo $username $password $serveraddr $serverport $progname $filename
read
echo -e "connect $username $password\n">temp.txt
echo -e "@prog $progname\n1 1000 d\ni\n">>temp.txt
cat $filename >> temp.txt
echo -e '\n.\nc\nq\n' >> temp.txt
bash slowprint.sh temp.txt | telnet $serveraddr $serverport
rm temp.txt