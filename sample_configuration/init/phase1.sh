#!/bin/bash -xe
# vim: ts=4 sw=4 et

####
# This init is used to configure a base disco ami.
####

unset HTTP_PROXY
unset HTTPS_PROXY

unset http_proxy
unset https_proxy

discoaws_init_path="`dirname $0`"
discoaws_root="$discoaws_init_path/.."
source "`dirname $0`/common.sh"

#Source the disto specific phase 1 script
if [[ "$DISCO_OS" == "ubuntu" ]] ; then
    source $discoaws_init_path/ubuntu_phase1.sh
elif [[ "$DISCO_OS" == "centos" ]] ; then
    source $discoaws_init_path/centos${DISCO_OS_VERSION}_phase1.sh
else
    echo "Unrecognized Operating System"
    exit 1
fi

#Delete old contents of /tmp so that our ephemeral content does not affect
#instance on boot
rm -Rf /tmp/*
