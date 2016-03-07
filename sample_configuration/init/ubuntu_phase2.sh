#!/bin/bash -xe
# vim: ts=4 sw=4 et

####
# This init is used to configure the hostclass specific ami. That is take a
# phase1 AMI, unpack config and install hostclass specific software.
####

hostclass_init="$discoaws_init_path/$hostclass.sh"
if [ -x "$hostclass_init" ]; then
    if [[ "$HAS_REPO" != "1" ]]; then
        disable_internal_repos
    fi

    "$hostclass_init"

    enable_internal_repos
else
    echo "No hostclass specific init found. Exiting."
    exit 1
fi
