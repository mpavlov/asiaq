"""
Integration tests for disco_accounts.py
"""
import os
from test.helpers.integration_helpers import IntegrationTest


TEST_ACCOUNT_NAME = "test_account"
TEST_ACCOUNT_S3_USER_KEY = "accounts/users/%s" % TEST_ACCOUNT_NAME
TEST_ACCOUNT_S3_GROUP_KEY = "accounts/groups/%s" % TEST_ACCOUNT_NAME
TEST_ACCOUNT_S3_KEYS = [TEST_ACCOUNT_S3_USER_KEY, TEST_ACCOUNT_S3_GROUP_KEY]
CREATE_CMD = "disco_accounts.py adduser --name %s --password password" % TEST_ACCOUNT_NAME
EDIT_CMD = "disco_accounts.py edituser --name %s" % TEST_ACCOUNT_NAME
DISABLE_CMD = "disco_accounts.py edituser --name %s --active no" % TEST_ACCOUNT_NAME
REMOVE_CMDS = ["disco_creds.py delete --key %s" % _key for _key in TEST_ACCOUNT_S3_KEYS]


class DiscoAccountsTests(IntegrationTest):
    """
    Tests bin/disco_accounts.py
    """

    def _create_test_account(self):
        old_editor = os.environ.get("EDITOR", "")
        os.environ["EDITOR"] = "true"  # make sure we don't open an interactive editor during adduser
        output = self.run_cmd(CREATE_CMD.split())
        os.environ["EDITOR"] = old_editor
        return output

    def _remove_test_account(self):
        for cmd in REMOVE_CMDS:
            self.run_cmd(cmd.split())

    def _get_test_account_settings(self):
        old_editor = os.environ.get("EDITOR", "")
        os.environ["EDITOR"] = "cat"  # print contents instead of editing account file
        output = self.run_cmd(EDIT_CMD.split())
        os.environ["EDITOR"] = old_editor
        return output

    def _is_test_account_active(self):
        return "active = yes" in self._get_test_account_settings()

    def _disable_test_account(self):
        self.run_cmd(DISABLE_CMD.split())

    def test_create_account(self):
        """
        we can create a new unix user account
        """
        self._create_test_account()

        try:
            user_output = self.run_cmd("disco_accounts.py listusers".split())
            group_output = self.run_cmd("disco_accounts.py listgroups".split())
            self.assertIn(TEST_ACCOUNT_NAME, user_output)
            self.assertIn(TEST_ACCOUNT_NAME, group_output)
        finally:
            self._remove_test_account()

    def test_disable_account(self):
        """
        we can disable an existing active account
        """
        self._create_test_account()

        try:
            self.assertTrue(self._is_test_account_active())
            self._disable_test_account()
            self.assertFalse(self._is_test_account_active())
        finally:
            self._remove_test_account()
