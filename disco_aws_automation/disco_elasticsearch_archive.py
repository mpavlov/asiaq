import re
import logging

from boto3.session import Session
from requests_aws4auth import AWS4Auth
from elasticsearch import (
    Elasticsearch,
    RequestsHttpConnection,
    NotFoundError,
    TransportError,
)


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
        if not self._host:
            #TODO find cluster connection info using cluster name and disco_aws
            self._host = {'host': 'es-logs-ci.aws.wgen.net', 'port': 80}
        return self._host

    @property
    def region(self):
        if not self._region:
            self._region = Session().region_name
        return self._region

    @property
    def role_arn(self):
        # TODO pick this up automatically
        return "arn:aws:iam::646102706174:role/disco_ci_es_archive"

    @property
    def es_client(self):
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
        index_health = self.es_client.cluster.health(level='indices')
        return [
            index
            for index in index_health['indices'].keys()
            if index_health['indices'][index]['status'] == 'green'
        ]

    def create_repository(self, bucket_name=None):
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
        indices = self.archivable_indices(threshold)
        if not indices:
            return

        green_indices = self.green_indices()
        green_archivable = set(indices) & set(green_indices)
        ungreen_archivable = set(indices) - set(green_indices)
        if ungreen_archivable:
            logging.error(
                "Skipping archiving of following unhealthy indexes: %s",
                ",".join(ungreen_archivable)
            )

        self.create_repository()

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

        #TODO wait for all indexes to complete snapshot and deactivate them on ES.
