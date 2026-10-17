#!/bin/sh
# Validated TLS observation from this host; never an independent upload/status pass.
set -u
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec sh "$script_dir/preflight.sh" --network-only --probe-external --require-tls "$@"
