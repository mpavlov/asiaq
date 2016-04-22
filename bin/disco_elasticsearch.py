#!/usr/bin/env python
"""
Manages ElasticSearch
"""
from __future__ import print_function
import argparse
import sys
from disco_aws_automation import DiscoElasticsearch
from disco_aws_automation.disco_aws_util import run_gracefully
from disco_aws_automation.disco_logging import configure_logging


# R0912 Allow more than 12 branches so we can parse a lot of commands..
# pylint: disable=R0912
def get_parser():
    '''Returns command line parser'''
    parser = argparse.ArgumentParser(description='Asiaq ElasticSearch Creation and Management')
    parser.add_argument('--debug', dest='debug', action='store_const', const=True, default=False,
                        help='Log in debug level')
    parser.add_argument("--env", dest="env", help="Environment name", type=str)

    subparsers = parser.add_subparsers(help='Sub-command help')

    parser_list = subparsers.add_parser("list", help="List all ElasticSearch domains")
    parser_list.set_defaults(mode="list")
    parser_list.add_argument("--endpoint", dest="endpoint", action='store_const', default=False, const=True,
                             help="Display AWS-provided endpoint")

    parser_create = subparsers.add_parser("create",
                                          help="Create an ElasticSearch domain. If no options are provided, "
                                          "default behavior is to create all ElasticSearch domains found in "
                                          "the config.")
    parser_create.set_defaults(mode="create")
    parser_create.add_argument("--name", dest="name", type=str, action="append",
                               help="Name of the ElasticSearch domain")

    parser_update = subparsers.add_parser("update",
                                          help="Update an ElasticSearch domain. If no options are provided, "
                                          "default behavior is to update all ElasticSearch domains found in "
                                          "the config.")
    parser_update.set_defaults(mode="update")
    parser_update.add_argument("--name", dest="name", type=str, action="append",
                               help="Name of the ElasticSearch domain")

    parser_delete = subparsers.add_parser("delete",
                                          help="Delete an ElasticSearch domain. If no options are provided, "
                                          "default behavior is to delete all ElasticSearch domains found in "
                                          "the config.")
    parser_delete.set_defaults(mode="delete")
    parser_delete.add_argument("--name", dest="name", type=str, action="append",
                               help="Name of the ElasticSearch domain")
    parser_delete.add_argument("--all", dest="delete_all", action='store_const', default=False, const=True,
                               help="Delete *all* ElasticSearch domains")

    return parser


def run():
    """Parses command line and dispatches the commands"""
    parser = get_parser()
    args = parser.parse_args()
    configure_logging(args.debug)
    env = args.env
    disco_es = DiscoElasticsearch(env)

    if args.mode == "list":
        entries = disco_es.list(include_endpoint=args.endpoint)
        headers = ["Elastic Search Domain Name", "Internal Name", "Route 53 Endpoint"]
        format_line = u"{0:<28} {1:<15} {2:<35}"
        if args.endpoint:
            format_line += u" {3:<80}"
            headers.append("Elastic Search Endpoint")
        print(format_line.format(*headers), file=sys.stderr)
        for entry in entries:
            values = [entry["elasticsearch_domain_name"], entry["internal_name"], entry["route_53_endpoint"]]
            if args.endpoint:
                values.append(entry["elasticsearch_endpoint"] or u"-")
            print(format_line.format(*values))

    elif args.mode == "create":
        if args.name:
            for name in args.name:
                disco_es.create(name)
        else:
            disco_es.create()

    elif args.mode == "update":
        if args.name:
            for name in args.name:
                disco_es.update(name)
        else:
            disco_es.update()

    elif args.mode == "delete":
        print("Deleting an ElasticSearch domain destroys all automated snapshots of its data. Be careful!")
        if args.name:
            prompt = "Are you sure you want to delete ElasticSearch domains {}? (y/N)".format(args.name)
            response = raw_input(prompt)
            if response.lower().startswith("y"):
                for name in args.name:
                    disco_es.delete(name)
        else:
            scope = "all configured" if not args.delete_all else "*all*"
            prompt = "Are you sure you want to delete {} ElasticSearch domains? (y/N)".format(scope)
            response = raw_input(prompt)
            if response.lower().startswith("y"):
                disco_es.delete(delete_all=args.delete_all)

if __name__ == "__main__":
    run_gracefully(run)
