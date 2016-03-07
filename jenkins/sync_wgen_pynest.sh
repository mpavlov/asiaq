#!/bin/bash

##################
# Sync all wgen eggs that Disco depends on from wgen pynest to mhcdiscojenkins host in the build env.
# Also sync all disco eggs back down to this pynest.
# CODE TLDR;
# Note this behavior before you update code
# For the moment, The script is running on burst jenkins. So it behaves like this
# push all local repo to pynest, then pull from disco jenkins
# so anything newly generated on Disco has to be pulled in before beiing pushed to pynest.
# so you need to run the script twice to sync to pynest
##################

set -e
set -x
shopt -s extglob

DEFAULT_LOCAL_EGGS_DIR="/opt/wgen/pynest"
DEFAULT_REMOTE_ENVIRONMENT="build"
DEFAULT_REMOTE_USER="jenkins"
DEFAULT_REMOTE_EGGS_DIR="/opt/wgen/build/pynest"
DEFAULT_REMOTE_HOSTCLASS="mhcdiscojenkins"
DEFAULT_SSH_OPTIONS="-oBatchMode=yes -oStrictHostKeyChecking=no -oUserKnownHostsFile=/dev/null"
DEFAULT_LOCAL_EGGS_TO_PUSH_GLOB="+(+(wgen.+(auth|logger|metrics|repoze|stats)*)|+(burst_disco*)|+(burstalgo*))"
DEFAULT_REMOTE_EGGS_TO_PULL_GLOB="+(+(disco_*)|+(vocab_*)|+(science_*))"

LOCAL_EGGS_DIR=${LOCAL_EGGS_DIR:-$DEFAULT_LOCAL_EGGS_DIR}
REMOTE_ENVIRONMENT=${REMOTE_ENVIRONMENT:-$DEFAULT_REMOTE_ENVIRONMENT}
REMOTE_USER=${REMOTE_USER:-$DEFAULT_REMOTE_USER}
REMOTE_EGGS_DIR=${REMOTE_EGGS_DIR:-$DEFAULT_REMOTE_EGGS_DIR}
REMOTE_HOSTCLASS=${REMOTE_HOSTCLASS:-$DEFAULT_REMOTE_HOSTCLASS}
SSH_OPTIONS=${SSH_OPTIONS:-$DEFAULT_SSH_OPTIONS}
LOCAL_EGGS_TO_PUSH_GLOB=${LOCAL_EGGS_TO_PUSH_GLOB:-$DEFAULT_LOCAL_EGGS_TO_PUSH_GLOB}
REMOTE_EGGS_TO_PULL_GLOB=${REMOTE_EGGS_TO_PULL_GLOB:-$DEFAULT_REMOTE_EGGS_TO_PULL_GLOB}

source "$(dirname $0)/boto_init.sh"
ssh-add ~jenkins/.ssh/id_rsa
disco_aws="disco_aws.py"

remote_servers=$($disco_aws --env "$REMOTE_ENVIRONMENT" listhosts | awk "/ $REMOTE_HOSTCLASS /{print \$3}")
[[ "$remote_servers" == "" ]] && echo "No destination servers found" && exit 1

# Push to all remote servers
for remote_server in $remote_servers; do
  scp $SSH_OPTIONS $LOCAL_EGGS_DIR/$LOCAL_EGGS_TO_PUSH_GLOB $REMOTE_USER@$remote_server:$REMOTE_EGGS_DIR/
done

# Pull from only the first in the list (this is a bit lame, it might be someone's sandbox)
pull_from_server=$(echo "$remote_servers" | awk '{print $1}')
scp $SSH_OPTIONS $REMOTE_USER@$pull_from_server:$REMOTE_EGGS_DIR/$REMOTE_EGGS_TO_PULL_GLOB $LOCAL_EGGS_DIR/
