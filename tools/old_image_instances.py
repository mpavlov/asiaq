#!/usr/bin/env python

"""
Will print out the list of ec2 instances that are running very old images.
Very old in this context would be 8 days.
"""

import boto3
import sys
import datetime
import math

from dateutil.parser import *
from dateutil.tz import *

MAX_DAYS = 8


def tags2dict(tags):
    return {tag.get('Key'): tag.get('Value') for tag in (tags or {})}


def time_diff(launch_time, current_time):
    running_time = current_time - launch_time
    return int(math.ceil((running_time.total_seconds()/(3600))/24))


def get_old_ami_offenders(ec2=None, max_days=MAX_DAYS):
    '''Returns list machines that don't have a product line tag'''
    if ec2 is None:
        ec2 = boto3.resource('ec2')
    instances = ec2.instances.filter(Filters=[{'Name': 'instance-state-name',
                                               'Values': ['running']}])
    inst = []
    for instance in instances:
        image = ec2.Image(instance.image_id)
        try:
            creation_time = parse(image.creation_date)
            current = datetime.datetime.now(creation_time.tzinfo)
            ami_age = time_diff(creation_time, current)
            if ami_age > max_days:
                inst.append({'id': instance.id, 'tags': tags2dict(instance.tags), 'age': ami_age})
        except AttributeError:
            inst.append({'id': instance.id, 'tags': tags2dict(instance.tags), 'age': 'del'})
    return inst


def print_offenders(offenders):
    '''Prints instances that are running AMI that are older than 8 days'''
    for inst in offenders:
        tags = inst.get('tags')
        print "{:<14} {:<16} {:<24} {:<8} {:<3}".format(
            inst.get('id'), tags.get('owner', '-'), tags.get('hostclass', '-'),
            tags.get('environment', '-'), inst.get('age'))


def main():
    '''Handle offenders and exit with the appropriate status code'''
    offenders = get_old_ami_offenders()
    print_offenders(offenders)
    sys.exit(len(offenders) > 0)

if __name__ == "__main__":
    main()
