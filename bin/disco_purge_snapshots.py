#!/usr/bin/env python
"""
Disco Snapshot Purger.

When AMIs are created or Volumes are copied AWS creates an object called a
snapshot. It is a reference to the new volume. Deleting the corresponding
vsdolume does not delete the snapshot pointer and so they can build up.

This script cleans up snapshots that we no longer need. Including snapshots
that:
    - Created by CreateImage process but AMI is no longer available
    - have no tags

Usage:
    disco_purge_snapshots.py [options]

Options:
    -h --help       Show this screen.
    --debug         Log in debug level.
    --stray-ami     Purge only snapshots created by CreateImage
    --no-metadata   Purge only snapshots with no tags
    --old           Purge only old snapshots (100 days)
    --dry-run       Only print what will be done
"""

from __future__ import print_function
import re
from datetime import datetime
import logging
import sys

import boto
from boto.exception import EC2ResponseError
from docopt import docopt
import iso8601
import pytz

from disco_aws_automation.disco_aws_util import run_gracefully
from disco_aws_automation.disco_logging import configure_logging

OLD_IMAGE_DAYS = 100


def run():
    """
    Main
    """
    args = docopt(__doc__)

    configure_logging(args["--debug"])

    # If no options are set, we assume user wants all of 'em.
    arg_options = ["--stray-ami", "--no-metadata", "--old"]
    if not any([args[option] for option in arg_options if option in args]):
        for option in arg_options:
            args[option] = True

    _ignore, failed_to_purge = purge_snapshots(args)
    if failed_to_purge:
        sys.exit(1)


def purge_snapshots(options):
    """
    Purge snapshots we concider no longer worth keeping
    """
    ec2_conn = boto.connect_ec2()
    snap_pattern = re.compile(
        r"Created by CreateImage\(i-[a-f0-9]+\) for ami-[a-f0-9]+"
    )
    ami_pattern = re.compile(r"ami-[a-f0-9]+")
    now = datetime.now(pytz.UTC)

    images_by_id = {
        image.id: image for image in ec2_conn.get_all_images(owners=['self'])
    }

    snaps_to_purge = []
    failed_to_purge = []

    for snap in ec2_conn.get_all_snapshots(owner='self'):
        # Filter snaps which look like they are created with CreateImage
        if options["--stray-ami"] and snap_pattern.search(snap.description):
            image_id = ami_pattern.search(snap.description).group(0)
            # Delete Snaps for which ami no longer exists
            if image_id not in images_by_id:
                print("Deleting stray ami snapshot: {0}".format(snap.id))
                snaps_to_purge.append(snap)
                continue

        if options["--no-metadata"] and not snap.description and not snap.tags:
            print("Deleting no-metadata snapshot: {0}".format(snap.id))
            snaps_to_purge.append(snap)
            continue

        if options["--old"]:
            snap_date = iso8601.parse_date(snap.start_time)
            snap_days_old = (now - snap_date).days
            if snap_days_old > OLD_IMAGE_DAYS:
                print("Deleting old ({1} days) snapshot: {0}".format(
                    snap.id, snap_days_old))
                snaps_to_purge.append(snap)
                continue

        logging.debug("skipping snapshot: %s description: %s tags: %s", snap.id, snap.description, snap.tags)

    if not options["--dry-run"]:
        for snap in snaps_to_purge:
            try:
                snap.delete()
            except EC2ResponseError:
                failed_to_purge.append(snap)
                logging.error("Failed to purge snapshot: %s", snap.id)

    return (snaps_to_purge, failed_to_purge)

if __name__ == "__main__":
    run_gracefully(run)
