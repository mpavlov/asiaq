#!/bin/bash -xe
# vim: ts=4 sw=4 et

####
# This init is used to configure the base ubuntu AMI.
# It takes a generic Ubuntu AMI, updates it and applies global changes.
####

# All system users should be initialized here, acfg runs to set
# file ownership before host specific phase2 scripts run and
# needs to be able to correlate user to uids.
init_system_user "apache"
init_system_user "celery"
init_system_user "rabbitmq"
init_system_user "git"; usermod --shell "/bin/bash" "git"
init_system_user "jenkins"; usermod --shell "/bin/bash" "jenkins"
init_system_user "disco_sender"

# TODO Add these more like we do the operators
init_one_command_user 'smoketest' '/opt/wgen/bin/smoketest.sh' '{s3cred://public_keys/ssh/smoketest.pub}'
init_shell_user 'snapshot' '*' '{s3cred://public_keys/ssh/snapshot.pub}'
init_shell_user 'disco_tester' '*' '{s3cred://public_keys/ssh/test.pub}'

apt-get update --quiet -y
apt-get upgrade --quiet -y --auto-remove
apt-get install --quiet -y python-pip apache2
