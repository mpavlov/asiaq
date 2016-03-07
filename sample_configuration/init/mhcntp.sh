#!/bin/bash -xe

# add hostclass specfic smoketest checks, otherwise smoketest.unit.sh will run without specific check, which still prove
# smoketest is executed

echo "teamname" > /opt/wgen/etc/productline

cat << SMOKETEST_CONF > /opt/wgen/etc/smoketest.conf
verify_init_status synapse 2 3 4 5
is_service_running synapse
verify_init_status ntpd 2 3 4 5
is_service_running ntpd
check_ntpstat
verify_init_status rsyslog 2 3 4 5
is_service_running rsyslog
SMOKETEST_CONF
