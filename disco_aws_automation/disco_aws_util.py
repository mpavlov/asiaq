"""
Misc functions frequently used in disco_aws
"""

import logging
import sys

from boto.exception import EC2ResponseError

from .disco_constants import YES_LIST


class EasyExit(Exception):
    """
    Raise this exception to exit your program with a log message and a non-zero status, but no stack trace
    (assuming you are running it with run_gracefully).
    """
    pass


def is_truthy(value):
    """
    Return true if value resembles a affirmation
    """
    return value and value.lower() in YES_LIST


def run_gracefully(main_function):
    """
    Run a "main" function with standardized exception trapping, to make it easy
    to avoid certain unnecessary stack traces.

    If debug logging is switched on, stack traces will return.
    """
    try:
        main_function()
    except EasyExit as msg:
        logging.error(str(msg))
        sys.exit(1)
    except KeyboardInterrupt:
        # swallow the exception unless we turned on debugging, in which case
        # we might want to know what infinite loop we were stuck in
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            raise
        sys.exit(1)
    except EC2ResponseError as err:
        logging.error("EC2 Error response: %s", err.message)
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            raise
        sys.exit(1)


def size_as_recurrence_map(size, sentinel=''):
    """
    :return: dict, size as "recurrence" map. For example:
             - size = no value, will return: {<sentinel>: None}
             - size = simple int value of 5, will return: {<sentinel>: 5}
             - size = timed interval(s), like "2@0 22 * * *:24@0 10 * * *", will return: {'0 10 * * *': 24,
                                                                                          '0 22 * * *': 2}
    """
    if not size:
        return {sentinel: None}
    else:
        return {sentinel: int(size)} if str(size).isdigit() else {
            part.split('@')[1]: int(part.split('@')[0])
            for part in str(size).split(':')}


def size_as_minimum_int_or_none(size):
    """
    :return: int, max_size as max int or None. For example:
             - size = no value, will return: None
             - size = simple int value of 5, will return: 5
             - size = timed interval(s), like "2@0 22 * * *:24@0 10 * * *", will return: 2
    """
    return min(size_as_recurrence_map(size).values())


def size_as_maximum_int_or_none(size):
    """
    :return: int, max_size as max int or None. For example:
             - size = no value, will return: None
             - size = simple int value of 5, will return: 5
             - size = timed interval(s), like "2@0 22 * * *:24@0 10 * * *", will return: 24
    """
    return max(size_as_recurrence_map(size).values())
