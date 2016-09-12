#!/usr/bin/env python
"""
Command line tool for provisioning SSM documents
"""

import argparse
from disco_aws_automation.disco_aws_util import run_gracefully
from disco_aws_automation import DiscoSSM
from disco_aws_automation.disco_logging import configure_logging


def parse_args():
    """Returns command line parser"""
    parser = argparse.ArgumentParser(description='Disco SSM provisioning')
    parser.add_argument('--debug', dest='debug', action='store_const',
                        const=True, default=False, help='Log in debug level.')
    subparsers = parser.add_subparsers(help='Sub-command help')

    # list mode
    parser_list = subparsers.add_parser("list", help="List all SSM documents")
    parser_list.set_defaults(mode="list")
    parser_list.add_argument("--headers", dest="headers", required=False, default=False, action="store_true",
                             help="Option to show headers in the output")

    # get mode
    parser_get = subparsers.add_parser("get", help="Print out the content of a SSM document")
    parser_get.set_defaults(mode="get")
    parser_get.add_argument("--name", dest="name", required=True, type=str,
                            help="The name of the document")

    # update mode
    parser_update = subparsers.add_parser("update",
                                          help="Update all SSM documents to reflect what's in configuration")
    parser_update.set_defaults(mode="update")
    parser_update.add_argument('--wait', dest='wait', action='store_const', const=True, default=False,
                               help="Wait for all the updates to finish before existing the command")
    parser_update.add_argument('--dry-run', dest='dry_run', action='store_const', const=True,
                               default=False, help="Test run the update command")

    return parser.parse_args()


def list_documents(disco_ssm, headers=False):
    """ Lists all the asiaq managed SSM documents """
    docs = sorted(disco_ssm.get_all_documents(),
                  key=lambda doc: doc["Name"])
    if headers:
        print u"{0:<30} {1:<20} {2}".format("Name", "Owner", "Platforms")

    for doc in docs:
        line = u"{0:<30} {1:<20} {2}".format(doc["Name"],
                                             doc["Owner"],
                                             ",".join(doc["PlatformTypes"]))
        print line


def print_content(disco_ssm, name):
    """ Prints out the content of a SSM document """
    doc = disco_ssm.get_document_content(name)
    if doc:
        print doc


def update_documents(disco_ssm, wait, dry_run):
    """ Update all SSM documents to reflect what's in configuration """
    disco_ssm.update(wait, dry_run)


def run():
    """ Parses command line and dispatches the commands disco_dynamodb.py list """
    args = parse_args()
    configure_logging(args.debug)

    disco_ssm = DiscoSSM()

    if args.mode == "list":
        list_documents(disco_ssm, args.headers)
    elif args.mode == "get":
        print_content(disco_ssm, args.name)
    elif args.mode == "update":
        update_documents(disco_ssm, args.wait, args.dry_run)


if __name__ == "__main__":
    run_gracefully(run)
