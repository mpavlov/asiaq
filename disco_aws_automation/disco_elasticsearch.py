"""
Manage AWS ElasticSearch
"""
import logging
import time
import json
from ConfigParser import NoOptionError

import boto3

from boto3.exceptions import Boto3Error
from botocore.exceptions import BotoCoreError
from . import read_config
from .disco_route53 import DiscoRoute53
from .resource_helper import throttled_call
from .disco_aws_util import is_truthy
from .disco_constants import DEFAULT_CONFIG_SECTION

CONFIG_FILE = "disco_elasticsearch.ini"


class DiscoElasticsearch(object):
    """
    A simple class to manage ElasticSearch
    """

    def __init__(self, environment_name, config_aws=None, config_es=None,
                 route53=None):
        self.config_aws = config_aws or read_config()
        self.config_es = config_es or read_config(CONFIG_FILE)
        self.route53 = route53 or DiscoRoute53()

        if environment_name:
            self.environment_name = environment_name.lower()
        else:
            self.environment_name = self.config_aws.get("disco_aws", "default_environment")

        self._conn = None  # Lazily initialized
        self._session = None  # Lazily initialized
        self._account_id = None  # Lazily initialized
        self._region = None  # Lazily initialized
        self._zone = None  # Lazily initialized

    @property
    def conn(self):
        """The boto3 elasticsearch connection object"""
        if not self._conn:
            self._conn = boto3.client('es')
        return self._conn

    @property
    def session(self):
        """Boto3 session"""
        if not self._session:
            self._session = boto3.session.Session()
        return self._session

    @property
    def account_id(self):
        """Account id of the current IAM user"""
        if not self._account_id:
            self._account_id = boto3.resource('iam').CurrentUser().arn.split(':')[4]
        return self._account_id

    @property
    def region(self):
        """Current region used by Boto"""
        if not self._region:
            # Doing this requires boto3>=1.2.4
            # Could use undocumented and unsupported workaround for earlier versions:
            # session._session.get_config_variable('region')
            self._region = self.session.region_name
        return self._region

    @property
    def zone(self):
        """The current Route 53 zone"""
        if not self._zone:
            self._zone = self.get_aws_option('domain_name')
        return self._zone

    def get_domain_name(self, elasticsearch_name):
        """
        Get the name of the ElasticSearch domain.
        Follows the format 'es-{elasticsearch_name}-{environment_name}'
        """
        return "es-{}-{}".format(elasticsearch_name, self.environment_name)

    def _list(self):
        """
        List all active ElasticSearch domains
        """
        response = throttled_call(self.conn.list_domain_names)
        return sorted([domain['DomainName'] for domain in response['DomainNames']])

    def list(self, include_endpoint=False):
        """
        Lists information about all active ElasticSearch domains, filtered by the current environment

        Returns a list of dictionaries, typically like this:

        [
            {
                "elasticsearch_domain_name": "es-logging-ci",
                "route_53_endpoint": "es-logging-ci.aws.wgen.net",
                "internal_name": "logging",
            }
        ]

        If endpoint is included, then the response will include the endpoint of the domain, provided it
        exists.

        [
            {
                "elasticsearch_domain_name": "es-logging-ci",
                "route_53_endpoint": "es-logging-ci.aws.wgen.net",
                "internal_name": "logging",
                "elasticsearch_endpoint": "search-es-logging-ci-xxxxxxxxxxxxxxxx.us-west-2.es.amazonaws.com",
            }
        ]
        """
        domain_infos = []
        for domain_name in self._list():
            try:
                # Somewhat annoying logic to handle the fact that elasticsearch names are allowed to have '-'
                # in them.
                domain_name_components = domain_name.split("-")
                prefix = domain_name_components[0]
                environment_name = domain_name_components[-1]
                elasticsearch_name = "-".join(domain_name_components[1:-1])
            except (ValueError, KeyError):
                logging.info("Could not parse ElasticSearch domain %s, expected format 'es-$name-$env'")
                continue
            if prefix != "es":
                logging.info("Could not parse ElasticSearch domain %s, expected format 'es-$name-$env'")
            if environment_name != self.environment_name:
                logging.debug("ElasticSearch domain %s is associated with a different environment, ignoring")
                continue

            domain_info = {}

            domain_info["elasticsearch_domain_name"] = domain_name
            domain_info["route_53_endpoint"] = "{}.{}".format(domain_name, self.zone)
            domain_info["internal_name"] = elasticsearch_name

            if include_endpoint:
                domain_info["elasticsearch_endpoint"] = self.get_endpoint(domain_name)

            domain_infos.append(domain_info)

        return domain_infos

    def _add_route53(self, domain_name):
        """Add a Route 53 record for the given domain name"""
        # Wait until AWS attaches an endpoint to the ElasticSearch domain
        while not self.get_endpoint(domain_name):
            logging.info('Waiting for ElasticSearch domain %s to finish being created', domain_name)
            time.sleep(60)

        name = '{}.{}'.format(domain_name, self.zone)
        value = self.get_endpoint(domain_name)

        return self.route53.create_record(self.zone, name, 'CNAME', value)

    def _remove_route53(self, domain_name):
        """Remove all Route 53 records for the given domain name"""
        value = self.get_endpoint(domain_name)

        return self.route53.delete_records_by_value('CNAME', value)

    def _describe_es_domain(self, domain_name):
        """
        Returns domain configuration information about the specified
        Elasticsearch domain, including the domain ID, domain endpoint, and
        domain ARN.
        """
        return self.conn.describe_elasticsearch_domain(DomainName=domain_name)

    def get_endpoint(self, domain_name):
        """
        Get Elasticsearch service endpoint
        """
        try:
            return self._describe_es_domain(domain_name)['DomainStatus']['Endpoint']
        except (BotoCoreError, Boto3Error, KeyError):
            return None

    def _access_policy(self, domain_name):
        """
        Construct an access policy for the new Elasticsearch cluster. Needs to be dynamically created because
        it will use the environment's proxy hostclass to forward requests to the elasticsearch cluster and the
        IP of the proxy hostclass could be different at run time.
        """
        proxy_hostclass = self.get_aws_option('http_proxy_hostclass')
        proxy_ip = self.get_hostclass_option('eip', proxy_hostclass)

        resource = "arn:aws:es:{region}:{account}:domain/{domain_name}/*".format(region=self.region,
                                                                                 account=self.account_id,
                                                                                 domain_name=domain_name)

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "AWS": "*"
                    },
                    "Action": "es:*",
                    "Resource": resource,
                    "Condition": {
                        "IpAddress": {
                            "aws:SourceIp": [
                                "66.104.227.162",
                                "38.117.159.162",
                                proxy_ip
                            ]
                        }
                    }
                }
            ]
        }
        return json.dumps(policy)

    def create(self, elasticsearch_name=None, es_config=None):
        """
        Create an ElasticSearch domain.
        """
        if elasticsearch_name:
            desired_elasticsearch_names = [elasticsearch_name]
        else:
            desired_elasticsearch_names = self._get_elasticsearch_names()

        all_elasticsearch_names = [domain_info["internal_name"] for domain_info in self.list()]

        for elasticsearch_name in desired_elasticsearch_names:
            domain_name = self.get_domain_name(elasticsearch_name)
            if elasticsearch_name in all_elasticsearch_names:
                logging.info('ElasticSearch domain %s already exists. Try updating it instead.', domain_name)
                continue

            logging.info('Creating ElasticSearch domain %s', domain_name)
            # Get the latest elasticsearch cluster config.
            desired_es_config = es_config or self._get_es_config(elasticsearch_name)
            # Create a new elasticsearch config using the latest config.
            throttled_call(self.conn.create_elasticsearch_domain, **desired_es_config)
            self._add_route53(domain_name)

    def update(self, elasticsearch_name=None, es_config=None):
        """
        Update an ElasticSearch domain.
        """
        if elasticsearch_name:
            desired_elasticsearch_names = [elasticsearch_name]
        else:
            desired_elasticsearch_names = self._get_elasticsearch_names()

        all_elasticsearch_names = [domain_info["internal_name"] for domain_info in self.list()]

        for elasticsearch_name in desired_elasticsearch_names:
            domain_name = self.get_domain_name(elasticsearch_name)
            if elasticsearch_name not in all_elasticsearch_names:
                logging.info('ElasticSearch domain %s does not exist. Try creating it instead.', domain_name)
                continue
            logging.info('Updating ElasticSearch domain %s', domain_name)
            # Get the latest elasticsearch cluster config.
            desired_es_config = es_config or self._get_es_config(elasticsearch_name)
            # Update the elasticsearch cluster config to be the latest one.
            throttled_call(self.conn.update_elasticsearch_domain_config, **desired_es_config)
            self._add_route53(domain_name)

    def delete(self, elasticsearch_name=None, delete_all=False):
        """
        Delete an ElasticSearch domain.
        """
        all_elasticsearch_names = [domain_info["internal_name"] for domain_info in self.list()]
        if delete_all:
            desired_elasticsearch_names = all_elasticsearch_names
        else:
            if elasticsearch_name:
                desired_elasticsearch_names = [elasticsearch_name]
            else:
                desired_elasticsearch_names = self._get_elasticsearch_names()

        for elasticsearch_name in desired_elasticsearch_names:
            domain_name = self.get_domain_name(elasticsearch_name)
            if elasticsearch_name not in all_elasticsearch_names:
                logging.info('ElasticSearch domain %s does not exist. Nothing to delete.', domain_name)
                continue

            logging.info('Deleting ElasticSearch domain %s', domain_name)
            self._remove_route53(domain_name)
            throttled_call(self.conn.delete_elasticsearch_domain, DomainName=domain_name)

    def _get_elasticsearch_names(self):
        """
        Returns a list of all ElasticSearch names defined for the current environment in the config files.
        """
        elasticsearch_names = []

        for section in self.config_es.sections():
            environment_name, elasticsearch_name = section.split(":")
            if environment_name == self.environment_name:
                elasticsearch_names.append(elasticsearch_name)

        return elasticsearch_names

    def _get_es_config(self, elasticsearch_name):
        """
        Create boto3 config for the ElasticSearch cluster.
        """
        es_cluster_config = {
            'InstanceType': self.get_es_option_default('instance_type', elasticsearch_name,
                                                       'm3.medium.elasticsearch'),
            'InstanceCount': int(self.get_es_option_default('instance_count', elasticsearch_name, 1)),
            'DedicatedMasterEnabled': is_truthy(self.get_es_option_default('dedicated_master',
                                                                           elasticsearch_name, "False")),
            'ZoneAwarenessEnabled': is_truthy(self.get_es_option_default('zone_awareness',
                                                                         elasticsearch_name, "False"))
        }

        if es_cluster_config['DedicatedMasterEnabled']:
            es_cluster_config['DedicatedMasterType'] = self.get_es_option('dedicated_master_type',
                                                                          elasticsearch_name)
            es_cluster_config['DedicatedMasterCount'] = int(
                self.get_es_option('dedicated_master_count', elasticsearch_name)
            )

        ebs_option = {
            'EBSEnabled': is_truthy(self.get_es_option_default('ebs_enabled', elasticsearch_name, "False"))
        }

        if ebs_option['EBSEnabled']:
            ebs_option['VolumeType'] = self.get_es_option_default('volume_type', elasticsearch_name,
                                                                  'standard')
            ebs_option['VolumeSize'] = int(self.get_es_option_default('volume_size', elasticsearch_name, 10))

            if ebs_option['VolumeType'] == 'io1':
                ebs_option['Iops'] = int(self.get_es_option_default('iops', elasticsearch_name, 1000))

        snapshot_options = {
            'AutomatedSnapshotStartHour': int(self.get_es_option_default('snapshot_start_hour',
                                                                         elasticsearch_name, 5))
        }

        domain_name = self.get_domain_name(elasticsearch_name)

        config = {
            'DomainName': domain_name,
            'ElasticsearchClusterConfig': es_cluster_config,
            'EBSOptions': ebs_option,
            'AccessPolicies': self._access_policy(domain_name),
            'SnapshotOptions': snapshot_options
        }

        return config

    def get_es_option(self, option, elasticsearch_name):
        """Returns appropriate configuration for the current environment"""
        section = "{}:{}".format(self.environment_name, elasticsearch_name)

        if self.config_es.has_option(section, option):
            value = self.config_es.get(section, option)
            if value:
                return value

        raise NoOptionError(option, section)

    def get_es_option_default(self, option, elasticsearch_name, default=None):
        """Returns appropriate configuration for the current environment"""
        try:
            return self.get_es_option(option, elasticsearch_name)
        except NoOptionError:
            return default

    def get_aws_option(self, option, section=DEFAULT_CONFIG_SECTION):
        """Get a value from the config"""
        env_option = "{0}@{1}".format(option, self.environment_name)
        default_option = "default_{0}".format(option)
        default_env_option = "default_{0}".format(env_option)

        if self.config_aws.has_option(section, env_option):
            value = self.config_aws.get(section, env_option)
            if value:
                return value
        if self.config_aws.has_option(section, option):
            value = self.config_aws.get(section, option)
            if value:
                return value
        elif self.config_aws.has_option(DEFAULT_CONFIG_SECTION, default_env_option):
            value = self.config_aws.get(DEFAULT_CONFIG_SECTION, default_env_option)
            if value:
                return value
        elif self.config_aws.has_option(DEFAULT_CONFIG_SECTION, default_option):
            value = self.config_aws.get(DEFAULT_CONFIG_SECTION, default_option)
            if value:
                return value

        raise NoOptionError(option, section)

    def get_aws_option_default(self, option, section=DEFAULT_CONFIG_SECTION, default=None):
        """Get a value from the config"""
        try:
            return self.get_aws_option(option, section)
        except NoOptionError:
            return default

    def get_hostclass_option(self, option, hostclass):
        """Fetch a hostclass configuration option, if it does not exist get the default"""
        return self.get_aws_option(option, hostclass)

    def get_hostclass_option_default(self, option, hostclass, default=None):
        """Fetch a hostclass configuration option, if it does not exist get the default"""
        return self.get_aws_option_default(option, hostclass, default)
