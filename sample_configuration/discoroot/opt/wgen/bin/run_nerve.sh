#!/bin/bash -e

set +e
. /etc/init.d/functions
source /etc/profile.d/rvm.sh # get the latest ruby
set -e

NERVE_LOG_FILE="/var/log/nerve.log"
CONFIG_FILE="/etc/nerve.conf.json"
CONFIG_DIR="/etc/nerve.d"

source "/opt/wgen/bin/user-data.sh" # pulls in 'zookeepers'

INSTANCE_ID=$(curl --silent http://169.254.169.254/latest/meta-data/instance-id)

function nerve_conf() {
    local IPV4=$(curl --silent http://169.254.169.254/2012-01-12/meta-data/local-ipv4)
    local ZK_HOSTS="$zookeepers"
    for FILE in $(echo $CONFIG_DIR/*.json $CONFIG_FILE) ; do
        sed -e "s/\$IPV4/$IPV4/g" \
            -e "s/\$ZK_HOSTS/$ZK_HOSTS/g" \
            -e "s/\$INSTANCE_ID/$INSTANCE_ID/g" \
            -i $FILE
    done

    # Don't advertise host to normal zookeeper path if we don't intend to
    # keep the host around post test.
    if [ "$is_testing" = "1" ]; then
        for FILE in $(ls -1 $CONFIG_DIR/*.json) ; do
            jq '.["zk_path"] = .["zk_path"]+"_test"' $FILE > ${FILE}~tmp
            mv ${FILE}~tmp $FILE
        done
    fi
}

nerve_conf

nerve --config "$CONFIG_FILE" --instance_id $INSTANCE_ID 2>&1
