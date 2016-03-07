#!/usr/bin/env python
"""
Command line interface for manipulating IAM
"""

from __future__ import print_function
import argparse

from disco_aws_automation import DiscoIAM
from disco_aws_automation.disco_aws_util import run_gracefully
from disco_aws_automation.disco_logging import configure_logging


# R0912 Allow more than 12 branches so we can parse a lot of commands..
# R0914 Allow more than 15 local variables so we can parse a lot of commands..
# R0915 Allow more than 50 statements so we can parse a lot of commands..
# pylint: disable=R0912,R0914,R0915
def get_parser():
    '''Returns command line parser'''
    parser = argparse.ArgumentParser(description='Disco AWS IAM management')
    parser.add_argument('--debug', dest='debug', action='store_const', const=True, default=False,
                        help='Log in debug level.')
    subparsers = parser.add_subparsers(help='Sub-command help')

    parser_listgroups = subparsers.add_parser("listgroups", help="List disco groups")
    parser_listgroups.set_defaults(mode="listgroups")

    parser_listgrouppolicies = subparsers.add_parser("listgrouppolicies", help="List group policies")
    parser_listgrouppolicies.set_defaults(mode="listgrouppolicies")
    parser_listgrouppolicies.add_argument("--group_name", dest="group_name", required=True,
                                          help="Group Name", type=str)

    parser_getgrouppolicy = subparsers.add_parser("getgrouppolicy", help="Get group policy")
    parser_getgrouppolicy.set_defaults(mode="getgrouppolicy")
    parser_getgrouppolicy.add_argument("--group_name", dest="group_name", required=True,
                                       help="Group Name", type=str)
    parser_getgrouppolicy.add_argument("--policy_name", dest="policy_name", required=True,
                                       help="Policy Name", type=str)

    parser_listusers = subparsers.add_parser("listusers", help="List users")
    parser_listusers.set_defaults(mode="listusers")

    parser_listusergroups = subparsers.add_parser("listusergroups", help="List all groups for user")
    parser_listusergroups.set_defaults(mode="listusergroups")
    parser_listusergroups.add_argument(
        "--user_name", dest="user_name", required=True, help="User Name", type=str
    )

    parser_listkeys = subparsers.add_parser("listkeys", help="List existing API access keys")
    parser_listkeys.set_defaults(mode="listkeys")
    parser_listkeys.add_argument("--user_name", dest="user_name", required=True,
                                 help="User Name", type=str)

    parser_createkey = subparsers.add_parser("createkey", help="Create new API access key")
    parser_createkey.set_defaults(mode="createkey")
    parser_createkey.add_argument("--user_name", dest="user_name", required=True,
                                  help="User Name", type=str)

    parser_removekey = subparsers.add_parser("removekey", help="Remove existing API access key")
    parser_removekey.set_defaults(mode="removekey")
    parser_removekey.add_argument("--user_name", dest="user_name", required=True,
                                  help="User Name", type=str)
    parser_removekey.add_argument("--access_key_id", dest="access_key_id", required=True,
                                  help="Access Key ID", type=str)

    parser_activatekey = subparsers.add_parser("activatekey", help="Remove existing API access key")
    parser_activatekey.set_defaults(mode="activatekey")
    parser_activatekey.add_argument("--user_name", dest="user_name", required=True,
                                    help="User Name", type=str)
    parser_activatekey.add_argument("--access_key_id", dest="access_key_id", required=True,
                                    help="Access Key ID", type=str)

    parser_deactivatekey = subparsers.add_parser("deactivatekey", help="Remove existing API access key")
    parser_deactivatekey.set_defaults(mode="deactivatekey")
    parser_deactivatekey.add_argument("--user_name", dest="user_name", required=True,
                                      help="User Name", type=str)
    parser_deactivatekey.add_argument("--access_key_id", dest="access_key_id", required=True,
                                      help="Access Key ID", type=str)

    parser_listinstanceprofiles = subparsers.add_parser("listinstanceprofiles",
                                                        help="List existing instance profiles")
    parser_listinstanceprofiles.set_defaults(mode="listinstanceprofiles")

    parser_listroles = subparsers.add_parser(
        "listroles", help="List existing IAM roles and, optionally, their federation status"
    )
    parser_listroles.set_defaults(mode="listroles")
    parser_listroles.add_argument(
        '--federation', dest='federation', action='store_const',
        const=True, default=False, help="Print federation status for roles"
    )

    parser_listrolepolicies = subparsers.add_parser(
        "listrolepolicies", help="List the policies of an IAM role")
    parser_listrolepolicies.set_defaults(mode="listrolepolicies")
    parser_listrolepolicies.add_argument("--role_name", dest="role_name", required=True,
                                         help="Role name", type=str)

    parser_decode = subparsers.add_parser(
        "decode", help="Decodes an encoded AWS failure message, such as one "
        "accompanying an UnauthorizedOperation"
    )
    parser_decode.set_defaults(mode="decode")
    parser_decode.add_argument("--message", dest="message", required=True, help="Encoded message", type=str)

    parser_update = subparsers.add_parser(
        "update", help="Update all AWS IAM configuration to reflect whats in configuration"
    )
    parser_update.set_defaults(mode="update")
    # TODO raname from environment to something more like account type
    parser_update.add_argument("--environment", dest="environment", required=True,
                               help="Environment name (e.g., dev, prod)", type=str)

    parser_listproviders = subparsers.add_parser("listproviders", help="List all SAML providers")
    parser_listproviders.set_defaults(mode="listproviders")

    return parser


def run():
    """Parses command line and dispatches the commands"""
    parser = get_parser()
    args = parser.parse_args()
    configure_logging(args.debug)

    iam = DiscoIAM()
    if args.mode == "listgroups":
        print("\n".join(sorted(iam.list_groups())))
    elif args.mode == "listgrouppolicies":
        print("\n".join(sorted(iam.list_group_policies(args.group_name))))
    elif args.mode == "getgrouppolicy":
        print(iam.get_group_policy(args.group_name, args.policy_name))
    elif args.mode == "listusers":
        iam.print_users()
    elif args.mode == "listusergroups":
        print("\n".join(sorted(iam.list_user_groups(args.user_name))))
    elif args.mode == "listkeys":
        key_fmt = "{0.user_name:<30}\t{0.access_key_id}\t{0.status:<8}\t{0.create_date}"
        keys = [key_fmt.format(key) for key in iam.list_access_keys(args.user_name)]
        print("\n".join(keys))
    elif args.mode == "createkey":
        iam.create_access_key(args.user_name)
    elif args.mode == "removekey":
        iam.remove_access_key(args.user_name, args.access_key_id)
    elif args.mode == "activatekey":
        iam.activate_access_key(args.user_name, args.access_key_id)
    elif args.mode == "deactivatekey":
        iam.deactivate_access_key(args.user_name, args.access_key_id)
    elif args.mode == "listinstanceprofiles":
        print("\n".join(sorted(iam.listinstanceprofiles())))
    elif args.mode == "listroles":
        for role in iam.listroles():
            output = role.role_name
            if args.federation:
                is_federated = role.assume_role_policy_document.is_federated()
                output += "\t{0}".format(
                    "federated" if is_federated else "unfederated"
                )
            print(output)
    elif args.mode == "listrolepolicies":
        print("\n".join(iam.listrolepolicies(args.role_name)))
    elif args.mode == "decode":
        iam.decode_message(args.message)
    elif args.mode == "update":
        # We don't use saml for api level access, I'm not sure
        # if reloading providers as such is safe. Does policy expire
        # as soon as trust is removed, probably not?
        iam.set_environment(args.environment)

        iam.delete_saml_providers()
        iam.create_saml_provider()

        iam.reapply_user_policies()
        iam.reapply_group_members()
        iam.reapply_instance_policies()
    elif args.mode == "listproviders":
        for provider in iam.list_saml_providers():
            print(provider.arn)


if __name__ == "__main__":
    run_gracefully(run)
