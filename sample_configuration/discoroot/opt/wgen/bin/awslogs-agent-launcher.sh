#!/bin/sh

# This replaces version 1.3.6 of the awglog's awslogs-agen-launcher.sh

# In the Disco version we use our proxy configuration to make sure logs
# can make it out into the world

echo -n $$ > /var/awslogs/state/awslogs.pid

source "/etc/profile.d/proxy.sh"
source "/opt/wgen/bin/user-data.sh"

CONFIG_FILE='/var/awslogs/etc/awslogs.conf'

sed -e "s/{env}/$environment_name/g" -e "s/{hostclass}/$hostclass/g" -i $CONFIG_FILE


AWS_CONFIG_FILE=/var/awslogs/etc/aws.conf HOME=/root /bin/nice -n 4 /var/awslogs/bin/aws logs push --config-file $CONFIG_FILE >> /var/log/awslogs.log 2>&1
