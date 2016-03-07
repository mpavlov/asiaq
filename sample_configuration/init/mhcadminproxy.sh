#!/bin/bash -xe
# vim: ts=4 sw=4 et

source "`dirname $0`/common.sh"

echo "teamname" > /opt/wgen/etc/productline

yum_install httpd mod_ssl
sed -i '/^After=/ s/$/ disco-update-creds.service/' /lib/systemd/system/httpd.service
systemctl enable httpd
systemctl daemon-reload

# allow smoketest to check httpd status
chmod 755 /var/run/httpd

# hostclass specfic smoketests
cat << SMOKETEST_CONF > /opt/wgen/etc/smoketest.conf
is_service_running synapse
is_service_running httpd
is_service_running haproxy
is_service_running rsyslog
SMOKETEST_CONF
