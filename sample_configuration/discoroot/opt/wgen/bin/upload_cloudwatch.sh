#!/bin/bash

source "/etc/profile.d/proxy.sh"

# Make sure rabbitmqctl, asiaq and iostat are in path
export PATH="/opt/wgen/asiaq/bin:$PATH:/usr/sbin:/usr/bin"

export ASIAQ_CONFIG="/opt/wgen/discoaws"
disco_metrics.py upload --jitter 45
