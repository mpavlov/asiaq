"""Tests of disco_vpc"""

import unittest

from mock import MagicMock, patch, PropertyMock
from netaddr import IPSet

from disco_aws_automation import DiscoVPC
from test.helpers.patch_disco_aws import get_mock_config


class DiscoVPCTests(unittest.TestCase):
    """Test DiscoVPC"""

    def test_get_random_free_subnet(self):
        """Test getting getting a random subnet from a network"""
        subnet = DiscoVPC.get_random_free_subnet('10.0.0.0/28', 30, [])

        possible_subnets = ['10.0.0.0/30', '10.0.0.4/30', '10.0.0.8/30', '10.0.0.12/30']
        self.assertIn(str(subnet), possible_subnets)

    def test_get_random_free_subnet_returns_none(self):
        """Test that None is returned if no subnets are available"""
        used_subnets = ['10.0.0.0/30', '10.0.0.4/32', '10.0.0.8/30', '10.0.0.12/30']

        subnet = DiscoVPC.get_random_free_subnet('10.0.0.0/28', 30, used_subnets)
        IPSet(subnet)
        self.assertIsNone(subnet)

    # pylint: disable=unused-argument
    @patch('disco_aws_automation.disco_vpc.DiscoVPCEndpoints')
    @patch('disco_aws_automation.disco_vpc.DiscoVPC.config', new_callable=PropertyMock)
    @patch('disco_aws_automation.disco_vpc.DiscoMetaNetwork')
    def test_create_meta_networks(self, meta_network_mock, config_mock, endpoints_mock):
        """Test creating meta networks with dynamic ip ranges"""
        vpc_mock = {'CidrBlock': '10.0.0.0/28',
                    'VpcId': 'mock_vpc_id'}

        config_mock.return_value = get_mock_config({
            'envtype:auto-vpc-type': {
                'vpc_cidr': '10.0.0.0/28',
                'intranet_cidr': 'auto',
                'tunnel_cidr': 'auto',
                'dmz_cidr': 'auto',
                'maintenance_cidr': 'auto'
            }
        })

        def _create_meta_network_mock(network_name, vpc, cidr):
            ret = MagicMock()
            ret.name = network_name
            ret.vpc = vpc
            ret.network_cidr = cidr

            return ret

        meta_network_mock.side_effect = _create_meta_network_mock

        auto_vpc = DiscoVPC('auto-vpc', 'auto-vpc-type', vpc_mock)

        meta_networks = auto_vpc._create_new_meta_networks()
        self.assertItemsEqual(['intranet', 'tunnel', 'dmz', 'maintenance'], meta_networks.keys())

        expected_ip_ranges = ['10.0.0.0/30', '10.0.0.4/30', '10.0.0.8/30', '10.0.0.12/30']
        actual_ip_ranges = [str(meta_network.network_cidr) for meta_network in meta_networks.values()]

        self.assertItemsEqual(actual_ip_ranges, expected_ip_ranges)

    @patch('disco_aws_automation.disco_vpc.DiscoVPCEndpoints')
    @patch('disco_aws_automation.disco_vpc.DiscoVPC.config', new_callable=PropertyMock)
    @patch('disco_aws_automation.disco_vpc.DiscoMetaNetwork')
    def test_create_meta_networks_static_dynamic(self, meta_network_mock, config_mock, endpoints_mock):
        """Test creating meta networks with a mix of static and dynamic ip ranges"""
        vpc_mock = {'CidrBlock': '10.0.0.0/28',
                    'VpcId': 'mock_vpc_id'}

        config_mock.return_value = get_mock_config({
            'envtype:auto-vpc-type': {
                'vpc_cidr': '10.0.0.0/28',
                'intranet_cidr': 'auto',
                'tunnel_cidr': 'auto',
                'dmz_cidr': '10.0.0.4/31',
                'maintenance_cidr': 'auto'
            }
        })

        def _create_meta_network_mock(network_name, vpc, cidr):
            ret = MagicMock()
            ret.name = network_name
            ret.vpc = vpc
            ret.network_cidr = cidr

            return ret

        meta_network_mock.side_effect = _create_meta_network_mock

        auto_vpc = DiscoVPC('auto-vpc', 'auto-vpc-type', vpc_mock)

        meta_networks = auto_vpc._create_new_meta_networks()
        self.assertItemsEqual(['intranet', 'tunnel', 'dmz', 'maintenance'], meta_networks.keys())

        expected_ip_ranges = ['10.0.0.0/30', '10.0.0.4/31', '10.0.0.8/30', '10.0.0.12/30']
        actual_ip_ranges = [str(meta_network.network_cidr) for meta_network in meta_networks.values()]

        self.assertItemsEqual(actual_ip_ranges, expected_ip_ranges)

    # pylint: disable=unused-argument
    @patch('disco_aws_automation.disco_vpc.DiscoVPCEndpoints')
    @patch('disco_aws_automation.disco_vpc.DiscoSNS')
    @patch('disco_aws_automation.disco_vpc.DiscoVPCGateways')
    @patch('time.sleep')
    @patch('disco_aws_automation.disco_vpc.DiscoVPC.config', new_callable=PropertyMock)
    @patch('boto3.client')
    @patch('boto3.resource')
    @patch('disco_aws_automation.disco_vpc.DiscoMetaNetwork')
    def test_create_auto_vpc(self, meta_network_mock, boto3_resource_mock,
                             boto3_client_mock, config_mock,
                             sleep_mock, gateways_mock, sns_mock, endpoints_mock):
        """Test creating a VPC with a dynamic ip range"""
        # FIXME This needs to mock way too many things. DiscoVPC needs to be refactored

        config_mock.return_value = get_mock_config({
            'envtype:auto-vpc-type': {
                'ip_space': '10.0.0.0/24',
                'vpc_cidr_size': '26',
                'intranet_cidr': 'auto',
                'tunnel_cidr': 'auto',
                'dmz_cidr': 'auto',
                'maintenance_cidr': 'auto',
                'ntp_server': '10.0.0.5'
            }
        })

        # pylint: disable=C0103
        def _create_vpc_mock(CidrBlock):
            return {'Vpc': {'CidrBlock': CidrBlock,
                            'VpcId': 'mock_vpc_id'}}

        client_mock = MagicMock()
        client_mock.create_vpc.side_effect = _create_vpc_mock
        client_mock.get_all_zones.return_value = [MagicMock()]
        client_mock.describe_dhcp_options.return_value = {'DhcpOptions': [MagicMock()]}
        boto3_client_mock.return_value = client_mock

        auto_vpc = DiscoVPC('auto-vpc', 'auto-vpc-type')

        possible_vpcs = ['10.0.0.0/26', '10.0.0.64/26', '10.0.0.128/26', '10.0.0.192/26']
        self.assertIn(str(auto_vpc.vpc['CidrBlock']), possible_vpcs)
