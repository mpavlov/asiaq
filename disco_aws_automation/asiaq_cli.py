"""
Code for a conventional entry-point based command-line interface.
"""

import argparse
import os
from logging import getLogger

from . import DiscoVPC, DiscoAWS, read_config
from .disco_aws_util import read_pipeline_file, graceful
from .disco_logging import configure_logging

PEERING_SECTION = 'peerings'
BLACK_LIST_S3_CONTAINER = "zookeeper-sync-black-lists"
BLACK_LIST_BUCKET = 'us-west-2.mclass.sandboxes'


@graceful
def sandbox_command():
    args = _command_init("Create and populate a sandbox for local development and testing.",
                         _sandbox_arg_init)
    _do_sandbox(args)


@graceful
def super_command():
    parser = argparse.ArgumentParser(description="All the Asiaq Things")
    _base_arg_init(parser)
    subcommands = parser.add_subparsers(dest="command")
    sandbox_parser = subcommands.add_parser(
        "sandbox", description="Create and populate a sandbox for local development and testing.")
    _sandbox_arg_init(sandbox_parser)
    args = parser.parse_args()
    configure_logging(debug=args.debug)

    if "sandbox" == args.command:
        _do_sandbox(args)


def _command_init(description, argparse_setup_func):
    parser = argparse.ArgumentParser(description=description)
    _base_arg_init(parser)
    argparse_setup_func(parser)
    args = parser.parse_args()
    configure_logging(debug=args.debug)
    return args


def _do_sandbox(args):
    logger = getLogger("asiaq_sandbox")
    logger.debug("Updating sandbox %s", args.sandbox_name)
    sandbox_name = args.sandbox_name
    pipeline_file = os.path.join("sandboxes", sandbox_name, "pipeline.csv")

    aws_config = read_config()
    hostclass_dicts = read_pipeline_file(pipeline_file)

    _update_blacklist(sandbox_name)

    logger.info("Checking if environment '%s' already exists", sandbox_name)
    vpc = DiscoVPC.fetch_environment(environment_name=sandbox_name)
    if vpc:
        logger.info("Sandbox %s already exists: updating it.", sandbox_name)
        vpc.update()
    else:
        vpc = DiscoVPC(environment_name=sandbox_name,
                       environment_type='sandbox',
                       defer_creation=True)
        peering_found = False
        peering_prefixes = ("*:sandbox", ("%s:sandbox" % sandbox_name))
        if vpc.config.has_section(PEERING_SECTION):
            for peering in vpc.config.options(PEERING_SECTION):
                peers = vpc.config.get(PEERING_SECTION, peering)
                logger.debug("Peering config: %s = '%s'", peering, peers)
                if peers.startswith(peering_prefixes):
                    peering_found = True
                    break
                elif peering.endswith("_99"):
                    raise Exception("oh this is going to be a problem")
        else:
            logger.warn("No peering section found")
            vpc.config.add_section(PEERING_SECTION)
        if not peering_found:
            logger.warn("Need to update peering config for %s", sandbox_name)
            vpc.config.set(PEERING_SECTION, "connection_99", "%s:sandbox/intranet ci/intranet" % sandbox_name)
        vpc.create()

    logger.debug("Hostclass definitions for spin-up: %s", hostclass_dicts)
    DiscoAWS(aws_config, vpc=vpc).spinup(hostclass_dicts)


def _update_blacklist(sandbox_name):
    local_blacklist = os.path.join("sandboxes", sandbox_name, "blacklist")
    remote_blacklist = os.path.join(BLACK_LIST_S3_CONTAINER, sandbox_name)
    logger.info("Uploading blacklist file %s to %s", local_blacklist, remote_blacklist)
    sandbox_s3_bucket = boto3.resource("s3").Bucket(name=BLACK_LIST_BUCKET)
    sandbox_s3_bucket.upload_file(local_blacklist, remote_blacklist)


def _sandbox_arg_init(parser):
    "Add arg options for the sandbox command, for top-level or subcommand parser."
    parser.add_argument("sandbox_name")


def _base_arg_init(parser):
    parser.add_argument("--debug", "-d", action='store_const', const=True,
                        help='Log at DEBUG level.')
