#!/bin/bash

if [[ "$SSH_ORIGINAL_COMMAND" == "" ]] ; then
   /sbin/service disco-booted status
else
   IP="$(echo "$SSH_ORIGINAL_COMMAND" | /bin/egrep '^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$')"
   if [[ "$IP" != "" ]] ; then
      /usr/bin/ssh -oStrictHostKeyChecking=no -oUserKnownHostsFile=/dev/null -AT "smoketest@$IP"
   else
      echo "Unable to reach host $SSH_ORIGINAL_COMMAND"
      exit 10
   fi
fi