# Change path for Asiaq scripts
# RPM installation: path to scripts /opt/wgen/asiaq/bin
# pip installation: path to scripts /usr/bin
#
# On Centos6 we install Asiaq via RPM
# On Centos7 we install Asiaq via pip
#
# Centos7 instances will ignore /opt/wgen/asiaq/bin becasue
# it cannot be found and will use /usr/bin instead

PATH=/opt/wgen/asiaq/bin:$PATH
