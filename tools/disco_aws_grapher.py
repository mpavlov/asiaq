#!/usr/bin/env python
# vim: ts=4 sw=4 et filetype=python

# Count how many instances each user has running and feed data to graphite
# Sample crontab entry:
#    */4 * * * * ~/vcs/disco_aws_automation/disco_aws_grapher.py >/dev/null 2>&1

import boto
from collections import defaultdict
import socket
from contextlib import closing
import time

CARBON_SERVER = '0.0.0.0'
CARBON_PORT = 2003
CARBON_SINK = "disco_aws.user_instances"

owner_count = defaultdict(int)

connection = boto.connect_ec2()
instances = [instance for reservation in connection.get_all_instances() for instance in reservation.instances]

for instance in instances:
    if instance.state == u"running":
        owner_count[instance.tags.get("owner", "unknown")] += 1

with closing(socket.socket()) as socket:
    socket.connect((CARBON_SERVER, CARBON_PORT))

    now = int(time.time())
    for owner, count in owner_count.iteritems():
        message = "{0}.{1} {2} {3}".format(CARBON_SINK, owner, count, now)
        print(message)
        socket.sendall(message + "\n")
