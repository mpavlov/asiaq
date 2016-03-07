#!/bin/bash -xe
# vim: ts=4 sw=4 et

####
# This init is used to configure the base disco ami. That is take a generic
# CentOS AMI, update it and set up global setting changes.
####

install_ruby() {
  # ruby dependencies
  yum_install curl bison git-core

  # yes, we install ruby like everybody else
  gpg2 --keyserver hkp://keys.gnupg.net --recv-keys D39DC0E3
  curl -L https://get.rvm.io | bash -s stable

  # disco_egg_template's (and so all our jobs') rake tasks absolutely require version 1.9
  set +e # rvm.sh doesn''t like -e so disable it temporarily
  source /etc/profile.d/rvm.sh
  set -e
  rvm install 1.9.3
  rvm use --default 1.9.3

  # Install rake for Jenkins
  gem install rake

  # Install explicit amq-protocol 1.9.2, since 2 is incompatible w/Ruby 1.x
  gem install -v 1.9.2 amq-protocol

  # Install the SmartStack discovery components
  gem install nerve
  gem install synapse

  # global env vars for ruby
gem_home=`find /usr/local/rvm/gems/ -maxdepth 1 -type d -regex ".*/ruby[^@/]*" -print0 | tr "\0" ":"`
gem_path=`find /usr/local/rvm/gems/ -maxdepth 1 -type d -regex ".*/ruby[^/]*" -print0 | tr "\0" ":"`
path=`find /usr/local/rvm/{gems,rubies} -maxdepth 4 -name bin -type d -print0 |tr "\0" ":"`
cat >> /etc/bashrc <<EOF
export GEM_HOME=${gem_home%:}
export GEM_PATH=${gem_path%:}
export PATH=${path%:}:$PATH
EOF
}

#Disable selinux now.
echo 0 > /selinux/enforce

#Disable iptables immediatelly
service iptables stop
service ip6tables stop

#Prevent iptable from starting on boot
chkconfig iptables off
chkconfig ip6tables off

#Set system time zone to Eastern, for compatibility with Splunk 5 and 4
# note: don't use symlinks: https://www.centos.org/forums/viewtopic.php?t=4248
\cp /usr/share/zoneinfo/US/Eastern /etc/localtime

#add epel repos for python-boto
epel_file="/tmp/epel-release.rpm"
if [ ! -e "$epel_file" ]; then
    curl http://dl.fedoraproject.org/pub/epel/6/x86_64/epel-release-6-8.noarch.rpm -o "$epel_file"
fi
if [ ! "$(rpm -qa epel-release)" ] ; then
    rpm -Uvh "$epel_file"
fi

#Add repos with modern rsyslog that has elasticsearch support
curl http://rpms.adiscon.com/v8-stable/rsyslog.repo -o /etc/yum.repos.d/rsyslog.repo
yum makecache

#Repo server is not avail in phase1 so we disable it for execution of this script
disable_internal_repos

yum remove -y yum-presto # this just slows things down

# Make sure we have all the latest stuff
yum update -y

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

#Install common packages
yum_install ntp ntpdate xfsprogs device-mapper cryptsetup mdadm tree vim nano
yum_install rsyslog rsyslog-elasticsearch rsyslog-mmjsonparse

#Install python packages
yum_install python python-argparse python-simplejson python-pip

#Install profiling tool
yum_install sysstat lsof iotop htop strace

#Install network debug tools
yum_install tcpdump

#Install nc so we can check some common network sevice in smoketest
yum_install nc

#Install jq so we can process json configuration files for zookeeper
yum_install jq

# Install supervisor (CentOS 6.5 has version 2.1), for use by nerve & synapse
yum_install supervisor

#Install AWS CLI, enable autocompletion in bash
pip install awscli docopt
echo "complete -C aws_completer aws" >> /etc/bashrc

install_ruby

#set bogus hostclass to unpack only common acfg files
mkdir -p /opt/wgen/etc/
echo "mhcgeneric" > /opt/wgen/etc/hostclass

#Install asiaq egg
pip install -e $discoaws_root/asiaq

#Unpack common configuration
$discoaws_root/asiaq/bin/acfg1.py $discoaws_root/discoroot /

#Uninstall asiaq egg (we'll install it as an rpm in phase2)
pip uninstall -y asiaq

install_splunklogger

# Update CA trust
update-ca-trust enable
update-ca-trust extract


#Enable ntpdate and ntp so we can keep time
chkconfig ntpdate on
chkconfig ntpd on

#Make rsyslogd status viewable to smoketest
sed -i 's/umask 077//g' /etc/init.d/rsyslog

#Enable logging
chkconfig rsyslog on

#Resize file system to partition on boot
chkconfig disco-resize-file-system on

#Run disco-booted last on startup so we know when initialization is complete
chkconfig disco-booted on
# Set up /etc/hosts, especially until we have cross-VPN DNS working
chkconfig disco-add-etc-hosts on
# Set up floating IP routing for people who need it (should be in a shared
# phase2 script, but we don't have those)
chkconfig disco-ip-route on

#Install the AWS root key if present (we do this late so the machine is in a good state).
sed -e 's/chkconfig:.*/chkconfig: - 99 90/' -i /etc/init.d/download-root-key
chkconfig --add download-root-key
chkconfig download-root-key on
