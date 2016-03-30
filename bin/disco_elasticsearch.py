#!/usr/bin/env python
"""
Manages ElasticSearch

Usage:
    disco_elasticsearch.py [--debug] list [--endpoint]
    disco_elasticsearch.py [--debug] create --domain ES_DOMAIN
    disco_elasticsearch.py [--debug] update --domain ES_DOMAIN
    disco_elasticsearch.py [--debug] delete --domain ES_DOMAIN
    disco_elasticsearch.py (-h | --help)

Commands:
    list      List all elasticsearch domains
    create    Creates an elasticsearch domain
    update    Update elasticsearch domain configuration
    delete    Delete an elasticsearch domain

Options:
    -h --help           Show this screen
    --debug             Log in debug level
    --endpoint          Display elasticsearch service endpoint
    --domain ES_DOMAIN  Name of elasticsearch domain
"""
from __future__ import print_function
import sys
from docopt import docopt
from disco_aws_automation import DiscoES#, DiscoAWS, read_config
from disco_aws_automation.disco_aws_util import run_gracefully
from disco_aws_automation.disco_logging import configure_logging


def run():
    """Parses command line and dispatches the commands"""
    args = docopt(__doc__)

    configure_logging(args["--debug"])

    #config = read_config()

    #aws = DiscoAWS(config, env)
    #disco_elasticsearch = DiscoES(aws=aws)
    disco_elasticsearch = DiscoES()

    if args['list']:
        for domain in disco_elasticsearch.list():
            if args['--endpoint']:
                try:
                    endpoint = disco_elasticsearch._describe_es_domain(domain)\
                    ['DomainStatus']['Endpoint']
                except KeyError:
                    endpoint = None
                print('{0:20}\t{1}'.format(domain,endpoint))
            else:
                print(domain)

    elif args['create']:
        disco_elasticsearch.create(args['--domain'])

    elif args['update']:
        disco_elasticsearch.update(args['--domain'])

    elif args['delete']:
        disco_elasticsearch.delete(args['--domain'])

if __name__ == "__main__":
    run_gracefully(run)
