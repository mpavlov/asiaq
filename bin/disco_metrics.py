#!/usr/bin/env python
"""
Upload Cloudwatch metrics

Usage:
    disco_metrics.py [--debug] [--dummy] upload [--jitter SECONDS]
    disco_metrics.py (-h | --help)

Options:
    -h --help         Show this screen
    --debug           Log in debug level.
    --dummy           Log these metrics under a dummy instance (for testing)
    --jitter SECONDS  Wait up to the specified number of seconds before sending collected metrics

Commands:
    upload            Upload the metrics to Cloudwatch

Inspired by:
   https://gist.githubusercontent.com/shevron/6204349/raw/cw-monitor-memusage.py
"""

import time
import random

from docopt import docopt

from disco_aws_automation import DiscoMetrics
from disco_aws_automation.disco_aws_util import run_gracefully
from disco_aws_automation.disco_logging import configure_logging


def run():
    """Parses command line and dispatches the commands"""
    args = docopt(__doc__)

    configure_logging(args["--debug"])

    if args["upload"]:
        metrics = DiscoMetrics(dummy=args['--dummy'])
        metrics.collect()
        if args["--jitter"]:
            sleep_time = random.randrange(0, int(args.get("--jitter")))
            time.sleep(sleep_time)
        metrics.upload()


if __name__ == "__main__":
    run_gracefully(run)
