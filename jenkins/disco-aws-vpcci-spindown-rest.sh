#!/bin/bash

set -ex

# common macros
DISCO_VPC="disco_vpc_ui.py"
JENKINS_SCRIPT_DIR=$(dirname $0)
DRYRUN=0
FAILED_TO_SHUTDOWN=0

# list of ignored vpc, such as build and ci, they are shutdown separately

function get_list_of_shutdown_vpcs() {
	# find out any vpcs that are in AWS, excludes 'build' and 'ci'.
	echo -e $(${DISCO_VPC} list | cut -f 2 | grep -v "^build *$" | grep -v "^ci *$")
}

# display usage for the script
function usage() {
    echo "Stop all instances and destroy enviroments from developers"
    echo "Usage $0 [ --dryrun ]"
    exit 1
}

function main()
{

	if [[ "$#" -gt "1" ]]; then
    	usage
	fi

	# check dry run mode
	if [[ -n "$1" ]]; then
		if [[ "$1" == "--dryrun" ]]; then
	    	DRYRUN=1
    	else
	    	usage
    	fi
	fi

	# set up disco environment to run
	source "${JENKINS_SCRIPT_DIR}/boto_init.sh"

	# get list of vpcs spun up by devs
	local vpcs_to_shutdown=($(get_list_of_shutdown_vpcs))

	# shutdown extra environments
	for vpc_name in ${vpcs_to_shutdown[@]}
	do
		if [[ ${DRYRUN} == "1" ]]; then
			echo "Shutting down ${vpc_name}"
		else
	    	if (${JENKINS_SCRIPT_DIR}/disco_down.sh $vpc_name); then
	    		echo "Shutted down ${vpc_name}"
	    	else
	    		echo "Couldn't shutted down ${vpc_name}"
	        	FAILED_TO_SHUTDOWN=1
	   		fi
		fi
	done

	exit ${FAILED_TO_SHUTDOWN}
}

main
