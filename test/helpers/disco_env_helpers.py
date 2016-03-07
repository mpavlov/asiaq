"""
Provides abstraction for creating and destroying disco environments.

Intended to be inherited together with TestCase
"""


import os
from re import search, MULTILINE
from random import randint

DISCO_VPC_COMMAND = "disco_vpc_ui.py"
DISCO_AWS_COMMAND = "disco_aws.py"
PIPELINES_PATH = os.getenv("ASIAQ_CONFIG", ".") + "/pipelines"
MINIMAL_PIPELINE_CSV = PIPELINES_PATH + "/minimal.csv"


# TODO this module overlaps with test/helpers/integration_helpers.py; merge them?


class DiscoEnv(object):
    """
    Abstact out command line based invocation of common environment operations
    """

    def setUp(self):
        """
        Generate random name for integration test env
        """
        self.env_name = "integrationtest{0}".format(randint(10000, 99999))

    def tearDown(self):
        """
        Destroy env if exists, so we don't leave anything behind after test
        """
        if self.env_exists():
            self.destroy_env()

    def env_exists(self):
        """
        True if envionment env_name exists
        """
        output = self.run_cmd([DISCO_VPC_COMMAND, "list"])
        env_regex = r"^vpc-[0-9a-f]+\s+{0}$".format(self.env_name)
        return bool(search(env_regex, output, MULTILINE))

    def create_env(self):
        """
        Destroy an env disco_vpc.py. Return output
        """
        self.run_cmd([
            DISCO_VPC_COMMAND, "create",
            "--name", self.env_name,
            "--type", "sandbox"
        ])

    def destroy_env(self):
        """
        Destroy an env and all its resourcs with disco_vpc.py. Return output
        """
        self.run_cmd([
            DISCO_VPC_COMMAND, "destroy",
            "--name", self.env_name,
        ])

    def spinup(self):
        """
        Spinup hosts from minimal pipeline def with disco_aws.py. Return output
        """
        self.run_cmd([
            DISCO_AWS_COMMAND,
            "--env", self.env_name,
            "spinup",
            "--pipeline", MINIMAL_PIPELINE_CSV,
        ])

    def spindown(self):
        """
        Return output from disco_aws.py spindown
        """
        self.run_cmd([
            DISCO_AWS_COMMAND,
            "--env", self.env_name,
            "spindown",
            "--pipeline", MINIMAL_PIPELINE_CSV,
        ])

    def instances(self):
        """
        Return output from disco_aws.py listhosts
        """
        return self.run_cmd([
            DISCO_AWS_COMMAND,
            "--env", self.env_name,
            "listhosts"
        ])

    def approx_instance_count(self):
        """
        Return approx number of running instances
        """
        return len(self.instances().splitlines())

    def create_mini_env(self):
        """
        Create an env with minimal required number of hosts
        """
        # Create env VPC
        self.create_env()

        # Start instances
        self.spinup()
