#!/bin/bash
# Source this script to get useful functions for fetching AWS metadata

AWS_METADATA_URL="http://169.254.169.254/latest/meta-data/"
INSTANCE_IDENTITY_URL="http://169.254.169.254/latest/dynamic/instance-identity/document"

function get_metadata_attribute() {
  local attribute=$1
  echo "$(curl --silent $AWS_METADATA_URL/$attribute)"
}

function get_instance_identity_attribute() {
  local attribute=$1
  # The installed version of jq doesn't support the fancy new ."key" syntax for
  # looking up keys with special characters.  So we have to use .["key"]
  # instead.
  curl --silent $INSTANCE_IDENTITY_URL | jq -r ".[\"${attribute}\"]"
#' <- this fools emacs shell script highlighting into doing the right thing
}

export AWS_DEFAULT_REGION=$(get_instance_identity_attribute region)
