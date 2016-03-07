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
setenforce 0

#add epel repos for python-boto
epel_file="/tmp/epel-release.rpm"
if [ ! -e "$epel_file" ]; then
    curl http://dl.fedoraproject.org/pub/epel/7/x86_64/e/epel-release-7-5.noarch.rpm -o "$epel_file"
fi
if [ ! "$(rpm -qa epel-release)" ] ; then
    rpm -Uvh "$epel_file"
fi

#Add repos with modern rsyslog that has elasticsearch support
curl http://rpms.adiscon.com/v8-stable/rsyslog.repo -o /etc/yum.repos.d/rsyslog.repo
yum makecache

#Repo server is not avail in phase1 so we disable it for execution of this script
disable_internal_repos

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
yum_install python python-boto python-argparse python-simplejson python-pip ntp ntpdate xfsprogs device-mapper cryptsetup mdadm tree vim nano rsyslog rsyslog-elasticsearch rsyslog-mmjsonparse

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

#TODO check for centos7 compatibility
install_splunklogger

# Update CA trust
update-ca-trust enable
update-ca-trust extract

#Enable ntp so we can keep time
timedatectl set-ntp true

#Make rsyslogd status viewable to smoketest
sed -i 's/umask 077//g' /etc/init.d/rsyslog

#Enable logging
systemctl enable rsyslog

#Run disco-booted last on startup so we know when initialization is complete
chkconfig disco-booted on
# Set up /etc/hosts, especially until we have cross-VPN DNS working
chkconfig disco-add-etc-hosts on
# Set up floating IP routing for people who need it (should be in a shared
# phase2 script, but we don't have those)
chkconfig disco-ip-route on

systemctl daemon-reload
