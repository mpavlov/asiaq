"""Tests of disco_vpc"""

import unittest

from mock import MagicMock, patch, PropertyMock
from disco_aws_automation import DiscoVPC
from test.helpers.patch_disco_aws import get_mock_config
from test.helpers.matchers import MatchClass


def create_vpc_mock(env_name, env_type):
    """vpc mock"""
    vpc = MagicMock()
    vpc.tags = {
        'Name': env_name,
        'type': env_type
    }

    return vpc


class DiscoVPCTests(unittest.TestCase):
    """Test DiscoVPC"""

    # pylint: disable=unused-argument
    @patch('disco_aws_automation.disco_vpc.DiscoVPC.config', new_callable=PropertyMock)
    @patch('disco_aws_automation.disco_vpc.VPCConnection')
    def test_create_meta_networks(self, vpc_conn_mock, config_mock):
        """Test creating meta networks with dynamic ip ranges"""
        vpc_mock = MagicMock()
        vpc_mock.cidr_block = '10.0.0.0/28'

        config_mock.return_value = get_mock_config({
            'envtype:auto-vpc-type': {
                'vpc_cidr': '10.0.0.0/28',
                'intranet_cidr': 'auto',
                'tunnel_cidr': 'auto',
                'dmz_cidr': 'auto',
                'maintenance_cidr': 'auto'
            }
        })

        auto_vpc = DiscoVPC('auto-vpc', 'auto-vpc-type', vpc_mock)

        meta_networks = auto_vpc._create_new_meta_networks()
        self.assertItemsEqual(['intranet', 'tunnel', 'dmz', 'maintenance'], meta_networks.keys())

        expected_ip_ranges = ['10.0.0.0/30', '10.0.0.4/30', '10.0.0.8/30', '10.0.0.12/30']
        actual_ip_ranges = [str(meta_network.network_cidr) for meta_network in meta_networks.values()]

        self.assertItemsEqual(actual_ip_ranges, expected_ip_ranges)

    # pylint: disable=unused-argument
    @patch('disco_aws_automation.disco_vpc.DiscoVPC.config', new_callable=PropertyMock)
    @patch('disco_aws_automation.disco_vpc.VPCConnection')
    def test_create_meta_networks_static_dynamic(self, vpc_conn_mock, config_mock):
        """Test creating meta networks with a mix of static and dynamic ip ranges"""
        vpc_mock = MagicMock()
        vpc_mock.cidr_block = '10.0.0.0/28'

        config_mock.return_value = get_mock_config({
            'envtype:auto-vpc-type': {
                'vpc_cidr': '10.0.0.0/28',
                'intranet_cidr': 'auto',
                'tunnel_cidr': 'auto',
                'dmz_cidr': '10.0.0.4/31',
                'maintenance_cidr': 'auto'
            }
        })

        auto_vpc = DiscoVPC('auto-vpc', 'auto-vpc-type', vpc_mock)

        meta_networks = auto_vpc._create_new_meta_networks()
        self.assertItemsEqual(['intranet', 'tunnel', 'dmz', 'maintenance'], meta_networks.keys())

        expected_ip_ranges = ['10.0.0.0/30', '10.0.0.4/31', '10.0.0.8/30', '10.0.0.12/30']
        actual_ip_ranges = [str(meta_network.network_cidr) for meta_network in meta_networks.values()]

        self.assertItemsEqual(actual_ip_ranges, expected_ip_ranges)

    # pylint: disable=unused-argument
    @patch('disco_aws_automation.disco_vpc.DiscoSNS')
    @patch('time.sleep')
    @patch('disco_aws_automation.disco_vpc.DiscoVPC._wait_for_vgw_states')
    @patch('disco_aws_automation.disco_vpc.DiscoVPC.config', new_callable=PropertyMock)
    @patch('disco_aws_automation.disco_vpc.VPCConnection')
    @patch('disco_aws_automation.disco_metanetwork.DiscoSubnet')
    def test_create_auto_vpc(self, subnet_mock, vpc_conn_mock, config_mock,
                             _wait_vgw_states_mock, sleep_mock, sns_mock):
        """Test creating a VPC with a dynamic ip range"""
        # FIXME This needs to mock way too many things. DiscoVPC needs to be refactored

        config_mock.return_value = get_mock_config({
            'envtype:auto-vpc-type': {
                'ip_space': '10.0.0.0/24',
                'vpc_cidr_size': '26',
                'intranet_cidr': 'auto',
                'tunnel_cidr': 'auto',
                'dmz_cidr': 'auto',
                'maintenance_cidr': 'auto'
            }
        })

        def _create_vpc_mock(cidr):
            vpc = MagicMock()
            vpc.cidr_block = cidr
            vpc.connection = vpc_conn_mock.return_value
            return vpc

        vpc_conn_mock.return_value.create_vpc.side_effect = _create_vpc_mock
        vpc_conn_mock.return_value.get_all_zones.return_value = [MagicMock()]

        auto_vpc = DiscoVPC('auto-vpc', 'auto-vpc-type')

        possible_vpcs = ['10.0.0.0/26', '10.0.0.64/26', '10.0.0.128/26', '10.0.0.192/26']
        self.assertIn(str(auto_vpc.vpc.cidr_block), possible_vpcs)

    @patch('disco_aws_automation.disco_vpc.DiscoVPC.config', new_callable=PropertyMock)
    def test_parse_peering_connection(self, config_mock):
        """test parsing a simple peering connection line"""
        config_mock.return_value = get_mock_config({
            'envtype:sandbox': {
                'vpc_cidr': '10.0.0.0/16',
                'intranet_cidr': 'auto'
            }
        })

        existing_vpc = [create_vpc_mock('env1', 'sandbox'),
                        create_vpc_mock('env2', 'sandbox')]

        result = DiscoVPC.parse_peering_connection_line('env1:sandbox/intranet env2:sandbox/intranet',
                                                        existing_vpc)

        peering_info = result['env1:sandbox/intranet env2:sandbox/intranet']

        self.assertEquals(peering_info['vpc_metanetwork_map'], {'env1': 'intranet', 'env2': 'intranet'})
        self.assertEquals(peering_info['vpc_map'], {'env1': MatchClass(DiscoVPC),
                                                    'env2': MatchClass(DiscoVPC)})

    @patch('disco_aws_automation.disco_vpc.DiscoVPC.config', new_callable=PropertyMock)
    def test_parse_peering_connection_wildcards(self, config_mock):
        """test parsing a peering connection line with wildcards"""
        config_mock.return_value = get_mock_config({
            'envtype:sandbox': {
                'vpc_cidr': '10.0.0.0/16',
                'intranet_cidr': 'auto'
            }
        })

        existing_vpc = [create_vpc_mock('env1', 'sandbox'),
                        create_vpc_mock('env2', 'sandbox'),
                        create_vpc_mock('env3', 'sandbox')]

        result = DiscoVPC.parse_peering_connection_line('*:sandbox/intranet env3:sandbox/intranet',
                                                        existing_vpc)

        self.assertEquals(2, len(result))

        peering_info1 = result['env1:sandbox/intranet env3:sandbox/intranet']

        self.assertEquals(peering_info1['vpc_metanetwork_map'], {'env1': 'intranet', 'env3': 'intranet'})
        self.assertEquals(peering_info1['vpc_map'], {'env1': MatchClass(DiscoVPC),
                                                     'env3': MatchClass(DiscoVPC)})

        peering_info2 = result['env2:sandbox/intranet env3:sandbox/intranet']

        self.assertEquals(peering_info2['vpc_metanetwork_map'], {'env2': 'intranet', 'env3': 'intranet'})
        self.assertEquals(peering_info2['vpc_map'], {'env2': MatchClass(DiscoVPC),
                                                     'env3': MatchClass(DiscoVPC)})
