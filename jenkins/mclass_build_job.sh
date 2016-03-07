#!/bin/bash -ex
# Tests and builds the egg in mclass Burst jenkins

export PYNEST=${PYNEST:-/tmp}
export PATH=/opt/wgen-3p/python27/bin:$PATH
export PATH=/opt/wgen-3p/ruby-1.9/bin:$PATH
export WORKSPACE=${WORKSPACE:-$PWD}
export PIP_LOG=${PIP_LOG:-$WORKSPACE/pip.log}

# Start ssh-agent because disco_remote_exec.py needs to add keys
eval $(ssh-agent)
trap "ssh-agent -k" EXIT

rake virtualenv:create
source venv/bin/activate
rake test
rake setup:pynest
