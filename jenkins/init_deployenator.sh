#!/bin/bash

set -ex

function usage() {
    echo "Initialize deployenator EBS volume"
    echo "Usage: $0 environmnent size"
    exit 1
}

if [ "$#" != "2" ]; then
    usage
fi

source "$(dirname $0)/boto_init.sh" $1

ENV_NAME=$1
SIZE=$2
MAX_ATTEMPTS=3

DISCO_AWS="disco_aws.py"

i=0;
while [ "$i" -lt "$MAX_ATTEMPTS" ]; do
    $DISCO_AWS --env $ENV_NAME createsnapshot --size $SIZE --hostclass mhcdiscodeployenator && break
    i=$((i+1))
done

if [ "$i" -lt "$MAX_ATTEMPTS" ]; then
    exit 0
else
    exit 1
fi