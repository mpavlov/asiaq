#!/bin/false

# This was created to be sourced by deployenator jobs.

# It makes asiaq commands use the RPM installed asiaq binaries and
# bake installed configuration. And it start the ssh-agent

export BOTO_CONFIG=/opt/wgen/discoaws/asiaq/jenkins/base_boto.cfg
export AWS_CONFIG_FILE="$BOTO_CONFIG"
export ASIAQ_CONFIG="/opt/wgen/discoaws"
export PATH="/opt/wgen/asiaq/bin:$PATH"

eval $(ssh-agent)
