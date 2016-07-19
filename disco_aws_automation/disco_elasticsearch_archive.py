import re
import logging
from time import time, sleep
from collections import defaultdict

from boto3.session import Session
from requests_aws4auth import AWS4Auth
from elasticsearch import (
    Elasticsearch,
    RequestsHttpConnection,
    TransportError,
)

ES_SNAPSHOT_FINAL_STATES = ['SUCCESS', 'FAILED']
SNAPSHOT_WAIT_TIMEOUT = 60*60
SNAPSHOT_POLL_INTERVAL = 60


class DiscoESArchive(object):
    def __init__(self, cluster_name, index_prefix_pattern=None, repository_name=None):
        self.cluster_name = cluster_name
        self._host = None
        self._es_client = None
        self._region = None
        self.index_prefix_pattern = index_prefix_pattern or r'.*'
        self.repository_name = repository_name or 's3'

    @property
    def host(self):
        """
        Return ES cluster hostname
        """
        if not self._host:
            #TODO find cluster connection info using cluster name and disco_aws
            self._host = {'host': 'es-logs-ci.aws.wgen.net', 'port': 80}
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
        # TODO pick this up automatically
        return "arn:aws:iam::646102706174:role/disco_ci_es_archive"

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

    def bytes_to_free(self, threshold):
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

    def archivable_indices(self, threshold):
        """
        Return list of indices that ough to be archived to get below
        max disk space threshold. Oldest first.
        """
        bytes_to_free = self.bytes_to_free(threshold)
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

    def green_indices(self):
        """
        Return list of indexes that are in green state (healthy)
        """
        index_health = self.es_client.cluster.health(level='indices')
        return [
            index
            for index in index_health['indices'].keys()
            if index_health['indices'][index]['status'] == 'green'
        ]

    def create_repository(self, bucket_name=None):
        """
        Creates a s3 type repository where archives can be stored
        and retrieved.
        """
        # TODO auto create bucket if necessary?
        bucket_name = bucket_name or '{0}.es-log-archive'.format(self.region)
        repository_config = {
            "type": "s3",
            "settings": {
                "bucket": bucket_name,
                "region": self.region,
                "role_arn": self.role_arn,
            }
        }
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

    def archive(self, threshold=.8):
        """
        Archive enough indexes to bring down disk usage to specified threshold.
        Archive means move to s3 and delete from es cluster.
        """
        indices = self.archivable_indices(threshold)
        green_indices = self.green_indices()
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


        self.create_repository()

        green_archivable = set([green_archivable[8]])

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
            break  # TODO remove this debug line

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
