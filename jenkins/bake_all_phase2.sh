#!/bin/bash

# The script usage for all teams except astronauts is:
#
# export TOKEN="INSERT_YOUR_BAKE_HOSTCLASS_STATUS_JOB_TOKEN_HERE"
# export LOG_DIR="$WORKSPACE/bake_logs.${BUILD_NUMBER}"
# rm -Rf asiaq ; git clone --depth 1 $GIT_URL/asiaq
# rm -Rf asiaq_TEAM_config ; git clone --depth 1 $GIT_URL/asiaq_TEAM_config
# cd asiaq_TEAM_config  # baking will look for disco_aws.ini here
# ../asiaq/jenkins/bake_all_phase2.sh
#
# Teams will need a bake-hostclass-STATUS job, like this:
#   https://your-jenkins-host/jenkins/job/bake-hostclass-STATUS/
# They also will need to replace TEAM above with their team name, and
# set the TOKEN value appropriately.
#
# Astronauts will want to call bake_all_phase1.sh as well.

source "$(dirname $0)/bake_common.sh" 2>&1 > /dev/null

echo "Baking the hostclasses"
HOSTCLASSES=$(echo init/mhc*.sh | sed -e 's.init/..g' -e 's/.*DISABLED.*//g' -e 's/\.sh//g')
bake_hostclasses $HOSTCLASSES
