#!/usr/bin/env python

"""
Will print out the list of ec2 instances that are running with no productline
tags. These exclude ec2 instance that are created for baking.
"""

import boto.ec2
import sys

def get_offenders():
    '''Returns list machines that don't have a product line tag'''
    connection = boto.ec2.connect_to_region("us-west-2")
    reservations = connection.get_all_instances()
    return [inst
            for reservation in reservations
            for inst in reservation.instances
            if (inst.state == 'running'
                and bool(inst.tags)
                and 'bake' != inst.tags['hostclass'][:4]
                and inst.tags.get('productline') in [None, 'unknown'])]

def print_offenders(offenders):
    '''Prints instances that don't have a product line tag'''
    for inst in sorted(offenders, key=lambda x: (x.tags.get('owner'), x.tags.get('environment'))):
        print "{:<14} {:<16} {:<24} {:<8}".format(
            inst.id, inst.tags.get('owner', '-'), inst.tags.get('hostclass', '-'),
            inst.tags.get('environment', '-'))

def main():
    '''Handle offenders and exit with the appropriate status code'''
    offenders = get_offenders()
    print_offenders(offenders)
    sys.exit(1 if len(offenders) > 0 else 0)

if __name__ == "__main__":
    main()
