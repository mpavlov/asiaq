"""Tests of disco_log_metrics"""
from unittest import TestCase
from mock import MagicMock, call, PropertyMock
from disco_aws_automation import DiscoLogMetrics
from test.helpers.patch_disco_aws import get_mock_config


class DiscoLogMetricsTests(TestCase):
    """Test DiscoLogMetrics"""

    def setUp(self):
        self.log_metrics = DiscoLogMetrics('test-env')
        self.log_metrics.logs = MagicMock()

        config_mock = PropertyMock(return_value=get_mock_config({
            'mhcdummy.metric_name': {
                'log_file': '/error_log',
                'filter_pattern': 'error',
                'metric_value': 1
            }
        }))
        type(self.log_metrics).config = config_mock

        # pylint: disable=C0103
        def _describe_log_groups(logGroupNamePrefix):
            if logGroupNamePrefix == 'test-env/':  # getting all log metrics in env
                return {'logGroups': [{'logGroupName': 'test-env/mhcdummy/info_log'},
                                      {'logGroupName': 'test-env/mhcbanana/warning_log'}]}

            else:  # getting all log metrics for hostclass
                return {'logGroups': [{'logGroupName': 'test-env/mhcdummy/info_log'}]}

        # pylint: disable=C0103
        def _describe_metric_filters(logGroupName):
            if logGroupName == 'test-env/mhcdummy/info_log':
                return {'metricFilters': [{'filterName': 'mhcdummy_metric'}]}
            elif logGroupName == 'test-env/mhcbanana/warning_log':
                return {'metricFilters': [{'filterName': 'mhcbanana_metric'}]}

        self.log_metrics.logs.describe_log_groups.side_effect = _describe_log_groups
        self.log_metrics.logs.describe_metric_filters.side_effect = _describe_metric_filters

    def test_list_log_groups(self):
        """Test listing log groups"""
        log_groups = self.log_metrics.list_log_groups('mhcdummy')

        self.assertEquals(len(log_groups), 1)
        self.assertEquals(log_groups[0]['logGroupName'], 'test-env/mhcdummy/info_log')

    def test_list_metrics(self):
        """Test list log metric filters for hostclass"""
        metrics = self.log_metrics.list_metric_filters('mhcdummy')

        self.assertEquals(len(metrics), 1)
        self.assertEquals(metrics[0]['filterName'], 'mhcdummy_metric')

    def test_delete_metrics(self):
        """Test delete metric filters for hostclass"""
        self.log_metrics.delete_metrics('mhcdummy')

        self.log_metrics.logs.delete_metric_filter.assert_called_once_with(
            logGroupName='test-env/mhcdummy/info_log',
            filterName='mhcdummy_metric')

    def test_delete_log_groups(self):
        """Test delete log groups for hostclass"""
        self.log_metrics.delete_log_groups('mhcdummy')

        self.log_metrics.logs.delete_log_group.assert_called_once_with(
            logGroupName='test-env/mhcdummy/info_log')

    def test_delete_all_metrics(self):
        """Test delete all metric filters in env"""
        self.log_metrics.delete_all_metrics()

        expected = [call(logGroupName='test-env/mhcdummy/info_log',
                         filterName='mhcdummy_metric'),
                    call(logGroupName='test-env/mhcbanana/warning_log',
                         filterName='mhcbanana_metric')]

        self.log_metrics.logs.delete_metric_filter.assert_has_calls(expected, any_order=True)

    def test_delete_all_log_groups(self):
        """Test delete all log groups in environment"""
        self.log_metrics.delete_all_log_groups()

        expected = [call(logGroupName='test-env/mhcdummy/info_log'),
                    call(logGroupName='test-env/mhcbanana/warning_log')]

        self.log_metrics.logs.delete_log_group.assert_has_calls(expected, any_order=True)

    def test_update(self):
        """Test deleting and creating metric filter from config"""
        self.log_metrics.update('mhcdummy')

        self.log_metrics.logs.delete_metric_filter.assert_called_once_with(
            logGroupName='test-env/mhcdummy/info_log',
            filterName='mhcdummy_metric')

        self.log_metrics.logs.put_metric_filter.assert_called_once_with(
            logGroupName='test-env/mhcdummy/error_log',
            filterName='mhcdummy-metric_name',
            filterPattern='error',
            metricTransformations=[{
                'metricName': 'mhcdummy-metric_name',
                'metricNamespace': 'LogMetrics/test-env',
                'metricValue': 1
            }])
