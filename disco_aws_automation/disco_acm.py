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
        """
        Returns whether the host is in the ACM certificate domain
        Only supports top level domain wildcard matching
        e.g. *.blah.com will match, but not *.*.blah.com
        It would be good to use a standard library here if becomes available.
        """
        if not (domain and dns_name):
            return False

        # sanity check left-most label
        name, subdomain = dns_name.split('.', 1)
        if not name or name == '*':
            logging.error('Left-most label "%s" of "%s" is invalid', name, dns_name)
            return False

        # exact match
        if dns_name == domain:
            return True

        # handle wildcard cert domains
        if domain.startswith(self.WILDCARD_PREFIX):
            domain = domain[len(self.WILDCARD_PREFIX):]
        return subdomain == domain

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
            cert_summary = self.acm.list_certificates()[CERT_SUMMARY_LIST_KEY]
            certs = [cert for cert in cert_summary if self._in_domain(cert[DOMAIN_NAME_KEY], dns_name)]
            # determine the most specific domain match
            certs.sort(key=lambda cert: len(cert[DOMAIN_NAME_KEY]), reverse=True)
            if not certs:
                logging.warning("No ACM certificates returned for %s", dns_name)
            return certs[0][CERT_ARN_KEY] if certs else None
        except (botocore.exceptions.EndpointConnectionError,
                botocore.vendored.requests.exceptions.ConnectionError):
            # some versions of botocore(1.3.26) will try to connect to acm even if outside us-east-1
            logging.exception("Unable to get ACM certificate")
            return None
