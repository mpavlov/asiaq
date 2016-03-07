#!/usr/bin/env python

"""
Will print out a list of autoscaling group that are flapping.
The code currently ignores activities if they are older than 20 minutes.
"""
import boto
import boto3
import datetime
import sys

MAX_DURATION = 2  # hours
MAX_COUNT = 3  # of instances
COOL_OFF = 25  # minutes since last activity


def detect_anomaly(autoscale_client, autoscale_group, duration=MAX_DURATION):
    ''' Detect if hostclass in the autoscaling group are flapping '''
    current_time = datetime.datetime.utcnow()
    cut_off = current_time - datetime.timedelta(hours=duration)
    response = autoscale_client.describe_scaling_activities(AutoScalingGroupName=autoscale_group)

    if response and response['Activities']:
        count = 0
        recent_activity_start = response['Activities'][0]['StartTime'].replace(tzinfo=None)
        if (current_time - recent_activity_start) > datetime.timedelta(minutes=COOL_OFF):
            return False

        for activity in response['Activities']:
            action = activity['Description'].split(' ', 1)[0]
            start = activity['StartTime'].replace(tzinfo=None)
            if (action != "Terminating" or
                (activity['Cause'].
                 find("an instance was taken out of service in response to a user health-check.") == -1 and
                 activity['Cause'].
                 find("an instance was taken out of service in response to a EC2 health check") == -1)):
                continue
            count += 1
            if count > MAX_COUNT:
                return True
            if start < cut_off:
                break
        return False


def get_flapping_services(groups):
    ''' Returns a list of autoscaling groups that are flapping '''
    autoscale_client = boto3.client('autoscaling')
    return [group.name for group in groups if detect_anomaly(autoscale_client, group.name)]


def print_offenders(offenders):
    ''' Print ASG that are flapping '''
    for offender in offenders:
        print offender


def main():
    '''Handle offenders and exit with the appropriate status code'''
    autoscaling = boto.connect_autoscale()
    groups = autoscaling.get_all_groups()
    print_offenders(get_flapping_services(groups))
    sys.exit(1 if len(groups) > 0 else 0)


if __name__ == "__main__":
    main()
