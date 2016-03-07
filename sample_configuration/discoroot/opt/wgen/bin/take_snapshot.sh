#!/bin/bash

source "/etc/init.d/disco-storage-functions.sh"
source "$(dirname ${BASH_SOURCE[0]})/disco-snapshot-functions.sh"
source "$(dirname ${BASH_SOURCE[0]})/user-data.sh"

device_name="/dev/sdb"
volume_description=$(get_volume_description $device_name)
snapshot_id=$(echo "$volume_description" | jq -r '.Volumes[0].SnapshotId')
snapshot_description=$(get_snapshot_description "$snapshot_id")
hostclass_line=$(echo $snapshot_description | grep '"Key": "hostclass"')

# If the snapshot isn't tagged with a hostclass, the associated volume isn't
# local
if [[ $hostclass_line == "" ]]; then
  echo >&2 "No local volume found.  Aborting snapshot"
  exit 1
fi

local_device_name=$(find_non_root_ebs_volumes)
mount_point=$(get_mount_point $local_device_name)

if [[ $mount_point == "" ]]; then
    echo "Volume not mounted.  No need to freeze."
else
    sync
    trap "xfs_freeze -u $mount_point" EXIT
    xfs_freeze -f $mount_point
    if [[ "$?" != "0" ]] ; then
        echo >&2 "Volume $local_device_name is not freezable. Aborting."
        exit 2
    fi
fi

instance_id=$(get_metadata_attribute instance-id)
volume_id=$(echo "$volume_description" | jq -r '.Volumes[0].VolumeId')
snapshot_output=$(aws ec2 create-snapshot --volume-id "$volume_id")
new_snapshot_id=$(echo "$snapshot_output" | jq -r '.SnapshotId')

# We don't distinguish between snapshot_output missing the key 'SnapshotId' (in
# which case jq will return null) and the actual snapshot id being null.  In
# practice it doesn't matter, since both cases indicate something's gone badly
# wrong.
if [[ $new_snapshot_id == "null" ]]; then
  echo >&2 "Snapshot failed with output:"
  echo >&2 "$snapshot_output"
  exit 3
fi

echo "Created snapshot $new_snapshot_id from volume $volume_id on instance $instance_id"

aws ec2 create-tags --resources $new_snapshot_id \
                    --tags Key="hostclass",Value="$hostclass" Key="env",Value="$environment_name"
if [[ "$?" != "0" ]]; then
    echo >&2 "Failed to tag $new_snapshot_id with hostclass $hostclass"
    exit 4
fi

export ASIAQ_CONFIG=/opt/wgen/discoaws/
export ASIAQ_PATH=/opt/wgen/asiaq/bin
export BOTO_CONFIG=/opt/wgen/asiaq/bin/base_boto.cfg

$ASIAQ_PATH/disco_snapshot.py --env $environment_name update --hostclass $hostclass
if [[ "$?" != "0" ]]; then
    echo >&2 "Updating autoscaling group to use latest snapshot failed"
    exit 5
fi
