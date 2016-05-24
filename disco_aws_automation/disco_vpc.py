"""
Amazon VPC (Virtual Private Cloud) orchestration code.  We use VPC's to provide isolation between
environments, and between an environment and the internet.  In particular non-VPC instances
(EC2-Classic) have internet routable addresses which is not what we want.
"""

import logging
import random

import time
from ConfigParser import ConfigParser

from boto.exception import EC2ResponseError
import boto3

from netaddr import IPNetwork, IPSet

from disco_aws_automation.network_helper import calc_subnet_offset
from . import read_config, normalize_path

from .resource_helper import (
    keep_trying,
    wait_for_state_boto3,
    get_name_tag_value
)
from .disco_log_metrics import DiscoLogMetrics
from .disco_alarm import DiscoAlarm
from .disco_alarm_config import DiscoAlarmsConfig
from .disco_autoscale import DiscoAutoscale
from .disco_constants import CREDENTIAL_BUCKET_TEMPLATE, NETWORKS
from .disco_metanetwork import DiscoMetaNetwork
from .disco_elasticache import DiscoElastiCache
from .disco_sns import DiscoSNS
from .disco_rds import DiscoRDS
from .disco_eip import DiscoEIP
from .disco_elb import DiscoELB
from .exceptions import (
    MultipleVPCsForVPCNameError, TimeoutError, VPCConfigError, VPCEnvironmentError, VPCPeeringSyntaxError,
    VPCNameNotFound, EIPConfigError)


CONFIG_FILE = "disco_vpc.ini"
VGW_STATE_POLL_INTERVAL = 2  # seconds
VGW_ATTACH_TIME = 600  # seconds. From observation, it takes about 300s to attach vgw
LIVE_PEERING_STATES = ["pending-acceptance", "provisioning", "active"]


def tag2dict(tags):
    ''' Converts a list of dict to dict '''
    return {tag.get('Key'): tag.get('Value') for tag in tags or {}}


# FIXME: pylint thinks too many lines are in the file and it has too many instance arguments
# pylint: disable=C0302, R0902
class DiscoVPC(object):
    """
    This class contains all our VPC orchestration code
    """

    def __init__(self, environment_name, environment_type, vpc=None, config_file=None, boto3_ec2=None):
        self.config_file = config_file or CONFIG_FILE

        self.environment_name = environment_name
        self.environment_type = environment_type
        self._config = None  # lazily initialized
        self._peerings = None  # lazily initialized
        self._region = None  # lazily initialized
        self._networks = None  # lazily initialized
        self._boto3_ec2 = boto3_ec2 # Lazily initialized if parameter is None
        self._alarms_config = None  # lazily initialized
        self.rds = DiscoRDS(vpc=self)
        self.eip = DiscoEIP()
        self.elb = DiscoELB(vpc=self)
        self.elasticache = DiscoElastiCache(vpc=self)
        self.log_metrics = DiscoLogMetrics(environment=environment_name)

        if "_" in environment_name:  # Underscores break our alarm name parsing.
            raise VPCConfigError(
                "VPC name {0} must not contain an underscore".format(environment_name))

        if vpc:
            self.vpc = vpc
        else:
            self._create_environment()

    @property
    def boto3_ec2(self):
        """
        Lazily creates boto3 EC2 connection
        """
        if not self._boto3_ec2:
            self._boto3_ec2 = boto3.client('ec2')
        return self._boto3_ec2

    @property
    def config(self):
        """lazy load config"""
        if not self._config:
            try:
                config = ConfigParser()
                config.read(normalize_path(self.config_file))
                self._config = config
            except Exception:
                return None
        return self._config

    def get_config(self, option, default=None):
        '''Returns appropriate configuration for the current environment'''
        env_section = "env:{0}".format(self.environment_name)
        envtype_section = "envtype:{0}".format(self.environment_type)
        peering_section = "peerings"
        if self.config.has_option(env_section, option):
            return self.config.get(env_section, option)
        elif self.config.has_option(envtype_section, option):
            return self.config.get(envtype_section, option)
        elif self.config.has_option(peering_section, option):
            return self.config.get(peering_section, option)
        else:
            return default

    def get_vpc_id(self):
        ''' Returns the vpc id '''
        return self.vpc['VpcId'] if self.vpc else None

    def ami_stage(self):
        '''Returns default AMI stage to deploy in a development environment'''
        return self.get_config("ami_stage")

    @staticmethod
    def get_credential_buckets_from_env_name(aws_config, environment_name):
        """Return the credentials S3 bucket names for this environment"""

        env_name = environment_name or aws_config.get("disco_aws", "default_environment")
        if not env_name:
            raise VPCEnvironmentError(
                "Can not determine credentials bucket name, need to know environment name"
            )

        project_name = aws_config.get("disco_aws", "project_name")
        if not env_name:
            raise VPCEnvironmentError(
                "Can not determine credentials bucket name, need to know project name"
            )

        vpc = DiscoVPC.fetch_environment(environment_name=env_name)
        if not vpc:
            raise VPCEnvironmentError(
                "Can not determine credentials from environment name unless vpc exists"
            )

        return vpc.get_credential_buckets(project_name)

    @property
    def region(self):
        """Region we're operating in"""
        if not self._region:
            # region = self.vpc.region.name <-- This doesn't work, so we use the HACK below
            self._region = self.boto3_ec2.describe_availability_zones()['AvailabilityZones'][0]['RegionName']
        return self._region

    @property
    def alarms_config(self):
        """The configuration for metrics and alarms"""
        if not self._alarms_config:
            self._alarms_config = DiscoAlarmsConfig(self.environment_name)
        return self._alarms_config

    def get_credential_buckets(self, project_name):
        """Returns list of buckets to locate credentials in"""
        return [CREDENTIAL_BUCKET_TEMPLATE.format(region=self.region, project=project_name, postfix=postfix)
                for postfix in self.get_config("credential_buckets", "").split()]

    @classmethod
    def fetch_environment(cls, vpc_id=None, environment_name=None):
        """
        Returns an instance of this class for the specified VPC, or None if it does not exist
        """
        client = boto3.client('ec2')
        try:
            if vpc_id:
                vpc = client.describe_vpcs(
                    Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])['Vpcs'][0]
            elif environment_name:
                vpc = client.describe_vpcs(
                    Filters=[{'Name': 'tag:Name', 'Values': [environment_name]}])['Vpcs'][0]
            else:
                raise VPCEnvironmentError("Expect vpc_id or environment_name")
        except IndexError:
            return None

        tags = tag2dict(vpc['Tags'] if 'Tags' in vpc else None)
        return cls(tags.get("Name", '-'), tags.get("type", '-'), vpc)

    @property
    def networks(self):
        """A dictionary containing each metanetwork name with its DiscoMetaNetwork class"""
        if self._networks:
            return self._networks
        self._networks = {
            network: DiscoMetaNetwork(network, self)
            for network in NETWORKS.keys()
            if self.get_config("{0}_cidr".format(network))  # don't create networks we haven't defined
        }
        return self._networks

    def _create_new_meta_networks(self):
        """Read the VPC config and create the DiscoMetaNetwork objects that should exist in a new VPC"""

        # don't create networks we haven't defined
        # a map of network names to the configured cidr value or "auto"
        networks = {network: self.get_config("{0}_cidr".format(network))
                    for network in NETWORKS.keys()
                    if self.get_config("{0}_cidr".format(network))}

        if len(networks) < 1:
            raise VPCConfigError('No Metanetworks configured for VPC %s' % self.environment_name)

        # calculate the extra cidr bits needed to represent the networks
        # for example breaking a /20 VPC into 4 meta networks will create /22 sized networks
        cidr_offset = calc_subnet_offset(len(networks))
        vpc_size = IPNetwork(self.vpc['CidrBlock']).prefixlen
        meta_network_size = vpc_size + cidr_offset

        # /32 is the smallest possible network
        if meta_network_size > 32:
            raise VPCConfigError('Unable to create %s metanetworks in /%s size VPC'
                                 % (len(networks), vpc_size))

        # keep a list of the cidrs used by the meta networks in case we need to pick a random one
        used_cidrs = [cidr for cidr in networks.values() if cidr != 'auto']

        metanetworks = {}
        for network_name, cidr in networks.iteritems():
            # pick a random ip range if there isn't one configured for the network in the config
            if cidr == 'auto':
                cidr = DiscoVPC.get_random_free_subnet(self.vpc['CidrBlock'], meta_network_size, used_cidrs)

                if not cidr:
                    raise VPCConfigError("Can't create metanetwork %s. No subnets available", network_name)

            metanetworks[network_name] = DiscoMetaNetwork(network_name, self, cidr)
            used_cidrs.append(cidr)

        return metanetworks

    def find_instance_route_table(self, instance):
        """ Return route tables corresponding to instance """
        rt_filter = []
        rt_filter.append(self.vpc_filter())
        rt_filter.append({"Name": "route.instance-id", "Values": [instance.id]})
        return self.boto3_ec2.describe_route_tables(Filters=rt_filter)['RouteTables']

    def delete_instance_routes(self, instance):
        """ Delete all routes associated with instance """
        route_tables = self.find_instance_route_table(instance)
        for route_table in route_tables:
            for route in route_table.routes:
                if route.instance_id == instance.id:
                    self.boto3_ec2.delete_route(
                        RouteTableId=route_table.id,
                        DestinationCidrBlock=route.destination_cidr_block)

    def _configure_dhcp(self):
        internal_dns = self.get_config("internal_dns")
        external_dns = self.get_config("external_dns")
        domain_name = self.get_config("domain_name")
        ntp_server = self.get_config("ntp_server")

        # internal_dns server should be default, and for this reason it comes last.
        dhcp_configs = []
        dhcp_configs.append({"Key": "domain-name", "Values": [domain_name]})
        dhcp_configs.append({"Key": "domain-name-servers", "Values": [internal_dns, external_dns]})
        dhcp_configs.append({"Key": "ntp-servers", "Values": [ntp_server]})

        response = self.boto3_ec2.create_dhcp_options(DhcpConfigurations=dhcp_configs)
        ec2 = boto3.resource('ec2')
        dhcp_options = ec2.DhcpOptions(response['DhcpOptions']['DhcpOptionsId'])
        dhcp_options.create_tags(Tags=[{'Key': 'Name', 'Value': self.environment_name}])
        return self.boto3_ec2.describe_dhcp_options(
            DhcpOptionsIds=[response['DhcpOptions']['DhcpOptionsId']]
        )['DhcpOptions']

    @staticmethod
    def _extract_port_range(port_def):
        ports = port_def.split(":")
        return [int(ports[0]), int(ports[1] if len(ports) > 1 else ports[0])]

    def _update_nat_gateways(self, network, dry_run=False):
        eips = self.get_config("{0}_nat_gateways".format(network.name))
        if not eips:
            # No NAT config, delete the gateways if any
            logging.debug("Deleting NAT gateways if any in meta network {0}"
                          .format(network.name))
            if not dry_run:
                network.delete_nat_gateways()
        else:
            eips = [eip.strip() for eip in eips.split(",")]
            allocation_ids = []
            for eip in eips:
                address = self.eip.find_eip_address(eip)
                if not address:
                    raise EIPConfigError("Couldn't find Elastic IP: {0}".format(eip))

                allocation_ids.append(address.allocation_id)

            if allocation_ids:
                logging.debug("Creating NAT in meta network {0} using these allocation IDs: {1}"
                              .format(network.name, allocation_ids))
                if not dry_run:
                    network.add_nat_gateways(allocation_ids)

    def _update_sg_rules(self):
        for network in self.networks.values():
            network.update_sg_rules(self._get_sg_rule_tuples(network))

    def _add_sg_rules_to_meta_networks(self):
        for network in self.networks.values():
            sg_rule_tuples = self._get_sg_rule_tuples(network)
            network.add_sg_rules(sg_rule_tuples)

    def _get_sg_rule_tuples(self, network):
        rules = self.get_config("{0}_sg_rules".format(network.name))
        if not rules:
            # No config, nothing to do
            return

        rules = rules.split(",")
        sg_rule_tuples = []
        for rule in rules:
            rule = rule.strip().split()
            if len(rule) < 3 or not all(rule):
                raise VPCEnvironmentError(
                    "Cannot make heads or tails of rule {0} for metanetwork {1}."
                    .format(" ".join(rule), network.name)
                )

            protocol = rule[0]
            source = rule[1]
            ports = rule[2:]

            for port_def in ports:
                port_def = self._extract_port_range(port_def)
                if source.lower() == "all":
                    # Handle rule where source is all other networks
                    for source_network in self.networks.values():
                        sg_rule_tuples.append(network.create_sg_rule_tuple(
                            protocol, port_def,
                            sg_source_id=source_network.security_group.id
                        ))
                elif "/" in source:
                    # Handle CIDR based sources
                    sg_rule_tuples.append(network.create_sg_rule_tuple(
                        protocol, port_def, cidr_source=source))
                else:
                    # Single network wide source
                    sg_rule_tuples.append(network.create_sg_rule_tuple(
                        protocol, port_def,
                        sg_source_id=self.networks[source].security_group.id
                    ))

        # Add security rules for customer ports
        sg_rule_tuples += self._get_dmz_customer_ports_sg_rules(network) +\
            self._get_intranet_customer_ports_sg_rules(network)

        # Add security rules to allow ICMP (ping, traceroute & etc) and DNS
        # traffic for all subnets
        sg_rule_tuples += self._get_icmp_sg_rules(network)

        return sg_rule_tuples

    def _get_icmp_sg_rules(self, network):
        return [network.create_sg_rule_tuple("icmp", [-1, -1],
                                             cidr_source=self.vpc['CidrBlock']),
                network.create_sg_rule_tuple("udp", [53, 53],
                                             cidr_source=self.vpc['CidrBlock'])]

    def _get_dmz_customer_ports_sg_rules(self, network):
        sg_rule_tuples = []
        if network.name == "dmz":
            customer_ports = self.get_config("customer_ports", "").split()
            customer_cidrs = self.get_config("customer_cidr", "").split()

            for port_def in customer_ports:
                port_range = DiscoVPC._extract_port_range(port_def)
                for customer_cidr in customer_cidrs:
                    # Allow traffic from customer to dmz
                    sg_rule_tuples.append(network.create_sg_rule_tuple(
                        "tcp", port_range, cidr_source=customer_cidr))

                # Allow within DMZ so that vpn host can talk to lbexternal
                sg_rule_tuples.append(network.create_sg_rule_tuple(
                    "tcp", port_range,
                    sg_source_id=network.security_group.id
                ))

        return sg_rule_tuples

    def _get_intranet_customer_ports_sg_rules(self, network):
        sg_rule_tuples = []
        if network.name == "intranet":
            customer_ports = self.get_config("customer_ports", "").split()
            for port_def in customer_ports:
                port_range = DiscoVPC._extract_port_range(port_def)
                # Allow traffic from dmz to intranet (for lbexternal)
                sg_rule_tuples.append(network.create_sg_rule_tuple(
                    "tcp", port_range,
                    sg_source_id=self.networks["dmz"].security_group.id
                ))

        return sg_rule_tuples

    def _set_up_gateways(self):
        # Set up Internet and VPN gateways
        internet_gateway = self._create_internet_gw()
        vpn_gateway = self._find_and_attach_vpn_gw()

        for network in self.networks.values():
            route_tuples = self._get_gateway_route_tuples(network.name, internet_gateway, vpn_gateway)

            logging.debug("Adding gateway routes to meta network {0}: {1}".format(
                network.name, route_tuples))
            network.add_gateway_routes(route_tuples)

    def _update_gateway_routes(self):
        internet_gateway = self._find_internet_gw()
        vpn_gateway = self._find_vgw()

        for network in self.networks.values():
            logging.debug("Update routes for meta network {0}".format(network.name))
            route_tuples = self._get_gateway_route_tuples(network.name, internet_gateway, vpn_gateway)
            network.update_gateway_routes(route_tuples)

    def _get_gateway_route_tuples(self, network_name, internet_gateway, vpn_gateway):
        route_tuples = []

        if internet_gateway:
            igw_routes = self.get_config("{0}_igw_routes".format(network_name))
            if igw_routes:
                igw_routes = igw_routes.split(" ")
                for igw_route in igw_routes:
                    route_tuples.append((igw_route, internet_gateway['InternetGatewayId']))

        if vpn_gateway:
            vgw_routes = self.get_config("{0}_vgw_routes".format(network_name))
            if vgw_routes:
                vgw_routes = vgw_routes.split(" ")
                for vgw_route in vgw_routes:
                    route_tuples.append(vgw_route, vpn_gateway['VpnGatewayId'])

        return route_tuples

    def _create_internet_gw(self):
        internet_gateway = self.boto3_ec2.create_internet_gateway()['InternetGateway']
        self.boto3_ec2.attach_internet_gateway(
            InternetGatewayId=internet_gateway['InternetGatewayId'],
            VpcId=self.get_vpc_id())
        logging.debug("internet_gateway: %s", internet_gateway)

        return internet_gateway

    def _find_and_attach_vpn_gw(self):
        """If configured, attach VPN Gateway and create corresponding routes"""
        vgw = self._find_vgw()
        if vgw:
            logging.debug("Attaching VGW: %s.", vgw)
            if vgw['VpcAttachments'] and vgw['VpcAttachments'][0]['State'] != 'detached':
                logging.info("VGW %s already attached to %s. Will detach and reattach to %s.",
                             vgw['VpnGatewayId'], vgw['VpcAttachments'][0]['VpcId'], self.get_vpc_id())
                self._detach_vgws()
                logging.debug("Waiting 30s to avoid VGW 'non-existance' conditon post detach.")
                time.sleep(30)
            self.boto3_ec2.attach_vpn_gateway(VpnGatewayId=vgw['VpnGatewayId'], VpcId=self.get_vpc_id())
            logging.debug("Waiting for VGW to become attached.")
            self._wait_for_vgw_states(u'attached')
            logging.debug("VGW have been attached.")
        else:
            logging.info("No VGW to attach.")

        return vgw

    def _set_up_nat_gateways(self):
        for network in self.networks.values():
            self._update_nat_gateways(network)

        # Setup NAT gateway routes
        nat_gateway_routes = self._parse_nat_gateway_routes_config()
        if nat_gateway_routes:
            logging.debug("Adding NAT gateway routes")
            self._add_nat_gateway_routes(nat_gateway_routes)
        else:
            logging.debug("No NAT gateway routes to add")

    def _update_nat_gateways_and_routes(self, dry_run=False):
        desired_nat_routes = set(self._parse_nat_gateway_routes_config())

        current_nat_routes = []
        for network in self.networks.values():
            nat_gateway_metanetwork = network.get_nat_gateway_metanetwork()
            if nat_gateway_metanetwork:
                current_nat_routes.append((network.name, nat_gateway_metanetwork))
        current_nat_routes = set(current_nat_routes)

        # Updating NAT gateways has to be done AFTER current NAT routes are calculated
        # because we don't want to delete existing NAT gateways before that.
        for network in self.networks.values():
            self._update_nat_gateways(network)

        routes_to_delete = list(current_nat_routes - desired_nat_routes)
        logging.debug("NAT gateway routes to delete (source, dest): {0}".format(routes_to_delete))

        routes_to_add = list(desired_nat_routes - current_nat_routes)
        logging.debug("NAT gateway routes to add (source, dest): {0}".format(routes_to_add))

        if not dry_run:
            self._delete_nat_gateway_routes([route[0] for route in routes_to_delete])
            self._add_nat_gateway_routes(routes_to_add)

    def _add_nat_gateway_routes(self, nat_gateway_routes):
        for route in nat_gateway_routes:
            self.networks[route[0]].add_nat_gateway_route(self.networks[route[1]])

    def _delete_nat_gateway_routes(self, meta_networks):
        for route in meta_networks:
            self.networks[route].delete_nat_gateway_route()

    def _parse_nat_gateway_routes_config(self):
        """ Returns a list of tuples whose first value is the source meta network and
        whose second value is the destination meta network """
        result = []
        nat_gateway_routes = self.get_config("nat_gateway_routes")
        if nat_gateway_routes:
            nat_gateway_routes = nat_gateway_routes.split(" ")
            for nat_gateway_route in nat_gateway_routes:
                network_pair = nat_gateway_route.split("/")
                result.append((network_pair[0].strip(), network_pair[1].strip()))

        return result

    def _find_internet_gw(self):
        """Locate Internet Gateway that corresponds to this VPN"""
        igw_filter = [{"Name": "attachment.vpc-id", "Values": [self.vpc['VpcId']]}]
        igws = self.boto3_ec2.describe_internet_gateways(Filters=igw_filter)
        try:
            return igws['InternetGateways'][0]
        except IndexError:
            logging.warning("Cannot find the required Internet Gateway named for VPC {0}."
                            .format(self.vpc['VpcId']))
            return None

    def _find_vgw(self):
        """Locate VPN Gateway that corresponds to this VPN"""
        vgw_filter = [{"Name": "tag-value", "Values": [self.environment_name]}]
        vgws = self.boto3_ec2.describe_vpn_gateways(Filters=vgw_filter)
        if not len(vgws['VpnGateways']):
            logging.debug("Cannot find the required VPN Gateway named %s.", self.environment_name)
            return None
        return vgws['VpnGateways'][0]

    def _check_vgw_states(self, state):
        """Checks if all VPN Gateways are in the desired state"""
        filters = {"Name": "tag:Name", "Values": [self.environment_name]}
        states = []
        vgws = self.boto3_ec2.describe_vpn_gateways(Filters=[filters])
        for vgw in vgws['VpnGateways']:
            for attachment in vgw['VpcAttachments']:
                if state == u'detached':
                    states.append(attachment['State'] == state)
                elif attachment['VpcId'] == self.get_vpc_id():
                    states.append(attachment['State'] == state)
        logging.debug("%s of %s VGW attachments are now in state '%s'",
                      states.count(True), len(states), state)
        return states and all(states)

    def _wait_for_vgw_states(self, state, timeout=VGW_ATTACH_TIME):
        """Wait for all VPN Gateways to reach a specified state"""
        time_passed = 0
        while True:
            try:
                if self._check_vgw_states(state):
                    return True
            except EC2ResponseError:
                pass  # These are most likely transient, we will timeout if they are not

            if time_passed >= timeout:
                raise TimeoutError(
                    "Timed out waiting for VPN Gateways to change state to {0} after {1}s."
                    .format(state, time_passed))

            time.sleep(VGW_STATE_POLL_INTERVAL)
            time_passed += VGW_STATE_POLL_INTERVAL

    def _detach_vgws(self):
        """Detach VPN Gateways, but don't delete them so they can be re-used"""
        vgw_filter = [
            {"Name": "attachment.state", "Values": ['attached']},
            {"Name": "tag:Name", "Values": [self.environment_name]}
        ]
        detached = False
        for vgw in self.boto3_ec2.describe_vpn_gateways(Filters=vgw_filter)['VpnGateways']:
            logging.debug("Detaching VGW: %s.", vgw)
            if not self.boto3_ec2.detach_vpn_gateway(VpnGatewayId=vgw['VpnGatewayId'],
                                                     VpcId=vgw['VpcAttachments'][0]['VpcId']):
                logging.error("Failed to detach %s from %s", vgw['VpnGatewayId'],
                              vgw['VpcAttachments'][0]['VpcId'])
            else:
                detached = True

        if not detached:
            return

        try:
            logging.debug("Waiting for VGWs to become detached.")
            self._wait_for_vgw_states(u'detached')
        except TimeoutError:
            logging.exception("Failed to detach VPN Gateways (Timeout).")

    def _update_peering_connections(self):
        """
        desired_peerings_map = {self.get_peering_tuple(peering_line): config
                                for peering_line, config in
                                DiscoVPC.parse_peerings_config(self.get_vpc_id()).iteritems()}
        """
        current_peerings = self._get_current_peerings()
        
        print '$$$$$$$$$$$$$$$'
        print current_peerings
        # TODO: Test this!!!!!!!!!!

       # DiscoVPC.create_peering_connections(DiscoVPC.parse_peerings_config(self.get_vpc_id()))

    def _get_current_peerings(self):
        current_peerings = set()

        for peering in DiscoVPC.list_peerings(self.get_vpc_id()):

            peer_vpc = self._find_peer_vpc(self._get_peer_vpc_id(peering))

            vpc_peering_route_tables = self.boto3_ec2.describe_route_tables(
                Filters=[{'Name': 'route.vpc-peering-connection-id',
                          'Values': [peering['VpcPeeringConnectionId']]}])['RouteTables']

            for route_table in vpc_peering_route_tables:
                subnet_name_parts = get_name_tag_value(route_table['Tags']).split('_')
                if subnet_name_parts[0] == self.environment_name:
                    source_network = subnet_name_parts[0] + ':' + \
                        self.environment_type + '/' + \
                        subnet_name_parts[1]

                    for route in route_table['Routes']:
                        if route.get('VpcPeeringConnectionId') == peering['VpcPeeringConnectionId']:
                            dest_network = peer_vpc.environment_name + ':' + \
                                           peer_vpc.environment_type + '/' + \
                                           [network.name for network in peer_vpc.networks.values()
                                            if str(network.network_cidr) == route['DestinationCidrBlock']][0]

                            current_peerings.add(source_network + ' ' + dest_network)

        return current_peerings

    def _get_peer_vpc_id(self, peering):
        if peering['AccepterVpcInfo']['VpcId'] != self.get_vpc_id():
            return peering['AccepterVpcInfo']['VpcId']
        else:
            return peering['RequesterVpcInfo']['VpcId']

    def _find_peer_vpc(self, peer_vpc_id):
        try:
            peer_vpc = self.boto3_ec2.describe_vpcs(VpcIds=[peer_vpc_id])['Vpcs'][0]
        except IndexError:
            raise RuntimeError("Failed to retrieve VPC with vpc_id: {0}".format(peer_vpc_id))

        try:
            for tag in peer_vpc['Tags']:
                if tag['Key'] == 'Name':
                    vpc_name = tag['Value']
                elif tag['Key'] == 'type':
                    vpc_type = tag['Value']

            return DiscoVPC(vpc_name, vpc_type, peer_vpc)
        except UnboundLocalError:
            raise RuntimeError("VPC {0} is missing tags: 'Name', 'type'.".format(peer_vpc_id))

    def get_peering_tuple(self, peering_line):
        peering_line.split('/')

    def _update_environment(self):
        """Update the disco style environment VPC"""
        # TODO: We should probably ignore changes in cidr
        """
        vpc_cidr = self.get_config("vpc_cidr")
        if vpc_cidr != self.vpc['CidrBlock']:
            logging.error("VPC cannot be updated, Cidr values are different, %s instead of"
                          "%s", vpc_cidr, self.vpc['CidrBlock'])
        """

        #self._update_sg_rules()
        #self._update_gateway_routes()
        #self._update_nat_gateways_and_routes()

        self._update_peering_connections()
        #self.configure_notifications()
        #DiscoVPC.create_peering_connections(DiscoVPC.parse_peerings_config(self.get_vpc_id()))
        #self.rds.update_all_clusters_in_vpc()

    def _create_environment(self):
        """Create a new disco style environment VPC"""
        vpc_cidr = self.get_config("vpc_cidr")

        # if a vpc_cidr is not configured then allocate one dynamically
        if not vpc_cidr:
            ip_space = self.get_config("ip_space")
            vpc_size = self.get_config("vpc_cidr_size")

            if not ip_space and vpc_size:
                raise VPCConfigError('Cannot create VPC %s. ip_space or vpc_cidr_size missing'
                                     % self.environment_name)

            # get the cidr for all other VPCs so we can avoid overlapping with other VPCs
            occupied_network_cidrs = [vpc['cidr_block'] for vpc in self.list_vpcs()]

            vpc_cidr = DiscoVPC.get_random_free_subnet(ip_space, int(vpc_size), occupied_network_cidrs)

            if vpc_cidr is None:
                raise VPCConfigError('Cannot create VPC %s. No subnets available' % self.environment_name)

        # Create VPC
        self.vpc = self.boto3_ec2.create_vpc(CidrBlock=str(vpc_cidr))['Vpc']
        waiter = self.boto3_ec2.get_waiter('vpc_available')
        waiter.wait(VpcIds=[self.vpc['VpcId']])
        ec2 = boto3.resource('ec2')
        vpc = ec2.Vpc(self.vpc['VpcId'])
        tags = vpc.create_tags(Tags=[{'Key': 'Name', 'Value': self.environment_name},
                                     {'Key': 'type', 'Value': self.environment_type}])
        logging.debug("vpc: %s", self.vpc)
        logging.debug("vpc tags: %s", tags)

        dhcp_options = self._configure_dhcp()[0]
        self.boto3_ec2.associate_dhcp_options(DhcpOptionsId=dhcp_options['DhcpOptionsId'],
                                           VpcId=self.vpc['VpcId'])

        # Enable DNS
        self.boto3_ec2.modify_vpc_attribute(VpcId=self.vpc['VpcId'],
                                         EnableDnsSupport={'Value': True})
        self.boto3_ec2.modify_vpc_attribute(VpcId=self.vpc['VpcId'],
                                         EnableDnsHostnames={'Value': True})

        # Create metanetworks (subnets, route_tables and security groups)
        self._networks = self._create_new_meta_networks()
        for network in self.networks.values():
            network.create()

        # Configure security group rules for all meta networks
        self._add_sg_rules_to_meta_networks()

        # Setup internet gateway and VPN gateway
        self._set_up_gateways()

        # Setup NAT gateways
        self._set_up_nat_gateways()

        self.configure_notifications()
        DiscoVPC.create_peering_connections(DiscoVPC.parse_peerings_config(self.get_vpc_id()))
        self.rds.update_all_clusters_in_vpc()

    def configure_notifications(self):
        """
        Configure SNS topics for CloudWatch alarms.
        Note that topics are not deleted with the VPC, since that would require re-subscribing the members.
        """
        notifications = self.alarms_config.get_notifications()
        DiscoSNS().update_sns_with_notifications(notifications, self.environment_name)

    def assign_eip(self, instance, eip_address, allow_reassociation=False):
        """
        Assign EIP to an instance
        """
        eip = self.boto3_ec2.describe_addresses(PublicIps=[eip_address])['Addresses'][0]
        try:
            self.boto3_ec2.associate_address(
                InstanceId=instance.id,
                AllocationId=eip['AllocationId'],
                AllowReassociation=allow_reassociation
            )
        except EC2ResponseError:
            logging.exception("Skipping failed EIP association. Perhaps reassociation of EIP is not allowed?")

    @staticmethod
    def _find_sg_by_id(groups, group_id):
        """
        Given a list of security groups, returns one with the matching ID

        raises KeyError if it is not found.
        """
        for group in groups:
            if group['GroupId'] == group_id:
                print "group:"
                print group
                return group
        raise KeyError("Security Group not found {0}".format(group_id))

    def vpc_filter(self):
        """Filter used to get only the current VPC when filtering an AWS reply by 'vpc-id'"""
        return {"Name": "vpc-id", "Values": [self.vpc['VpcId']]}

    def update(self):
        ''' Update an existing VPC '''
        self._update_environment()

    def destroy(self):
        """ Delete all VPC resources in the right order and then delete the vpc itself """
        DiscoAlarm().delete_environment_alarms(self.environment_name)
        self.log_metrics.delete_all_metrics()
        self.log_metrics.delete_all_log_groups()
        self._destroy_instances()
        self.elb.destroy_all_elbs()
        self._destroy_rds()
        self.elasticache.delete_all_cache_clusters(wait=True)
        self.elasticache.delete_all_subnet_groups()
        self._destroy_interfaces()
        self._destroy_nat_gateways()
        self._destroy_subnets()
        self._delete_security_group_rules()
        keep_trying(60, self._destroy_security_groups)
        self._destroy_igws()
        self._destroy_routes()
        self._detach_vgws()
        DiscoVPC.delete_peerings(self.get_vpc_id())
        return self._destroy_vpc()

    def _destroy_instances(self):
        """ Find all instances in vpc and terminate them """
        autoscale = DiscoAutoscale(environment_name=self.environment_name)
        autoscale.clean_groups(force=True)
        instances = [i['InstanceId']
                     for r in self.boto3_ec2.describe_instances(Filters=[self.vpc_filter()])['Reservations']
                     for i in r['Instances']]

        if not instances:
            logging.debug("No running instances")
            return
        logging.debug("terminating %s instance(s) %s", len(instances), instances)

        # for instance in instances:
        #    instance.terminate()
        # for instance in instances:
        #    wait_for_state(instance, u'terminated')

        self.boto3_ec2.terminate_instances(InstanceIds=instances)
        waiter = self.boto3_ec2.get_waiter('instance_terminated')
        waiter.wait(InstanceIds=instances,
                    Filters=[{'Name': 'instance-state-name', 'Values': ['terminated']}])
        autoscale.clean_configs()

        logging.debug("waiting for instance shutdown scripts")

    def _destroy_rds(self, wait=True):
        """ Delete all RDS instances/clusters. Final snapshots are automatically taken. """
        self.rds.delete_all_db_instances(wait=wait)

    def _destroy_interfaces(self):
        """ Deleting interfaces explicitly lets go of subnets faster """
        for interface in self.boto3_ec2.describe_network_interfaces(
                Filters=[self.vpc_filter()])["NetworkInterfaces"]:
            try:
                self.boto3_ec2.delete_network_interface(NetworkInterfaceId=interface['NetworkInterfaceId'])
            except EC2ResponseError:
                # Occasionally we get InvalidNetworkInterfaceID.NotFound, not sure why.
                logging.exception("Skipping error deleting network.")

    def _destroy_nat_gateways(self):
        """ Find all NAT gateways belonging to a vpc and destroy them"""
        filter_params = {'Filters': [{'Name': 'vpc-id', 'Values': [self.vpc['VpcId']]}]}

        nat_gateways = self.boto3_ec2.describe_nat_gateways(**filter_params)['NatGateways']
        for nat_gateway in nat_gateways:
            self.boto3_ec2.delete_nat_gateway(NatGatewayId=nat_gateway['NatGatewayId'])

        # Need to wait for all the NAT gateways to be deleted
        wait_for_state_boto3(self.boto3_ec2.describe_nat_gateways, filter_params,
                             'NatGateways', 'deleted', 'State')

    def _destroy_subnets(self):
        """ Find all subnets belonging to a vpc and destroy them"""
        for subnet in self.boto3_ec2.describe_subnets(Filters=[self.vpc_filter()])['Subnets']:
            self.boto3_ec2.delete_subnet(SubnetId=subnet['SubnetId'])

    def _delete_security_group_rules(self):
        """ Delete all security group rules."""
        security_groups = self.get_all_security_groups_for_vpc()
        for security_group in security_groups:
            for permission in security_group['IpPermissions']:
                try:
                    logging.debug(
                        "revoking %s %s %s %s", security_group, permission.get('IpProtocol'),
                        permission.get('FromPort', '-'), permission.get('ToPort', '-'))
                    self.boto3_ec2.revoke_security_group_ingress(
                        GroupId=security_group['GroupId'],
                        IpPermissions=[permission]
                    )
                except EC2ResponseError:
                    logging.exception("Skipping error deleting sg rule.")

    def _destroy_security_groups(self):
        """ Find all security groups belonging to vpc and destroy them."""
        for security_group in self.get_all_security_groups_for_vpc():
            if security_group['GroupName'] != u'default':
                logging.debug("deleting sg: %s", security_group)
                self.boto3_ec2.delete_security_group(GroupId=security_group['GroupId'])

    def get_all_security_groups_for_vpc(self):
        """ Find all security groups belonging to vpc and return them """
        return self.boto3_ec2.describe_security_groups(Filters=[self.vpc_filter()])['SecurityGroups']

    def _destroy_igws(self):
        """ Find all gateways belonging to vpc and destroy them"""
        vpc_attachment_filter = {"Name": "attachment.vpc-id", "Values": [self.get_vpc_id()]}
        # delete gateways
        for igw in self.boto3_ec2.describe_internet_gateways(
                Filters=[vpc_attachment_filter])['InternetGateways']:
            self.boto3_ec2.detach_internet_gateway(
                InternetGatewayId=igw['InternetGatewayId'],
                VpcId=self.get_vpc_id())
            self.boto3_ec2.delete_internet_gateway(InternetGatewayId=igw['InternetGatewayId'])

    def _destroy_routes(self):
        """ Find all route_tables belonging to vpc and destroy them"""
        for route_table in self.boto3_ec2.describe_route_tables(Filters=[self.vpc_filter()])['RouteTables']:
            if len(route_table['Tags']) < 1:
                logging.info("Skipping untagged (default) route table %s", route_table['RouteTableId'])
                continue
            try:
                self.boto3_ec2.delete_route_table(RouteTableId=route_table['RouteTableId'])
            except EC2ResponseError:
                logging.error("Error deleting route_table %s:.", route_table['RouteTableId'])
                raise

    def _destroy_vpc(self):
        """Delete VPC and then delete the dhcp_options that were associated with it. """

        # save function and parameters so we can delete dhcp_options after vpc. We do this becase botos
        # get_all_dhcp_options does not support filter. Because we cannot easily find the default dhcp
        # options, re-assigning default dhcp option is not trivial.
        # delete_dhcp_options = self.vpc.connection.delete_dhcp_options
        dhcp_options_id = self.vpc['DhcpOptionsId']

        self.boto3_ec2.delete_vpc(VpcId=self.get_vpc_id())
        # delete_status = keep_trying(30, self.vpc.delete)
        self.vpc = None

        self.boto3_ec2.delete_dhcp_options(DhcpOptionsId=dhcp_options_id)
        # if not delete_dhcp_options(dhcp_options_id):
        #    logging.warning("failed to delete dhcp options (%s)", dhcp_options_id)

        # return delete_status

    @staticmethod
    def find_vpc_id_by_name(vpc_name):
        """Find VPC by name"""
        client = boto3.client('ec2')
        vpcs = client.describe_vpcs(Filters=[{'Name': 'tag:Name', 'Values': [vpc_name]}])['Vpcs']
        if len(vpcs) == 1:
            return vpcs[0]['VpcId']
        elif len(vpcs) == 0:
            raise VPCNameNotFound("No VPC is named as {}".format(vpc_name))
        else:
            raise MultipleVPCsForVPCNameError("More than 1 VPC is named as {}".format(vpc_name))

    @staticmethod
    def parse_peering_connection_line(line, vpc_conn):
        """
        Parses vpc connections of the form `vpc_name[:vpc_type]/metanetwork vpc_name[:vpc_type]/metanetwork`
        and returns the data in two dictionaries: vpc_name -> DiscoVPC instance and vpc_name -> metanetwork.
        vpc_type defaults to vpc_name if unspecified.
        """
        logging.debug('checking existence for peering %s', line)
        endpoints = line.split(' ')

        def get_vpc_name(endpoint):
            """return name from `name[:type]/metanetwork`"""
            return endpoint.split('/')[0].split(':')[0].strip()

        def get_vpc_type(endpoint):
            """return type from `name[:type]/metanetwork`, defaulting to name if type is omitted"""
            return endpoint.split('/')[0].split(':')[-1].strip()

        def get_metanetwork(endpoint):
            """return metanetwork from `name[:type]/metanetwork`"""
            return endpoint.split('/')[1].strip()

        def safe_get_from_list(_list, i):
            """returns the i-th element in a list, or None if it doesn't exist"""
            return _list[i] if _list and len(_list) > i else None

        vpc_type_map = {
            get_vpc_name(endpoint): get_vpc_type(endpoint)
            for endpoint in endpoints
        }

        vpc_objects = {
            vpc_name: safe_get_from_list(
                vpc_conn.describe_vpcs(Filters=[{'Name': 'tag-value', 'Values': [vpc_name]}])['Vpcs'], 0)
            for vpc_name in vpc_type_map.keys()
        }

        missing_vpcs = [vpc_name for vpc_name, vpc_object in vpc_objects.items() if not vpc_object]
        if missing_vpcs:
            logging.debug(
                "Skipping peering %s because the following VPC(s) are not up: %s",
                line, ", ".join(map(str, missing_vpcs)))
            return {}

        vpc_map = {
            k: DiscoVPC(k, v, vpc_objects[k])
            for k, v in vpc_type_map.iteritems()
        }

        for vpc in vpc_map.values():
            if not vpc.networks:
                raise RuntimeError("No metanetworks found for vpc {}. Are you sure it's of type {}?".format(
                    vpc.environment_name, vpc.environment_type))

        vpc_metanetwork_map = {
            get_vpc_name(endpoint): get_metanetwork(endpoint)
            for endpoint in endpoints
        }

        return {
            'vpc_metanetwork_map': vpc_metanetwork_map,
            'vpc_map': vpc_map
        }

    @staticmethod
    def parse_peerings_config(vpc_id=None):
        """
        Parses configuration from disco_vpc.ini's peerings sections.
        If vpc_id is specified, only configuration relevant to vpc_id is included.
        """
        logging.debug("Parsing peerings configuration specified in %s", CONFIG_FILE)
        config = read_config(CONFIG_FILE)

        if 'peerings' not in config.sections():
            logging.info("No VPC peering configuration defined.")
            return {}

        peerings = [
            peering[1]
            for peering in config.items('peerings')
            if peering[0].startswith('connection_')
        ]

        for peering in peerings:
            endpoints = [_.strip() for _ in peering.split(' ')]
            if len(endpoints) != 2:
                raise VPCPeeringSyntaxError(
                    "Syntax error in vpc peering connection. "
                    "Expected 2 space-delimited endpoints but found: '{}'".format(peering))

        # vpc_conn = VPCConnection()
        client = boto3.client('ec2')
        peering_configs = {}
        for peering in peerings:
            peering_config = DiscoVPC.parse_peering_connection_line(peering, client)
            vpc_ids_in_peering = [vpc.vpc['VpcId'] for vpc in peering_config.get("vpc_map", {}).values()]

            if len(vpc_ids_in_peering) < 2:
                pass  # not all vpcs were up, nothing to do
            elif vpc_id and vpc_id not in vpc_ids_in_peering:
                logging.debug("Skipping peering %s because it doesn't include %s", peering, vpc_id)
            else:
                peering_configs[peering] = peering_config

        return peering_configs

    @staticmethod
    def create_peering_connections(peering_configs):
        """ create vpc peering configuration from the peering config dictionary"""
        client = boto3.client('ec2')
        for peering in peering_configs.keys():
            vpc_map = peering_configs[peering]['vpc_map']
            vpc_metanetwork_map = peering_configs[peering]['vpc_metanetwork_map']
            vpc_ids = [vpc.vpc['VpcId'] for vpc in vpc_map.values()]
            existing_peerings = client.describe_vpc_peering_connections(
                Filters=[
                    {'Name': 'status-code', 'Values': ['active']},
                    {'Name': 'accepter-vpc-info.vpc-id', 'Values': [vpc_ids[0]]},
                    {'Name': 'requester-vpc-info.vpc-id', 'Values': [vpc_ids[1]]}
                ]
            )['VpcPeeringConnections'] + client.describe_vpc_peering_connections(
                Filters=[
                    {'Name': 'status-code', 'Values': ['active']},
                    {'Name': 'accepter-vpc-info.vpc-id', 'Values': [vpc_ids[1]]},
                    {'Name': 'requester-vpc-info.vpc-id', 'Values': [vpc_ids[0]]}
                ]
            )['VpcPeeringConnections']

            # create peering when peering doesn't exist
            if not existing_peerings:
                peering_conn = client.create_vpc_peering_connection(
                    VpcId=vpc_ids[0], PeerVpcId=vpc_ids[1])['VpcPeeringConnection']
                client.accept_vpc_peering_connection(
                    VpcPeeringConnectionId=peering_conn['VpcPeeringConnectionId'])
                logging.info("created new peering connection %s for %s",
                             peering_conn['VpcPeeringConnectionId'], peering)
            else:
                peering_conn = existing_peerings[0]
                logging.info("peering connection %s exists for %s",
                             existing_peerings[0]['VpcPeeringConnectionId'], peering)
            DiscoVPC.create_peering_routes(vpc_map, vpc_metanetwork_map, peering_conn)

    @staticmethod
    def create_peering_routes(vpc_map, vpc_metanetwork_map, peering_conn):
        """ create/update routes via peering connections between VPCs """
        cidr_map = {
            _: vpc_map[_].networks[vpc_metanetwork_map[_]].network_cidr
            for _ in vpc_map.keys()
        }
        network_map = {
            _: vpc_map[_].networks[vpc_metanetwork_map[_]]
            for _ in vpc_map.keys()
        }
        for vpc_name, network in network_map.iteritems():
            remote_vpc_names = vpc_map.keys()
            remote_vpc_names.remove(vpc_name)

            network.create_peering_route(peering_conn['VpcPeeringConnectionId'],
                                         str(cidr_map[remote_vpc_names[0]]))

    @staticmethod
    def list_vpcs():
        """Returns list of boto.vpc.vpc.VPC classes, one for each existing VPC"""
        client = boto3.client('ec2')
        vpcs = client.describe_vpcs()
        return [{'id': vpc['VpcId'],
                 'tags': tag2dict(vpc['Tags'] if 'Tags' in vpc else None),
                 'cidr_block': vpc['CidrBlock']}
                for vpc in vpcs['Vpcs']]

    @staticmethod
    def list_peerings(vpc_id=None, include_failed=False):
        """
        Return list of live vpc peering connection id.
        If vpc_id is given, return only that vpcs peerings
        Peerings that cannot be manipulated are ignored.
        """
        client = boto3.client('ec2')
        if vpc_id:
            peerings = client.describe_vpc_peering_connections(
                Filters=[{'Name': 'requester-vpc-info.vpc-id', 'Values': [vpc_id]}]
            )['VpcPeeringConnections'] + client.describe_vpc_peering_connections(
                Filters=[{'Name': 'accepter-vpc-info.vpc-id', 'Values': [vpc_id]}]
            )['VpcPeeringConnections']
        else:
            peerings = client.describe_vpc_peering_connections()['VpcPeeringConnections']

        peering_states = LIVE_PEERING_STATES + (["failed"] if include_failed else [])
        return [
            peering
            for peering in peerings
            if peering['Status']['Code'] in peering_states
        ]

    @staticmethod
    def delete_peerings(vpc_id=None):
        """Delete peerings. If vpc_id is specified, delete all peerings of the VPCs only"""
        client = boto3.client('ec2')
        for peering in DiscoVPC.list_peerings(vpc_id):
            try:
                logging.info('deleting peering connection %s', peering['VpcPeeringConnectionId'])
                client.delete_vpc_peering_connection(VpcPeeringConnectionId=peering['VpcPeeringConnectionId'])
            except EC2ResponseError:
                raise RuntimeError('Failed to delete VPC Peering connection \
                                    {}'.format(peering['VpcPeeringConnectionId']))

    @staticmethod
    def get_random_free_subnet(network_cidr, network_size, occupied_network_cidrs):
        """
        Pick a random available subnet from a bigger network
        Args:
            network_cidr (str): CIDR string describing a network
            network_size (int): The number of bits for the CIDR of the subnet
            occupied_network_cidrs (List[str]): List of CIDR strings describing existing networks
                                                to avoid overlapping with

        Returns str: The CIDR of a randomly chosen subnet that doesn't intersect with
                     the ip ranges of any of the given other networks
        """
        possible_subnets = IPNetwork(network_cidr).subnet(int(network_size))
        occupied_networks = [IPSet(IPNetwork(cidr)) for cidr in occupied_network_cidrs]

        # find the subnets that don't overlap with any other networks
        available_subnets = [subnet for subnet in possible_subnets
                             if all([IPSet(subnet).isdisjoint(occupied_network)
                                     for occupied_network in occupied_networks])]

        return random.choice(available_subnets) if available_subnets else None
