#!/usr/bin/python
"""
Associate an ENI with an instance

Usage:
    associate-eni.py (--region REGION) (--instance INSTANCE) IP...

This will associate the first available IP with this instance, or if none
are unattached it will steal one from another instance.
"""

import logging
import time
import boto
import boto.ec2
import random
from docopt import docopt

MAX_POLL_INTERVAL = 60  # seconds

def keep_trying(min_time, fun, *args, **kwargs):
    """
    Execute function fun with args and kwargs until it does
    not throw exception or min time has passed.

    After each failed attempt a delay is introduced of an
    increasing number seconds following the fibonacci series
    (up to MAX_POLL_INTERVAL seconds).
    """

    last_delay = 0
    curr_delay = 1
    expire_time = time.time() + min_time
    while True:
        try:
            return fun(*args, **kwargs)
        except Exception:
            if logging.getLogger().level == logging.DEBUG:
                logging.exception("Failed to run {0}.".format(fun))
            if time.time() > expire_time:
                raise
            time.sleep(curr_delay)
            delay_register = last_delay
            last_delay = curr_delay
            curr_delay = min(curr_delay + delay_register, MAX_POLL_INTERVAL)


def associate_eni(region, instance_id, ip_addresses):
    conn = boto.ec2.connect_to_region(region)
    instance = conn.get_only_instances(instance_ids=[instance_id])[0]

    all_enis = conn.get_all_network_interfaces(filters={"vpc-id": instance.vpc_id, "availability-zone": instance.placement})
    secondary_enis = [
        eni
        for eni in all_enis
        if eni.private_ip_address in ip_addresses
    ]

    if [
        eni
        for eni in secondary_enis
        if eni.attachment and eni.attachment.instance_id == instance.id
    ]:
        return  # nothing to do; already bound to us, or nothing to bind

    # Obtain an unattached ENI, detaching from another instance if necessary
    unattached_enis = [eni for eni in secondary_enis if eni.attachment is None]
    if not unattached_enis and secondary_enis:
        random_eni = random.choice(secondary_enis)
        conn.detach_network_interface(random_eni.attachment.id, force=True)
        unattached_enis = [random_eni]

    if not unattached_enis:
        raise Exception("No secondary ENIs available")

    # Allow sending traffic from secondary interface IP through primary interface.
    our_enis = [
        eni for eni in all_enis
        if eni.attachment and eni.attachment.instance_id == instance.id]
    # And allow second interface to spoof traffic, used by hosts talking to openswan
    our_enis.append(unattached_enis[0])
    for eni in our_enis:
        conn.modify_network_interface_attribute(eni.id, "sourceDestCheck", "false")

    keep_trying(60, conn.attach_network_interface, unattached_enis[0].id, instance.id, 1)

    with open('/etc/floating_ip', 'w+') as floating_ip_file:
        floating_ip_file.write(unattached_enis[0].private_ip_address)

if __name__ == "__main__":
    args = docopt(__doc__)

    associate_eni(args["REGION"], args["INSTANCE"], args["IP"])
