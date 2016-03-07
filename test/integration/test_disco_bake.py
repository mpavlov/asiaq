"""
Integration tests for disco_bake.py
"""
import re
from unittest import skip

from disco_aws_automation.resource_helper import keep_trying
from test.helpers.integration_helpers import IntegrationTest, cleanup_amis, TEST_HOSTCLASS


class DiscoBakeTests(IntegrationTest):
    '''
    Tests bin/disco_bake.py
    '''

    @skip("This test currently runs for a good half hour, and if it fails it's usually due to config error")
    @cleanup_amis
    def test_phase1_bake_succeeds(self, captured_stdout):
        """
        phase1 bake of a hostclass creates an AMI
        """
        output = self._bake(captured_stdout, "bake")

        ami_id = self.get_ami_id(output)
        self.assertIsNotNone(ami_id)
        self._verify_ami_in_listamis(captured_stdout, ami_id)

    @skip("There is a race condition between this test and the test-and-promote job.")
    @cleanup_amis
    def test_cleanupamis(self, captured_stdout):
        """
        phase2 bake of a hostclass creates an AMI, and cleanupamis can delete the freshly created ami
        """
        output = self._bake(captured_stdout, "bake", "--use-local-ip", "--hostclass", TEST_HOSTCLASS)

        ami_id = self.get_ami_id(output)
        self.assertIsNotNone(ami_id)
        self._verify_ami_in_listamis(captured_stdout, ami_id)

        # Ensure test-and-promote didn't just promote our ami, and unpromote the stage if it did
        self._bake(captured_stdout, "promote", "--ami", ami_id, "--stage", "untested")

        # Try cleaning up our new ami
        output = self._bake(captured_stdout,
                            "cleanupamis",
                            "--keep", "0",
                            "--age", "0",
                            "--hostclass", TEST_HOSTCLASS,
                            "--stage", "untested")
        self.assertIsNotNone(output)

        # Wait for ami to go away
        keep_trying(240, self._check_ami_gone, ami_id)

    @cleanup_amis
    def test_promote(self, captured_stdout):
        '''Verify we can bake a pahse 2 AMI and promote it'''
        output = self._bake(captured_stdout, "bake", "--use-local-ip", "--hostclass", TEST_HOSTCLASS)

        ami_id = self.get_ami_id(output)
        self.assertIsNotNone(ami_id)
        self._verify_ami_in_listamis(captured_stdout, ami_id, stage="untested")

        output = self._bake(captured_stdout,
                            "promote",
                            "--ami", ami_id,
                            "--stage", "tested")

        self._verify_ami_in_listamis(captured_stdout, ami_id, stage="tested")

    def _verify_ami_in_listamis(self, captured_stdout, ami_id, stage=None):
        if stage:
            output = self._bake(captured_stdout, "listamis", "--ami", ami_id, "--stage", stage)
        else:
            output = self._bake(captured_stdout, "listamis", "--ami", ami_id)

        self.assertIsNotNone(output)
        match = re.search(ami_id, output)
        self.assertTrue(match)

    def _check_ami_gone(self, ami_id):
        images = self.connect.get_all_images(image_ids=[ami_id])
        if images:
            raise RuntimeError("AMI %s still there" % ami_id)

    def _bake(self, captured_stdout, *args):
        return self.run_cmd(("disco_bake.py", "--debug") + args, captured_stdout)
