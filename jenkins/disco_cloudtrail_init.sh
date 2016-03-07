#!/bin/bash -e

# Note that this script must be run by the account's root, or someone with "cloudtrail:*" IAM permissions

function print_help() {
    echo "The first parameter is the region to enable cloud trail for [us-west-1,us-east-1,etc]"
    echo "The second parameter is the account to enable cloud trail for [prod,dev,audit]"
}

if [[ "$1" == "-h" || "$1" == "--help" || "$2" == "" ]] ; then
    print_help
    exit 1
fi

REGION="$1"
ACCOUNT="$2"

BUCKET="$REGION.disco.audit.$ACCOUNT"

source "$(dirname $0)/boto_init.sh"

pip install awscli

aws cloudtrail --region $REGION create-subscription --s3-use-bucket $BUCKET --name "Default"
