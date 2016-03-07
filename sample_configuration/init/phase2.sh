#!/bin/bash -xe
# vim: ts=4 sw=4 et

####
# This init is used to configure the hostclass specific ami. That is take a
# phase1 AMI, unpack config and install hostclass specific software.
####

unset HTTP_PROXY
unset http_proxy
unset HTTPS_PROXY
unset https_proxy

source "`dirname $0`/common.sh"

hostclass=$1
repo_ip=$2

discoaws_init_path="`dirname $0`"
discoaws_root="$discoaws_init_path/.."

#save hostclass name
mkdir -p /opt/wgen/etc
echo "$hostclass" > /opt/wgen/etc/hostclass

#If the repo is available, add it to /etc/hosts
if [[ "$repo_ip" != "" ]] ; then
    if ping -c 1 $repo_ip ; then
        echo "$repo_ip repo" >> /etc/hosts
        HAS_REPO=1
    fi
fi

#Unpack common configuration, using latest asiaq
pip install -e $discoaws_root/asiaq
$discoaws_root/asiaq/bin/acfg1.py $discoaws_root/discoroot /
pip uninstall -y asiaq

#Source the distro specific phase 2 script
if [[ "$DISCO_OS" == "ubuntu" ]] ; then
    source $discoaws_init_path/ubuntu_phase2.sh
elif [[ "$DISCO_OS" == "centos" ]] ; then
    source $discoaws_init_path/centos${DISCO_OS_VERSION}_phase2.sh
else
    echo "Unrecognized Operating System"
    exit 1
fi

#Remove repo line from /etc/hosts
NEW_HOSTS=$(mktemp) ; grep -v "$repo_ip repo" /etc/hosts > $NEW_HOSTS ; cat $NEW_HOSTS > /etc/hosts

#Delete old contents of /tmp so that our ephemeral content does not affect
#instance on boot
rm -Rf /tmp/*
