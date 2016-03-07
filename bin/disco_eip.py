#!/usr/bin/env python
"""
Command line tool for working with EIP's.
"""

from __future__ import print_function
import argparse
import sys

from disco_aws_automation import DiscoEIP
from disco_aws_automation.disco_aws_util import run_gracefully
from disco_aws_automation.disco_logging import configure_logging


def parse_arguments():
    """Read in options passed in over command line"""
    parser = argparse.ArgumentParser(description='Disco EIP automation')
    parser.add_argument('--debug', dest='debug', action='store_const',
                        const=True, default=False, help='Log in debug level.')
    subparsers = parser.add_subparsers(help='Sub-command help')

    parser_list_eips = subparsers.add_parser('list', help='List all allocated EIPs')
    parser_list_eips.set_defaults(mode="list")

    parser_allocate_eip = subparsers.add_parser('allocate', help='Allocate a new EIP address for use.')
    parser_allocate_eip.set_defaults(mode="allocate")

    parser_release_eip = subparsers.add_parser('release', help='Release an allocated & unused EIP.')
    parser_release_eip.set_defaults(mode="release")
    parser_release_eip.add_argument('--eip', required=True,
                                    help='Which address to release.')
    parser_release_eip.add_argument('--force', action='store_const',
                                    const=True, default=False, help='Release EIP even if it is assigned.')

    return parser.parse_args()


def run():
    """Parses command line and dispatches the commands"""
    args = parse_arguments()
    configure_logging(args.debug)

    deip = DiscoEIP()

    if args.mode == "list":
        for eip in sorted(deip.list()):
            print("{0}\t{1}".format(eip.public_ip, eip.instance_id if eip.instance_id else "-"))

    elif args.mode == "allocate":
        eip = deip.allocate()
        print(eip.public_ip)

    elif args.mode == "release":
        if not deip.release(args.eip, args.force):
            sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    run_gracefully(run)
