#!/bin/bash

set -x

function usage() {
    echo "Create disco build environment and spinup"
    exit 1
}

source "$(dirname $0)/boto_init.sh"

DISCO_VPC="disco_vpc_ui.py"
DISCO_AWS="disco_aws.py"
ENV_NAME=build
ENV_TYPE=build
PIPELINE=build

function error() {
    echo "Encountered an error"
    echo "Destroying vpc $ENV_NAME"
    $DISCO_VPC destroy --name $ENV_NAME
    exit 1
}

trap error ERR
$DISCO_VPC create --type $ENV_TYPE --name $ENV_NAME
$DISCO_AWS --env $ENV_NAME spinup --pipeline pipelines/$PIPELINE/$PIPELINE.csv
