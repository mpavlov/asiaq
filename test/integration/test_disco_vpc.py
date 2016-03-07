"""
Creates then destroys a vpc environment ensuring that both operations
succeed
"""

from unittest import TestCase
from test.helpers.disco_env_helpers import DiscoEnv
from test.helpers.integration_helpers import IntegrationTest


class TestDiscoVPCEnv(IntegrationTest, DiscoEnv, TestCase):
    """
    Test VPC creation and destruction
    """

    def test_create_destroy_vpc(self):
        """
        Create a vpc then destroy it
        """
        # Create env VPC
        self.create_env()
        self.assertTrue(self.env_exists())

        # Clean up our mess
        self.destroy_env()
        self.assertFalse(self.env_exists())
