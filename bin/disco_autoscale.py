#!/usr/bin/env python
"""
Command line tool for working with autoscaling groups and launch configurations.
"""

from __future__ import print_function
import argparse
import sys

from disco_aws_automation import DiscoAutoscale, read_config
from disco_aws_automation.disco_aws_util import run_gracefully
from disco_aws_automation.disco_logging import configure_logging


def parse_arguments():
    """Read in options passed in over command line"""
    parser = argparse.ArgumentParser(description='Disco autoscaling automation')
    parser.add_argument('--debug', dest='debug', action='store_const',
                        const=True, default=False, help='Log in debug level.')
    parser.add_argument('--env', dest='env', type=str, default=None,
                        help="Environment. Normally, the name of a VPC. Default is taken from config file.")
    subparsers = parser.add_subparsers(help='Sub-command help')

    # Autoscaling group commands

    parser_list_groups = subparsers.add_parser('listgroups', help='List all autoscaling groups')
    parser_list_groups.set_defaults(mode="listgroups")

    parser_clean_groups = subparsers.add_parser('cleangroups', help='Delete unused autoscaling groups')
    parser_clean_groups.set_defaults(mode="cleangroups")

    parser_delete_group = subparsers.add_parser('deletegroup', help='Delete autoscaling group')
    parser_delete_group.set_defaults(mode="deletegroup")
    parser_delete_group.add_argument("--force", action='store_true',
                                     required=False, default=False, help='Force deletion')
    parser_delete_specifier_group = parser_delete_group.add_mutually_exclusive_group(required=True)
    parser_delete_specifier_group.add_argument("--hostclass", default=None, help='Name of the hostclass')
    parser_delete_specifier_group.add_argument("--name", default=None,
                                               help='Name of the autoscaling group')

    # Launch Configuration commands

    parser_list_configs = subparsers.add_parser('listconfigs', help='List all launch configurations')
    parser_list_configs.set_defaults(mode="listconfigs")

    parser_clean_configs = subparsers.add_parser('cleanconfigs', help='Delete unused launch configurations')
    parser_clean_configs.set_defaults(mode="cleanconfigs")

    parser_delete_config = subparsers.add_parser('deleteconfig', help='Delete launch configuration')
    parser_delete_config.set_defaults(mode="deleteconfig")
    parser_delete_config.add_argument("--config", required=True, help='Name of launch configuration')

    # Autoscaling policy commands

    parser_list_policies = subparsers.add_parser('listpolicies', help='List all autoscaling policies')
    parser_list_policies.set_defaults(mode="listpolicies")

    parser_create_policy = subparsers.add_parser('createpolicy', help='Create autoscaling policy')
    parser_create_policy.set_defaults(mode="createpolicy")
    parser_create_policy.add_argument("--policy_name", required=True, help='Name of autoscaling policy')
    parser_create_policy.add_argument("--group_name", required=True, help='Name of autoscaling group')
    parser_create_policy.add_argument("--adjustment", required=True,
                                      help='By how many instances to adjust capacity (can be negative)')
    parser_create_policy.add_argument("--cooldown", default=120, required=False,
                                      help='Cooldown (sec) before policy can trigger again (default: 120)')

    parser_delete_policy = subparsers.add_parser('deletepolicy', help='Delete autoscaling policy')
    parser_delete_policy.set_defaults(mode="deletepolicy")
    parser_delete_policy.add_argument("--policy_name", required=True, help='Name of autoscaling policy')
    parser_delete_policy.add_argument("--group_name", required=True, help='Name of autoscaling group')

    return parser.parse_args()


# R0912 Allow more than 12 branches so we can parse a lot of commands..
# pylint: disable=R0912
def run():
    """Parses command line and dispatches the commands"""
    config = read_config()
    args = parse_arguments()
    configure_logging(args.debug)

    environment_name = args.env or config.get("disco_aws", "default_environment")

    autoscale = DiscoAutoscale(environment_name)

    # Autoscaling group commands
    if args.mode == "listgroups":
        format_str = "{0} {1:12} {2:3} {3:3} {4:3} {5:3}"
        groups = autoscale.get_existing_groups()
        instances = autoscale.get_instances()
        if args.debug:
            print(format_str.format(
                "Name".ljust(26 + len(environment_name)), "AMI", "min", "des", "max", "cnt"))
        for group in groups:
            launch_cfg = list(autoscale.get_configs(names=[group.launch_config_name]))
            image_id = launch_cfg[0].image_id if len(launch_cfg) else ""
            group_str = group.name.ljust(26 + len(environment_name))
            group_cnt = len([instance for instance in instances if instance.group_name == group.name])
            print(format_str.format(group_str, image_id,
                                    group.min_size, group.desired_capacity, group.max_size,
                                    group_cnt))
    elif args.mode == "cleangroups":
        autoscale.clean_groups()
    elif args.mode == "deletegroup":
        autoscale.delete_groups(hostclass=args.hostclass, group_name=args.name, force=args.force)

    # Launch Configuration commands
    elif args.mode == "listconfigs":
        for config in autoscale.get_configs():
            print("{0:24} {1}".format(config.name, config.image_id))
    elif args.mode == "cleanconfigs":
        autoscale.clean_configs()
    elif args.mode == "deleteconfig":
        autoscale.delete_config(args.config)

    # Scaling policy commands
    elif args.mode == "listpolicies":
        policies = autoscale.list_policies()
        for policy in policies:
            print("{0:30} {1}".format(policy.name, policy.policy_arn))
    elif args.mode == "createpolicy":
        autoscale.create_policy(args.policy_name, args.group_name, args.adjustment, args.cooldown)
    elif args.mode == "deletepolicy":
        autoscale.delete_policy(args.policy_name, args.group_name)

    sys.exit(0)

if __name__ == "__main__":
    run_gracefully(run)
