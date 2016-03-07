#!/bin/bash
#
# Pushes the local documentation to the docs S3 bucket.
# Should be run periodically, ideally after each build of an egg,
# or at worst daily.
#
# Note that this script must be run by a user or role (such as disco_jenkins.iam)
# with appropriate permissions on the documentation S3 bucket.
set -e

function print_help() {
    echo "Usage: sync_docs.sh [region]"
    echo "  [region] is the AWS region in which the docs bucket exists (default: us-west-2)"
    echo "  Requires the DOCUMENTATION_BASE env variable to be set."
}

if [[ "$1" == "help" || "$1" == "-h" || "$1" == "--help" ]] ; then
    print_help
    exit 1
fi
if [ -z $DOCUMENTATION_BASE ]; then
    print_help
    exit 1
fi

REGION="${1:-us-west-2}"
DOCS_BUCKET_NAME="disco-docs.mc.wgenhq.net"

aws s3 cp --region "$REGION" --recursive "$DOCUMENTATION_BASE" "s3://${DOCS_BUCKET_NAME}"
