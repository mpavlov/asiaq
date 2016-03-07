"""
Tests of disco_rds
"""
import unittest
from mock import MagicMock

from disco_aws_automation.disco_rds import DiscoRDS


TEST_ENV_NAME = 'unittestenv'
TEST_VPC_ID = 'vpc-56e10e3d'  # the hard coded VPC Id that moto will always return


def _get_vpc_mock():
    "Nastily copied from test_disco_elb"
    vpc_mock = MagicMock()
    vpc_mock.environment_name = TEST_ENV_NAME
    vpc_mock.vpc = MagicMock()
    vpc_mock.vpc.id = TEST_VPC_ID
    return vpc_mock


class DiscoRDSTests(unittest.TestCase):
    '''Test DiscoRDS class'''

    def test_get_db_parameter_group_family(self):
        "Tests that get_db_parameter_group_family handles all the expected cases"
        rds = DiscoRDS(_get_vpc_mock())
        self.assertEquals("postgresql9.3", rds.get_db_parameter_group_family("postgresql", "9.3.1"))
        self.assertEquals("oracle-se2-12.1", rds.get_db_parameter_group_family("oracle-se2", "12.1.0.2.v2"))
        self.assertEquals("mysql123.5", rds.get_db_parameter_group_family("MySQL", "123.5"))


if __name__ == '__main__':
    unittest.main()
