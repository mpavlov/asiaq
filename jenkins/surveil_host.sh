#!/bin/bash -e

# This script reports on as much info as it can gather about an AWS host.
#
# Note that due to the abundance of stdout and stderr output of info-gathering
# commands below, it is virtually impossible to modularize the code into
# functions that cleanly pass parameters to each other.

source jenkins/boto_init.sh

function usage() {
  # print usage and exit
  echo "$0 <env> <hostname>"
  exit 1
}

function error() {
  # print error message and exit
  local message="$1"
  echo "Error: $message" >&2
  exit 2
}

function echo_section() {
  # print an easily visible section heading, suitable to being surrounded by a sea of debug output
  local section_name="$1"
  local repeat=$((${#section_name} + 8))
  printf "\n"
  printf "#%.0s" $(seq $repeat)
  printf "\n### $section_name ###\n"
  printf "#%.0s" $(seq $repeat)
  printf "\n\n"
}

function are_we_on_jenkins() {
  # print 'yes' if this code is running on mhcdiscojenkins, else print 'no'
  [[ "$(cat /opt/wgen/etc/hostclass 2> /dev/null)" == "mhcdiscojenkins" ]] && echo "yes" || echo "no"
}

function get_jenkins_build_output() {
  # curls the jenkins build url for a given component and prints the console output
  local component_name="$1"
  local build_number="$2"
  local jenkins_host=$([[ "$(are_we_on_jenkins)" == "yes" ]] && echo "localhost" || echo "couldntfindhost")
  local jenkins_build_url="https://${jenkins_host}/jenkins/job/${main_package_name}-future-BUILD/${main_package_build}/consoleFull"

  build_output=$(curl -L -k -s "$jenkins_build_url")
  build_has_errors=$(echo -e "$build_output" | grep "<title>Error 404 Not Found</title>" || true)
  [[ "$build_has_errors" ]] && error "Failed to get build info at: $jenkins_build_url"

  echo -e "$build_output"
}

function main() {
  local environment="$1"
  local hostname="$2"

  echo_section "Querying AWS"
  echo "Getting instance info"
  local host_tuple=( $(disco_aws.py --env $environment listhosts --all | grep " $hostname " || true) )
  [[ "${host_tuple[@]}" == "" ]] && error "Hostname not found: $hostname"

  instance_id=${host_tuple[0]}
  instance_hostclass=${host_tuple[1]}
  instance_ip=${host_tuple[2]}
  instance_state=${host_tuple[3]}
  instance_hostname=${host_tuple[4]}
  instance_owner=${host_tuple[5]}
  instance_type=${host_tuple[6]}
  instance_ami=${host_tuple[7]}
  instance_packages="${host_tuple[8]}"
  instance_private_ip=${host_tuple[9]}

  echo "Getting installed packages info"
  _instance_packages_array=( ${instance_packages//,/ } )
  main_package=${_instance_packages_array[0]}
  _main_package_array=( ${main_package//-/ } )
  main_package_name=${_main_package_array[0]}
  main_package_version=${_main_package_array[1]}
  main_package_build=${_main_package_array[2]}

  echo_section "Querying Jenkins"
  build_output=$(get_jenkins_build_output "$main_package_name" "$main_package_build")

  echo "Getting build info"
  git_commit_hash=$(echo -e "$build_output" | egrep -o "^Checking out Revision .*$" | egrep -o "[0-9a-f]{40}" | sort | uniq)
  git_repo_url=$(echo -e "$build_output" | egrep -o "^Fetching upstream changes from .*$" | egrep -o "git@.*:.*" | sort | uniq)
  git_repo_name=$(echo "$git_repo_url" | egrep -o "@.*:.*" | egrep -o "[^/]*$" | sed "s/.git$//g")

  echo_section "Querying Git"
  if [[ "$(are_we_on_jenkins)" == "no" ]]; then
    echo "Getting git server address"
    git_hostname=$(echo "$git_repo_url" | egrep -o "git[0-9]{1,9}")
    git_server_ip=$(disco_aws.py --env build listhosts --hostname | grep " $git_hostname " | awk '{print $3}')
    git_repo_url=${git_repo_url//$git_hostname/$git_server_ip}
  fi

  echo "Cloning $git_repo_url"
  tmpdir=$(mktemp -d /tmp/inspect.XXXXXX)
  trap "rm -rf $tmpdir" EXIT
  git clone --quiet "$git_repo_url" "$tmpdir"
  cd $tmpdir

  echo "Getting git commit info"
  git_commit_author=$(git show -s $git_commit_hash | grep Author | cut -d " " -f2-)
  git_commit_message_short=$(git show -s --pretty=oneline $git_commit_hash | cut -d " " -f2-)
  _git_commit_merge=$(git log ${git_commit_hash}~1..HEAD --pretty=oneline --abbrev-commit --merges | tail -n 1)
  git_commit_was_direct_to_master=$([[ "$_git_commit_merge" == "" ]] && echo "yes" || echo "no")

  if [[ "$git_commit_was_direct_to_master" == "no" ]]; then
    echo "Getting pull request info"
    pull_request_number=$(echo "$_git_commit_merge" | egrep -o "Merge pull request #[0-9]{1,9} " | egrep -o "[0-9]{1,9}")
    pull_request_source_branch=$(echo "$_git_commit_merge" | egrep -o "[^ ]*$")
    pull_request_url="https://$GITHUB_URL/Disco/${git_repo_name}/pull/${pull_request_number}"
    # this is as far as we go without adding LDAP authentication
  else
    pull_request_url="n/a"
  fi

  echo_section "Surveillance report on $hostname"
  for var in $(compgen -v | egrep "^instance_|^git_|^pull_request_|^main_package"); do
    echo "${var}: ${!var}"
  done
  echo
}

[[ $# != 2 ]] && usage
main $*
