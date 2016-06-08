"""Tests of disco_vpc_peerings"""

import unittest
from mock import MagicMock, call, patch, PropertyMock

from disco_aws_automation.disco_vpc import DiscoVPC
from disco_aws_automation.disco_vpc_peerings import DiscoVPCPeerings

from test.helpers.patch_disco_aws import get_mock_config


# pylint: disable=unused-argument
@patch('disco_aws_automation.disco_vpc.DiscoVPC.config', new_callable=PropertyMock)
@patch('boto3.client')
def _get_vpc_mock(boto3_client_mock=None, config_mock=None):

    config_mock.return_value = get_mock_config({
        'envtype:sandbox': {
            'ip_space': '10.0.0.0/24',
            'vpc_cidr_size': '26',
            'intranet_cidr': 'auto',
            'tunnel_cidr': 'auto',
            'dmz_cidr': 'auto',
            'maintenance_cidr': 'auto',
            'ntp_server': '10.0.0.5'
        }
    })

    client_mock = MagicMock()
    client_mock.describe_dhcp_options.return_value = {'DhcpOptions': [MagicMock()]}
    boto3_client_mock.return_value = client_mock

    ret = DiscoVPC('mock-vpc-1', 'sandbox',
                   {'CidrBlock': '10.0.0.0/26', 'VpcId': 'mock_vpc_1_id'})
    return ret


# pylint: disable=C0103,dangerous-default-value
def _describe_vpcs_mock(VpcIds=[], Filters=[]):
    vpc1 = {'Vpcs': [{'VpcId': 'mock_vpc_1_id',
                      'Tags': [{'Key': 'Name', 'Value': 'mock-vpc-1'},
                               {'Key': 'type', 'Value': 'sandbox'}]}]}
    vpc2 = {'Vpcs': [{'VpcId': 'mock_vpc_2_id',
                      'Tags': [{'Key': 'Name', 'Value': 'mock-vpc-2'},
                               {'Key': 'type', 'Value': 'sandbox'}]}]}
    vpc3 = {'Vpcs': [{'VpcId': 'mock_vpc_3_id',
                      'Tags': [{'Key': 'Name', 'Value': 'mock-vpc-3'},
                               {'Key': 'type', 'Value': 'sandbox'}]}]}

    ret = None
    if Filters:
        for vpc_filter in Filters:
            if vpc_filter['Name'] == 'tag-value':
                if vpc_filter['Values'][0] == 'mock-vpc-1':
                    ret = vpc1
                elif vpc_filter['Values'][0] == 'mock-vpc-2':
                    ret = vpc2
                elif vpc_filter['Values'][0] == 'mock-vpc-3':
                    ret = vpc3
    else:
        for vpc_id in VpcIds:
            if vpc_id == 'mock_vpc_1_id':
                ret = vpc1
            elif vpc_id == 'mock_vpc_2_id':
                ret = vpc2
            elif vpc_id == 'mock_vpc_3_id':
                ret = vpc3

    return ret


class DiscoVPCPeeringsTests(unittest.TestCase):
    """Test DiscoVPCPeerings"""

    def setUp(self):
        self.mock_vpc = _get_vpc_mock()
        self.disco_vpc_peerings = DiscoVPCPeerings(self.mock_vpc, self.mock_vpc.boto3_ec2)

    @patch('disco_aws_automation.disco_vpc.DiscoMetaNetwork')
    @patch('disco_aws_automation.disco_vpc_peerings.read_config')
    @patch('boto3.client')
    def test_update_peering_connections(self, boto3_client_mock, config_mock, meta_network_mock):
        """ Verify new peering connections are created properly """

        config_mock.return_value = get_mock_config({
            'peerings': {
                'connection_1': 'mock-vpc-1:sandbox/intranet mock-vpc-2:sandbox/intranet'
            }
        })

        client_mock = MagicMock()
        client_mock.describe_vpc_peering_connections.return_value = {'VpcPeeringConnections': []}
        client_mock.create_vpc_peering_connection.return_value = {
            'VpcPeeringConnection': {'VpcPeeringConnectionId': 'mock_vpc_peering_id'}}
        client_mock.describe_vpcs.side_effect = _describe_vpcs_mock
        boto3_client_mock.return_value = client_mock

        network_1_mock = MagicMock()
        network_2_mock = MagicMock()

        def _mock_meta_network(network, vpc):
            if vpc.vpc['VpcId'] == 'mock_vpc_1_id':
                return network_1_mock
            else:
                return network_2_mock
        meta_network_mock.side_effect = _mock_meta_network
        # End setting up test

        # Calling method under test
        self.disco_vpc_peerings.update_peering_connections()

        # Verifying correct behavior
        client_mock.create_vpc_peering_connection.assert_called_once_with(
            PeerVpcId='mock_vpc_2_id', VpcId='mock_vpc_1_id')
        client_mock.accept_vpc_peering_connection.assert_called_once_with(
            VpcPeeringConnectionId='mock_vpc_peering_id')
        network_1_mock.create_peering_route.assert_called_once_with(
            'mock_vpc_peering_id', str(network_2_mock.network_cidr))
        network_2_mock.create_peering_route.assert_called_once_with(
            'mock_vpc_peering_id', str(network_1_mock.network_cidr))

    @patch('disco_aws_automation.disco_vpc.DiscoMetaNetwork')
    @patch('disco_aws_automation.disco_vpc_peerings.read_config')
    @patch('boto3.client')
    def test_update_peerings_with_existing_ones(
            self, boto3_client_mock, config_mock, meta_network_mock):
        """ Verify new peering connections are created properly while there are existing ones """

        config_mock.return_value = get_mock_config({
            'peerings': {
                'connection_1': 'mock-vpc-1:sandbox/intranet mock-vpc-2:sandbox/intranet',
                'connection_2': 'mock-vpc-1:sandbox/intranet mock-vpc-3:sandbox/intranet'
            }
        })

        # pylint: disable=C0103
        def _describe_vpc_peering_connections_mock(Filters):
            count = 0
            for peering_filter in Filters:
                if (peering_filter['Name'] == 'accepter-vpc-info.vpc-id' and
                        peering_filter['Values'][0] == 'mock_vpc_1_id') or \
                    (peering_filter['Name'] == 'requester-vpc-info.vpc-id' and
                     peering_filter['Values'][0] == 'mock_vpc_2_id'):
                    count += 1

            if count == 2 or \
                    (len(Filters) == 1 and
                     Filters[0]['Name'] == 'accepter-vpc-info.vpc-id' and
                     Filters[0]['Values'][0] == 'mock_vpc_1_id'):
                return {'VpcPeeringConnections': [
                    {'Status': {'Code': 'active'},
                     'VpcPeeringConnectionId': 'mock_vpc_peering_id_existing',
                     'AccepterVpcInfo': {'VpcId': 'mock_vpc_1_id'},
                     'RequesterVpcInfo': {'VpcId': 'mock_vpc_2_id'}}]}
            else:
                return {'VpcPeeringConnections': []}

        network_1_mock = MagicMock()
        network_1_mock.network_cidr = '10.0.23.23/23'
        network_1_mock.name = 'intranet'
        network_2_mock = MagicMock()
        network_2_mock.network_cidr = '10.0.123.123/23'
        network_2_mock.name = 'intranet'
        network_3_mock = MagicMock()
        network_3_mock.network_cidr = '10.2.123.123/23'
        network_3_mock.name = 'intranet'

        def _mock_meta_network(network, vpc):
            if vpc.vpc['VpcId'] == 'mock_vpc_1_id':
                return network_1_mock
            elif vpc.vpc['VpcId'] == 'mock_vpc_2_id':
                return network_2_mock
            elif vpc.vpc['VpcId'] == 'mock_vpc_3_id':
                return network_3_mock
            return None

        client_mock = MagicMock()
        client_mock.describe_vpc_peering_connections.side_effect = _describe_vpc_peering_connections_mock
        client_mock.create_vpc_peering_connection.return_value = {
            'VpcPeeringConnection': {'VpcPeeringConnectionId': 'mock_vpc_peering_id_new'}}
        client_mock.describe_vpcs.side_effect = _describe_vpcs_mock
        self.mock_vpc.boto3_ec2.describe_vpcs.side_effect = _describe_vpcs_mock
        self.mock_vpc.boto3_ec2.describe_route_tables.return_value = {
            'RouteTables': [{'Tags': [{'Key': 'Name', 'Value': 'mock-vpc-1_intranet'}],
                             'Routes': [{'VpcPeeringConnectionId': 'mock_vpc_peering_id_existing',
                                         'DestinationCidrBlock': network_2_mock.network_cidr}]},
                            {'Tags': [{'Key': 'Name', 'Value': 'mock-vpc-2_intranet'}],
                             'Routes': [{'VpcPeeringConnectionId': 'mock_vpc_peering_id_existing',
                                         'DestinationCidrBlock': network_1_mock.network_cidr}]}]}
        boto3_client_mock.return_value = client_mock

        meta_network_mock.side_effect = _mock_meta_network
        # End setting up test

        # Calling method under test
        self.disco_vpc_peerings.update_peering_connections()

        # Asserting correct behavior
        client_mock.create_vpc_peering_connection.assert_called_once_with(
            PeerVpcId='mock_vpc_3_id', VpcId='mock_vpc_1_id')
        client_mock.accept_vpc_peering_connection.assert_called_once_with(
            VpcPeeringConnectionId='mock_vpc_peering_id_new')
        expected_calls_network_1 = [call('mock_vpc_peering_id_new',
                                         str(network_3_mock.network_cidr)),
                                    call('mock_vpc_peering_id_existing',
                                         str(network_2_mock.network_cidr))]
        network_1_mock.create_peering_route.assert_has_calls(
            expected_calls_network_1)

        network_2_mock.create_peering_route.assert_called_once_with(
            'mock_vpc_peering_id_existing', str(network_1_mock.network_cidr))

        network_3_mock.create_peering_route.assert_called_once_with(
            'mock_vpc_peering_id_new', str(network_1_mock.network_cidr))
