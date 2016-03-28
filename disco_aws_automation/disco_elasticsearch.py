"""
Manage AWS ElasticSearch
"""
import getpass
import logging
import hashlib
from ConfigParser import ConfigParser

import boto3
import botocore
from semantic_version import Spec, Version

from . import normalize_path
from .disco_route53 import DiscoRoute53
from .exceptions import CommandError
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

        return sorted([ domain['DomainName'] for domain in
            response['DomainNames'] ])

    def update(self, cluster_name):
        """
        Create a new cluster or modify an existing one based on the config file

        Modifying tags, number of nodes, instance type, engine type, and port is not supported
        Args:
            cluster_name (str): name of cluster
        """
        meta_network = self._get_option(cluster_name, 'meta_network') or self.aws.get_default_meta_network()
        if not self._get_subnet_group(meta_network):
            self._create_subnet_group(meta_network)

        engine_version = self._get_option(cluster_name, 'engine_version')
        instance_type = self._get_option(cluster_name, 'instance_type')
        parameter_group = self._get_option(cluster_name, 'parameter_group')
        num_nodes = int(self._get_option(cluster_name, 'num_nodes'))
        port = int(self._get_option(cluster_name, 'port'))
        auto_failover = self._has_auto_failover(engine_version, instance_type, num_nodes)
        domain_name = self._get_option(cluster_name, 'domain_name') or self.aws.get_default_domain_name()
        tags = [{
            'Key': 'product_line',
            'Value': self._get_option(cluster_name, 'product_line') or self.aws.get_default_product_line('')
        }, {
            'Key': 'owner',
            'Value': getpass.getuser()
        }, {
            'Key': 'name',
            'Value': cluster_name
        }, {
            'Key': 'environment',
            'Value': self.vpc.environment_name
        }]

        cache_cluster = self._get_redis_cluster(cluster_name)
        if not cache_cluster:
            self._create_redis_cluster(cluster_name, engine_version, num_nodes, instance_type,
                                       parameter_group, port, meta_network, auto_failover, domain_name, tags)
        else:
            if cache_cluster['Status'] == 'available':
                self._modify_redis_cluster(cluster_name, engine_version,
                                           parameter_group, auto_failover, domain_name)
            else:
                logging.error('Unable to update cache cluster %s. Its status is not available',
                              cache_cluster['Description'])

    def delete(self, domain_name):
        """
        Delete an elasticsearch domain
        Args:
            domain_name (str): name of elasticsearch domain
        """
        domains = self.list()

        if domain_name not in domains:
            logging.info('Elasticsearch domain {} does not exist. Nothing to '
                        'delete.'.format(domain_name))
            return

        logging.info('Deleting elasticsearch domain {}'.format(domain_name))
        throttled_call(self.conn.delete_elasticsearch_domain,
                DomainName=domain_name)

    def _describe_elasticsearch_domain(self,domain_name):
        """
        Returns domain configuration information about the specified
        Elasticsearch domain, including the domain ID, domain endpoint, and
        domain ARN.
        """
        return self.conn.describe_elasticsearch_domain(DomainName=domain_name)


    def delete_all_cache_clusters(self, wait=False):
        """
        Delete all cache clusters in environment
        Args:
            wait (bool): block until all cache clusters are deleted
        """
        clusters = self.list()
        for cluster in clusters:
            logging.info('Deleting cache cluster %s', cluster['Description'])
            throttled_call(self.conn.delete_replication_group,
                           ReplicationGroupId=cluster['ReplicationGroupId'])

            address = cluster['NodeGroups'][0]['PrimaryEndpoint']['Address']
            self.route53.delete_records_by_value('CNAME', address)

        if wait:
            for cluster in clusters:
                self.conn.get_waiter('replication_group_deleted').wait(
                    ReplicationGroupId=cluster['ReplicationGroupId'])

    def delete_all_subnet_groups(self):
        """Delete all subnet groups in environment"""
        response = throttled_call(self.conn.describe_cache_subnet_groups)
        subnet_groups = [group for group in response.get('CacheSubnetGroups', [])
                         if group['CacheSubnetGroupName'].startswith(self.vpc.environment_name + '-')]

        for group in subnet_groups:
            logging.info('Deleting cache subnet group %s', group['CacheSubnetGroupName'])
            throttled_call(self.conn.delete_cache_subnet_group,
                           CacheSubnetGroupName=group['CacheSubnetGroupName'])

    def _get_redis_cluster(self, cluster_name):
        """Returns a Redis Replication group by its name"""
        replication_group_id = self._get_redis_replication_group_id(cluster_name)
        try:
            response = throttled_call(self.conn.describe_replication_groups,
                                      ReplicationGroupId=replication_group_id)
            groups = response.get('ReplicationGroups', [])
            return groups[0] if groups else None
        except Exception:
            return None

    # too many arguments and local variables for pylint
    # pylint: disable=R0913, R0914
    def _create_redis_cluster(self, cluster_name, engine_version, num_nodes, instance_type,
                              parameter_group,
                              port, meta_network_name, auto_failover, domain_name, tags):
        """
        Create a redis cache cluster

        Redis clusters are actually 'Replication Groups' in ElastiCache.
        Each Replication Group is a set of single node Redis Cache Clusters with one read/write cluster and
        the rest as read only.

        Waits until cluster is created

        Args:
            cluster_name (str): name of cluster
            engine_version (str): redis version to use
            num_nodes (int): number of nodes in replication group. must be at least 2 if auto_failover is on
            instance_type (str): instance types. only allowed to use instance types that start with 'cache.'
            parameter_group (str): name of parameter group to use
            port (int): port to make cache available on
            meta_network_name (str): meta network to use (intranet, tunnel, etc)
            auto_failover (bool): enable automatic promotion of read only cluster when primary fails.
                                  only supported for redis versions>2.8.6.
                                  not allowed for T1 and T2 instance types.
            domain_name (str): hosted zone id to use for Route53 domain name
            tags (List[dict]): list of tags to add to replication group
        """
        replication_group_id = self._get_redis_replication_group_id(cluster_name)
        description = self._get_redis_description(cluster_name)
        meta_network = self.vpc.networks[meta_network_name]
        subnet_group = self._get_subnet_group_name(meta_network_name)

        logging.info('Creating "%s" Redis cache', description)
        throttled_call(self.conn.create_replication_group,
                       ReplicationGroupId=replication_group_id,
                       ReplicationGroupDescription=description,
                       NumCacheClusters=num_nodes,
                       CacheNodeType=instance_type,
                       Engine='redis',
                       EngineVersion=engine_version,
                       CacheParameterGroupName=parameter_group,
                       CacheSubnetGroupName=subnet_group,
                       SecurityGroupIds=[meta_network.security_group.id],
                       Port=port,
                       AutomaticFailoverEnabled=auto_failover,
                       Tags=tags)

        self.conn.get_waiter('replication_group_available').wait(
            ReplicationGroupId=replication_group_id
        )

        cluster = self._get_redis_cluster(cluster_name)

        if domain_name:
            address = cluster['NodeGroups'][0]['PrimaryEndpoint']['Address']
            subdomain = self._get_subdomain(cluster_name, domain_name)
            self.route53.create_record(domain_name, subdomain, 'CNAME', address)

    def _modify_redis_cluster(self, cluster_name, engine_version, parameter_group,
                              auto_failover, domain_name, apply_immediately=True):
        """
        Modify an existing Redis replication group
        Args:
            cluster_name (str): name of cluster
            engine_version (str): redis version to use
            parameter_group (str): name of parameter group to use
            auto_failover (bool): True to enable automatic promotion of read only cluster after primary fails
            domain_name (str): Hosted zone where to create subdomain for cluster
            apply_immediately (bool): True to immediately update the cluster
                                      False to schedule update at next cluster maintenance window or restart
        """
        replication_group_id = self._get_redis_replication_group_id(cluster_name)
        cluster = self._get_redis_cluster(cluster_name)

        throttled_call(self.conn.modify_replication_group,
                       ReplicationGroupId=replication_group_id,
                       AutomaticFailoverEnabled=auto_failover,
                       CacheParameterGroupName=parameter_group,
                       ApplyImmediately=apply_immediately,
                       EngineVersion=engine_version)

        if domain_name:
            address = cluster['NodeGroups'][0]['PrimaryEndpoint']['Address']
            self.route53.delete_records_by_value('CNAME', address)
            subdomain = self._get_subdomain(cluster_name, domain_name)
            self.route53.create_record(domain_name, subdomain, 'CNAME', address)

    def _create_subnet_group(self, meta_network_name):
        subnet_group_name = self._get_subnet_group_name(meta_network_name)
        meta_network = self.vpc.networks[meta_network_name]

        logging.info('Creating cache subnet group %s', subnet_group_name)
        throttled_call(self.conn.create_cache_subnet_group,
                       CacheSubnetGroupName=subnet_group_name,
                       CacheSubnetGroupDescription=subnet_group_name,
                       SubnetIds=[subnet.id for subnet in meta_network.subnets])

    def _get_subnet_group(self, meta_network_name):
        try:
            response = throttled_call(self.conn.describe_cache_subnet_groups,
                                      CacheSubnetGroupName=self._get_subnet_group_name(meta_network_name))
            groups = response.get('CacheSubnetGroups', [])
            return groups[0] if groups else None
        except botocore.exceptions.ClientError:
            return None

    def _get_redis_replication_group_id(self, cluster_name):
        """Get a unique id for a redis cluster. This will not be human readable"""

        # Redis Replication Groups Ids are limited to 16 characters so hash the group name to get a shorter id
        # Ids must also start with a letter
        return 'A' + hashlib.md5(self.vpc.environment_name + '-' + cluster_name).hexdigest()[:15]

    def _get_redis_description(self, cluster_name):
        """Get a human readable name for a redis cluster"""
        return self.vpc.environment_name + '-' + cluster_name

    def _get_subnet_group_name(self, meta_network_name):
        return self.vpc.environment_name + '-' + meta_network_name

    def _get_subdomain(self, cluster, domain_name):
        """Get the expected subdomain for a cache cluster"""
        return cluster + '-' + self.vpc.environment_name + '.' + domain_name

    def _get_option(self, cluster_name, option_name):
        """Get a config option for a cluster"""
        if not self.config:
            raise CommandError('ElastiCache config file missing')

        section_name = self.vpc.environment_name + ':' + cluster_name

        if not self.config.has_section(section_name):
            raise CommandError('%s section missing in ElastiCache config' % section_name)

        if self.config.has_option(section_name, option_name):
            return self.config.get(section_name, option_name)

        return None

    def _has_auto_failover(self, engine_version, instance_type, num_nodes):
        """auto failover is only supported for Redis versions >= 2.8.6 and not for t1, t2 instance types"""
        return ('t1.' not in instance_type and
                't2.' not in instance_type and
                Spec('>=2.8.6').match(Version(engine_version)) and
                num_nodes > 1)
