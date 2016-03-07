#!/bin/bash

set -ex

function usage() {
    echo "Stop all instances and destroy envionment."
    echo "Usage: $0 environment"
    exit 1
}

if [ "$#" != "1" ]; then
    usage
fi

source "$(dirname $0)/boto_init.sh" $1

ENV_NAME=$1
MAX_ATTEMPTS=${2:-1}

DISCO_VPC="disco_vpc_ui.py"

i=0;
while [ "$i" -lt "$MAX_ATTEMPTS" ]; do
    $DISCO_VPC --debug destroy --name $ENV_NAME && break
    i=$((i+1))
done

if [ "$i" -lt "$MAX_ATTEMPTS" ]; then
    exit 0
else
    exit 1
fi
