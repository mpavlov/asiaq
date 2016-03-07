'''Contains DiscoAutoscale class that orchestrates AWS Autoscaling'''
import logging
import random

import boto
import boto.ec2
import boto.ec2.autoscale
import boto.ec2.autoscale.launchconfig
import boto.ec2.autoscale.group
from boto.ec2.autoscale.policy import ScalingPolicy
from boto.exception import BotoServerError
import boto3

from .resource_helper import throttled_call


DEFAULT_TERMINATION_POLICIES = ["OldestLaunchConfiguration"]


class DiscoAutoscale(object):
    '''Class orchestrating autoscaling'''

    def __init__(self, environment_name, autoscaling_connection=None, boto3_autoscaling_connection=None):
        self.environment_name = environment_name
        self.connection = autoscaling_connection or boto.ec2.autoscale.AutoScaleConnection(
            use_block_device_types=True
        )
        self.boto3_autoscale = boto3_autoscaling_connection or boto3.client('autoscaling')

    def get_groupname(self, hostclass):
        '''Returns the autoscaling group name when given a hostclass'''
        return self.environment_name + '_' + hostclass

    def _filter_by_environment(self, items):
        '''Filters autoscaling groups and launch configs by environment'''
        return [
            item for item in items
            if item.name.startswith("{0}_".format(self.environment_name))
        ]

    def _filter_instance_by_environment(self, items):
        return [
            item for item in items
            if item.group_name.startswith("{0}_".format(self.environment_name))
        ]

    def get_hostclass(self, groupname):
        '''Returns the hostclass when given an autoscaling group name'''
        return groupname.replace(self.environment_name + '_', '')

    def _get_group_generator(self):
        '''Yields groups in current environment'''
        next_token = None
        while True:
            groups = throttled_call(self.connection.get_all_groups,
                                    next_token=next_token)
            for group in self._filter_by_environment(groups):
                yield group
            next_token = groups.next_token
            if not next_token:
                break

    def get_groups(self):
        '''Returns Autoscaling groups in current environment'''
        return list(self._get_group_generator())

    def _get_instance_generator(self, instance_ids=None):
        '''Yields autoscaled instances in current environment'''
        next_token = None
        while True:
            instances = throttled_call(
                self.connection.get_all_autoscaling_instances,
                instance_ids=instance_ids, next_token=next_token)
            for instance in self._filter_instance_by_environment(instances):
                yield instance
            next_token = instances.next_token
            if not next_token:
                break

    def get_instances(self, instance_ids=None):
        '''Returns autoscaled instances in the current environment'''
        return list(self._get_instance_generator(instance_ids=instance_ids))

    def _get_config_generator(self, names=None):
        '''Yields Launch Configurations in current environment'''
        next_token = None
        while True:
            configs = throttled_call(self.connection.get_all_launch_configurations,
                                     names=names, next_token=next_token)
            for config in self._filter_by_environment(configs):
                yield config
            next_token = configs.next_token
            if not next_token:
                break

    def get_configs(self, names=None):
        '''Returns Launch Configurations in current environment'''
        return list(self._get_config_generator(names=names))

    def get_config(self, *args, **kwargs):
        '''Returns a new launch configuration'''
        config = boto.ec2.autoscale.launchconfig.LaunchConfiguration(
            connection=self.connection, *args, **kwargs
        )
        throttled_call(self.connection.create_launch_configuration, config)
        return config

    def delete_config(self, config_name):
        '''Delete a specific Launch Configuration'''
        throttled_call(self.connection.delete_launch_configuration, config_name)

    def clean_configs(self):
        '''Delete unused Launch Configurations in current environment'''
        for config in self._get_config_generator():
            try:
                self.delete_config(config.name)
            except BotoServerError:
                pass

    def delete_group(self, hostclass, force=False):
        '''Delete a specific Autoscaling Group'''
        throttled_call(self.connection.delete_auto_scaling_group,
                       self.get_groupname(hostclass), force_delete=force)

    def clean_groups(self, force=False):
        '''Delete unused Autoscaling Groups in current environment'''
        for group in self._filter_by_environment(self.get_groups()):
            try:
                self.delete_group(self.get_hostclass(group.name), force)
            except BotoServerError:
                pass

    def scaledown_group(self, hostclass):
        '''Scales down number of instances in Autoscaling group to zero'''
        group_list = throttled_call(self.connection.get_all_groups,
                                    names=[self.get_groupname(hostclass)])
        if group_list:
            group = group_list[0]
            group.min_size = group.max_size = group.desired_capacity = 0
            throttled_call(group.update)

    def has_group(self, hostclass):
        '''Returns True iff current environment has an autoscaling group a hostclass'''
        return len(throttled_call(self.connection.get_all_groups,
                                  names=[self.get_groupname(hostclass)])) != 0

    @staticmethod
    def create_autoscale_tags(group_name, tags):
        '''Given a python dictionary return list of boto autoscale Tag objects'''
        return [boto.ec2.autoscale.Tag(key=key, value=value, resource_id=group_name, propagate_at_launch=True)
                for key, value in tags.iteritems()] if tags else None

    def update_group(self, group, launch_config, vpc_zone_id=None,
                     min_size=None, max_size=None, desired_size=None,
                     termination_policies=None, tags=None,
                     load_balancers=None):
        '''Update an existing autoscaling group'''
        group.launch_config_name = launch_config
        if vpc_zone_id:
            group.vpc_zone_identifier = vpc_zone_id
        if min_size is not None:
            group.min_size = min_size
        if max_size is not None:
            group.max_size = max_size
        if desired_size is not None:
            group.desired_capacity = desired_size
        if termination_policies:
            group.termination_policies = termination_policies
        throttled_call(group.update)
        if tags:
            throttled_call(self.connection.create_or_update_tags,
                           DiscoAutoscale.create_autoscale_tags(group.name, tags))
        if load_balancers:
            throttled_call(self.boto3_autoscale.attach_load_balancers,
                           AutoScalingGroupName=group.name,
                           LoadBalancerNames=load_balancers)
        return group

    def create_group(self, hostclass, launch_config, vpc_zone_id,
                     min_size=None, max_size=None, desired_size=None,
                     termination_policies=None, tags=None,
                     load_balancers=None):
        '''
        Create an autoscaling group.

        The group must not already exist. Use get_group() instead if you want to update a group if it
        exits or create it if it does not.
        '''
        _min_size = min_size or 0
        _max_size = max([min_size, max_size, desired_size, 0])
        _desired_capacity = desired_size or max_size
        termination_policies = termination_policies or DEFAULT_TERMINATION_POLICIES
        group_name = self.get_groupname(hostclass)
        group = boto.ec2.autoscale.group.AutoScalingGroup(
            connection=self.connection,
            name=group_name,
            launch_config=launch_config,
            load_balancers=load_balancers,
            default_cooldown=None,
            health_check_type=None,
            health_check_period=None,
            placement_group=None,
            vpc_zone_identifier=vpc_zone_id,
            desired_capacity=_desired_capacity,
            min_size=_min_size,
            max_size=_max_size,
            tags=DiscoAutoscale.create_autoscale_tags(group_name, tags),
            termination_policies=termination_policies,
            instance_id=None)
        throttled_call(self.connection.create_auto_scaling_group, group)
        return group

    def get_group(self, hostclass, launch_config, vpc_zone_id=None,
                  min_size=None, max_size=None, desired_size=None,
                  termination_policies=None, tags=None,
                  load_balancers=None):
        '''
        Returns autoscaling group.
        This updates an existing autoscaling group if it exists,
        otherwise this creates a new autoscaling group.

        NOTE: Deleting tags is not currently supported.
        NOTE: Detaching ELB is not currently supported.
        '''
        group = self.get_existing_group(hostclass)
        if group:
            return self.update_group(
                group=group, launch_config=launch_config, vpc_zone_id=vpc_zone_id,
                min_size=min_size, max_size=max_size, desired_size=desired_size,
                termination_policies=termination_policies, tags=tags, load_balancers=load_balancers)
        else:
            return self.create_group(
                hostclass=hostclass, launch_config=launch_config, vpc_zone_id=vpc_zone_id,
                min_size=min_size, max_size=max_size, desired_size=desired_size,
                termination_policies=termination_policies, tags=tags, load_balancers=load_balancers)

    def get_existing_group(self, hostclass):
        """Returns autoscaling group for a hostclass iff it already exists"""
        group_name = self.get_groupname(hostclass)
        group_list = throttled_call(self.connection.get_all_groups, names=[group_name])
        return group_list[0] if group_list else None

    def terminate(self, instance_id, decrement_capacity=True):
        """
        Terminates an instance using the autoscaling API.

        When decrement_capacity is True this allows us to avoid
        autoscaling immediately replacing a terminated instance.
        """
        throttled_call(self.connection.terminate_instance,
                       instance_id, decrement_capacity=decrement_capacity)

    def get_launch_config_for_hostclass(self, hostclass):
        """Returns an launch configuration for a hostclass if it exists, None otherwise"""
        group_list = throttled_call(self.connection.get_all_groups,
                                    names=[self.get_groupname(hostclass)])
        if not group_list:
            return None
        config_list = self.get_configs(names=[group_list[0].launch_config_name])
        return config_list[0] if config_list else None

    def list_policies(self):
        """Returns all autoscaling policies"""
        return throttled_call(self.connection.get_all_policies)

    def create_policy(self, policy_name, group_name, adjustment, cooldown):
        """Creates an autoscaling policy and associates it with an autoscaling group"""
        policy = ScalingPolicy(name=policy_name, adjustment_type='ChangeInCapacity',
                               as_name=group_name, scaling_adjustment=adjustment, cooldown=cooldown)
        throttled_call(self.connection.create_scaling_policy, policy)

    def delete_policy(self, policy_name, group_name):
        """Deletes an autoscaling policy"""
        return throttled_call(self.connection.delete_policy, policy_name, group_name)

    def delete_all_recurring_group_actions(self, hostclass):
        """Deletes all recurring scheduled actions for a hostclass"""
        as_group = self.get_groupname(hostclass)
        actions = throttled_call(self.connection.get_all_scheduled_actions, as_group=as_group)
        recurring_actions = [action for action in actions if action.recurrence is not None]
        for action in recurring_actions:
            throttled_call(self.connection.delete_scheduled_action,
                           scheduled_action_name=action.name, autoscale_group=as_group)

    def create_recurring_group_action(self, hostclass, recurrance,
                                      min_size=None, desired_capacity=None, max_size=None):
        """Creates a recurring scheduled action for a hostclass"""
        as_group = self.get_groupname(hostclass)
        action_name = "{0}_{1}".format(as_group, recurrance.replace('*', 'star').replace(' ', '_'))
        throttled_call(self.connection.create_scheduled_group_action,
                       as_group=as_group, name=action_name,
                       min_size=min_size,
                       desired_capacity=desired_capacity,
                       max_size=max_size,
                       recurrence=recurrance)

    @staticmethod
    def _get_snapshot_dev(launch_config, hostclass):
        snapshot_devs = [key for key, value in launch_config.block_device_mappings.iteritems()
                         if value.snapshot_id]
        if not snapshot_devs:
            raise Exception("Hostclass {0} does not mount a snapshot".format(hostclass))
        elif len(snapshot_devs) > 1:
            raise Exception("Unsupported configuration: hostclass {0} has multiple snapshot based devices."
                            .format(hostclass))
        return snapshot_devs[0]

    def _create_new_launchconfig(self, hostclass, launch_config):
        return self.get_config(
            name='{0}_{1}_{2}'.format(self.environment_name, hostclass, str(random.randrange(0, 9999999))),
            image_id=launch_config.image_id,
            key_name=launch_config.key_name,
            security_groups=launch_config.security_groups,
            block_device_mappings=[launch_config.block_device_mappings],
            instance_type=launch_config.instance_type,
            instance_monitoring=launch_config.instance_monitoring,
            instance_profile_name=launch_config.instance_profile_name,
            ebs_optimized=launch_config.ebs_optimized,
            user_data=launch_config.user_data,
            associate_public_ip_address=launch_config.associate_public_ip_address)

    def update_snapshot(self, hostclass, snapshot_id, snapshot_size):
        '''Updates an existing autoscaling group to use a different snapshot'''
        launch_config = self.get_launch_config_for_hostclass(hostclass)
        if not launch_config:
            raise Exception("Can't locate hostclass {0}".format(hostclass))
        snapshot_bdm = launch_config.block_device_mappings[
            DiscoAutoscale._get_snapshot_dev(launch_config, hostclass)]
        if snapshot_bdm.snapshot_id != snapshot_id:
            old_snapshot_id = snapshot_bdm.snapshot_id
            snapshot_bdm.snapshot_id = snapshot_id
            snapshot_bdm.size = snapshot_size
            self.update_group(self.get_existing_group(hostclass),
                              self._create_new_launchconfig(hostclass, launch_config).name)
            logging.info(
                "Updating %s group's snapshot from %s to %s", hostclass, old_snapshot_id, snapshot_id)
        else:
            logging.debug(
                "Autoscaling group %s is already referencing latest snapshot %s", hostclass, snapshot_id)

    def update_elb(self, hostclass, elb_names):
        '''Updates an existing autoscaling group to use a different set of load balancers'''
        group = self.get_existing_group(hostclass)

        if not group:
            logging.warning("Auto Scaling group %s does not exist. Cannot change %s ELB(s)",
                            hostclass, ', '.join(elb_names))
            return (set(), set())

        new_lbs = set(elb_names) - set(group.load_balancers)
        extras = set(group.load_balancers) - set(elb_names)
        if new_lbs or extras:
            logging.info("Updating %s group's elb from [%s] to [%s]",
                         hostclass, ", ".join(group.load_balancers), ", ".join(elb_names))
        if new_lbs:
            throttled_call(self.boto3_autoscale.attach_load_balancers,
                           AutoScalingGroupName=group.name,
                           LoadBalancerNames=list(new_lbs))
        if extras:
            throttled_call(self.boto3_autoscale.detach_load_balancers,
                           AutoScalingGroupName=group.name,
                           LoadBalancerNames=list(extras))
        return (new_lbs, extras)
