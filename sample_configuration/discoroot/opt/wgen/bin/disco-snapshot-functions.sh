#!/bin/bash
# Some functions to extract snapshot metadata
source "$(dirname ${BASH_SOURCE[0]})/aws-utility-functions.sh"

# The instance identity document contains dynamically generated
# metadata:
# http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/AESDG-chapter-instancedata.html#dynamic-data-categories
# It may not be available for all combinations of ami and region:
# http://stackoverflow.com/questions/4249488/find-region-from-within-ec2-instance
# If so, we can fall back to getting the availability zone from the
# metadata instead and chopping off the last character to get the
# region.
export AWS_DEFAULT_REGION=$(get_instance_identity_attribute region)

function get_volume_description() {
  # Echo the volume description for the given device name
  local device_name=$1

  local instance_id=$(get_metadata_attribute instance-id) || return 1
  aws ec2 describe-volumes \
    --filters Name="attachment.device",Values="$device_name" \
              Name="attachment.instance-id",Values="$instance_id"
}

function get_snapshot_description() {
  # Echo the snapshot description for the snapshot with the given id
  local snapshot_id=$1

  aws ec2 describe-snapshots \
    --filters Name="snapshot-id",Values="$snapshot_id"
}
