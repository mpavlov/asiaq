#!/bin/bash -xe

source "`dirname $0`/common.sh"
source "`dirname $0`/jenkins-common.sh"

install_repo() {
  yum_install createrepo httpd
}

install_rake() {
  set +e  # rvm.sh doesn't like -e so temporarily disable it
  source /etc/profile.d/rvm.sh
  set -e
  rvm install 1.9.3

  # quick fix for http://makandracards.com/makandra/20751-how-to-fix-undefined-method-name-for-array-error-when-running-bundled-commands-on-ruby-1-8-7-+-rails-2-3
  rvm @global
  gem uninstall rubygems-bundler
}

install_job_requirements() {
  # git is required for git plugin
  yum_install git

  # graphviz is a requirement of the dependency graph plugin: https://wiki.jenkins-ci.org/display/JENKINS/Dependency+Graph+View+Plugin
  yum_install graphviz

  # rpmbuild and rpm-devel are required to build rpms
  yum_install rpm-build gcc sqlite-devel readline-devel zlib-devel bzip2-devel openssl-devel rpm-devel

  # install compiler cache to speed up builds
  yum_install ccache
  ln -s /usr/bin/ccache /usr/local/bin/gcc
  ln -s /usr/bin/ccache /usr/local/bin/g++
  ln -s /usr/bin/ccache /usr/local/bin/cc
  ln -s /usr/bin/ccache /usr/local/bin/c++

  # rake is required for running rake tasks
  install_rake

  # Dependencies required for building wsgi
  yum_install httpd-devel.x86_64

  # Dependencies required for building haproxy
  yum_install wget pcre-devel

  # Dependencies required for building scipy for disco_grouping_service
  yum_install lapack-devel blas-devel

  # Dependencies required for building matplotlib for disco_insight_service
  yum_install freetype-devel libpng-devel subversion atlas-sse3 atlas-sse3-devel
}

echo "teamname" > /opt/wgen/etc/productline

disable_proxy
disable_internal_repos
install_repo
install_jenkins
# add_to_alternatives
install_job_requirements
enable_internal_repos

chkconfig disco-tmp-storage on
chkconfig disco-backup-logs on
chkconfig disco-snapshot-volume on

# add hostclass specfic smoketest checks, otherwise smoketest.unit.sh will run without specific check, which still prove
# smoketest is executed

cat << SMOKETEST_CONF > /opt/wgen/etc/smoketest.conf
verify_init_status httpd 2 3 4 5
is_service_running httpd
verify_init_status jenkins 2 3 4 5
is_service_running jenkins
verify_init_status rsyslog 2 3 4 5
is_service_running rsyslog
SMOKETEST_CONF
