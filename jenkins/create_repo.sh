#!/bin/bash
##
# Update the rpm repository metadata
##

set -ex

repo_path="/opt/wgen/build/repos/"

for dir in `find "$repo_path" -maxdepth 1 -mindepth 1 -type d`; do
    createrepo --update "$dir" &
done

wait
