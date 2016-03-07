#!/bin/bash

# This script is intended to be run regularly by crond via discoroot/etc/cron.d/internal_smoketest
# After a reasonable grace period it checks if the machine is healthy and calls mark_unhealthy.sh if
# it is not in a good state.
#
# There are two health checks. There is a cheap call to disco-booted which will return a good state
# if the machine at some point the smoketest.unit.sh script ran successfully after all other boot
# scripts had a chance to run. The second health check is a call to smoketest.unit.sh which performs
# a hostclass specific health check. If either one fails we immediately call the mark unhealthy script.

RUN_INTERVAL=300 # Time in seconds between exexution of this script.
DISCO_SMOKE_UNIT="/opt/wgen/bin/smoketest.unit.sh"
source "/etc/disco-boot.conf" # for REASONABLE_*_TIME and MAINTENANCE_MODE_FILE
source "/opt/wgen/bin/user-data.sh"
source "/opt/wgen/bin/get_status.sh" # for get_hostclass

HOSTCLASS=$(get_hostclass)
UPTIME_SECONDS=$(cat /proc/uptime | grep -o "^[0-9]*")
if [ "$smoketest_termination" != "0" ]; then
    MARK_UNHEALTHY="/opt/wgen/bin/mark_unhealthy.sh"
else
    echo "Disabling marking hosts as unhealthy"
    MARK_UNHEALTHY="/bin/echo"
fi

if [[ $UPTIME_SECONDS -lt $REASONABLE_BOOT_TIME ]] ; then
    echo "We have not been running long enough to do a proper status check."
    exit 0
fi

/sbin/service disco-booted status
if [[ "$?" != "0" ]] ; then
    $MARK_UNHEALTHY "Failed to boot in a reasonable time ($UPTIME_SECONDS >= $REASONABLE_BOOT_TIME)"
    exit 1
fi

if [[ -e $MAINTENANCE_MODE_FILE ]] ; then
    NOW=$(date -u "+%s")
    THEN=$(date --date="$(cat $MAINTENANCE_MODE_FILE)" -u "+%s")
    if [[ $(( $NOW - $THEN )) -gt $REASONABLE_MAINTENANCE_TIME ]] ; then
        echo "System is unhealthy -- too long in maintenance mode"
        $MARK_UNHEALTHY "System left in maintenance mode more than $REASONABLE_MAINTENANCE_TIME seconds"
        exit 1
    else
        echo "System in maintenance mode for $(( $NOW - $THEN )) seconds"
        exit 0
    fi
fi

if [[ -x $DISCO_SMOKE_UNIT ]] ; then
    #To spread out test runs sleep random amount of time up to execution interval
    sleep "$((RANDOM%RUN_INTERVAL))"
    $DISCO_SMOKE_UNIT
    if [[ "$?" != "0" ]] ; then
        if [[ -e $MAINTENANCE_MODE_FILE ]] ; then
            echo "System is in maintenance mode -- failed smoke test but NOT marking unhealthy."
        else
            echo "System is unhealthy -- failed smoke test"
            $MARK_UNHEALTHY "Smoke test failed"
            exit 1
        fi
    fi
else
    echo "No smoketest script, assuming system is still healthy"
fi

exit 0
