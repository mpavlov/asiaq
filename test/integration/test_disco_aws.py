"""
Test functionality provided by disco_aws.py things like:
provision, terminate, isready, exec ...
"""

from unittest import TestCase
from re import search, MULTILINE
from time import time, sleep

from test.helpers.disco_env_helpers import DiscoEnv, DISCO_AWS_COMMAND
from test.helpers.integration_helpers import IntegrationTest


class TestDiscoAWS(IntegrationTest, DiscoEnv, TestCase):
    """
    Test disco_aws.py operations
    """

    def setUp(self):
        """
        Create VPC and start up minimal env for our tests.
        """
        super(TestDiscoAWS, self).setUp()
        self.create_mini_env()

    def isready(self, hostclass):
        """
        Return true if all instances of a hostclass are reported ready by disco_aws.py
        """
        output = self.run_cmd([
            DISCO_AWS_COMMAND,
            "--env", self.env_name,
            "isready",
            "--hostclass", hostclass
        ])
        isready_regex = r"i-[0-9a-f]+ is ready$"
        return search(isready_regex, output, MULTILINE)

    def test_isready(self):
        """
        Instance isready test
        """
        max_wait = 300
        max_time = time() + max_wait
        hostclass = "mhcs3proxy"

        last_status = self.isready(hostclass)
        while time() < max_time and not last_status:
            sleep(5)
            last_status = self.isready(hostclass)

        self.assertTrue(last_status)

    def provision(self, hostclass):
        """
        Provision instance of hostclass, return false on error

        $ disco_aws.py --env ci provision --hostclass mhcntp --min-size 1 --desired-size 1
        INFO:root:Waiting for 1 host[s] to pass smoke test
        INFO:root:Smoke tested 1 host[s] in 80 seconds
        Instance:i-919e3799
        """
        self.run_cmd([
            DISCO_AWS_COMMAND,
            "--env", self.env_name,
            "provision",
            "--hostclass", hostclass,
            "--instance-type", "c3.large",
            "--min-size", "1",
            "--desired-size", "1"
        ])

    def terminate(self, hostclass):
        """
        Terminate all instances of a hostclass
        """
        output = self.run_cmd([
            DISCO_AWS_COMMAND,
            "--env", self.env_name,
            "terminate",
            "--hostclass", hostclass
        ])
        provision_regex = r"Terminated: .*Instance:i-[0-9a-f]+"
        return search(provision_regex, output, MULTILINE)

    def deprovision(self, hostclass):
        """
        Deprovision a hostclass
        """
        self.run_cmd([
            DISCO_AWS_COMMAND,
            "--env", self.env_name,
            "provision",
            "--hostclass", hostclass,
            "--instance-type", "c3.large",
            "--min-size", "0",
            "--desired-size", "0",
            "--max-size", "0"
        ])

    def test_provision_terminate(self):
        """
        Start instance with provision and then terminate it
        """
        hostclass = "mhcntp"
        self.provision(hostclass)
        self.assertRegexpMatches(self.instances(), hostclass)
        self.terminate(hostclass)
        self.assertNotRegexpMatches(self.instances(), hostclass)
        self.deprovision(hostclass)

    def ssh_exec(self):
        """
        Run ls on adminproxy return True if there were no errors
        disco_aws.py --env ci exec --command "ls /" --hostclass mhcadminproxy --user disco_tester
        """
        self.run_cmd([
            DISCO_AWS_COMMAND,
            "--env", self.env_name,
            "exec",
            "--command", "ls /",
            "--hostclass", "mhcadminproxy",
            "--user", "disco_tester"
        ])

    def test_ssh_exec(self):
        """
        Run a trivial command on a host with disco_aws
        """
        self.ssh_exec()
