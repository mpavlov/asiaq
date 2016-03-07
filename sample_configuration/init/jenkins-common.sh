#!/bin/false

# Add the Oracle JDK to alternatives as the default
function add_to_alternatives() {
  local jdk_home="/opt/wgen/build/java/jdk1.6.0_45"
  local base_cmd="alternatives --install /usr/bin/java java $jdk_home/bin/java 99999"
  local tools="keytool orbd pack200 rmid rmiregistry servertool tnameserv unpack200"
  local docs="java $tools"
  local set_manual_cmd="alternatives --set java $jdk_home/bin/java"

  # Add tools
  for tool in $tools; do
    local slave_cmd="$slave_cmd --slave /usr/bin/$tool $tool $jdk_home/bin/$tool"
  done

  # Add man pages
  for doc in $docs; do
    slave_cmd="$slave_cmd --slave /usr/share/man/man1/$doc.1.gz $doc.1.gz $jdk_home/man/man1/$doc.1.gz"
  done

  local final_cmd="$base_cmd $slave_cmd"
  $final_cmd
  echo "Added $jdk_home to alternatives"

  # Set the alternative explicitly and disable auto mode so that something can't take a higher priority
  $set_manual_cmd
  echo "Disabled auto mode and forced $jdk_home to be the default"
}

function install_jenkins() {
  # Change our timezone to eastern to make jenkins schedule more intuituve
  # (avoiding links: https://www.centos.org/forums/viewtopic.php?t=4248)
  sed 's#^ZONE=.*#ZONE="US/Eastern"#' -i /etc/sysconfig/clock
  cp /usr/share/zoneinfo/US/Eastern /etc/localtime

  # java is an unspecified dependency of jenkins. note that java 1.5, 1.6 (which some centos versions come with) are incompatible with jenkins
  yum_install java-1.7.0-openjdk

  # install jenkins himself
  curl -o /etc/yum.repos.d/jenkins.repo http://pkg.jenkins-ci.org/redhat/jenkins.repo
  rpm --import http://pkg.jenkins-ci.org/redhat/jenkins-ci.org.key
  yum_install jenkins httpd mod_ssl

  # install requirements for our init script
  yum_install xmlstarlet

  # fix for https://wiki.jenkins-ci.org/display/JENKINS/Jenkins+got+java.awt.headless+problem
  yum_install dejavu-sans-fonts

  # Use our logrotation script, not the RPM one..
  mv /etc/logrotate.d/jenkins.rpmorig /etc/logrotate.d/jenkins

  # add a link to jenkins.log so it's together with apache error and access logs
  ln -s /var/log/jenkins/jenkins.log /opt/wgen/log/jenkins.log

  `dirname $0`/initmunge.py --required-start "discojenkins" /etc/init.d/jenkins

  #Allow jenkins to read shadow so it can be used for authentication
  groupmems -g root -a jenkins
  chmod g+r /etc/shadow

  chkconfig disco-jenkins on
  chkconfig jenkins on
  chkconfig httpd on
}

function download_required_plugins() {
  REQUIRED_PLUGINS_DIR=$1
  TARGET_PLUGINS_DIR=$2
  for PLUGIN in $(ls ${REQUIRED_PLUGINS_DIR});
  do
    echo ${TARGET_PLUGINS_DIR} ${PLUGIN}
    install_required_plugins ${TARGET_PLUGINS_DIR} ${PLUGIN}
  done
}

function install_required_plugins() {
    TARGET_PLUGINS_DIR=$1
    PLUGIN=$2
    url="https://updates.jenkins-ci.org/latest/${PLUGIN}.hpi"
    cd "${TARGET_PLUGINS_DIR}"
    curl -L -O "$url"
    chown jenkins:sys "${PLUGIN}.hpi"
    chmod 664 "${PLUGIN}.hpi"
  # plugins are installed automatically at jenkins start
}
