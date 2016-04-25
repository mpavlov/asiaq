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
    def __init__(self, name, metanetwork, cidr, route_table_id=None, boto3_connection=None):
        self.name = name
        self.metanetwork = metanetwork
        self.cidr = cidr
        self.eip_allocation_id = None
        self._boto3_connection = boto3_connection
        self._nat_gateway = None
        self._subnet = self.subnet

        if route_table_id:
            self._route_table = self._find_route_table_by_id(route_table_id)
            if not self._route_table:
                raise RuntimeError("Could not find table by the id {0}".format(route_table_id))
        else:
            self._route_table = find_or_create(
                self._find_route_table, self._create_and_associate_route_table
            )

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
        """Finds or creates the AWS subnet"""
        if not self._subnet:
            self._subnet = find_or_create(
                self._find_subnet, self._create_subnet
            )
        return self._subnet

    @property
    def route_table(self):
        """Returns the route table for our subnet"""
        return self._route_table

    @property
    def nat_gateway(self):
        """Finds or creates the NAT gateway for our subnet if needed"""
        # TODO: make sure nat_eip_allocation_id matches with the one currently in nat_gateway

        if self.nat_eip_allocation_id and not self._nat_gateway:
            self._nat_gateway = find_or_create(
                self._find_nat_gateway, self._create_nat_gateway
            )

        return self._nat_gateway

    @property
    def _resource_filter(self):
        resource_filter = dict()
        resource_filter['Filter'] = []
        resource_filter['Filter'].append({'Name': 'tag:metanetwork', 'Values': [self.metanetwork.name]})
        resource_filter['Filter'].append({'Name': 'tag:subnet', 'Values': [self.name]})

        return resource_filter

    def recreate_route_table(self):
        """ Re-create the route table with all the routes from the current route table """
        route_table = self._create_route_table()

        if self.route_table:
            association = (assoc for assoc in self.route_table['Associations']
                           if assoc['SubnetId'] == self.subnet['SubnetId']).next()
            if association:
                # If there is an association between this subnet and the old route table
                # copy the routes to the new route table and disassociate the old one
                for route in self.route_table['Routes']:
                    self._add_route_to_gateway(route_table,
                                               route['DestinationCidrBlock'],
                                               route['GatewayId'])
                self.boto3_ec2.disassociate_route_table(AssociationId=association['RouteTableAssociationId'])

        self._associate_route_table(route_table)

    def create_nat_gateway(self, eip_allocation_id):
        """ Create a NAT gateway for the subnet"""
        self.eip_allocation_id = eip_allocation_id
        self._nat_gateway = self.nat_gateway

    def create_peering_routes(self, peering_conn_id, cidr):
        """ create/update a route between the peering connection and the current subnet. """
        peering_routes_for_peering = [
            _ for _ in self.route_table['Routes']
            if _['VpcPeeringConnectionId'] == peering_conn_id
        ]
        if not peering_routes_for_peering:
            # Create route to the peering connection
            params = dict()
            params['RouteTableId'] = self.route_table['RouteTableId']
            params['DestinationCidrBlock'] = cidr
            params['VpcPeeringConnectionId'] = peering_conn_id

            peering_routes_for_cidr = [
                _ for _ in self.route_table['Routes']
                if _['DestinationCidrBlock'] == cidr
            ]

            if not peering_routes_for_cidr:
                logging.info(
                    'create routes for (route_table: %s, dest_cidr: %s, connection: %s)',
                    params['RouteTableId'], params['DestinationCidrBlock'],
                    params['VpcPeeringConnectionId'])
                self.boto3_ec2.create_route(**params)
            else:
                logging.info(
                    'update routes for (route_table: %s, dest_cidr: %s, connection: %s)',
                    params['RouteTableId'], params['DestinationCidrBlock'],
                    params['VpcPeeringConnectionId'])
                self.boto3_ec2.replace_route(**params)

    def add_route_to_gateway(self, destination_cidr_block, gateway_id):
        """ Try adding a route to a gateway, if fails delete matching CIDR route and try again """
        return self._add_route_to_gateway(self.route_table, destination_cidr_block, gateway_id)

    def _add_route_to_gateway(self, route_table, destination_cidr_block, gateway_id):
        params = dict()
        params['RouteTableId'] = route_table['RouteTableId']
        params['DestinationCidrBlock'] = destination_cidr_block
        params['GatewayId'] = gateway_id
        result = self.boto3_ec2.create_route(**params)['Return']

        if result:
            return result

        logging.exception("Failed to create route due to conflict. Deleting old route and re-trying.")
        delete_params = dict()
        delete_params['RouteTableId'] = route_table['RouteTableId']
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

    def _find_route_table_by_id(self, id):
        params = dict()
        params['RouteTableIds'] = [id]
        try:
            return handle_date_format(
                self.boto3_ec2.describe_route_tables(**params)
            )['RouteTables'][0]
        except IndexError:
            return None

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

    def _associate_route_table(self, route_table):
        # Associate route table with subnet
        params = dict()
        params['SubnetId'] = self.subnet['SubnetId']
        params['RouteTableId'] = route_table['RouteTableId']
        self.boto3_ec2.associate_route_table(**params)

    def _create_and_associate_route_table(self):
        route_table = self._create_route_table()
        self._associate_route_table(route_table)
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
        self.add_route_to_gateway("0.0.0.0/0", nat_gateway['NatGatewayId'])

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
