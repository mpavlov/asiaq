"""
Subnet abstraction
"""

import copy
import logging

import boto3

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
    def __init__(self, name, metanetwork, cidr, centralized_route_table_id=None, boto3_connection=None):
        self.name = name
        self.metanetwork = metanetwork
        self.cidr = cidr
        self.nat_eip_allocation_id = None
        self._boto3_connection = boto3_connection  # Lazily initialized if parameter is None
        self._nat_gateway = None

        if centralized_route_table_id:
            # Centralized route table is being used here
            self._subnet_dict = self._find_subnet()
            if not self._subnet_dict:
                raise RuntimeError("Could not find subnet by the AZ "
                                   "name '{0}' for metanetwork '{1}'"
                                   .format(name, self.metanetwork.name))
            # Have to add new tags going forward
            self._apply_subnet_tags(self._subnet_dict['SubnetId'])

            self._route_table = self._find_route_table_by_id(centralized_route_table_id)
            if not self._route_table:
                raise RuntimeError("Could not find centralized route table by the id {0}"
                                   .format(centralized_route_table_id))
        else:
            self._subnet_dict = find_or_create(self._find_subnet, self._create_subnet)

            self._route_table = find_or_create(
                self._find_route_table, self._create_and_associate_route_table
            )

    @property
    def boto3_ec2(self):
        """
        Lazily creates boto3 EC2 connection
        """
        if not self._boto3_connection:
            self._boto3_connection = boto3.client('ec2')
        return self._boto3_connection

    @property
    def subnet_dict(self):
        """Returns the AWS subnet"""
        return self._subnet_dict

    @property
    def route_table(self):
        """Returns the route table for our subnet"""
        return self._route_table

    @property
    def nat_gateway(self):
        """Finds or creates the NAT gateway for our subnet if needed"""
        if self.nat_eip_allocation_id and not self._nat_gateway:
            self._nat_gateway = find_or_create(
                self._find_nat_gateway, self._create_nat_gateway
            )

        return self._nat_gateway

    @property
    def _resource_filter(self):
        return {
            'Filters': [{'Name': 'vpc-id',
                         'Values': [str(self.metanetwork.vpc.vpc.id)]},
                        {'Name': 'tag:meta_network',
                         'Values': [self.metanetwork.name]}]
        }

    def recreate_route_table(self):
        """ Re-create the route table with all the routes from the current route table """
        new_route_table = self._create_route_table()

        if self.route_table:
            association = (assoc for assoc in self.route_table['Associations']
                           if assoc['SubnetId'] == self.subnet_dict['SubnetId']).next()
            if association:
                # If there is an association between this subnet and the old route table
                # copy the routes to the new route table and disassociate the old one
                for route in self.route_table['Routes']:
                    self._add_route(route_table_id=new_route_table['RouteTableId'],
                                    destination_cidr_block=route['DestinationCidrBlock'],
                                    gateway_id=route.get('GatewayId'),
                                    instance_id=route.get('InstanceId'),
                                    network_interface_id=route.get('NetworkInterfaceId'),
                                    vpc_peering_connection_id=route.get('VpcPeeringConnectionId'),
                                    nat_gateway_id=route.get('NatGatewayId'))
                self.boto3_ec2.disassociate_route_table(AssociationId=association['RouteTableAssociationId'])

        self._associate_route_table(new_route_table)
        self._route_table = new_route_table

    def create_nat_gateway(self, eip_allocation_id):
        """ Create a NAT gateway for the subnet"""
        self.nat_eip_allocation_id = eip_allocation_id
        self._nat_gateway = self.nat_gateway

    def delete_nat_gateway(self):
        """ Delete the NAT gateway that is currently associated with the subnet """
        self.nat_eip_allocation_id = None
        if self.nat_gateway:
            self.boto3_ec2.delete_nat_gateway(NatGatewayId=self.nat_gateway['NatGatewayId'])
            self._nat_gateway = None

    def create_peering_routes(self, peering_conn_id, cidr):
        """ create/update a route between the peering connection and the current subnet. """
        peering_routes_for_peering = [
            _ for _ in self.route_table['Routes']
            if _.get('VpcPeeringConnectionId') == peering_conn_id
        ]
        if not peering_routes_for_peering:
            # Create route to the peering connection
            params = {
                'RouteTableId': self.route_table['RouteTableId'],
                'DestinationCidrBlock': cidr,
                'VpcPeeringConnectionId': peering_conn_id
            }

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

            self._route_table = self._find_route_table()

    def add_route_to_gateway(self, destination_cidr_block, gateway_id):
        """ Try adding a route to a gateway, if fails delete matching CIDR route and try again """
        return self._add_route(route_table_id=self.route_table['RouteTableId'],
                               destination_cidr_block=destination_cidr_block,
                               gateway_id=gateway_id)

    def add_route_to_nat_gateway(self, destination_cidr_block, nat_gateway_id):
        """ Try adding a route to a NAT gateway, if fails delete matching CIDR route and try again """
        return self._add_route(route_table_id=self.route_table['RouteTableId'],
                               destination_cidr_block=destination_cidr_block,
                               nat_gateway_id=nat_gateway_id)

    def _add_route(self, route_table_id, destination_cidr_block,
                   gateway_id=None, instance_id=None, network_interface_id=None,
                   vpc_peering_connection_id=None, nat_gateway_id=None):
        params = {
            'RouteTableId': route_table_id,
            'DestinationCidrBlock': destination_cidr_block
        }
        if gateway_id:
            params['GatewayId'] = gateway_id
        if instance_id:
            params['InstanceId'] = instance_id
        if network_interface_id:
            params['NetworkInterfaceId'] = network_interface_id
        if vpc_peering_connection_id:
            params['VpcPeeringConnectionId'] = vpc_peering_connection_id
        if nat_gateway_id:
            params['NatGatewayId'] = nat_gateway_id

        result = self.boto3_ec2.create_route(**params)['Return']

        if result:
            self._route_table = self._find_route_table()
            return result

        logging.info("Failed to create route due to conflict. Deleting old route and re-trying.")
        delete_params = {
            'RouteTableId': route_table_id,
            'DestinationCidrBlock': destination_cidr_block
        }
        self.boto3_ec2.delete_route(**delete_params)

        logging.error("Re-creating route.")
        result = self.boto3_ec2.create_route(**params)['Return']
        self._route_table = self._find_route_table()
        return result

    def _find_subnet(self):
        filters = copy.copy(self._resource_filter)
        filters['Filters'].append({'Name': 'availabilityZone', 'Values': [self.name]})
        try:
            return handle_date_format(
                self.boto3_ec2.describe_subnets(**filters)
            )['Subnets'][0]
        except IndexError:
            return None

    def _create_subnet(self):
        params = {
            'VpcId': self.metanetwork.vpc.vpc.id,
            'CidrBlock': self.cidr,
            'AvailabilityZone': self.name
        }
        subnet_dict = handle_date_format(self.boto3_ec2.create_subnet(**params))['Subnet']
        self._apply_subnet_tags(subnet_dict['SubnetId'])
        logging.debug("%s subnet_dict: %s", self.name, subnet_dict)
        return subnet_dict

    def _find_route_table_by_id(self, route_table_id):
        params = dict()
        params['RouteTableIds'] = [route_table_id]
        try:
            return handle_date_format(
                self.boto3_ec2.describe_route_tables(**params)
            )['RouteTables'][0]
        except IndexError:
            return None

    def _find_route_table(self):
        filters = copy.copy(self._resource_filter)
        filters['Filters'].append({'Name': 'tag:subnet', 'Values': [self.name]})
        try:
            return handle_date_format(
                self.boto3_ec2.describe_route_tables(**filters)
            )['RouteTables'][0]
        except IndexError:
            return None

    def _create_route_table(self):
        params = dict()
        params['VpcId'] = self.metanetwork.vpc.vpc.id
        route_table = handle_date_format(self.boto3_ec2.create_route_table(**params))['RouteTable']
        self._apply_subnet_tags(route_table['RouteTableId'])
        logging.debug("%s route table: %s", self.name, route_table)

        return route_table

    def _associate_route_table(self, route_table):
        # Associate route table with subnet
        params = dict()
        params['SubnetId'] = self.subnet_dict['SubnetId']
        params['RouteTableId'] = route_table['RouteTableId']
        self.boto3_ec2.associate_route_table(**params)

    def _create_and_associate_route_table(self):
        route_table = self._create_route_table()
        self._associate_route_table(route_table)
        return route_table

    def _find_nat_gateway(self):
        params = {
            'Filters': [{'Name': 'subnet-id',
                         'Values': [self.subnet_dict['SubnetId']]},
                        {'Name': 'vpc-id',
                         'Values': [self.metanetwork.vpc.vpc.id]}]
        }
        try:
            result = handle_date_format(
                self.boto3_ec2.describe_nat_gateways(**params)
            )['NatGateways'][0]
        except IndexError:
            return None

        if result['NatGatewayAddresses'][0]['AllocationId'] != self.nat_eip_allocation_id:
            raise RuntimeError("EIP allocation id ({0}) doesn't match with existing "
                               "NAT gateway's allocation id ({1}) in subnet ({2})."
                               .format(self.nat_eip_allocation_id,
                                       result['NatGatewayAddresses'][0]['AllocationId'],
                                       self.subnet_dict['SubnetId']))

        return result

    def _create_nat_gateway(self):
        params = {
            'SubnetId': self.subnet_dict['SubnetId'],
            'AllocationId': self.nat_eip_allocation_id
        }
        logging.debug("Creating NAT gateway: %s", self.nat_eip_allocation_id)
        nat_gateway = handle_date_format(self.boto3_ec2.create_nat_gateway(**params))['NatGateway']

        # TODO: refactor the waiter logic out
        waiter = self.boto3_ec2.get_waiter('nat_gateway_available')
        waiter.wait(NatGatewayIds=[nat_gateway['NatGatewayId']])

        return self._find_nat_gateway()

    def _resource_name(self, suffix=None):
        suffix = "_{0}".format(suffix) if suffix else ""
        return "{0}_{1}_{2}{3}".format(self.metanetwork.vpc.environment_name,
                                       self.metanetwork.name,
                                       self.name, suffix)

    def _apply_subnet_tags(self, resource_id, suffix=None):
        tag_params = {
            'Resources': [resource_id],
            'Tags': [{'Key': 'Name', 'Value': self._resource_name(suffix)},
                     {'Key': 'meta_network', 'Value': self.metanetwork.name},
                     {'Key': 'subnet', 'Value': self.name}]
        }
        keep_trying(300, self.boto3_ec2.create_tags, **tag_params)
