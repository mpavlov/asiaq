"""
Subnet abstraction
"""

import boto3
import logging
import uuid

from .resource_helper import (
    handle_date_format,
    keep_trying,
    find_or_create
)


class DiscoSubnet(object):
    """
    Representation of a disco subnet, which contains an AWS subnet object, and its own
    route table and possibly a NAT gateway
    """
    def __init__(self, name, metanetwork, cidr, boto3_connection=None):
        self.name = name
        self.metanetwork = metanetwork
        self.cidr = cidr
        self.eip_allocation_id = None
        self._boto3_connection = boto3_connection
        self._subnet = None
        self._route_table = None
        self._nat_gateway = None

    @property
    def boto3_ec2(self):
        """
        Lazily creates boto3 IAM connection
        """
        if not self._boto3_connection:
            self._boto3_connection = boto3.client('ec2')
        return self._boto3_connection

    @property
    def subnet(self):
        '''Finds or creates the AWS subnet'''
        if not self._subnet:
            self._subnet = find_or_create(
                self._find_subnet, self._create_subnet
            )
        return self._subnet

    @property
    def route_table(self):
        '''Finds or creates the route table for our subnet'''
        if not self._route_table:
            self._route_table = find_or_create(
                self._find_route_table, self._create_route_table
            )
        return self._route_table

    @property
    def nat_gateway(self):
        '''Finds or creates the NAT gateway for our subnet if needed'''
        # TODO: make sure nat_eip_allocation_id matches with the one currently in nat_gateway

        if self.nat_eip_allocation_id and not self._nat_gateway:
            self._nat_gateway = find_or_create(
                self._find_nat_gateway, self._create_nat_gateway
            )

        self.add_route_to_gateway("0.0.0.0/0", self._nat_gateway['NatGatewayId'])

        return self._nat_gateway

    @property
    def _resource_filter(self):
        resource_filter = dict()
        resource_filter['Filter'] = []
        resource_filter['Filter'].append({'Name': 'tag:metanetwork', 'Values': [self.metanetwork.name]})
        resource_filter['Filter'].append({'Name': 'tag:subnet', 'Values': [self.name]})

        return resource_filter

    def create(self):
        self._subnet = self.subnet
        self._route_table = self.route_table

        # Associate route table with subnet
        params = dict()
        params['SubnetId'] = self.subnet['SubnetId']
        params['RouteTableId'] = self.route_table['RouteTableId']
        self.boto3_ec2.associate_route_table(**params)

    def create_nat_gateway(self, eip_allocation_id):
        self.eip_allocation_id = eip_allocation_id
        self._nat_gateway = self.nat_gateway

    def add_route_to_gateway(self, destination_cidr_block, gateway_id):
        """ Try adding a route to a gateway, if fails delete matching CIDR route and try again """
        params = dict()
        params['RouteTableId'] = self.route_table['RouteTableId']
        params['DestinationCidrBlock'] = destination_cidr_block
        params['GatewayId'] = gateway_id

        result = self.boto3_ec2.create_route(**params)['Return']

        if result:
            return result

        logging.exception("Failed to create route due to conflict. Deleting old route and re-trying.")
        delete_params = dict()
        delete_params['RouteTableId'] = self.route_table['RouteTableId']
        delete_params['DestinationCidrBlock'] = destination_cidr_block
        self.boto3_ec2.delete_route(**delete_params)

        logging.error("Re-creating route.")
        return self.boto3_ec2.create_route(**params)['Return']

    def _find_subnet(self):
        try:
            return handle_date_format(
                self.boto3_ec2.describe_subnets(**self._resource_filter)
            )['Subnets'][0]
        except IndexError:
            return None

    def _create_subnet(self):
        params = dict()
        params['VpcId'] = self.metanetwork.vpc.vpc.id
        params['CidrBlock'] = self.cidr
        params['AvailabilityZone'] = self.name
        subnet = handle_date_format(self.boto3_ec2.create_subnet(**params))['Subnet']
        self._tag_resource(subnet['SubnetId'])
        logging.debug("%s subnet: %s", self.name, subnet)
        return subnet

    def _find_route_table(self):
        try:
            return handle_date_format(
                self.boto3_ec2.describe_route_tables(**self._resource_filter)
            )['RouteTables'][0]
        except IndexError:
            return None

    def _create_route_table(self):
        params = dict()
        params['VpcId'] = self.metanetwork.vpc.vpc.id
        route_table = handle_date_format(self.boto3_ec2.create_route_table(**params))['RouteTable']
        self._tag_resource(route_table['RouteTableId'])
        logging.debug("%s route table: %s", self.name, route_table)

        return route_table

    def _find_nat_gateway(self):
        try:
            return handle_date_format(
                    self.boto3_ec2.describe_nat_gateways(**self._resource_filter)
            )['NatGateways'][0]
        except IndexError:
            return None

    def _create_nat_gateway(self):
        params = dict()
        params['SubnetId'] = self.subnet['SubnetId']
        params['AllocationId'] = self.nat_eip_allocation_id
        params['ClientToken'] = str(uuid.uuid4())
        nat_gateway = handle_date_format(self.boto3_ec2.create_nat_gateway(**params))['NatGateway']
        self._tag_resource(nat_gateway['NatGatewayId'])
        logging.debug("%s route table: %s", self.name, nat_gateway)
        return nat_gateway

    def _resource_name(self, suffix=None):
        suffix = "_{0}".format(suffix) if suffix else ""
        return "{0}_{1}_{2}{3}".format(self.metanetwork.vpc.environment_name,
                                       self.metanetwork.name,
                                       self.name, suffix)

    def _tag_resource(self, resource_id, suffix=None):
        tag_params = dict()
        tag_params['Resources'] = [resource_id]
        tag_params['Tags'] = [{'Name': self._resource_name(suffix)},
                              {'meta_network': self.metanetwork.name},
                              {'subnet': self.name}]
        keep_trying(300, self.boto3_ec2.create_tags, **tag_params)
