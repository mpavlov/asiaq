#!/usr/bin/env python
"""
Manages Route53 domains and DNS records

Usage:
    disco_route53.py [--debug] list-zones
    disco_route53.py [--debug] list-records [--zone <zone-name>]
    disco_route53.py [--debug] create-record <zone-name> <record-name> <type> <value>
    disco_route53.py [--debug] delete-record <zone-name> <record-name> <type>
    disco_route53.py (-h | --help)

Commands:
    list-zones      List all Hosted Zones
    list-records    List all DNS records
    create-record   Create a new DNS record
    delete-record   Delete a DNS record

Options:
    -h --help           Show this screen
    --zone <zone-name>  Show records for a specific Hosted Zone
    --debug             Log in debug level
"""

from __future__ import print_function
from docopt import docopt

from disco_aws_automation import DiscoRoute53
from disco_aws_automation.disco_aws_util import run_gracefully
from disco_aws_automation.disco_logging import configure_logging


def run():
    """Parses command line and dispatches the commands"""
    args = docopt(__doc__)

    configure_logging(args["--debug"])

    disco_route53 = DiscoRoute53()

    if args['list-zones']:
        for hosted_zone in disco_route53.list_zones():
            is_private_zone = hosted_zone.config['PrivateZone']
            print("{0:<20} {1:10} {2:5}".format(hosted_zone.name, hosted_zone.id, is_private_zone))
    elif args['list-records']:
        for hosted_zone in disco_route53.list_zones():
            # the Hosted Zone name is the domain name with a period appended to it
            # allow searching by either with or without the period
            if not args['--zone'] or hosted_zone.name in (args['--zone'], args['--zone'] + '.'):
                for record in disco_route53.list_records(hosted_zone.name):
                    values = ','.join(record.resource_records)
                    print("{0:<5} {1:20} {2:50}".format(record.type, record.name, values))
    elif args['create-record']:
        disco_route53.create_record(args['<zone-name>'],
                                    args['<record-name>'],
                                    args['<type>'],
                                    args['<value>'])
    elif args['delete-record']:
        record_name = args['<record-name>']
        # AWS appends a . to the end of the record name.
        # Add it here as a convenience if the argument is missing it
        if not record_name.endswith('.'):
            record_name += '.'
        disco_route53.delete_record(args['<zone-name>'], record_name, args['<type>'])


if __name__ == "__main__":
    run_gracefully(run)
