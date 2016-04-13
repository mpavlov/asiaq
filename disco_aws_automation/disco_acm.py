"""
Some code to manage the Amazon Certificate Service.
"""
import logging

import boto3
import botocore


class DiscoACM(object):
    """
    A class to manage the Amazon Certificate Service

    """

    def __init__(self, connection=None):
        self._acm = connection

    @property
    def acm(self):
        """
        Lazily creates ACM connection

        NOTE!!! As of 2016-02-11 ACM is not supported outside the us-east-1 region.
        Return None if service does not exist in current region
        """
        if not self._acm:
            try:
                self._acm = boto3.client('acm', region_name='us-east-1')
            except Exception:
                logging.warning("ACM service does not exist in current region")
                return None
        return self._acm

    def get_certificate_arn(self, dns_name):
        """Returns a Certificate ARN from the Amazon Certificate Service given the DNS name"""
        if not self.acm:
            return None

        try:
            certs = self.acm.list_certificates()["CertificateSummaryList"]
            cert = [cert['CertificateArn'] for cert in certs if cert['DomainName'] == dns_name]
            return cert[0] if cert else None
        except (botocore.exceptions.EndpointConnectionError, botocore.vendored.requests.exceptions.ConnectionError):
            # some versions of botocore(1.3.26) will try to connect to acm even if outside us-east-1
            return None
