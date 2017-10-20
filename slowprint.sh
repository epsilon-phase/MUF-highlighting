first=1
while read -r line 
do
	echo $line
    if [[ first = 1 ]]; then
        sleep 0.5
        first=0
    else
        sleep 0.1
    fi
done < $1