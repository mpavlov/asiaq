#!/bin/bash -xe
# vim: ts=4 sw=4 et

source "`dirname $0`/common.sh"

echo "teamname" > /opt/wgen/etc/productline

yum_install httpd mod_ssl

chkconfig httpd on

# allow smoketest to check httpd status
chmod 755 /var/run/httpd

# hostclass specfic smoketests
cat << SMOKETEST_CONF > /opt/wgen/etc/smoketest.conf
verify_init_status synapse 2 3 4 5
is_service_running synapse
verify_init_status httpd 2 3 4 5
is_service_running httpd
verify_init_status haproxy 2 3 4 5
is_service_running haproxy
verify_init_status rsyslog 2 3 4 5
is_service_running rsyslog
SMOKETEST_CONF
