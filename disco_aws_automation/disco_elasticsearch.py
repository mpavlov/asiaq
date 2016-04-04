"""
Manage AWS ElasticSearch
"""
import logging
from ConfigParser import ConfigParser

import boto3
# import botocore

from .disco_iam import DiscoIAM

from . import normalize_path
# from .exceptions import CommandError
from .resource_helper import throttled_call
from .disco_aws_util import is_truthy

class DiscoES(object):
    """
    A simple class to manage ElasticSearch
    """

    def __init__(self, config_file, aws):
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

    @property
    def _cluster_name(self):
        return "{0}-log-es".format(self.aws.environment_name)

    def list(self):
        """List all elasticsearch domains in an account"""
        response = throttled_call(self.conn.list_domain_names)

        return sorted([domain['DomainName'] for domain in
                       response['DomainNames']])

    def delete(self):
        """
        Delete an elasticsearch domain
        """
        domains = self.list()

        if self._cluster_name not in domains:
            logging.info('Elasticsearch domain %s does not exist. Nothing to delete.', self._cluster_name)
            return

        logging.info('Deleting elasticsearch domain %s', self._cluster_name)
        throttled_call(self.conn.delete_elasticsearch_domain,
                       DomainName=self._cluster_name)

    def _describe_es_domain(self, cluster_name):
        """
        Returns domain configuration information about the specified
        Elasticsearch domain, including the domain ID, domain endpoint, and
        domain ARN.
        """
        return self.conn.describe_elasticsearch_domain(DomainName=cluster_name)

    def _access_policy(self):
        disco_iam = DiscoIAM(
                environment=self.aws.environment_name,
                boto2_connection=self.aws.connection
        )

        policy = '''
                {{
                  "Version": "2012-10-17",
                  "Statement": [
                    {{
                      "Effect": "Allow",
                      "Principal": {{
                        "AWS": [
                          "{1}"
                        ]
                      }},
                      "Action": "es:*",
                      "Resource": "arn:aws:es:{0}:{1}:domain/{2}/*"
                    }}
                  ]
                }}
                '''

        return policy.format(self.aws.vpc.region, disco_iam.account_id(), self._cluster_name)

    def create(self):
        return self._upsert(self.conn.create_elasticsearch_domain)

    def update(self):
        return self._upsert(self.conn.update_elasticsearch_domain_config)

    def _upsert(self, generator):
        es_cluster_config = {
                'InstanceType': self.aws.vpc.get_config('es_instance_type', 'm3.medium.elasticsearch'),
                'InstanceCount': int(self.aws.vpc.get_config('es_instance_count', 1)),
                'DedicatedMasterEnabled': bool(self.aws.vpc.get_config('es_dedicated_master', False)),
                'ZoneAwarenessEnabled': bool(self.aws.vpc.get_config('es_zone_awareness', False))
                }

        if is_truthy(es_cluster_config['DedicatedMasterEnabled']):
            es_cluster_config['DedicatedMasterType'] = self.aws.vpc.get_config('es_dedicated_master_type')
            es_cluster_config['DedicatedMasterCount'] = int(self.aws.vpc.get_config('es_dedicated_master_count'))

        ebs_option = {
                'EBSEnabled': bool(self.aws.vpc.get_config('es_ebs_enabled', False))
                }

        if is_truthy(ebs_option['EBSEnabled']):
            ebs_option['VolumeType'] = self.aws.vpc.get_config('es_volume_type', 'standard')
            ebs_option['VolumeSize'] = int(self.aws.vpc.get_config('es_volume_size', 10))

            if ebs_option['VolumeType'] == 'io1':
                ebs_option['Iops'] = int(self.aws.vpc.get_config('es_iops', 1000))

        snapshot_options = {
                'AutomatedSnapshotStartHour': int(self.aws.vpc.get_config('es_snapshot_start_hour', 5))
                }

        es_kwargs = {
                'DomainName': self._cluster_name,
                'ElasticsearchClusterConfig': es_cluster_config,
                'EBSOptions': ebs_option,
                'AccessPolicies': self._access_policy(),
                'SnapshotOptions': snapshot_options
            }

        throttled_call(generator, **es_kwargs)
