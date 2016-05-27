"""
This module contains logic that processes a VPC's Internet, VPN, and NAT gateways and the routes to them
"""

import logging
import time

from boto.exception import EC2ResponseError

from .resource_helper import wait_for_state_boto3
from .disco_eip import DiscoEIP
from .exceptions import (TimeoutError, EIPConfigError)


VGW_STATE_POLL_INTERVAL = 2  # seconds
VGW_ATTACH_TIME = 600  # seconds. From observation, it takes about 300s to attach vgw


class DiscoVPCGateways(object):
    """
    This class takes care of processing of a VPC's Internet, VPN, and NAT gateways and the routes to them
    """
    # TODO: implement logging
    def __init__(self, vpc, boto3_ec2):
        self.disco_vpc = vpc
        self.boto3_ec2 = boto3_ec2
        self.eip = DiscoEIP()

    def set_up_gateways(self):
        # Set up Internet and VPN gateways
        internet_gateway = self._create_internet_gw()
        vpn_gateway = self._find_and_attach_vpn_gw()

        for network in self.disco_vpc.networks.values():
            route_tuples = self._get_gateway_route_tuples(network.name, internet_gateway, vpn_gateway)

            logging.debug("Adding gateway routes to meta network {0}: {1}".format(
                network.name, route_tuples))
            network.add_gateway_routes(route_tuples)

    def update_gateway_routes(self, dry_run=False):
        # Update routes to Internet and VPN gateways
        internet_gateway = self._find_internet_gw()
        vpn_gateway = self._find_vgw()

        for network in self.disco_vpc.networks.values():
            logging.info("Updating gateway routes for meta network: {0}".format(network.name))
            route_tuples = self._get_gateway_route_tuples(network.name, internet_gateway, vpn_gateway)
            network.update_gateway_routes(route_tuples, dry_run)

    def destroy_all(self):
        self._destroy_igws()
        self._detach_vgws()
        self._destroy_nat_gateways()

    def _get_gateway_route_tuples(self, network_name, internet_gateway, vpn_gateway):
        route_tuples = []

        if internet_gateway:
            igw_routes = self.disco_vpc.get_config("{0}_igw_routes".format(network_name))
            if igw_routes:
                igw_routes = igw_routes.split(" ")
                for igw_route in igw_routes:
                    route_tuples.append((igw_route, internet_gateway['InternetGatewayId']))

        if vpn_gateway:
            vgw_routes = self.disco_vpc.get_config("{0}_vgw_routes".format(network_name))
            if vgw_routes:
                vgw_routes = vgw_routes.split(" ")
                for vgw_route in vgw_routes:
                    route_tuples.append((vgw_route, vpn_gateway['VpnGatewayId']))

        return route_tuples

    def _create_internet_gw(self):
        internet_gateway = self.boto3_ec2.create_internet_gateway()['InternetGateway']
        self.boto3_ec2.attach_internet_gateway(
            InternetGatewayId=internet_gateway['InternetGatewayId'],
            VpcId=self.disco_vpc.get_vpc_id())
        logging.debug("internet_gateway: %s", internet_gateway)

        return internet_gateway

    def _find_and_attach_vpn_gw(self):
        """If configured, attach VPN Gateway and create corresponding routes"""
        vgw = self._find_vgw()
        if vgw:
            logging.debug("Attaching VGW: %s.", vgw)
            if vgw['VpcAttachments'] and vgw['VpcAttachments'][0]['State'] != 'detached':
                logging.info("VGW %s already attached to %s. Will detach and reattach to %s.",
                             vgw['VpnGatewayId'], vgw['VpcAttachments'][0]['VpcId'],
                             self.disco_vpc.get_vpc_id())
                self._detach_vgws()
                logging.debug("Waiting 30s to avoid VGW 'non-existance' conditon post detach.")
                time.sleep(30)
            self.boto3_ec2.attach_vpn_gateway(
                VpnGatewayId=vgw['VpnGatewayId'], VpcId=self.disco_vpc.get_vpc_id())
            logging.debug("Waiting for VGW to become attached.")
            self._wait_for_vgw_states(u'attached')
            logging.debug("VGW have been attached.")
        else:
            logging.info("No VGW to attach.")

        return vgw

    def _find_internet_gw(self):
        """Locate Internet Gateway that corresponds to this VPN"""
        igw_filter = [{"Name": "attachment.vpc-id", "Values": [self.disco_vpc.vpc['VpcId']]}]
        igws = self.boto3_ec2.describe_internet_gateways(Filters=igw_filter)
        try:
            return igws['InternetGateways'][0]
        except IndexError:
            logging.warning("Cannot find the required Internet Gateway named for VPC {0}."
                            .format(self.disco_vpc.vpc['VpcId']))
            return None

    def _find_vgw(self):
        """Locate VPN Gateway that corresponds to this VPN"""
        vgw_filter = [{"Name": "tag-value", "Values": [self.disco_vpc.environment_name]}]
        vgws = self.boto3_ec2.describe_vpn_gateways(Filters=vgw_filter)
        if not len(vgws['VpnGateways']):
            logging.debug("Cannot find the required VPN Gateway named %s.", self.disco_vpc.environment_name)
            return None
        return vgws['VpnGateways'][0]

    def _check_vgw_states(self, state):
        """Checks if all VPN Gateways are in the desired state"""
        filters = {"Name": "tag:Name", "Values": [self.disco_vpc.environment_name]}
        states = []
        vgws = self.boto3_ec2.describe_vpn_gateways(Filters=[filters])
        for vgw in vgws['VpnGateways']:
            for attachment in vgw['VpcAttachments']:
                if state == u'detached':
                    states.append(attachment['State'] == state)
                elif attachment['VpcId'] == self.disco_vpc.get_vpc_id():
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
            {"Name": "tag:Name", "Values": [self.disco_vpc.environment_name]}
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

    def _destroy_igws(self):
        """ Find all gateways belonging to vpc and destroy them"""
        vpc_attachment_filter = {"Name": "attachment.vpc-id", "Values": [self.disco_vpc.get_vpc_id()]}
        # delete gateways
        for igw in self.boto3_ec2.describe_internet_gateways(
                Filters=[vpc_attachment_filter])['InternetGateways']:
            self.boto3_ec2.detach_internet_gateway(
                InternetGatewayId=igw['InternetGatewayId'],
                VpcId=self.disco_vpc.get_vpc_id())
            self.boto3_ec2.delete_internet_gateway(InternetGatewayId=igw['InternetGatewayId'])

    def set_up_nat_gateways(self):
        """ Set up NAT gateways and the routes to them for the VPC """
        for network in self.disco_vpc.networks.values():
            self._update_nat_gateways(network)

        # Setup NAT gateway routes
        nat_gateway_routes = self._parse_nat_gateway_routes_config()
        if nat_gateway_routes:
            logging.debug("Adding NAT gateway routes")
            self._add_nat_gateway_routes(nat_gateway_routes)
        else:
            logging.debug("No NAT gateway routes to add")

    def update_nat_gateways_and_routes(self, dry_run=False):
        """ Update the NAT gateways and the routes to them for the VPC based on
        the config file """

        desired_nat_routes = set(self._parse_nat_gateway_routes_config())

        current_nat_routes = []
        for network in self.disco_vpc.networks.values():
            nat_gateway_metanetwork = network.get_nat_gateway_metanetwork()
            if nat_gateway_metanetwork:
                current_nat_routes.append((network.name, nat_gateway_metanetwork))
        current_nat_routes = set(current_nat_routes)

        # Updating NAT gateways has to be done AFTER current NAT routes are calculated
        # because we don't want to delete existing NAT gateways before that.
        for network in self.disco_vpc.networks.values():
            self._update_nat_gateways(network)

        routes_to_delete = list(current_nat_routes - desired_nat_routes)
        logging.info("NAT gateway routes to delete (source, dest): {0}".format(routes_to_delete))

        routes_to_add = list(desired_nat_routes - current_nat_routes)
        logging.info("NAT gateway routes to add (source, dest): {0}".format(routes_to_add))

        if not dry_run:
            self._delete_nat_gateway_routes([route[0] for route in routes_to_delete])
            self._add_nat_gateway_routes(routes_to_add)

    def _update_nat_gateways(self, network, dry_run=False):
        eips = self.disco_vpc.get_config("{0}_nat_gateways".format(network.name))
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

    def _add_nat_gateway_routes(self, nat_gateway_routes):
        for route in nat_gateway_routes:
            self.disco_vpc.networks[route[0]].add_nat_gateway_route(self.disco_vpc.networks[route[1]])

    def _delete_nat_gateway_routes(self, meta_networks):
        for route in meta_networks:
            self.disco_vpc.networks[route].delete_nat_gateway_route()

    def _parse_nat_gateway_routes_config(self):
        """ Returns a list of tuples whose first value is the source meta network and
        whose second value is the destination meta network """
        result = []
        nat_gateway_routes = self.disco_vpc.get_config("nat_gateway_routes")
        if nat_gateway_routes:
            nat_gateway_routes = nat_gateway_routes.split(" ")
            for nat_gateway_route in nat_gateway_routes:
                network_pair = nat_gateway_route.split("/")
                result.append((network_pair[0].strip(), network_pair[1].strip()))

        return result

    def _destroy_nat_gateways(self):
        """ Find all NAT gateways belonging to a vpc and destroy them"""
        filter_params = {'Filters': [{'Name': 'vpc-id', 'Values': [self.disco_vpc.vpc['VpcId']]}]}

        nat_gateways = self.boto3_ec2.describe_nat_gateways(**filter_params)['NatGateways']
        for nat_gateway in nat_gateways:
            self.boto3_ec2.delete_nat_gateway(NatGatewayId=nat_gateway['NatGatewayId'])

        # Need to wait for all the NAT gateways to be deleted
        wait_for_state_boto3(self.boto3_ec2.describe_nat_gateways, filter_params,
                             'NatGateways', 'deleted', 'State')
