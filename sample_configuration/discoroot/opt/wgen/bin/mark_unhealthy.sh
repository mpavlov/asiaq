#!/bin/bash

MESSAGE="$1"

source "/etc/profile.d/proxy.sh" # for HTTP_PROXY

source $(dirname ${BASH_SOURCE[0]})/aws-utility-functions.sh

INSTANCE_ID=$(get_metadata_attribute instance-id)
HOSTCLASS=$(cat "/opt/wgen/etc/hostclass")

logger -t disco.smoketest -p local0.err "Marking $HOSTCLASS $INSTANCE_ID as unhealthy. Cause: $MESSAGE"

aws autoscaling set-instance-health --instance-id $INSTANCE_ID --health-status Unhealthy \
                                    --should-respect-grace-period
