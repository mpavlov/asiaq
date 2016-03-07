#!/bin/bash

##
# Promote currently running AMIs that have been running
# for long enough.
##

source "$(dirname $0)/boto_init.sh" $1

disco_aws.py --debug --env ci promoterunning --hours 2
for hostclass in mhccustomerswan mhcdiscodeployenator; do
    disco_bake.py hostclasspromote --hostclass $hostclass
done
