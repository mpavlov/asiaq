#!/bin/bash -e

set +e
. /etc/init.d/functions
source /etc/profile.d/rvm.sh # get the latest ruby
set -e

SYNAPSE_LOG_FILE="/var/log/synapse.log"
CONFIG_FILE="/etc/synapse.conf.json"
CONFIG_DIR="/etc/synapse.d"

source "/opt/wgen/bin/user-data.sh" # pulls in 'zookeepers'

INSTANCE_ID=$(curl --silent http://169.254.169.254/latest/meta-data/instance-id)

function synapse_conf() {
    local IPV4=$(curl --silent http://169.254.169.254/2012-01-12/meta-data/local-ipv4)
    local ZK_HOSTS="$zookeepers"
    for FILE in $(echo $CONFIG_DIR/*.json $CONFIG_FILE) ; do
        sed -e "s/\$IPV4/$IPV4/g" \
            -e "s/\$ZK_HOSTS/$ZK_HOSTS/g" \
            -e "s/\$INSTANCE_ID/$INSTANCE_ID/g" \
            -i $FILE
    done
}

synapse_conf

synapse --config "$CONFIG_FILE" 2>&1
