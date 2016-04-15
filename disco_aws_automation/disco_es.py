"""
Manage AWS ElasticSearch
"""
import logging
import time
import boto3

from .disco_route53 import DiscoRoute53
from .resource_helper import throttled_call


class DiscoES(object):
    """
    A simple class to manage ElasticSearch
    """

    def __init__(self, config):
        self.conn = boto3.client('es')
        self.config = config
        self.route53 = DiscoRoute53()

    @property
    def _cluster_name(self):
        return "{0}-log-es".format(self.config['environment_name'])

    def list(self):
        """List all elasticsearch domains in an account"""
        response = throttled_call(self.conn.list_domain_names)

        return sorted([domain['DomainName'] for domain in
                       response['DomainNames']])

    def _add_route53(self):
        while not self.get_endpoint(self._cluster_name):
            time.sleep(60)

        zone = self.config['domain_name']
        name = '{}.{}'.format(self._cluster_name, zone)
        value = self.get_endpoint(self._cluster_name)

        return self.route53.create_record(zone, name, 'CNAME', value)

    def _remove_route53(self):
        zone = self.config['domain_name']
        name = '{}.{}'.format(self._cluster_name, zone)

        return self.route53.delete_record(zone, name, 'CNAME')

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

        return policy.format(region=self.config['region'], account_id=self.config['account_id'],
                             cluster_name=self._cluster_name, proxy_ip=self.config['proxy_ip'])

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
            'InstanceType': self.config['instance_type'],
            'InstanceCount': self.config('instance_count'),
            'DedicatedMasterEnabled': self.config('dedicated_master'),
            'ZoneAwarenessEnabled': self.config('zone_awareness')
        }

        if es_cluster_config['DedicatedMasterEnabled']:
            es_cluster_config['DedicatedMasterType'] = self.config('dedicated_master_type')
            es_cluster_config['DedicatedMasterCount'] = self.config('dedicated_master_count')

        ebs_options = {
            'EBSEnabled': self.config('ebs_enabled')
        }

        if ebs_options['EBSEnabled']:
            ebs_options['VolumeType'] = self.config('volume_type')
            ebs_options['VolumeSize'] = self.config('volume_size')

            if ebs_options['VolumeType'] == 'io1':
                ebs_options['Iops'] = self.config('iops')

        snapshot_options = {
            'AutomatedSnapshotStartHour': self.config('snapshot_start_hour', 5)
        }

        es_kwargs = {
            'DomainName': self._cluster_name,
            'ElasticsearchClusterConfig': es_cluster_config,
            'EBSOptions': ebs_options,
            'AccessPolicies': self._access_policy(),
            'SnapshotOptions': snapshot_options
        }

        throttled_call(generator, **es_kwargs)
