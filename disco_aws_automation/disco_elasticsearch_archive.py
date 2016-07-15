import re
import logging

from boto3.session import Session
from requests_aws4auth import AWS4Auth
import curator
from elasticsearch import Elasticsearch, RequestsHttpConnection, NotFoundError, TransportError


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
            self._es_client = client = Elasticsearch(
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
        return need_bytes - free_bytes


    def archivable_indices(self, threshold):
        """
        Return list of indices that ough to be archived to get below
        max disk space threshold. Oldest first.
        """
        bytes_to_free = self.bytes_to_free(threshold)
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

    def create_repository(self, bucket_name=None):
        # Looks like it idempotent
        #try:
        #    print("here")
        #    repository = self.es_client.snapshot.get_repository(self.repository_name)
        #    if self.repository_name in repository: 
        #        f=self.es_client.snapshot.delete_repository(self.repository_name)
        #        print(f)
        #    print("here")
        #except NotFoundError:
        #    pass
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


    def archive(self, threshold=.8, wait=False):
        indices = self.archivable_indices(threshold)
        if not indices:
            return

        self.create_repository()

        indices = [indices[0]]
        print("Archiving: {0}".format(indices))
        self.es_client.snapshot.create(
            self.repository_name,
            "master",
            {
                indices: ",".join(indexes)
                "settings": {
                    "role_arn": self.role_arn
                }
            }
        )
        #TODO do we need to delete them, I suspect so
