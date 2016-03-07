#!/bin/bash -xe

# add hostclass specfic smoketest checks.
# otherwise smoketest.unit.sh will run without specific check,
# which still prove smoketest is executed

cat << SMOKETEST_CONF > /opt/wgen/etc/smoketest.conf
verify_init_status rsyslog 2 3 4 5
is_service_running rsyslog
SMOKETEST_CONF
