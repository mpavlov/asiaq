'''Contains DiscoAlarm class for orchestrating CloudWatch alarms'''

import logging

from boto.ec2.cloudwatch import CloudWatchConnection

from .disco_sns import DiscoSNS
from .disco_alarm_config import DiscoAlarmConfig
from .resource_helper import throttled_call

# Max batch size for alarm deletion http://goo.gl/vMQOrX
DELETE_BATCH_SIZE = 100


class DiscoAlarm(object):
    """
    Class orchestrating CloudWatch alarms
    """

    def __init__(self, disco_sns=None):
        self.cloudwatch = CloudWatchConnection()
        self._disco_sns = disco_sns

    def upsert_alarm(self, alarm):
        """
        Create an alarm, delete and re-create if it already exists
        """
        existing_alarms = self.cloudwatch.describe_alarms(alarm_names=[alarm.name])
        for existing_alarm in existing_alarms:
            throttled_call(
                existing_alarm.delete
            )
        throttled_call(
            self.cloudwatch.create_alarm,
            alarm
        )

    @property
    def disco_sns(self):
        """
        Lazy sns connection
        """
        self._disco_sns = self._disco_sns or DiscoSNS()
        return self._disco_sns

    def _sns_topic(self, alarm):
        """
        retrieve SNS topic correspoding to the alarm
        """
        return self.disco_sns.topic_arn_from_name(alarm.notification_topic)

    def create_alarms(self, alarms):
        """
        Create alarms from dict of DiscoAlarmConfig objects.
        """
        for alarm in alarms:
            self.upsert_alarm(
                alarm.to_metric_alarm(
                    self._sns_topic(alarm)
                )
            )

    def alarms(self):
        """
        Iterate alarms
        """
        next_token = None
        while True:
            alarms = throttled_call(
                self.cloudwatch.describe_alarms,
                next_token=next_token,
            )
            for alarm in alarms:
                yield alarm
            next_token = alarms.next_token
            if not next_token:
                break

    def get_alarms(self, desired=None):
        """
        Get all alarms for an environment filtered on the desired dictionary keys
        """
        desired = desired or {}
        keys = set(desired.keys())

        def _key_filter(dictionary, keys):
            return {key: value for key, value in dictionary.iteritems() if key in keys}

        return [alarm for alarm in self.alarms()
                if _key_filter(DiscoAlarmConfig.decode_alarm_name(alarm.name), keys) == desired]

    def _delete_alarms(self, alarms):
        alarm_names = [alarm.name for alarm in alarms]
        alarm_len = len(alarm_names)
        logging.debug("Deleting %s alarms.", alarm_len)
        for index in range(0, alarm_len, DELETE_BATCH_SIZE):
            throttled_call(
                self.cloudwatch.delete_alarms,
                alarm_names[index:min(index + DELETE_BATCH_SIZE, alarm_len)]
            )

    def delete_hostclass_environment_alarms(self, environment, hostclass):
        """
        Delete alarm in an environment by hostclass name
        """
        self._delete_alarms(self.get_alarms({"env": environment, "hostclass": hostclass}))

    def delete_environment_alarms(self, environment):
        """
        Delete all alarms for an environment
        """
        self._delete_alarms(self.get_alarms({"env": environment}))
