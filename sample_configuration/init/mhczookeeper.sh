#!/bin/bash -xe

# This is based on the recipe here
# http://jbowles.github.io/blog/2013/02/09/zookeeper-on-centos/

echo "teamname" > /opt/wgen/etc/productline

yum install -y java-1.7.0-openjdk

ZOO_VERSION="3.4.8"
APACHE_MIRROR="http://apache.mirrors.lucidnetworks.net"
ZOO_DIRECTORY="/opt/wgen/zookeeper-$ZOO_VERSION"

cd /tmp
curl -O $APACHE_MIRROR/zookeeper/stable/zookeeper-$ZOO_VERSION.tar.gz
cd /opt/wgen/zookeeper/
tar zxvf /tmp/zookeeper-$ZOO_VERSION.tar.gz --owner=root --strip 1

chkconfig disco-add-zookeeper-storage on
chkconfig zookeeper on

# add hostclass specfic smoketest checks, otherwise smoketest.unit.sh will run without specific check, which still prove
# smoketest is executed

cat << SMOKETEST_CONF > /opt/wgen/etc/smoketest.conf
verify_init_status zookeeper 2 3 4 5
is_service_running zookeeper
check_zookeeper
verify_init_status rsyslog 2 3 4 5
is_service_running rsyslog
SMOKETEST_CONF
