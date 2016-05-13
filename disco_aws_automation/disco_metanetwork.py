"""
Network abstraction
"""

import logging
from random import choice

from netaddr import IPNetwork, IPAddress
from boto.ec2.networkinterface import (
    NetworkInterfaceSpecification,
    NetworkInterfaceCollection
)
from boto.exception import EC2ResponseError

from disco_aws_automation.network_helper import calc_subnet_offset
from .resource_helper import keep_trying
from .disco_constants import NETWORKS
from .exceptions import IPRangeError


def find_or_create(find, create):
    """Given a find and a create function, create a resource iff it doesn't exist"""
    result = find()
    if result:
        return result
    else:
        return create()


class DiscoMetaNetwork(object):
    """
    Representation of a disco meta-network. Contains a subnet for each availability zone,
    along with a route table which is applied all the subnets.
    """
    def __init__(self, name, vpc, network_cidr=None):
        self.vpc = vpc
        self.name = name
        if network_cidr:
            self._network_cidr = IPNetwork(network_cidr)
        self._route_table = None  # lazily initialized
        self._security_group = None  # lazily initialized
        self._subnets = None  # lazily initialized

    @property
    def network_cidr(self):
        """Get the network_cidr for the meta network"""
        if not self._network_cidr:
            # if we don't have a network_cidr yet (if it wasn't passed in the constructor)
            # then calculate it from the subnets
            subnets = self._find_subnets()

            # calculate how big the meta network must have been if we divided it into the existing subnets
            subnet_cidr_offset = calc_subnet_offset(len(subnets))

            # pick one of the subnets to do our math from
            subnet_network = IPNetwork(subnets[0].cidr_block)

            # the meta network cidr is the cidr of one of the subnets but with a smaller prefix
            subnet_network.prefixlen = subnet_network.prefixlen - subnet_cidr_offset
            self._network_cidr = subnet_network.cidr

        return self._network_cidr

    def _resource_name(self, suffix=None):
        suffix = "_{0}".format(suffix) if suffix else ""
        return "{0}_{1}{2}".format(self.vpc.environment_name, self.name, suffix)

    def create(self):
        """
        Metanetwork is initialized lazily. This forces creation of all
        components.
        """
        self._route_table = self.route_table
        self._security_group = self.security_group
        self._subnets = self.subnets

    @property
    def _resource_filter(self):
        resource_filter = self.vpc.vpc_filter()
        resource_filter["tag:meta_network"] = self.name
        return resource_filter

    def _tag_resource(self, resource, suffix=None):
        keep_trying(300, resource.add_tag, "Name", self._resource_name(suffix))
        keep_trying(300, resource.add_tag, "meta_network", self.name)

    @property
    def route_table(self):
        '''Finds or creates the route table for our metanetwork'''
        if not self._route_table:
            self._route_table = find_or_create(
                self._find_route_table, self._create_route_table
            )
        return self._route_table

    def _find_route_table(self):
        try:
            return self.vpc.vpc.connection.get_all_route_tables(
                filters=self._resource_filter
            )[0]
        except IndexError:
            return None

    def _create_route_table(self):
        route_table = self.vpc.vpc.connection.create_route_table(self.vpc.vpc.id)
        self._tag_resource(route_table)
        logging.debug("%s route table: %s", self.name, self._route_table)
        return route_table

    @property
    def security_group(self):
        '''Finds or creates the security group for our metanetwork'''
        if not self._security_group:
            self._security_group = find_or_create(
                self._find_security_group, self._create_security_group
            )
        return self._security_group

    def _find_security_group(self):
        try:
            return self.vpc.vpc.connection.get_all_security_groups(
                filters=self._resource_filter
            )[0]
        except IndexError:
            return None

    @property
    def sg_description(self):
        """Returns a description of the metanetwork's purpose"""
        return NETWORKS[self.name]

    def _create_security_group(self):
        security_group = self.vpc.vpc.connection.create_security_group(
            self._resource_name(),
            self.sg_description,
            self.vpc.vpc.id
        )
        self._tag_resource(security_group)
        logging.debug("%s security_group: %s", self.name, security_group)
        return security_group

    @property
    def subnets(self):
        '''Finds or creates the subnets for our metanetwork'''
        if not self._subnets:
            self._subnets = find_or_create(
                self._find_subnets, self._create_subnets
            )
        return self._subnets

    @property
    def subnet_ip_networks(self):
        """
        Return IPNetwork of all subnet CIDRs
        """
        return [
            IPNetwork(subnet.cidr_block)
            for subnet in
            self.subnets
        ]

    def _find_subnets(self):
        return self.vpc.vpc.connection.get_all_subnets(
            filters=self._resource_filter
        )

    def _create_subnets(self):
        logging.debug("creating subnets")
        zones = self.vpc.vpc.connection.get_all_zones()
        logging.debug("zones: %s", zones)
        # We'll need to split each subnet into smaller ones, one per zone
        # offset is how much we need to add to cidr divisor to create at least
        # that len(zone) subnets
        zone_cidr_offset = calc_subnet_offset(len(zones))
        logging.debug("zone_offset: %s", zone_cidr_offset)

        zone_cidrs = self.network_cidr.subnet(
            int(self.network_cidr.prefixlen + zone_cidr_offset)
        )

        subnets = []
        for zone, cidr in zip(zones, zone_cidrs):
            logging.debug("%s %s", zone, cidr)
            subnet = self.vpc.vpc.connection.create_subnet(self.vpc.vpc.id, cidr, zone.name)
            self.vpc.vpc.connection.associate_route_table(self.route_table.id, subnet.id)
            self._tag_resource(subnet, zone.name)
            subnets.append(subnet)
            logging.debug("%s subnet: %s", self.name, subnet)

        return subnets

    def subnet_by_ip(self, ip_address):
        """ Return the subnet to which the ip address belongs to """
        ip_address = IPAddress(ip_address)
        for subnet in self.subnets:
            cidr = IPNetwork(subnet.cidr_block)
            if ip_address >= cidr[0] and ip_address <= cidr[-1]:
                return subnet
        raise IPRangeError(
            "IP {0} is not in Metanetwork {1} ({2}) range."
            .format(ip_address, self.name, cidr)
        )

    def create_interfaces_specification(self, subnets=None, public_ip=False):
        """
        Create a network interface specification for an instance -- to be used
        with run_instance()
        """
        random_subnet = choice(subnets if subnets else self.subnets)
        interface = NetworkInterfaceSpecification(
            subnet_id=random_subnet.id,
            groups=[self.security_group.id],
            associate_public_ip_address=public_ip)
        interfaces = NetworkInterfaceCollection(interface)
        return interfaces

    def get_interface(self, private_ip):
        """
        Allocate a 'floating' network inteface with static ip --
        if it does not already exist.
        """
        interface_filter = self.vpc.vpc_filter()
        interface_filter["private-ip-address"] = private_ip
        interfaces = self.vpc.vpc.connection.get_all_network_interfaces(
            filters=interface_filter
        )
        if interfaces:
            return interfaces[0]

        logging.debug("Creating floating ENI %s", private_ip)
        subnet = self.subnet_by_ip(private_ip)
        return self.vpc.vpc.connection.create_network_interface(
            subnet_id=subnet.id,
            private_ip_address=private_ip,
            description="floating interface",
            groups=[self.security_group.id],
        )

    def add_route(self, destination_cidr_block, *args, **kwargs):
        """ Try adding a route, if fails delete matching CIDR route and try again """
        try:
            return self.vpc.vpc.connection.create_route(
                self.route_table.id,
                destination_cidr_block,
                *args,
                **kwargs
            )
        except EC2ResponseError:
            logging.exception("Failed to create route due to conflict. Deleting old route and re-trying.")
            self.vpc.vpc.connection.delete_route(self.route_table.id, destination_cidr_block)
            new_route = self.vpc.vpc.connection.create_route(
                self.route_table_id,
                destination_cidr_block,
                *args,
                **kwargs
            )
            logging.error("Route re-created")
            return new_route

    def add_sg_rule(self, protocol, ports, sg_source=None, cidr_source=None):
        """ Add a security rule to the network """
        sg_args = {
            "group_id": self.security_group.id,
            "ip_protocol": protocol
        }
        if sg_source:
            sg_args["src_security_group_group_id"] = sg_source
        if cidr_source:
            sg_args["cidr_ip"] = cidr_source

        sg_args["from_port"] = ports[0]
        sg_args["to_port"] = ports[1]
        logging.debug("Adding sg_rule: %s", sg_args)
        self.vpc.vpc.connection.authorize_security_group(**sg_args)

    def ip_by_offset(self, offset):
        """
        Pass in +10 and get 10th ip of subnet range
        Pass in -2 and get 2nd to last ip of subnet

        Returns IpAddress object, usually you'll want
        to cast this to str.
        """

        try:
            offset = int(offset)
        except ValueError:
            raise IPRangeError(
                "Cannot find IP in metanetwork {0} by offset {1}."
                .format(self.name, offset)
            )

        subnets = sorted(self.subnet_ip_networks)
        base_address = subnets[0].first if offset >= 0 else subnets[-1].last
        desired_address = IPAddress(base_address + offset)
        # Lazy check to ensure IP address is in metanetwork range
        self.subnet_by_ip(desired_address)

        return desired_address
