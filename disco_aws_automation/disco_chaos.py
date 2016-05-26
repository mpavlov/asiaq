'''Class that kills instances in a controlled manner'''

import random
import math
from . import DiscoAWS
from .disco_aws_util import is_truthy


class DiscoChaos(object):
    '''Class that kills instances in a controlled manner'''

    def __init__(self, config, environment_name, level, retainage):
        """
        :param config: Configuration object to use
        :param environment_name: Environment to operate on
        :param level: Percentage of instances to kill
        :param retainage: Percentage of instances to keep in each autoscaling group
        """
        self._config = config
        self._level = level
        self._retainage = retainage
        self._environment_name = environment_name
        self._disco_aws = None
        self._groups = None

    @property
    def disco_aws(self):
        '''Lazily creates Disco AWS instance'''
        if not self._disco_aws:
            self._disco_aws = DiscoAWS(self._config, self._environment_name)  # pragma: no cover
        return self._disco_aws

    def _get_autoscaling_groups(self):
        '''Returns list of autoscaling groups (with caching)'''
        if self._groups is None:
            self._groups = self.disco_aws.autoscale.get_existing_groups()  # pragma: no cover
        return self._groups

    @staticmethod
    def _has_chaos(group):
        return is_truthy({tag.key: tag.value for tag in group.tags}.get('chaos', "True"))

    def _instances_not_to_retain(self, group):
        '''
        Returns a random subset of an autoscaling group's instances based on retainage.

        For example, if retainage is 33.3% and there are three instances then two instances
        should be eligible for termination. So two instances will be picked from the list
        and returned from this function.
        '''
        keep_count = int(math.floor(group.desired_capacity * (1 - self._retainage * 0.01)))
        return random.sample(group.instances, keep_count)

    def _get_chaotic_groups(self):
        '''Returns list of autoscaling groups that haven't had chaos disabled'''
        return [group for group in self._get_autoscaling_groups() if DiscoChaos._has_chaos(group)]

    def _termination_eligible_instances(self):
        '''Returns list of instances eligible for termination'''
        return [instance.instance_id
                for group in self._get_chaotic_groups()
                for instance in self._instances_not_to_retain(group)]

    def _total_instances(self):
        return sum([len(group.instances) for group in self._get_chaotic_groups()])

    def _select_instances(self, eligible, count):
        '''Selects a set number of instances'''
        return random.sample(eligible, min(count, len(eligible)))

    def get_instances_to_terminate(self):
        '''Returns instances to terminate'''
        instance_ids_to_kill = self._select_instances(
            eligible=self._termination_eligible_instances(),
            count=max(int(self._total_instances() * self._level * 0.01), 1))
        return self.disco_aws.instances(instance_ids=instance_ids_to_kill) if instance_ids_to_kill else []

    def terminate(self, instances):
        '''Terminates instances'''
        self.disco_aws.terminate(instances)
