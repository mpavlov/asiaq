#!/bin/bash

DISCO_AWS="disco_aws.py"
DISCO_BAKE="disco_bake.py"
DISCO_VPC="disco_vpc_ui.py"
LOG=$(mktemp /tmp/bake.XXXXXX)

usage() {
  echo "this script bakes your local hostclass changes onto an (untested) AMI,"
  echo "terminates old hostclasses and deploys that AMI in an env of your choice"
  echo
  echo "usage: $0 <env> <hostclass> [host_count] [phase1_ami]"
  exit 1
}

check_params() {
  (( $# < 2 )) && usage
}

check_env() {
  local env=$1
  local output=$($DISCO_VPC list | grep "\t$env$")
  [[ "$output" == "" ]] && echo "env not found: $env" && exit 1
}

bake() {
  local hostclass=$1
  local source_ami=$2
  [[ "$source_ami" != "" ]] && local source_ami_args="--source-ami $source_ami"
  echo "baking..." >&2
  $DISCO_BAKE bake --hostclass $hostclass $source_ami_args 2>&1 >> $LOG
  tail -n 1 $LOG | grep -o "ami-.*$"
}

terminate() {
  local env=$1
  local hostclass=$2
  echo "terminating..." >&2
  $DISCO_AWS --env $env terminate --hostclass $hostclass 2>&1 >> $LOG
}

provision() {
  local env=$1
  local ami=$2
  local host_count=$3
  for (( i=1; i<=$host_count; i++ )); do
    echo "provisioning $i of ${host_count}..." >&2
    $DISCO_AWS --env $env provision --ami $ami 2>&1 >> $LOG
  done
}

run() {
  echo "logging to $LOG"
  local env=$1
  local hostclass=$2
  local host_count=$3
  local phase1_ami=$4
  local ami=$(bake $hostclass $phase1_ami)
  [[ "$ami" == "" ]] && echo "ERROR: could not find baked AMI" && exit 1
  terminate $env $hostclass
  provision $env $ami $host_count
  #[[ $? == 0 ]] && rm -f $LOG  # uncomment this line if you feel this script is causing you to run out of space
}

check_params $*
check_env $1
run $*
