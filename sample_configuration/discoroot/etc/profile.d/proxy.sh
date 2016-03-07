# Convenience function to reset proxies without having
# to manually unset all the environment vars.
function unproxy {
    unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
}

# Enable proxy only if proxy entry exists in /etc/hosts
if [[ "$(getent hosts s3proxy)" != "" ]]; then
    export HTTP_PROXY='http://s3proxy:80'
    export HTTPS_PROXY='http://s3proxy:80'
    export NO_PROXY='169.254.169.254,localhost'

    export http_proxy="$HTTP_PROXY"
    export https_proxy="$HTTPS_PROXY"
    export no_proxy="$NO_PROXY"
fi
