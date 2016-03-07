#! /bin/false #This file is for sourcing
# vim: ts=4 sw=4 et filetype=sh

function find_root_block_device_mapping() {
    # find out AWS root block device type
    # it should return either block type like "ami", "ebs" for root volume,
    local AWS_ENDPOINT="http://169.254.169.254/2014-02-25/meta-data/block-device-mapping/"
    local root_device_id=$(curl -s $AWS_ENDPOINT/root)
    local block_device_mapping=$(curl -s $AWS_ENDPOINT|sed -e "/root/d" -e "/swap/d")
    local volume_devices=$(for i in $block_device_mapping; do echo "$i"_$(curl -s $AWS_ENDPOINT/$i); done)
    for i in $volume_devices;
    do
        local dev_id=$(echo $i|cut -d "_" -f2)
        if [[ $root_device_id == *"$dev_id"* ]];
        then
            echo $i|cut -d "_" -f1
        fi
    done
}

function find_volume() {
    # find out all block device ids under Xen for AWS ephemeral volumes
    # We assume the order of http://169.254.169.254/2014-02-25/meta-data/block-device-mapping/$volume
    # is in the same order as xvd block device order.
    # but if it starts to mismatched, We need to rewrite this code
    # by review results from http://169.254.169.254/2014-02-25/meta-data/block-device-mapping/$volume
    local volume_type=$1 # volumne type, must be "ephemeral" or "ebs" to be usable
    local root_flag=$2 # "include_root_volume" to match root ebs, "exclude_root_volume" to exclude root ebs
    local root_block_mapping=$(find_root_block_device_mapping) # "volume type reserved for disco root partition"

    local AWS_ENDPOINT="http://169.254.169.254/2014-02-25/meta-data/block-device-mapping/"
    local volume_type_list=($(for i in $(curl -s $AWS_ENDPOINT|sed -e "/root/d" -e "/swap/d"); do echo $i $(curl -s $AWS_ENDPOINT$i) ; done|sort -k2|cut -d " " -f1))
    local device_ids=($(lsblk -dn|cut -d " " -f 1|sort))

    # both lists should match in number of items
    if ((  "${#volume_type_list[@]}" ==  "${#device_ids[@]}" ));
    then
        for i in ${!device_ids[@]};
            do
            if [[ "${volume_type_list[$i]}" =~ "${volume_type}" ]];
            then
                if [[ "$root_flag" == "include_root_volume"  ]];
                then
                    if [[ "${volume_type_list[$i]}" == "${root_block_mapping}" ]];
                    then
                        echo "/dev/${device_ids[$i]}";
                    fi
                else
                    if [[ "${volume_type_list[$i]}" != "${root_block_mapping}" ]];
                    then
                        echo "/dev/${device_ids[$i]}";
                    fi
                fi
            fi
        done
    fi
}


function find_all_ephemeral_volumes() {
    # find out all block device ids under Xen for AWS ephemeral volumes
    find_volume "ephemeral" "exclude_root_volume"
}

function find_non_root_ebs_volumes() {
    # find out all block device ids under Xen for AWS EBS volumne that are not our root EBS volumes
    find_volume "ebs" "exclude_root_volume"
}

function find_root_volume() {
   # find out the root partition block device under linux
   # it should be something like /dev/xvda1, /dev/sdb or whatever
   local disk=$(df /|tail -n 1|cut -d ' ' -f 1)
   echo "$disk"
}

function create_ephemeral_encrypted_volume() {
    # This function accepts the base device and target directory as
    # parameters and encrypts the device, formats it as xfs and then
    # mounts it on the target directory.
    #
    # If a pre_mount function is defined it is called with the name of
    # the encrypted device and the name of the target directory before
    # the device is mounted but after it is formatted.
    #
    # If a post_mount function is defined it is called with the name of
    # the encrypted device and the name of the target directory after
    # the device is mounted on the target directory

    local base_dev="$1"
    local target_dir="$2"

    local volume_name="volume0"

    # create temporary key in memory
    local mem_dir=$(mktemp -d --tmpdir=/tmp)
    mount -o size=1m -t tmpfs tmpfs "$mem_dir"
    chmod go-rwxt "$mem_dir"
    local key_file="$mem_dir/keyfile.enc"
    umask 0077
    dd bs=512 count=1 if=/dev/urandom of="$key_file"

    # format raw volume with LUKS data
    cryptsetup --batch-mode --cipher aes-cbc-essiv:sha256 --key-size 256 --iter-time 100 \
               --use-random luksFormat "$base_dev" --key-file "$key_file"

    # map the volume and delete the temporary key
    cryptsetup luksOpen "$base_dev" "$volume_name" --key-file "$key_file"
    umount "$mem_dir"
    rm -rf "$mem_dir"

    local enc_vol="/dev/mapper/$VOL_NAME"
    if [ -b $enc_vol ] ; then
        if [[ "$(grep -c $enc_vol /etc/fstab)" == "0" ]] ; then
            mkfs.xfs $enc_vol

            [ "`type -t pre_mount`"  = "function" ] && \
                pre_mount $enc_vol $target_dir

            # Add to fstab & mount the volume
            echo "$enc_vol $target_dir xfs defaults 0 0" >> /etc/fstab
            mount -a

            [ "`type -t post_mount`"  = "function" ] && \
                post_mount $enc_vol $target_dir
         fi
    fi

    return 0
}

function create_ephemeral_volume() {
    # This function accepts the block device and target directory as
    # parameters and formats the device as xfs and then mounts it on
    # the target directory.
    #
    # If a pre_mount function is defined it is called with the name of
    # the base device and the name of the target directory before
    # the device is mounted but after it is formatted.
    #
    # If a post_mount function is defined it is called with the name of
    # the base device and the name of the target directory after
    # the device is mounted on the target directory

    local dev="$1"
    local target_dir="$2"

    mkfs.xfs -f $dev

    [ "`type -t pre_mount`"  = "function" ] && pre_mount $dev $target_dir

    # Add to fstab & mount the volume
    echo "$dev $target_dir xfs defaults 0 0" >> /etc/fstab
    mount -a

    [ "`type -t post_mount`"  = "function" ] && post_mount $dev $target_dir

    return 0
}

function raid0_devices()
{
    # RAIDs devices together, assumes at least one device is passed in
    # param 1 raid device to create
    # 1 to 24 devices may in subsequent params

    local raid_dev="$1"
    shift
    declare -a devs=($@)

    if [[ ${#devs[@]} > 1 ]] ; then
        yes | mdadm --create --force --verbose "$raid_dev" --level=raid0 \
            --raid-devices=${#devs[@]} \
             $(printf "%s " ${devs[@]}) &> /dev/null
        echo "$raid_dev"
    else
        echo "$devs"
    fi
}

function remove_from_fstab() {
    # Removes device from fstab given either the device or target directory
    # Param device to remove or target directory

    local dev_or_target="$1"
    local tmp_file=$(mktemp)
    cat /etc/fstab | grep -v "^$dev_or_target" > $tmp_file
    mv $tmp_file /etc/fstab

    local tmp_file=$(mktemp)
    cat /etc/fstab | grep -v " $dev_or_target " > $tmp_file
    mv $tmp_file /etc/fstab
}

function is_device_freezable() {
  # Check if the given device is formatted with a freezable filesystem, aka
  # XFS/ext3/ext4
  local device_name=$1

  local file_output=$(
    file --special-file --dereference $device_name | egrep '(XFS|ext3|ext4)'
  )

  if [[ $file_output == "" ]]; then
    >&2 echo "$device_name isn't freezable.  Must be XFS/ext3/ext4 formatted."
    return 1
  fi
}

function get_mount_point() {
  # Echo the mount point for the given device
  local device_name=$1

  mount -l | grep "$device_name" | awk '{print $3}'
}
