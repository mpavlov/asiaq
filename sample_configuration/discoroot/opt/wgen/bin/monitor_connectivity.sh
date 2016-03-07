#!/bin/bash

WHERE="local0.info"
TAG="monitor_connectivity"
nc -z 10.1.0.24 389 | logger -p $WHERE -t $TAG
# -z don't send data
# 10.1.0.24 Active Directory host
# 389 Unencrypted AD port

