"""
Manage AWS ElasticSearch
"""
# import getpass
import logging
# import hashlib
from ConfigParser import ConfigParser

import boto3
# import botocore
# from semantic_version import Spec, Version

from . import normalize_path
# from .disco_route53 import DiscoRoute53
# from .exceptions import CommandError
from .resource_helper import throttled_call


class DiscoES(object):
    """
    A simple class to manage ElasticSearch
    """

    def __init__(self, config_file='disco_elasticsearch.ini', aws=None):
        self.conn = boto3.client('es')
        self.config_file = config_file
        self._config = None  # lazily initialized
        self.aws = aws

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

    def list(self):
        """List all elasticsearch domains in an account"""
        response = throttled_call(self.conn.list_domain_names)

        return sorted([domain['DomainName'] for domain in
                       response['DomainNames']])

   #def create(self, domain_name):
   #    """
   #    Create a new elasticsearch domain based on the config file
   #    """

   #    logging.info('Creating elasticsearch domain %s...', domain_name)
   #    throttled_call(self.conn.create_elasticsearch_domain, DomainName=domain_name)
   #    logging.info('Creating elasticsearch domain %s will take approx. 10 minutes', domain_name)

   #    return None

    def delete(self, domain_name):
        """
        Delete an elasticsearch domain
        Args:
            domain_name (str): name of elasticsearch domain
        """
        domains = self.list()

        if domain_name not in domains:
            logging.info('Elasticsearch domain %s does not exist. Nothing to delete.', domain_name)
            return

        logging.info('Deleting elasticsearch domain %s', domain_name)
        throttled_call(self.conn.delete_elasticsearch_domain,
                       DomainName=domain_name)

    def _describe_es_domain(self, domain_name):
        """
        Returns domain configuration information about the specified
        Elasticsearch domain, including the domain ID, domain endpoint, and
        domain ARN.
        """
        return self.conn.describe_elasticsearch_domain(DomainName=domain_name)

    # pylint: disable=too-many-arguments
    #def _create_es_domain(self, domain_name, instance_type, instance_count,
    def create(self, domain_name, instance_type, instance_count,
                          dedicated_master, zone_awareness, dedicated_master_type,
                          dedicated_master_count, ebs_enabled, volume_type,
                          volume_size, iops, access_policies, snapshot_start_hour):
        """
        Create an elasticsearch domain

        Args:
            domain_name (str): name of elasticsearch domain
            instance_type (str): instance types, use instance types that end with '.elasticsearch'
            instance_count (int): number of instances in the specified domain cluster
            dedicated_master (boolean): indicate whether a dedicated master node is enabled
            zone_awareness (boolean): indicate whether zone awareness is enabled
            dedicated_master_type (string): instance type for a dedicated master node
            dedicated_master_count (int): total number of dedicated master nodes for the cluster
            ebs_enabled (boolean): whether EBS-based storage is enabled
            volume_type (string): volume type for EBS-based storage
            volume_size (int): specify the size of an EBS volume
            iops (int): specify IOPD for a Provisioned IOPS EBS volume (SSD)
            access_policies (string): IAM access policy as a JSON-formatted string
            snapshot_start_hour (int): time, in UTC format, when the service takes a daily automated snapshot
        """

        throttled_call(self.conn.create_elasticsearch_domain,
                       DomainName=domain_name,
                       InstanceType=instance_type,
                       InstanceCount=instance_count,
                       DedicatedMasterEnabled=dedicated_master,
                       ZoneAwarenessEnabled=zone_awareness,
                       DedicatedMasterType=dedicated_master_type,
                       DedicatedMasterCount=dedicated_master_count,
                       EBSEnabled=ebs_enabled,
                       VolumeType=volume_type,
                       VolumeSize=volume_size,
                       Iops=iops,
                       AccessPolicies=access_policies,
                       AutomatedSnapshotStartHour=snapshot_start_hour)

        return None

    #  pylint: disable=too-many-arguments
    def _update_es_domain(self, domain_name, instance_type, instance_count,
                          dedicated_master, zone_awareness, dedicated_master_type,
                          dedicated_master_count, ebs_enabled, volume_type,
                          volume_size, iops, snapshot_start_hour,
                          access_policies):
        """
        Modifies the cluster configuration of the specified Elasticsearch domain,
        setting as setting the instance type and the number of instances.

        Args:
            domain_name (str): name of elasticsearch domain
            instance_type (str): instance types, use instance types that end with '.elasticsearch'
            instance_count (int): number of instances in the specified domain cluster
            dedicated_master (boolean): indicate whether a dedicated master node is enabled
            zone_awareness (boolean): indicate whether zone awareness is enabled
            dedicated_master_type (string): instance type for a dedicated master node
            dedicated_master_count (int): total number of dedicated master nodes for the cluster
            ebs_enabled (boolean): whether EBS-based storage is enabled
            volume_type (string): volume type for EBS-based storage
            volume_size (int): specify the size of an EBS volume
            iops (int): specify IOPD for a Provisioned IOPS EBS volume (SSD)
            snapshot_start_hour (int): time, in UTC format, when the service takes a daily automated snapshot
            access_policies (string): IAM access policy as a JSON-formatted string
        """

        throttled_call(self.conn.create_elasticsearch_domain,
                       DomainName=domain_name,
                       InstanceType=instance_type,
                       InstanceCount=instance_count,
                       DedicatedMasterEnabled=dedicated_master,
                       ZoneAwarenessEnabled=zone_awareness,
                       DedicatedMasterType=dedicated_master_type,
                       DedicatedMasterCount=dedicated_master_count,
                       EBSEnabled=ebs_enabled,
                       VolumeType=volume_type,
                       VolumeSize=volume_size,
                       Iops=iops,
                       AccessPolicies=access_policies,
                       AutomatedSnapshotStartHour=snapshot_start_hour)

        return None
