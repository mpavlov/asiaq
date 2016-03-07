#!/bin/bash

WHERE="local0.info"
TAG="monitor_processes"
top -b -n 1 | logger -p $WHERE -t $TAG
# top: -b batch mode
# top: -n # number of runs
