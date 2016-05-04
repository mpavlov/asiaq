'Contains DiscoDeploy class'

import copy
import logging
import random
import sys

from ConfigParser import NoOptionError
from boto.exception import EC2ResponseError

from . import DiscoBake, read_config
from .exceptions import TimeoutError, MaintenanceModeError, IntegrationTestError, SmokeTestError
from .disco_aws_util import is_truthy, size_as_minimum_int_or_none, size_as_maximum_int_or_none
from .disco_constants import DEFAULT_CONFIG_SECTION


def snap_to_range(val, mini, maxi):
    '''Returns a value snapped into [mini, maxi]'''
    return min(max(int(val), int(mini)), int(maxi))


class DiscoDeploy(object):
    '''DiscoDeploy takes care of testing, promoting and deploying the latests AMIs'''

    # pylint: disable=too-many-arguments
    def __init__(self, aws, test_aws, bake, pipeline_definition,
                 ami=None, hostclass=None, allow_any_hostclass=False, config=None):
        '''
        Constructor for DiscoDeploy

        :param aws a DiscoAWS instance to use
        :param test_aws DiscoAWS instance for integration tests. may be different environment than "aws" param
        :param bake a DiscoBake instance to use
        :param pipeline_definition a list of dicts containing hostname, deployable and other pipeline values
        :param allow_any_hostclass do not restrict to hostclasses in the pipeline definition
        :param config: Configuration object to use.
        '''
        self._config = config or read_config()

        self._restrict_amis = [ami] if ami else None
        self._restrict_hostclass = hostclass
        self._disco_aws = aws
        self._test_aws = test_aws
        self._disco_bake = bake
        self._all_stage_amis = None
        self._hostclasses = self._get_hostclasses_from_pipeline_definition(pipeline_definition)
        self._allow_any_hostclass = allow_any_hostclass

    def _get_hostclasses_from_pipeline_definition(self, pipeline_definition):
        ''' Return hostclasses from pipeline definitions, validating numeric input '''
        hostclasses = {entry["hostclass"]: entry for entry in pipeline_definition}

        for entry in hostclasses.itervalues():
            if "min_size" in entry:
                entry["min_size"] = int(size_as_minimum_int_or_none(entry["min_size"]))
            if "desired_size" in entry:
                entry["desired_size"] = int(size_as_maximum_int_or_none(entry["desired_size"]))
            if "max_size" in entry:
                entry["max_size"] = int(size_as_maximum_int_or_none(entry["max_size"]))

        return hostclasses

    def _filter_amis(self, amis):
        if self._restrict_amis:
            return [ami for ami in amis if ami.id in self._restrict_amis]
        elif self._restrict_hostclass:
            return [ami for ami in amis if DiscoBake.ami_hostclass(ami) == self._restrict_hostclass]
        elif not self._allow_any_hostclass:
            return [ami for ami in amis if DiscoBake.ami_hostclass(ami) in self._hostclasses]
        else:
            return amis

    @property
    def all_stage_amis(self):
        '''Returns AMIs filtered on AMI ids, hostclass and state == available'''
        if not self._all_stage_amis:
            self._all_stage_amis = [ami for ami in self._filter_amis(
                self._disco_bake.list_amis(ami_ids=self._restrict_amis)) if ami.state == u'available']
        return self._all_stage_amis

    def get_latest_ami_in_stage_dict(self, stage):
        '''Returns latest AMI for each hostclass in a specific stage

        :param stage If set filter by stage, else only return instance without tag
        '''
        latest_ami = {}
        for ami in self.all_stage_amis:
            if stage and ami.tags.get("stage") != stage:
                continue
            elif stage is None and ami.tags.get("stage") is not None:
                continue
            hostclass = DiscoBake.ami_hostclass(ami)
            old_ami = latest_ami.get(hostclass)
            new_time = self._disco_bake.get_ami_creation_time(ami)
            if not new_time:
                continue
            if not old_ami:
                latest_ami[hostclass] = ami
                continue
            old_time = self._disco_bake.get_ami_creation_time(old_ami)
            if old_time and (new_time > old_time):
                latest_ami[hostclass] = ami
        return latest_ami

    def get_latest_untested_amis(self):
        '''Returns latest untested AMI for each hostclass'''
        return self.get_latest_ami_in_stage_dict(self._disco_bake.ami_stages()[0])

    def get_latest_untagged_amis(self):
        '''Returns latest untagged AMI for each hostclass'''
        return self.get_latest_ami_in_stage_dict(None)

    def get_latest_tested_amis(self):
        '''Returns latest tested AMI for each hostclass'''
        return self.get_latest_ami_in_stage_dict(self._disco_bake.ami_stages()[-1])

    def get_latest_failed_amis(self):
        '''Returns latest failed AMI for each hostclass'''
        return self.get_latest_ami_in_stage_dict('failed')

    def get_items_newer_in_second_map(self, first, second):
        '''Returns AMIs from second dict which are newer than the corresponding item in the first dict'''
        return [ami for (hostclass, ami) in second.iteritems()
                if (first.get(hostclass) is None) or (
                    self._disco_bake.get_ami_creation_time(ami) >
                    self._disco_bake.get_ami_creation_time(first[hostclass]))]

    def get_newest_in_either_map(self, first, second):
        '''Returns AMIs which are newest for each hostclass'''
        newest_for_hostclass = first
        for (hostclass, ami) in second.iteritems():
            if hostclass not in newest_for_hostclass:
                newest_for_hostclass[hostclass] = ami
            elif (self._disco_bake.get_ami_creation_time(ami) >
                  self._disco_bake.get_ami_creation_time(first[hostclass])):
                newest_for_hostclass[hostclass] = ami
        return newest_for_hostclass

    def get_test_amis(self):
        '''Returns untested AMIs that are newer than the newest tested AMIs'''
        return self.get_items_newer_in_second_map(
            self.get_latest_tested_amis(), self.get_latest_untested_amis())

    def get_failed_amis(self):
        '''Returns failed AMIs that are newer than the newest tested AMIs'''
        return self.get_items_newer_in_second_map(
            self.get_latest_tested_amis(), self.get_latest_failed_amis())

    def get_latest_running_amis(self):
        '''Retuns hostclass: ami mapping with latest running AMIs'''
        running_ami_ids = list({instance.image_id for instance in self._disco_aws.instances()})
        running_amis = self._disco_bake.get_amis(running_ami_ids)
        sorted_amis = sorted(running_amis, key=self._disco_bake.get_ami_creation_time)
        return {DiscoBake.ami_hostclass(ami): ami for ami in sorted_amis}

    def get_update_amis(self):
        '''
        Returns list of AMIs that are ready to be deployed in production.

        Hosts must be in the pipeline definition and marked as deployable and
        the AMI must be newer than the one currently running AMI for that host.
        '''
        available = self.get_newest_in_either_map(
            self.get_latest_tested_amis(), self.get_latest_untagged_amis())
        newer = self.get_items_newer_in_second_map(self.get_latest_running_amis(), available)
        return [ami for ami in newer
                if (DiscoBake.ami_hostclass(ami) in self._hostclasses and
                    self.is_deployable(DiscoBake.ami_hostclass(ami)))]

    def is_deployable(self, hostclass):
        """Returns true for all hostclasses which aren't tagged as non-ZDD hostclasses"""
        return ((hostclass in self._hostclasses and
                 is_truthy(self._hostclasses[hostclass].get("deployable"))) or
                hostclass not in self._hostclasses)

    def get_integration_test(self, hostclass):
        """Returns the integration test for this hostclass, or None if none exists"""
        return (hostclass in self._hostclasses and
                self._hostclasses[hostclass].get("integration_test")) or None

    def wait_for_smoketests(self, ami_id, min_count):
        '''
        Waits for smoketests to complete for an AMI.

        Returns True on success, False on failure.
        '''

        try:
            self._disco_aws.wait_for_autoscaling(ami_id, min_count)
        except TimeoutError:
            logging.info("autoscaling timed out")
            return False

        try:
            self._disco_aws.smoketest(self._disco_aws.instances_from_amis([ami_id]))
        except TimeoutError:
            logging.info("smoketest timed out")
            return False
        except SmokeTestError:
            logging.info("smoketest instance was terminated")
            return False

        return True

    # Disable W0702 We want to swallow all the exceptions here
    # pylint: disable=W0702
    def _promote_ami(self, ami, stage):
        """
        Promote AMI to specified stage. And, conditionally, make executable by
        production account if ami is staged as tested.
        """

        prod_baker = self._disco_bake.option("prod_baker")
        promote_conditions = [
            stage == "tested",
            prod_baker,
            ami.tags.get("baker") == prod_baker,
        ]

        try:
            self._disco_bake.promote_ami(ami, stage)
            if all(promote_conditions):
                self._disco_bake.promote_ami_to_production(ami)
        except:
            logging.exception("promotion failed")

    def handle_nodeploy_ami(self, old_hostclass_dict, ami, desired_size, dry_run):
        '''Promotes a non-deployable host and updates the autoscaling group to use it next time

        A host is launched in testing mode and if it passes smoketests it is promoted and
        the autoscaling group for that hostclass is updated.

        The currently active instances of this hostclass are not put in maintenance mode and
        are not replaced by the new AMI.

        '''
        if not old_hostclass_dict:
            old_hostclass_dict = {"hostclass": DiscoBake.ami_hostclass(ami)}

        logging.info("Smoke testing non-deploy Hostclass %s AMI %s", old_hostclass_dict["hostclass"], ami.id)

        if dry_run:
            return

        new_size = desired_size * 2 if desired_size else 1
        new_hostclass_dict = copy.deepcopy(old_hostclass_dict)
        new_hostclass_dict["sequence"] = 1
        new_hostclass_dict["max_size"] = new_size
        new_hostclass_dict["min_size"] = new_size / 2
        new_hostclass_dict["desired_size"] = new_size
        new_hostclass_dict["smoke_test"] = "no"
        new_hostclass_dict["ami"] = ami.id
        rollback_hostclass_dict = copy.deepcopy(old_hostclass_dict)

        self._disco_aws.spinup([new_hostclass_dict], testing=True)

        rollback_hostclass_dict["sequence"] = 1
        rollback_hostclass_dict["smoke_test"] = "no"
        rollback_hostclass_dict["max_size"] = old_hostclass_dict.get("max_size", desired_size)
        rollback_hostclass_dict["min_size"] = old_hostclass_dict.get("min_size", desired_size)
        rollback_hostclass_dict["desired_size"] = old_hostclass_dict.get("desired_size", desired_size)
        rollback_hostclass_dict["desired_size"] = snap_to_range(
            rollback_hostclass_dict["desired_size"],
            rollback_hostclass_dict["min_size"], rollback_hostclass_dict["max_size"])

        if self.wait_for_smoketests(ami.id, desired_size or 1):
            self._promote_ami(ami, "tested")
            rollback_hostclass_dict["ami"] = ami.id
        else:
            self._promote_ami(ami, "failed")
            rollback_hostclass_dict.pop("ami", None)

        if rollback_hostclass_dict["desired_size"]:
            self._disco_aws.terminate(self._get_new_instances(ami.id), use_autoscaling=True)
            self._disco_aws.spinup([rollback_hostclass_dict])
        else:
            self._disco_aws.autoscale.delete_group(rollback_hostclass_dict["hostclass"], force=True)

    def _get_old_instances(self, new_ami_id):
        '''Returns instances of the hostclass of new_ami_id that are not running new_ami_id'''
        hostclass = DiscoBake.ami_hostclass(self._disco_bake.connection.get_image(new_ami_id))
        group_name = self._disco_aws.autoscale.get_groupname(hostclass)
        all_instance_ids = [inst.instance_id for inst in self._disco_aws.autoscale.get_instances()
                            if inst.group_name == group_name]
        all_instances = self._disco_aws.instances(instance_ids=all_instance_ids)
        return [inst for inst in all_instances if inst.image_id != new_ami_id]

    def _get_new_instances(self, new_ami_id):
        '''Returns instances running new_ami_id'''
        hostclass = DiscoBake.ami_hostclass(self._disco_bake.connection.get_image(new_ami_id))
        group_name = self._disco_aws.autoscale.get_groupname(hostclass)
        all_instance_ids = [inst.instance_id for inst in self._disco_aws.autoscale.get_instances()
                            if inst.group_name == group_name]
        return self._disco_aws.instances(filters={"image_id": [new_ami_id]}, instance_ids=all_instance_ids)

    def _get_latest_other_image_id(self, new_ami_id):
        '''
        Returns image id of latest currently deployed image other than the specified one.

        Returns None if none of the images currently deployed still exist.
        '''
        old_instances = self._get_old_instances(new_ami_id)
        deployed_ami_ids = list(set([instance.image_id for instance in old_instances]))
        images = []
        for ami_id in deployed_ami_ids:
            try:
                images.extend(self._disco_bake.get_amis(image_ids=[ami_id]))
            except EC2ResponseError as err:
                if err.code == "InvalidAMIID.NotFound":
                    logging.warning("Unable to find old AMI %s, it was probably deleted", ami_id)
                else:
                    raise
        return max(images, key=self._disco_bake.get_ami_creation_time).id if len(images) else None

    def run_tests_with_maintenance_mode(self, ami):
        '''
        Runs integration tests for a hostclass beloning to a particular AMI.

        This method puts all AMIs not matching the passed in AMI into maintenance mode.
        If tests pass the old instances are left in maintenance mode, otherwise they are returned to normal.
        '''
        hostclass = DiscoBake.ami_hostclass(ami)
        self._set_maintenance_mode(hostclass, self._get_old_instances(ami.id), True)
        ret = self.run_integration_tests(ami)
        if not ret:
            self._set_maintenance_mode(hostclass, self._get_old_instances(ami.id), False)
        return ret

    def handle_tested_ami(self, old_hostclass_dict, ami, desired_size,
                          run_tests=False, dry_run=False):
        '''
        Tests hostclasses which we can deploy normally

        If hosts running the new AMI pass tests we use that host going forward,
        otherwise we roll back to the previous AMI.

        '''
        logging.info("testing deployable hostclass %s AMI %s", old_hostclass_dict["hostclass"], ami.id)

        if dry_run:
            return

        if desired_size and run_tests and not self.run_integration_tests(ami):
            raise Exception("Failed pre-test -- not testing AMI {}".format(ami.id))

        new_size = desired_size * 2 if desired_size else 1
        new_hostclass_dict = copy.deepcopy(old_hostclass_dict)
        new_hostclass_dict["sequence"] = 1
        new_hostclass_dict["max_size"] = new_size
        new_hostclass_dict["min_size"] = new_size / 2
        new_hostclass_dict["desired_size"] = new_size
        new_hostclass_dict["smoke_test"] = "no"
        new_hostclass_dict["ami"] = ami.id
        post_hostclass_dict = copy.deepcopy(new_hostclass_dict)

        self._disco_aws.spinup([new_hostclass_dict])

        try:
            if (self.wait_for_smoketests(ami.id, desired_size or 1) and
                    (not run_tests or self.run_tests_with_maintenance_mode(ami))):
                # Roll forward with new configuration
                post_hostclass_dict["max_size"] = old_hostclass_dict.get("max_size") or desired_size
                post_hostclass_dict["min_size"] = old_hostclass_dict.get("min_size") or desired_size
                post_hostclass_dict["desired_size"] = snap_to_range(
                    desired_size, post_hostclass_dict["min_size"], post_hostclass_dict["max_size"])
                self._disco_aws.terminate(self._get_old_instances(ami.id), use_autoscaling=True)
                self._disco_aws.spinup([post_hostclass_dict])
                self._promote_ami(ami, "tested")
                return
            else:
                self._promote_ami(ami, "failed")
        except (MaintenanceModeError, IntegrationTestError):
            logging.exception("Failed to run integration test")

        # Revert to old configuration
        post_hostclass_dict = copy.deepcopy(old_hostclass_dict)
        post_hostclass_dict["max_size"] = old_hostclass_dict.get("max_size") or desired_size
        post_hostclass_dict["min_size"] = old_hostclass_dict.get("min_size") or desired_size
        post_hostclass_dict["desired_size"] = snap_to_range(
            desired_size, post_hostclass_dict["min_size"], post_hostclass_dict["max_size"])
        post_hostclass_dict["smoke_test"] = "no"

        # Revert to the latest tested AMI if possible
        old_ami_id = self._get_latest_other_image_id(ami.id)
        if old_ami_id:
            post_hostclass_dict["ami"] = old_ami_id
        else:
            logging.error("Unable to rollback to old AMI. Autoscaling group will use new AMI on next event!")

        self._disco_aws.terminate(self._get_new_instances(ami.id), use_autoscaling=True)
        self._disco_aws.spinup([post_hostclass_dict])

    def _set_maintenance_mode(self, hostclass, instances, mode_on):
        '''
        Takes instances into or out of maintenance mode.


        If we fail to put an instance into the desired mode we terminate that instance
        and raise a MaintenanceModeError exception.
        '''
        exit_code = 0
        bad_instances = []
        for inst in instances:
            _code, _stdout = self._disco_aws.remotecmd(
                inst, ["sudo", "/opt/wgen/bin/maintenance-mode.sh", "on" if mode_on else "off"],
                user=self.hostclass_option(hostclass, "test_user"), nothrow=True)
            sys.stdout.write(_stdout)
            if _code:
                exit_code = _code
                bad_instances.append(inst)
        if exit_code:
            self._disco_aws.terminate(bad_instances)
            raise MaintenanceModeError(
                "Failed to {} maintenance mode".format("enter" if mode_on else "exit"))

    def get_host(self, hostclass):
        '''Returns an instance to use for running integration tests'''
        instances = self._test_aws.instances_from_hostclasses([hostclass])
        for inst in instances:
            try:
                self._disco_aws.smoketest_once(inst)
            except TimeoutError:
                continue
            return inst
        raise IntegrationTestError("Unable to find test host")

    def run_integration_tests(self, ami):
        '''
        Runs integration tests for the hostclass belonging to the passed in AMI

        NOTE: This does not put any instances into maintenance mode.
        '''
        hostclass = DiscoBake.ami_hostclass(ami)
        test_hostclass = self.hostclass_option(hostclass, "test_hostclass")
        test_command = self.hostclass_option(hostclass, "test_command")
        test_user = self.hostclass_option(hostclass, "test_user")
        test_name = self.get_integration_test(hostclass)
        logging.info("running integration test %s on %s", test_name, test_hostclass)
        exit_code, stdout = self._test_aws.remotecmd(
            self.get_host(test_hostclass), [test_command, test_name],
            user=test_user, nothrow=True)
        sys.stdout.write(stdout)
        return exit_code == 0

    def test_ami(self, ami, dry_run):
        '''Handles testing and promoting a new AMI for a hostclass'''
        logging.info("testing %s %s", ami.id, ami.name)
        hostclass = DiscoBake.ami_hostclass(ami)
        old_hostclass_dict = self._hostclasses.get(hostclass)
        group = self._disco_aws.autoscale.get_existing_group(hostclass)
        desired_capacity = group.desired_capacity if group else 0
        if not self.is_deployable(hostclass):
            self.handle_nodeploy_ami(
                old_hostclass_dict, ami, desired_capacity, dry_run=dry_run)
        elif self.get_integration_test(hostclass):
            self.handle_tested_ami(
                old_hostclass_dict, ami, desired_capacity, run_tests=True, dry_run=dry_run)
        elif old_hostclass_dict:
            self.handle_tested_ami(
                old_hostclass_dict, ami, desired_capacity, dry_run=dry_run)
        else:
            self.handle_nodeploy_ami(None, ami, 0, dry_run=dry_run)

    def update_ami(self, ami, dry_run):
        '''Handles updating a hostclass to the latest tested AMI'''
        logging.info("updating %s %s", ami.id, ami.name)
        hostclass = DiscoBake.ami_hostclass(ami)
        old_hostclass_dict = self._hostclasses.get(hostclass)
        if not old_hostclass_dict:
            return

        group = self._disco_aws.autoscale.get_existing_group(hostclass)
        desired_capacity = group.desired_capacity if group else old_hostclass_dict.get("desired_size", 0)

        if not self.is_deployable(hostclass):
            self.handle_nodeploy_ami(old_hostclass_dict, ami, desired_capacity, dry_run=dry_run)
        else:
            self.handle_tested_ami(old_hostclass_dict, ami, desired_capacity, dry_run=dry_run)

    def test(self, dry_run=False):
        '''Tests a single untested AMI and marks it as tested or failed'''
        amis = self.get_test_amis()
        if len(amis):
            self.test_ami(random.choice(amis), dry_run)

    def update(self, dry_run=False):
        '''Updates a single autoscaling group with a newer AMI'''
        amis = self.get_update_amis()
        if len(amis):
            self.update_ami(random.choice(amis), dry_run)

    def hostclass_option(self, hostclass, key):
        '''
        Returns an option from the [hostclass] section of the disco_aws.ini config file if it is set,
        otherwise it returns that value from the [test] section if it is set,
        minus that prefix, otherwise it returns that value from the DEFAULT_CONFIG_SECTION if it is set.
        '''
        alt_key = key.split("test_").pop()
        if self._config.has_option(hostclass, key):
            return self._config.get(hostclass, key)
        elif self._config.has_option("test", key):
            return self._config.get("test", key)
        elif alt_key != key and self._config.has_option("test", alt_key):
            return self._config.get("test", alt_key)
        else:
            return self._config.get(DEFAULT_CONFIG_SECTION, "default_{0}".format(key))

    def hostclass_option_default(self, hostclass, key, default=None):
        """Fetch a hostclass configuration option if it exists, otherwise return value passed in as default"""
        try:
            return self.hostclass_option(hostclass, key)
        except NoOptionError:
            return default
