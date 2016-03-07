#!/bin/bash

WHERE="local0.info"
TAG="ipsec_status"
ipsec auto --status | tee -a /opt/wgen/log/ipsec_status.log | logger -p $WHERE -t $TAG
