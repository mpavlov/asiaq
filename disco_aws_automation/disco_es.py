"""
Manage AWS ElasticSearch
"""
import logging
from ConfigParser import ConfigParser

import time
import boto3
# import botocore

from .disco_iam import DiscoIAM
from .disco_route53 import DiscoRoute53

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
        self.route53 = DiscoRoute53()

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
        return "{0}-log-es".format(self.aws.environment_name.lower())

    def list(self):
        """List all elasticsearch domains in an account"""
        response = throttled_call(self.conn.list_domain_names)

        return sorted([domain['DomainName'] for domain in
                       response['DomainNames']])

    @property
    def _get_zone(self):
        if self.aws.environment_name == 'staging':
            return 'staging.wgen.net'
        elif self.aws.environment_name == 'production':
            return 'production.wgen.net'
        else:
            return 'aws.wgen.net'

    def _add_route53(self):
        while not self.get_endpoint(self._cluster_name):
            time.sleep(60)

        zone = self._get_zone
        value = self.get_endpoint(self._cluster_name)
        name = '{}.{}'.format(self._cluster_name, zone)

        return self.route53.create_record(zone, name, 'CNAME', value)

    def _remove_route53(self):
        value = self.get_endpoint(self._cluster_name)

        return self.route53.delete_records_by_value('CNAME', value)

    def delete(self):
        """
        Delete an elasticsearch domain
        """
        domains = self.list()

        if self._cluster_name not in domains:
            logging.info('Elasticsearch domain %s does not exist. Nothing to delete.', self._cluster_name)
            return

        logging.info('Deleting elasticsearch domain %s', self._cluster_name)
        self._remove_route53()
        throttled_call(self.conn.delete_elasticsearch_domain,
                       DomainName=self._cluster_name)

    def _describe_es_domain(self, cluster_name):
        """
        Returns domain configuration information about the specified
        Elasticsearch domain, including the domain ID, domain endpoint, and
        domain ARN.
        """
        return self.conn.describe_elasticsearch_domain(DomainName=cluster_name)

    def get_endpoint(self, cluster_name):
        '''
        Get elasticsearch service endpoint
        '''
        try:
            return self._describe_es_domain(cluster_name)['DomainStatus']['Endpoint']
        except:
            return False

    def _access_policy(self):
        disco_iam = DiscoIAM(
            environment=self.aws.environment_name,
            boto2_connection=self.aws.connection
        )
        proxy_hostclass = self.aws.config('http_proxy_hostclass', 'disco_aws')
        proxy_ip = self.aws.config('eip', proxy_hostclass)

        policy = '''
                {{
                  "Version": "2012-10-17",
                  "Statement": [
                    {{
                      "Effect": "Allow",
                      "Principal": {{
                        "AWS": "*"
                      }},
                      "Action": "es:*",
                      "Resource": "arn:aws:es:{region}:{account_id}:domain/{cluster_name}/*",
                      "Condition": {{
                        "IpAddress": {{
                          "aws:SourceIp": [
                            "66.104.227.162",
                            "38.117.159.162",
                            "{proxy_ip}"
                          ]
                        }}
                      }}
                    }}
                  ]
                }}
                '''

        return policy.format(region=self.aws.vpc.region, account_id=disco_iam.account_id(),
                             cluster_name=self._cluster_name, proxy_ip=proxy_ip)

    def create(self):
        '''
        Create elasticsearch cluster using _upsert method
        Configuration is read from disco_vpc.ini
        '''
        self._upsert(self.conn.create_elasticsearch_domain)
        self._add_route53()

    def update(self):
        '''
        Update elasticsearch cluster using _upsert method
        Configuration is read from disco_vpc.ini
        '''
        self._upsert(self.conn.update_elasticsearch_domain_config)
        self._add_route53()

    def _upsert(self, generator):
        es_cluster_config = {
            'InstanceType': self.aws.vpc.get_config('es_instance_type', 'm3.medium.elasticsearch'),
            'InstanceCount': int(self.aws.vpc.get_config('es_instance_count', 1)),
            'DedicatedMasterEnabled': bool(self.aws.vpc.get_config('es_dedicated_master', False)),
            'ZoneAwarenessEnabled': bool(self.aws.vpc.get_config('es_zone_awareness', False))
        }

        if is_truthy(es_cluster_config['DedicatedMasterEnabled']):
            es_cluster_config['DedicatedMasterType'] = self.aws.vpc.get_config('es_dedicated_master_type')
            es_cluster_config['DedicatedMasterCount'] = int(
                self.aws.vpc.get_config('es_dedicated_master_count')
            )

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
