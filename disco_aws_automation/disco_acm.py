"""
Some code to manage the Amazon Certificate Service.
"""
import logging

import boto3
import botocore

CERT_SUMMARY_LIST_KEY = 'CertificateSummaryList'
CERT_ARN_KEY = 'CertificateArn'
DOMAIN_NAME_KEY = 'DomainName'

class DiscoACM(object):
    """
    A class to manage the Amazon Certificate Service

    """
    WILDCARD_PREFIX = "*."

    def __init__(self, connection=None):
        self._acm = connection

    def _in_domain(self, domain, dns_name):
        """Returns whether the host is in the ACM certificate domain"""
        if dns_name == domain:
            return True

        # handle wildcard cert domains
        name, subdomain = dns_name.split('.', 1)
        if not name:
            return False

        domain_suffix = (domain[len(self.WILDCARD_PREFIX):]
                         if domain.startswith(self.WILDCARD_PREFIX) else domain)
        return subdomain.endswith(domain_suffix)

    @property
    def acm(self):
        """
        Lazily creates ACM connection

        Return None if service does not exist in current region
        """
        if not self._acm:
            try:
                self._acm = boto3.client('acm')
            except Exception:
                logging.warning("ACM service does not exist in current region")
                return None
        return self._acm

    def get_certificate_arn(self, dns_name):
        """Returns a Certificate ARN from the Amazon Certificate Service given the DNS name"""
        if not self.acm:
            return None

        try:
            certs = self.acm.list_certificates()[CERT_SUMMARY_LIST_KEY]
            cert = [cert[CERT_ARN_KEY] for cert in certs if self._in_domain(cert[DOMAIN_NAME_KEY], dns_name)]
            return cert[0] if cert else None
        except (botocore.exceptions.EndpointConnectionError,
                botocore.vendored.requests.exceptions.ConnectionError):
            # some versions of botocore(1.3.26) will try to connect to acm even if outside us-east-1
            return None
