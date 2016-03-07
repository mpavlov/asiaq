"""
Integration tests for disco_iam.py
"""
from unittest import skip
from test.helpers.integration_helpers import IntegrationTest

LISTUSERS_CMD = "disco_iam.py listusers"
LISTGROUPS_CMD = "disco_iam.py listgroups"
LISTROLES_CMD = "disco_iam.py listroles --federation"
LISTPROVIDERS_CMD = "disco_iam.py listproviders"
LISTINSTANCEPROFILES_CMD = "disco_iam.py listinstanceprofiles"

LISTUSERGROUPS_CMD = "disco_iam.py listusergroups --user_name {username}"
LISTKEYS_CMD = "disco_iam.py listkeys --user_name {username}"
LISTGROUPPOLICIES_CMD = "disco_iam.py listgrouppolicies --group_name {groupname}"
LISTROLEPOLICIES_CMD = "disco_iam.py listrolepolicies --role_name {rolename}"


class DiscoIamTests(IntegrationTest):
    """
    Tests bin/disco_iam.py
    """

    def test_list_user(self):
        """
        List users
        """
        self.assertTrue(self.run_cmd(LISTUSERS_CMD).count("\n") >= 2)

    def test_list_groups(self):
        """
        List groups
        """
        self.assertTrue(self.run_cmd(LISTGROUPS_CMD).count("\n") >= 2)

    def test_list_roles(self):
        """
        List roles
        """
        self.assertTrue(self.run_cmd(LISTROLES_CMD).count("\n") >= 2)

    @skip("enable this if you require identity providers")
    def test_list_providers(self):
        """
        List providers
        """
        self.assertTrue(self.run_cmd(LISTPROVIDERS_CMD).count("\n") >= 1)

    def test_list_instanceprofiles(self):
        """
        List instance profiles
        """
        self.assertTrue(self.run_cmd(LISTINSTANCEPROFILES_CMD).count("\n") >= 1)

    def test_list_usergroups(self):
        """
        List a users group membership
        """
        user = self.run_cmd(LISTUSERS_CMD).split()[0]
        command = LISTGROUPS_CMD.format(username=user)
        self.assertTrue(self.run_cmd(command).count("\n") >= 2)

    def test_list_userkeys(self):
        """
        List a users keys
        """
        user = self.run_cmd(LISTUSERS_CMD).split()[0]
        command = LISTKEYS_CMD.format(username=user)
        self.assertTrue(self.run_cmd(command).count("\n") >= 1)

    def test_list_grouppolicies(self):
        """
        List policies of a group
        """
        group = self.run_cmd(LISTGROUPS_CMD).split()[0]
        command = LISTGROUPPOLICIES_CMD.format(groupname=group)
        self.assertTrue(self.run_cmd(command).count("\n") >= 1)

    def test_list_rolepolicies(self):
        """
        List policies of a role
        """
        role = self.run_cmd(LISTROLES_CMD).split()[0]
        command = LISTROLEPOLICIES_CMD.format(rolename=role)
        self.assertTrue(self.run_cmd(command).count("\n") >= 1)
