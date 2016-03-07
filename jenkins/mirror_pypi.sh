#!/bin/bash

MAX_FAILURES=15  # it is not unusual for pypi to timeout or return 503s on many packages during a successful run :(

VENV_DIRECTORY=$WORKSPACE/venv

if [[ ! -d ${VENV_DIRECTORY} ]]; then
    /opt/wgen-3p/python27/bin/virtualenv --no-site-packages ${VENV_DIRECTORY}
fi

source ${VENV_DIRECTORY}/bin/activate

# install the latest bandersnatch
pip install --upgrade bandersnatch
ERROR_UPGRADE="$?"

# Run bandersnatch to mirror
bandersnatch mirror 2>&1 | tee log.txt

# Note: it is normal for some packages to fail to mirror (people don't always push their packages correctly).
# When a packages fails for us, it is failing for everyone so the author usually fixes the problem
# within 24h. However, we don't want failure notifications each time a pypi author messes up,
# so we only exit 1 if a large number of packages fail.
# We also ignore any "Stale serial" errors, which are actually warnings and not errors.
ERROR_COUNT=$(grep ERROR log.txt | grep -v "ERROR: Stale serial" | wc -l)
echo "Error Count: $ERROR_COUNT"

if [[ "$ERROR_COUNT" -gt "$MAX_FAILURES" ]] ; then
    echo "Mirroring Failure: too many packages failed"
    exit 1
fi

if [[ "$ERROR_UPGRADE" != "0" ]] ; then
    echo "Failed to update bandersnatch to latest"
    exit 1
fi
