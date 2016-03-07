#!/bin/bash
# source this script to get your host's user data as env vars

file=$(mktemp)
if curl -sfS http://169.254.169.254/latest/user-data > "$file"; then
    # we could cache the result since user data is immutable, but if we do we'd have
    # to be careful about not allowing anything to modify the cache
    source "$file"
else
    echo "user data could not be loaded: see error message above" >&2
fi
rm -f "$file"  # don't trap-exit this; script might be sourced by a long-running process
