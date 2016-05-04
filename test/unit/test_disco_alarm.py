"""Test disco_alarm"""
from unittest import TestCase
from random import randint
import logging

from moto import mock_cloudwatch
from boto.ec2.cloudwatch import CloudWatchConnection
from disco_aws_automation import DiscoAlarm, DiscoAlarmsConfig
from disco_aws_automation import DiscoAlarmConfig
from disco_aws_automation import DiscoSNS
from disco_aws_automation import AlarmConfigError
from test.helpers.patch_disco_aws import get_mock_config

TOPIC_ARN = "arn:aws:sns:us-west-2:123456789012:ci"
ENVIRONMENT = "testenv"
ACCOUNT_ID = "123456789012"  # mock_sns uses account id 123456789012


class DiscoAlarmTests(TestCase):
    """Test disco_alarm"""

    def setUp(self):
        self.cloudwatch_mock = mock_cloudwatch()
        self.cloudwatch_mock.start()
        disco_sns = DiscoSNS(account_id=ACCOUNT_ID)
        self.alarm = DiscoAlarm(disco_sns)

    def tearDown(self):
        self.alarm.cloudwatch.delete_alarms(
            [
                alarm.name
                for alarm in self.alarm.cloudwatch.describe_alarms()
            ]
        )
        self.cloudwatch_mock.stop()
        self.cloudwatch_mock = None

    def test_init(self):
        """
        Alarm object is correctly instanciated
        """
        self.assertIsInstance(self.alarm.cloudwatch, CloudWatchConnection)

    def _alarm_count(self):
        alarms = self.alarm.cloudwatch.describe_alarms()
        return len(alarms)

    def _make_alarm(self, hostclass="hcfoo"):
        options = {
            "namespace": "nsfoo",
            "metric_name": "metric{0}".format(
                randint(100000, 999999),
            ),
            "hostclass": hostclass,
            "environment": ENVIRONMENT,
            "duration": "5",
            "period": "60",
            "statistic": "Average",
            "custom_metric": "false",
            "threshold_max": "90",
            "level": "critical",
            "team": "america",
        }
        return DiscoAlarmConfig(options)

    def test_upsert_alarm(self):
        """
        Creating same alert overwrites old one
        """
        self.assertEqual(0, self._alarm_count())
        metric_alarm = self._make_alarm().to_metric_alarm(TOPIC_ARN)
        logging.debug("metric_alarm: %s", metric_alarm)
        self.alarm.upsert_alarm(metric_alarm)
        self.assertEqual(1, self._alarm_count())
        self.alarm.upsert_alarm(metric_alarm)
        self.assertEqual(1, self._alarm_count())

    def test_create_delete_alarms(self):
        """
        Create and delete bunch of alarms
        """
        number_of_alarms = 10
        self.assertEqual(0, self._alarm_count())
        alarms = [
            self._make_alarm()
            for _ in range(0, number_of_alarms)
        ]
        logging.debug("alarms: %s", alarms)
        self.alarm.create_alarms(alarms)
        self.assertEqual(number_of_alarms, self._alarm_count())

        self.alarm.delete_environment_alarms(ENVIRONMENT)
        self.assertEqual(0, self._alarm_count())

    def test_delete_by_hostclass(self):
        """
        Deletion by hostclass name
        """
        self.alarm.upsert_alarm(self._make_alarm(hostclass="hcfoo").to_metric_alarm(TOPIC_ARN))
        self.alarm.upsert_alarm(self._make_alarm(hostclass="hcfoo").to_metric_alarm(TOPIC_ARN))
        self.alarm.upsert_alarm(self._make_alarm(hostclass="hcbar").to_metric_alarm(TOPIC_ARN))
        self.assertEqual(3, self._alarm_count())
        self.alarm.delete_hostclass_environment_alarms(ENVIRONMENT, "hcfoo")
        self.assertEqual(1, self._alarm_count())

    def test_get_alarms(self):
        """Test that get_alarms filter works"""
        self.alarm.upsert_alarm(self._make_alarm(hostclass="hcfoo").to_metric_alarm(TOPIC_ARN))
        self.alarm.upsert_alarm(self._make_alarm(hostclass="hcbar").to_metric_alarm(TOPIC_ARN))
        self.assertEqual(2, len(self.alarm.get_alarms()))
        self.assertEqual(1, len(self.alarm.get_alarms({"hostclass": "hcfoo"})))

    def test_decode_alarm_name_old(self):
        """Decoding Disco era Alarm Names works"""
        expected = {
            "team": None,
            "env": "ci",
            "hostclass": "mhcscone",
            "metric_name": "CPUUtilization",
            "threshold_type": "max",
        }
        self.assertEqual(DiscoAlarmConfig.decode_alarm_name("ci_mhcscone_CPUUtilization_max"), expected)

    def test_decode_alarm_name_new(self):
        """Decoding Team based Alarm Names works"""
        expected = {
            "team": "rocket",
            "env": "ci",
            "hostclass": "mhcscone",
            "metric_name": "CPUUtilization",
            "threshold_type": "max",
        }
        self.assertEqual(
            DiscoAlarmConfig.decode_alarm_name("rocket_ci_mhcscone_CPUUtilization_max"), expected)

    def test_decode_bogus_alarm_name_raises(self):
        """decode_alarm_name raises on bogus name"""
        self.assertRaises(AlarmConfigError, DiscoAlarmConfig.decode_alarm_name, "bogus")

    def test_get_alarm_config(self):
        """Test DiscoAlarmsConfig get_alarms for regular metrics"""
        disco_alarms_config = DiscoAlarmsConfig(ENVIRONMENT)
        disco_alarms_config.config = get_mock_config({
            'reporting.EC2.CPU.mhcrasberi': {
                'log_pattern_metric': 'false',
                'threshold_max': '1',
                'duration': '60',
                'period': '5',
                'statistic': 'average',
                'custom_metric': 'false',
                'level': 'critical'
            }
        })

        alarm_configs = disco_alarms_config.get_alarms('mhcrasberi')
        self.assertEqual(1, len(alarm_configs))
        self.assertEquals('EC2', alarm_configs[0].namespace)
        self.assertEquals('CPU', alarm_configs[0].metric_name)

    def test_get_alarm_config_log_pattern_metric(self):
        """Test DiscoAlarmsConfig get_alarms for log pattern metrics"""
        disco_alarms_config = DiscoAlarmsConfig(ENVIRONMENT)
        disco_alarms_config.config = get_mock_config({
            'reporting.LogMetrics.ErrorCount.mhcrasberi': {
                'log_pattern_metric': 'true',
                'threshold_max': '1',
                'duration': '60',
                'period': '5',
                'statistic': 'average',
                'custom_metric': 'false',
                'level': 'critical'
            }
        })

        alarm_configs = disco_alarms_config.get_alarms('mhcrasberi')
        self.assertEqual(1, len(alarm_configs))
        self.assertEquals('LogMetrics/' + ENVIRONMENT, alarm_configs[0].namespace)
        self.assertEquals('mhcrasberi-ErrorCount', alarm_configs[0].metric_name)

    def test_get_alarm_config_elb_metric(self):
        """Test DiscoAlarmsConfig get_alarms for ELB metrics"""
        disco_alarms_config = DiscoAlarmsConfig(ENVIRONMENT)
        disco_alarms_config.config = get_mock_config({
            'reporting.AWS/ELB.HealthyHostCount.mhcbanana': {
                'threshold_min': '1',
                'duration': '60',
                'period': '5',
                'statistic': 'Minimum',
                'custom_metric': 'false',
                'level': 'critical'
            }
        })

        alarm_configs = disco_alarms_config.get_alarms('mhcbanana')
        self.assertEqual(1, len(alarm_configs))
        self.assertEquals({'LoadBalancerName': 'testenv-mhcbanana'}, alarm_configs[0].dimensions)
