"""Tests of disco_metanetwork"""
from unittest import TestCase

from mock import MagicMock, call, patch, create_autospec
from moto import mock_ec2

from disco_aws_automation.disco_metanetwork import DiscoMetaNetwork

from test.helpers.patch_disco_aws import (patch_disco_aws,
                                          get_default_config_dict,
                                          get_mock_config,
                                          TEST_ENV_NAME)


MOCK_ROUCE_FILTER = {"vpc-id": "mock_vpc_id",
                     "tag:meta_network": TEST_ENV_NAME}

def _get_vpc_mock():
    ret = MagicMock()
    ret.vpc_filter.return_value = {"vpc-id": MOCK_ROUCE_FILTER["vpc-id"]}
    ret.vpc = MagicMock()
    ret.vpc.connection = MagicMock()
    ret.vpc.connection.get_all_zones.return_value = ["aws-zone1", "aws-zone2"]
    ret.vpc.connection.get_all_security_groups.return_value = MagicMock()
    return ret


class DiscoMetaNetworkTests(TestCase):
    """Test DiscoMetaNetwork"""

    @mock_ec2
    def test_meta_network_create(self):
        mock_vpc = _get_vpc_mock()
        meta_network = DiscoMetaNetwork(TEST_ENV_NAME, mock_vpc)
        meta_network.create()
        mock_vpc.vpc.connection.get_all_route_tables.assert_called_once_with(filters=MOCK_ROUCE_FILTER)
        mock_vpc.vpc.connection.get_all_security_groups.assert_called_once_with(filters=MOCK_ROUCE_FILTER)
        self.assertTrue(meta_network.centralized_route_table is None)
        self.assertTrue(meta)

