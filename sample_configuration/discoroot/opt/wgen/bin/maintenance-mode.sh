#!/bin/bash

source "/etc/disco-boot.conf" # for MAINTENANCE_MODE_FILE

USAGE="$0 on|off|pause|resume|help"
HAS_HTTP=$(chkconfig --list httpd 2>/dev/null)
HAS_CELERY=$(chkconfig --list celeryd 2>/dev/null)
NOW=$(date -u --rfc-3339=seconds)

function enable_service() {
    if [[ "$HAS_HTTP" != "" ]] ; then
        sudo service httpd restart
    fi

    if [[ "$HAS_CELERY" != "" ]] ; then
        sudo service celeryd restart
    fi

    resume_service
}

function resume_service() {
    rm -f $MAINTENANCE_MODE_FILE
}

function disable_service() {
    pause_service

    if [[ "$HAS_HTTP" != "" ]] ; then
        sudo service httpd stop
    fi

    if [[ "$HAS_CELERY" != "" ]] ; then
        sudo service celeryd stop
    fi
}

function pause_service() {
    echo $NOW > $MAINTENANCE_MODE_FILE
}

case "$1" in
    on)
        disable_service
        ;;
    off)
        enable_service
        ;;
    pause)
        pause_service
        ;;
    resume)
        resume_service
        ;;
    help)
        echo "Usage: $USAGE"
        echo "       to stop services and place in maint mode, use on/off"
        echo "       to place in maint mode without stopping services, use pause/resume"
        ;;
    *)
        echo "Usage: $USAGE"
        exit 1
        ;;
esac

exit 0
