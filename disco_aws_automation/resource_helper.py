"""
This module has a bunch of functions about waiting for an AWS resource to become available
"""
import json
import logging
import time

import botocore
from boto.exception import EC2ResponseError, BotoServerError

from .exceptions import (
    TimeoutError,
    ExpectedTimeoutError,
    S3WritingError
)

STATE_POLL_INTERVAL = 2  # seconds
INSTANCE_SSHABLE_POLL_INTERVAL = 15  # seconds
MAX_POLL_INTERVAL = 60  # seconds


def handle_date_format(obj):
    def date_handler(item):
        return item.isoformat() if hasattr(item, 'isoformat') else item

    return json.loads(json.dumps(obj, default=date_handler))


def find_or_create(find, create):
    """Given a find and a create function, create a resource iff it doesn't exist"""
    result = find()
    if result:
        return result
    else:
        return create()


def keep_trying(max_time, fun, *args, **kwargs):
    """
    Execute function fun with args and kwargs until it does
    not throw exception or max time has passed.

    After each failed attempt a delay is introduced of an
    increasing number seconds following the fibonacci series
    (up to MAX_POLL_INTERVAL seconds).

    Note: If you are only concerned about throttling use throttled_call
    instead. Any irrecoverable exception within a keep_trying will
    cause a max_time delay.
    """

    last_delay = 0
    curr_delay = 1
    expire_time = time.time() + max_time
    while True:
        try:
            return fun(*args, **kwargs)
        except Exception:
            if logging.getLogger().level == logging.DEBUG:
                logging.exception("Failed to run %s.", fun)
            if time.time() > expire_time:
                raise
            time.sleep(curr_delay)
            delay_register = last_delay
            last_delay = curr_delay
            curr_delay = min(curr_delay + delay_register, MAX_POLL_INTERVAL)


def throttled_call(fun, *args, **kwargs):
    """
    Execute function fun with args and kwargs until it does
    not throw a throttled exception or 5 minutes have passed.

    After each failed attempt a delay is introduced of an
    increasing number seconds following the fibonacci series
    (up to MAX_POLL_INTERVAL seconds).
    """
    max_time = 5 * 60
    last_delay = 0
    curr_delay = 1
    expire_time = time.time() + max_time
    while True:
        try:
            return fun(*args, **kwargs)
        except (BotoServerError, botocore.exceptions.ClientError) as err:
            if logging.getLogger().level == logging.DEBUG:
                logging.exception("Failed to run %s.", fun)

            if isinstance(err, BotoServerError):
                error_code = err.error_code
            else:
                error_code = err.response['Error'].get('Code', 'Unknown')

            if (error_code != "Throttling") or (time.time() > expire_time):
                raise

            time.sleep(curr_delay)
            delay_register = last_delay
            last_delay = curr_delay
            curr_delay = min(curr_delay + delay_register, MAX_POLL_INTERVAL)


def wait_for_state(resource, state, timeout=15 * 60, state_attr='state'):
    """Wait for an AWS resource to reach a specified state"""
    time_passed = 0
    while True:
        try:
            resource.update()
            current_state = getattr(resource, state_attr)
            if current_state == state:
                return
            elif current_state in (u'failed', u'terminated'):
                raise ExpectedTimeoutError(
                    "{0} entered state {1} after {2}s waiting for state {3}"
                    .format(resource, current_state, time_passed, state))
        except EC2ResponseError:
            pass  # These are most likely transient, we will timeout if they are not

        if time_passed >= timeout:
            raise TimeoutError(
                "Timed out waiting for {0} to change state to {1} after {2}s."
                .format(resource, state, time_passed))

        time.sleep(STATE_POLL_INTERVAL)
        time_passed += STATE_POLL_INTERVAL


def wait_for_sshable(remotecmd, instance, timeout=15 * 60, quiet=False):
    """Returns True when host is up and sshable
    returns False on timeout
    """
    start_time = time.time()
    max_time = start_time + timeout

    if not quiet:
        logging.info("Waiting for instance %s to be fully provisioned.", instance.id)
    wait_for_state(instance, u'running', timeout)
    if not quiet:
        logging.info("Instance %s running (booting up).", instance.id)

    while True:
        logging.debug(
            "Waiting for %s to become sshable.", instance.id)
        if remotecmd(instance, ['true'], nothrow=True)[0] == 0:
            logging.info("Instance %s now SSHable.", instance.id)
            logging.debug("Waited %s seconds for instance to boot", int(time.time() - start_time))
            return
        if time.time() >= max_time:
            break
        time.sleep(INSTANCE_SSHABLE_POLL_INTERVAL)

    raise TimeoutError(
        "Timed out waiting for instance {0} to become sshable after {1}s."
        .format(instance, timeout))


def check_written_s3(object_name, expected_written_length, written_length):
    """Check S3 object is written by checking the bytes_written from key.set_contents_from_* method
    Raise error if any problem happens so we can diagnose the causes
    """
    if expected_written_length != written_length:
        raise S3WritingError(
            "{0} is not written correctly to S3 bucket".format(object_name)
        )
