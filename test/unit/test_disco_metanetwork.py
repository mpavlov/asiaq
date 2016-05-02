"""Tests of disco_metanetwork"""
from unittest import TestCase

from mock import MagicMock, call, patch, create_autospec
from moto import mock_ec2

from disco_aws_automation.disco_metanetwork import DiscoMetaNetwork
from disco_aws_automation.exceptions import EIPConfigError

from test.helpers.patch_disco_aws import (patch_disco_aws,
                                          get_default_config_dict,
                                          get_mock_config,
                                          TEST_ENV_NAME)


MOCK_ROUCE_FILTER = {"vpc-id": "mock_vpc_id",
                     "tag:meta_network": TEST_ENV_NAME}
MOCK_ZONE1 = MagicMock()
MOCK_ZONE1.name = "aws-zone1"
MOCK_ZONE2 = MagicMock()
MOCK_ZONE2.name = "aws-zone2"
MOCK_ZONE3 = MagicMock()
MOCK_ZONE3.name = "aws-zone3"
MOCK_ZONES = [MOCK_ZONE1, MOCK_ZONE2, MOCK_ZONE3]
MOCK_ROUTE_TABLE = MagicMock()
MOCK_ROUTE_TABLE.id = "route_table_id"


def _get_vpc_mock():
    ret = MagicMock()
    ret.get_config.return_value = "10.101.0.0/16"
    ret.vpc_filter.return_value = {"vpc-id": MOCK_ROUCE_FILTER["vpc-id"]}
    ret.vpc = MagicMock()
    ret.vpc.connection = MagicMock()
    ret.vpc.connection.get_all_zones.return_value = MOCK_ZONES
    ret.vpc.connection.get_all_security_groups.return_value = [MagicMock()]
    ret.vpc.connection.get_all_route_tables.return_value = [MOCK_ROUTE_TABLE]

    return ret


class DiscoMetaNetworkTests(TestCase):
    """Test DiscoMetaNetwork"""

    def setUp(self):
        self.mock_vpc = _get_vpc_mock()
        self.meta_network = DiscoMetaNetwork(TEST_ENV_NAME, self.mock_vpc)

    @patch('disco_aws_automation.disco_subnet.DiscoSubnet.__init__', return_value=None)
    def test__create_meta_network__successful(self, mock_subnet_init):
        self.meta_network.create()

        self.mock_vpc.vpc.connection.get_all_route_tables.assert_called_once_with(filters=MOCK_ROUCE_FILTER)
        self.mock_vpc.vpc.connection.get_all_security_groups.assert_called_once_with(filters=MOCK_ROUCE_FILTER)

        self.assertEquals(self.meta_network.centralized_route_table,
                          MOCK_ROUTE_TABLE)
        self.assertEquals(self.meta_network.security_group,
                          self.mock_vpc.vpc.connection.get_all_security_groups.return_value[0])

        calls = [call(MOCK_ZONE1.name, self.meta_network, "10.101.0.0/18", MOCK_ROUTE_TABLE.id),
                 call(MOCK_ZONE2.name, self.meta_network, "10.101.64.0/18", MOCK_ROUTE_TABLE.id),
                 call(MOCK_ZONE3.name, self.meta_network, "10.101.128.0/18", MOCK_ROUTE_TABLE.id)]
        mock_subnet_init.assert_has_calls(calls)
        self.assertEquals(len(self.meta_network.subnets), len(MOCK_ZONES))

    @patch('disco_aws_automation.disco_subnet.DiscoSubnet.__init__', return_value=None)
    @patch('disco_aws_automation.disco_subnet.DiscoSubnet.recreate_route_table', return_value=None)
    @patch('disco_aws_automation.disco_subnet.DiscoSubnet.create_nat_gateway', return_value=None)
    def test__create_nat_gateways__successful(self, mock_create_nat_gateway,
                                              mock_recreate_route_table, mock_subnet_init):
        mock_allocation_ids = ["allocation_id1", "allocation_id2", "allocation_id3"]

        self.meta_network.create()
        self.meta_network.add_nat_gateways(mock_allocation_ids)

        self.assertFalse(self.meta_network.centralized_route_table)
        self.mock_vpc.vpc.connection.delete_route_table.assert_called_once_with(MOCK_ROUTE_TABLE.id)

        recreate_route_table_calls = []
        for _ in range(len(MOCK_ZONES)):
            recreate_route_table_calls.append(call())
        mock_recreate_route_table.assert_has_calls(recreate_route_table_calls)

        nat_gateway_calls = []
        for allocation_id in mock_allocation_ids:
            nat_gateway_calls.append(call(allocation_id))
        mock_create_nat_gateway.assert_has_calls(nat_gateway_calls)

    @patch('disco_aws_automation.disco_subnet.DiscoSubnet.__init__', return_value=None)
    def test__create_nat_gateways__failed(self, mock_subnet_init):
        mock_allocation_ids = ["allocation_id1"]

        self.meta_network.create()

        with self.assertRaises(EIPConfigError):
            self.meta_network.add_nat_gateways(mock_allocation_ids)

    @patch('disco_aws_automation.disco_subnet.DiscoSubnet.__init__', return_value=None)
    def test__add_route__with_centralized_route_table(self, mock_subnet_init):
        self.meta_network.create()

        mock_gateway_id = 'mock_gateway_id'
        mock_cidr = '10.101.0.0/16'

        self.meta_network.add_route(mock_cidr, mock_gateway_id)
        self.mock_vpc.vpc.connection.create_route.\
            assert_called_once_with(destination_cidr_block=mock_cidr,
                                    route_table_id=MOCK_ROUTE_TABLE.id,
                                    gateway_id=mock_gateway_id)

    @patch('disco_aws_automation.disco_subnet.DiscoSubnet.__init__', return_value=None)
    @patch('disco_aws_automation.disco_subnet.DiscoSubnet.add_route_to_gateway', return_value=True)
    def test__add_route__without_centralized_route_table(self, mock_add_route,
                                                         mock_subnet_init):
        self.mock_vpc.vpc.connection.get_all_route_tables.return_value = []
        self.meta_network.create()

        mock_gateway_id = 'mock_gateway_id'
        mock_cidr = '10.101.0.0/16'

        self.meta_network.add_route(mock_cidr, mock_gateway_id)

        add_route_calls = []
        for _ in range(len(MOCK_ZONES)):
            add_route_calls.append(call(mock_cidr, mock_gateway_id))

        mock_add_route.assert_has_calls(add_route_calls)

    @patch('disco_aws_automation.disco_subnet.DiscoSubnet.__init__', return_value=None)
    def test__create_peering_route__with_centralized_route_table(self, mock_subnet_init):
        self.meta_network.create()

        mock_peering_conn = MagicMock()
        mock_peering_conn.id = 'peering_conn_id'
        mock_cidr = '10.101.0.0/16'

        self.meta_network.create_peering_route(mock_peering_conn, mock_cidr)
        self.mock_vpc.vpc.connection.create_route.\
            assert_called_once_with(destination_cidr_block=mock_cidr,
                                    route_table_id=MOCK_ROUTE_TABLE.id,
                                    vpc_peering_connection_id=mock_peering_conn.id)

    @patch('disco_aws_automation.disco_subnet.DiscoSubnet.__init__', return_value=None)
    def test__create_peering_route__with_existing_route(self, mock_subnet_init):
        mock_peering_conn = MagicMock()
        mock_peering_conn.id = 'peering_conn_id'
        mock_cidr = '10.101.0.0/16'

        mock_route = MagicMock()
        mock_route.destination_cidr_block = mock_cidr
        mock_route_table = MagicMock()
        mock_route_table.id = "route_table_id"
        mock_route_table.routes = [mock_route]

        self.mock_vpc.vpc.connection.get_all_route_tables.return_value = [mock_route_table]
        self.meta_network.create()

        self.meta_network.create_peering_route(mock_peering_conn, mock_cidr)
        self.mock_vpc.vpc.connection.replace_route.\
            assert_called_once_with(destination_cidr_block=mock_cidr,
                                    route_table_id=MOCK_ROUTE_TABLE.id,
                                    vpc_peering_connection_id=mock_peering_conn.id)

    @patch('disco_aws_automation.disco_subnet.DiscoSubnet.__init__', return_value=None)
    @patch('disco_aws_automation.disco_subnet.DiscoSubnet.create_peering_routes', return_value=None)
    def test__create_peering_route__without_centralized_route_table(self, mock_create_peering_routes,
                                                                    mock_subnet_init):
        self.mock_vpc.vpc.connection.get_all_route_tables.return_value = []
        self.meta_network.create()

        mock_peering_conn = MagicMock()
        mock_peering_conn.id = 'peering_conn_id'
        mock_cidr = '10.101.0.0/16'

        self.meta_network.create_peering_route(mock_peering_conn, mock_cidr)

        create_peering_routes_calls = []
        for _ in range(len(MOCK_ZONES)):
            create_peering_routes_calls.append(call(mock_peering_conn.id, mock_cidr))

        mock_create_peering_routes.assert_has_calls(create_peering_routes_calls)
