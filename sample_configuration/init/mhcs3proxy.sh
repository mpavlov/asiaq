#!/bin/bash -xe

yum install -y tinyproxy

chkconfig tinyproxy on

# add hostclass specfic smoketest checks, otherwise smoketest.unit.sh will run without specific check, which still prove
# smoketest is executed

echo "teamname" > /opt/wgen/etc/productline

cat << SMOKETEST_CONF > /opt/wgen/etc/smoketest.conf
verify_init_status tinyproxy 2 3 4 5
is_service_running tinyproxy
verify_init_status rsyslog 2 3 4 5
is_service_running rsyslog
SMOKETEST_CONF
