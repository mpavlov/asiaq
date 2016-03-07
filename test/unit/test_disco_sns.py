"""Tests of disco_sns"""
from unittest import TestCase
from moto import mock_sns
import boto
from disco_aws_automation import DiscoSNS


ACCOUNT_ID = "123456789012"  # mock_sns uses account id 123456789012
TOPIC = "fake_topic"
SUBSCRIPTION_EMAIL_LIST = ["a@example.com", "b@example.com"]
SUBSCRIPTION_URL = "https://example.com/fake_api_endpoint"


class DiscoSNSTests(TestCase):
    """Test DiscoSNS class"""

    @mock_sns
    def get_region(self):
        """Return SNS region of SNS Mock"""
        return boto.connect_sns().region.name

    @mock_sns
    def test_constructor(self):
        """Ensure a valid object was created"""
        disco_sns = DiscoSNS(account_id=ACCOUNT_ID)
        self.assertIsNotNone(disco_sns.sns)

    @mock_sns
    def test_create_topic(self):
        """Ensure we can create topics"""
        disco_sns = DiscoSNS(account_id=ACCOUNT_ID)
        disco_sns.create_topic(TOPIC)
        topics_json = disco_sns.sns.get_all_topics()
        topic_arn = topics_json["ListTopicsResponse"]["ListTopicsResult"]["Topics"][0]['TopicArn']
        self.assertIn(TOPIC, topic_arn)

    @mock_sns
    def test_subscribe_emails(self):
        """Ensure we can subscribe emails"""
        disco_sns = DiscoSNS(account_id=ACCOUNT_ID)
        disco_sns.create_topic(TOPIC)
        disco_sns.subscribe(TOPIC, SUBSCRIPTION_EMAIL_LIST)
        self.assertGreater(disco_sns.sns.get_all_subscriptions(), 0)

    @mock_sns
    def test_subscribe_url(self):
        """Ensure we can subscribe urls"""
        disco_sns = DiscoSNS(account_id=ACCOUNT_ID)
        disco_sns.create_topic(TOPIC)
        disco_sns.subscribe(TOPIC, [SUBSCRIPTION_URL])
        self.assertGreater(disco_sns.sns.get_all_subscriptions(), 0)

    @mock_sns
    def test_topic_arn_from_name(self):
        """Ensure proper topic arn is constructed from a topic name"""
        disco_sns = DiscoSNS(account_id=ACCOUNT_ID)
        arn = disco_sns.topic_arn_from_name(TOPIC)
        self.assertEquals(arn, "arn:aws:sns:{0}:{1}:{2}".format(self.get_region(), ACCOUNT_ID, TOPIC))

    @mock_sns
    def test_get_topics_to_delete(self):
        "Ensure the right topics are returned for deletion"
        env = "ci"
        existing_topics = ["astro_topic1_ci_critical", "astro_topic1_staging_critical",
                           "astro_topic2_ci_critical", "astro_topic1_another-ci_critical",
                           "test"]
        desired_topics = ["astro_topic1_ci_critical"]
        expected_topic_to_delete = ["astro_topic2_ci_critical"]
        topic_to_delete = DiscoSNS.get_topics_to_delete(existing_topics, desired_topics, env)
        self.assertItemsEqual(expected_topic_to_delete, topic_to_delete)
