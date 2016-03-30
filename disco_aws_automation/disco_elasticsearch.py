"""
Manage AWS ElasticSearch
"""
import logging
from ConfigParser import ConfigParser

import boto3
# import botocore

from . import normalize_path
# from .exceptions import CommandError
from .resource_helper import throttled_call


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

    def _describe_es_domain(self):
        """
        Returns domain configuration information about the specified
        Elasticsearch domain, including the domain ID, domain endpoint, and
        domain ARN.
        """
        return self.conn.describe_elasticsearch_domain(DomainName=self._cluster_name)

    @property
    def _cluster_name(self):
	return "{0}-log-es".format(aws.environment_name)

    def _access_policy(self):
	disco_iam = DiscoIAM(
		environment=self.aws.environment_name,
		boto2_connection=self.aws.connection
	)
	return '''
	    {
	      "Version": "2012-10-17",
	      "Statement": [
		{
		  "Effect": "Allow",
		  "Principal": {
		    "AWS": [
		      "{1}"
		    ]
		  },
		  "Action": [
		    "es:*"
		  ],
		  "Resource": "arn:aws:es:{0}:{1}:domain/{2}/*"
		}
	      ]
	    }
	'''.format(
                self.aws.vpc.region,
                disco_iam.account_id(),
                self._cluster_name,
	)

    def create(self):
        return self._upsert(self.conn.create_elasticsearch_domain)

    def update(self):
        return self._upsert(self.conn.update_elasticsearch_domain_config)

    def _upsert(self, generator):
        throttled_call(
           generator,
           DomainName=self._cluster_name,
           InstanceType=self.aws.vpc.get_config('es_instance_type', 't2.medium.elasticsearch'),
           InstanceCount=self.aws.vpc.get_config('es_instance_count', 2),
           DedicatedMasterEnabled=self.aws.vpc.get_config('dedicated_master', False),
           ZoneAwarenessEnabled=self.aws.vpc.get_config('zone_awareness', False),
           DedicatedMasterType=self.aws.vpc.get_config('dedicated_master_type', None),
           DedicatedMasterCount=self.aws.vpc.get_config('dedicated_master_count', None),
           EBSEnabled=self.aws.vpc.get_config('ebs_enabled', False),
           VolumeType=self.aws.vpc.get_config('volume_type', 'standard'),
           VolumeSize=self.aws.vpc.get_config('volume_size', 10),
           Iops=self.aws.vpc.get_config('iops', None),
           AccessPolicies=self._access_policy(),
           AutomatedSnapshotStartHour=self.aws.vpc.get_config('snapshot_start_hour', 5)
        )
