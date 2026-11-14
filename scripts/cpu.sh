#!/usr/bin/env bash
set -euo pipefail

read -r _ user1 nice1 system1 idle1 iowait1 irq1 softirq1 steal1 _ < /proc/stat
sleep 1
read -r _ user2 nice2 system2 idle2 iowait2 irq2 softirq2 steal2 _ < /proc/stat

total1=$((user1 + nice1 + system1 + idle1 + iowait1 + irq1 + softirq1 + steal1))
total2=$((user2 + nice2 + system2 + idle2 + iowait2 + irq2 + softirq2 + steal2))
total_del=$((total2 - total1))
idle_del=$(((idle2 + iowait2) - (idle1 + iowait1)))

if (( total_del == 0 )); then
    echo 0
else
    echo $(( ((total_del - idle_del) * 100 / total_del) ))
fi