from ConfigParser import NoOptionError
from collections import defaultdict
from time import time, sleep
import json
import logging
import re

from boto3.session import Session
from elasticsearch import (
    Elasticsearch,
    RequestsHttpConnection,
    TransportError,
)
from requests_aws4auth import AWS4Auth
import boto3

from . import read_config, DiscoElasticsearch, DiscoIAM
from .disco_constants import (
    ES_ARCHIVE_LIFECYCLE_DIR,
    ES_CONFIG_FILE
)

ES_SNAPSHOT_FINAL_STATES = ['SUCCESS', 'FAILED']
SNAPSHOT_WAIT_TIMEOUT = 60*60
SNAPSHOT_POLL_INTERVAL = 60
ES_ARCHIVE_ROLE = "es_archive"


class DiscoESArchive(object):
    def __init__(self, environment_name, cluster_name, config_aws=None,
                 config_es=None,
                 index_prefix_pattern=None, repository_name=None, disco_es=None,
                 disco_iam=None):
        self.config_aws = config_aws or read_config()
        self.config_es = config_es or read_config(ES_CONFIG_FILE)

        if environment_name:
            self.environment_name = environment_name.lower()
        else:
            self.environment_name = self.config_aws.get("disco_aws", "default_environment")

        self.cluster_name = cluster_name
        self._host = None
        self._es_client = None
        self._region = None
        self._s3_client = None
        self._disco_es = disco_es
        self._disco_iam = disco_iam
        self.index_prefix_pattern = index_prefix_pattern or r'.*'
        self.repository_name = repository_name or 's3'

    @property
    def host(self):
        """
        Return ES cluster hostname
        """
        if not self._host:
            es_domains = self.disco_es.list()
            try:
                host = [es_domain["route_53_endpoint"]
                        for es_domain in es_domains
                        if es_domain.get("internal_name") == self.cluster_name][0]
            except IndexError:
                logging.info("Unable to find")
                raise RuntimeError("Unable to find ES cluster: {}".format(self.cluster_name))
            self._host = {'host': host, 'port': 80}
        return self._host

    @property
    def region(self):
        """
        Current region, based of boto connection.
        """
        if not self._region:
            self._region = Session().region_name
        return self._region

    @property
    def role_arn(self):
        """
        Return aws role_arn
        """
        arn = self.disco_iam.get_role_arn(ES_ARCHIVE_ROLE)
        if not arn:
            raise RuntimeError("Unable to find ARN for role: {}".format(ES_ARCHIVE_ROLE))

        return arn

    @property
    def es_client(self):
        """
        Return authenticated ElasticSeach connection object
        """
        if not self._es_client:
            session = Session()
            credentials = session.get_credentials()
            aws_auth = AWS4Auth(
                credentials.access_key,
                credentials.secret_key,
                self.region,
                'es'
            )
            self._es_client = Elasticsearch(
                [self.host],
                http_auth=aws_auth,
                use_ssl=False,
                verify_certs=False,
                connection_class=RequestsHttpConnection,
            )
        return self._es_client

    @property
    def disco_es(self):
        if not self._disco_es:
            self._disco_es = DiscoElasticsearch(self.environment_name)

        return self._disco_es

    @property
    def disco_iam(self):
        if not self._disco_iam:
            self._disco_iam = DiscoIAM(environment=self.environment_name)

        return self._disco_iam

    @property
    def s3_client(self):
        if not self._s3_client:
            self._s3_client = boto3.client("s3")

        return self._s3_client

    def _bytes_to_free(self, threshold):
        """
        Number of bytes disk space threshold is exceeded by. In other
        words, number of bytes of data that needs to be delted to drop
        below threshold.
        threshold range 0-1
        """
        cluster_stats = self.es_client.cluster.stats()
        total_bytes = cluster_stats["nodes"]["fs"]["total_in_bytes"]
        free_bytes = cluster_stats["nodes"]["fs"]['free_in_bytes']
        need_bytes = total_bytes * (1 - threshold)
        logging.debug("disk utilization : %i%%", (total_bytes-free_bytes)*101/total_bytes)
        return need_bytes - free_bytes

    def _archivable_indices(self, threshold):
        """
        Return list of indices that ough to be archived to get below
        max disk space threshold. Oldest first.
        """
        bytes_to_free = self._bytes_to_free(threshold)
        logging.debug("Need to free %i bytes.", bytes_to_free)
        if bytes_to_free <= 0:
            return []

        stats = self.es_client.indices.stats()
        dated_index_pattern = re.compile(
            self.index_prefix_pattern + r'-[\d]{4}(\.[\d]{2}){2}$'
        )
        index_sizes = [
            (index, stats['indices'][index]['total']['store']['size_in_bytes'])
            for index in sorted(stats['indices'], key=lambda k: k[-10:])
            if re.match(dated_index_pattern, index)
        ]

        archivable_indices = []
        freed_size = 0
        for index, size in index_sizes:
            if freed_size > bytes_to_free:
                break
            archivable_indices.append(index)
            freed_size += size
        return archivable_indices

    def _green_indices(self):
        """
        Return list of indexes that are in green state (healthy)
        """
        index_health = self.es_client.cluster.health(level='indices')
        return [
            index
            for index in index_health['indices'].keys()
            if index_health['indices'][index]['status'] == 'green'
        ]

    def _create_repository(self, bucket_name=None):
        """
        Creates a s3 type repository where archives can be stored
        and retrieved.
        """
        bucket_name = self._get_s3_bucket_name()

        # Update S3 bucket based on config.
        self._update_s3_bucket(bucket_name)

        repository_config = {
            "type": "s3",
            "settings": {
                "bucket": bucket_name,
                "region": self.region,
                "role_arn": self.role_arn,
            }
        }
        logging.info("Creating ES snapshot repository: {0}".format(self.repository_name))
        try:
            self.es_client.snapshot.create_repository(self.repository_name, repository_config)
        except TransportError:
            print(
                "Could not create archive repository. "
                "Make sure bucket {0} exists and IAM policy allows es to access bucket. "
                "repository config:{1}"
                .format(bucket_name, repository_config)
            )
            raise

    def _get_s3_bucket_name(self):
        return "{0}.es-{1}-archive.{2}".format(self.region, self.cluster_name,
                                               self.environment_name)

    def _update_s3_bucket(self, name):
        # Auto create bucket if necessary
        buckets = self.s3_client.list_buckets()['Buckets']
        if name not in [bucket['Name'] for bucket in buckets]:
            logging.info("Creating bucket {0}".format(name))
            self.s3_client.create_bucket(
                Bucket=name,
                CreateBucketConfiguration={
                    'LocationConstraint': self.region})

        lifecycle_policy = "{0}/{1}.lifecycle".format(
            ES_ARCHIVE_LIFECYCLE_DIR,
            self.get_es_option_default('s3_archive_lifecycle', 'default'))

        with open(lifecycle_policy) as lifecycle_file:
            lifecycle_config = json.load(lifecycle_file)

        logging.info("Setting lifecycle configuration: {0}".format(lifecycle_config))
        self.s3_client.put_bucket_lifecycle_configuration(
            Bucket=name, LifecycleConfiguration=lifecycle_config)


    def get_es_option(self, option):
        """Returns appropriate configuration for the current environment"""
        section = "{}:{}".format(self.environment_name, self.cluster_name)

        if self.config_es.has_option(section, option):
            return self.config_es.get(section, option)

        raise NoOptionError(option, section)

    def get_es_option_default(self, option, default=None):
        """Returns appropriate configuration for the current environment"""
        try:
            return self.get_es_option(option)
        except NoOptionError:
            return default

    def archive(self):
        """
        Archive enough indexes to bring down disk usage to specified threshold.
        Archive means move to s3 and delete from es cluster.
        """
        threshold = float(self.get_es_option("archive_threshold"))
        if threshold > 1.0:
            raise RuntimeError("ElasticSearch archive threshold cannot exceed 1")

        indices = self._archivable_indices(threshold)
        green_indices = self._green_indices()
        green_archivable = set(indices) & set(green_indices)
        ungreen_archivable = set(indices) - set(green_indices)
        if ungreen_archivable:
            logging.error(
                "Skipping archiving of following unhealthy indexes: %s",
                ",".join(ungreen_archivable)
            )
        if not green_archivable:
            logging.warning("No indexes to archive.")
            return

        self._create_repository()

        for index in green_archivable:
            logging.info("Archiving index: %s", index)
            self.es_client.snapshot.create(
                self.repository_name,
                index,
                {
                    "indices": index,
                    "settings": {
                        "role_arn": self.role_arn
                    }
                }
            )

        return self.wait_for_complete_snaps(green_archivable)


    def snapshots(self, snapshots=None):
        """
        List snapshots their state & etc.
        """
        snaps = self.es_client.snapshot.get(self.repository_name, snapshots or '_all')
        return snaps['snapshots']

    def snapshots_by_state(self, snapshots=None):
        """
        Return all snapshots of by state type
        {'FAILED': ['foo'], 'SUCCESS': ['bar', 'baz']}
        """
        # We don't use the more sensible methods which use ES's _snapshot endpoint,
        # it is not exposed on AWS
        snaps = self.snapshots(",".join(snapshots))
        snap_by_state = defaultdict(list)
        for snap in snaps['snapshots']:
            snap_by_state[snap['state']].append(snap['snapshot'])

    def _complete_snaps(self, snap_states):
        return set([
            snap
            for state in snap_states
            for snap in snap_states[state]
            if state in ES_SNAPSHOT_FINAL_STATES
        ])

    def wait_for_complete_snaps(self, snapshots=None):
        """
        Wait for specified snapshots to complete snapshotting process.
        """
        snapshots = set(snapshots)
        max_time = time() + SNAPSHOT_WAIT_TIMEOUT
        while True:
            snap_states = self.snapshots_by_state(snapshots)
            uncompleted = snapshots - self._complete_snaps(snap_states)
            if not uncompleted or time() < max_time:
                break
            sleep(SNAPSHOT_POLL_INTERVAL)
        return snap_states

    def restore(self, snapshot):
        """
        Bring back index from archive to ES cluster
        """
        self.es_client.snapshot.restore(self.repository_name, snapshot)
