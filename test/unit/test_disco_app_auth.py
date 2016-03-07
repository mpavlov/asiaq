"""
Tests of disco_aws
"""
from unittest import TestCase

from disco_aws_automation import DiscoAppAuth


class DiscoAppAuthTests(TestCase):
    '''Test DiscoAppAuth class'''

    def test_password_length(self):
        """random passwords are at least 60 characters long"""
        self.assertEqual(len(DiscoAppAuth.generate_random_password()), 60)
