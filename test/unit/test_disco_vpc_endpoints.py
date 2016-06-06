""" Test VPC endpoint creation/deletion"""

import unittest
import json

from mock import MagicMock

from disco_aws_automation import DiscoVPCEndpoints
from disco_aws_automation.disco_vpc_endpoints import S3_POLICY

VPC_ID = "vpc-fb5ed79f"
REPLY_ROUTE_TABLE = {
    'RouteTables': [
        {'RouteTableId': 'rtb-018ff265'},
        {'RouteTableId': 'rtb-0c8ff268'},
        {'RouteTableId': 'rtb-028ff266'},
        {'RouteTableId': 'rtb-008ff264'},
        {'RouteTableId': 'rtb-3e8ff25a'},
        {'RouteTableId': 'rtb-0e8ff26a'},
        {'RouteTableId': 'rtb-368ff252'},
        {'RouteTableId': 'rtb-068ff262'},
        {'RouteTableId': 'rtb-318ff255'},
    ]
}
REPLY_S3_ENDPOINTS = {
    'VpcEndpoints': [
        {
            'RouteTableIds': [
                'rtb-018ff265',
                'rtb-0c8ff268',
                'rtb-028ff266',
                'rtb-008ff264',
                'rtb-3e8ff25a',
                'rtb-0e8ff26a',
                'rtb-368ff252',
                'rtb-068ff262',
                'rtb-318ff255',
                'rtb-2a8ff24e',
                'rtb-0f8ff26b',
                'rtb-3b8ff25f',
                'rtb-338ff257'
            ],
            'ServiceName': 'com.amazonaws.us-west-2.s3',
            'State': 'available',
            'VpcEndpointId': 'vpce-b6a44bdf',
            'VpcId': VPC_ID
        }
    ]
}
REPLY_ENDPOINT_SERVICES = {'ServiceNames': ['com.amazonaws.us-west-2.s3']}


class DiscoVPCEndpointsTests(unittest.TestCase):
    """ Test VPC endpoint creation/deletion"""

    def test_update(self):
        """test vpc endpoint update"""
        client = MagicMock()
        client.describe_route_tables.return_value = REPLY_ROUTE_TABLE
        client.describe_vpc_endpoint_services.return_value = REPLY_ENDPOINT_SERVICES
        client.describe_vpc_endpoints.return_value = REPLY_S3_ENDPOINTS

        endpoints = DiscoVPCEndpoints(VPC_ID, client)
        endpoints.update()
        client.delete_vpc_endpoints.assert_called_with(
            DryRun=False,
            VpcEndpointIds=[REPLY_S3_ENDPOINTS["VpcEndpoints"][0]["VpcEndpointId"]]
        )
        client.create_vpc_endpoint.assert_called_with(
            DryRun=False,
            PolicyDocument=json.dumps(S3_POLICY),
            VpcId=VPC_ID,
            ServiceName=REPLY_S3_ENDPOINTS["VpcEndpoints"][0]["ServiceName"],
            RouteTableIds=[
                rt["RouteTableId"]
                for rt in REPLY_ROUTE_TABLE["RouteTables"]
            ]
        )
