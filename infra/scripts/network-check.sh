#!/bin/sh
# Inventory/TLS observation only; independent upload/status smoke belongs to O3.
set -u
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec sh "$script_dir/preflight.sh" --network-only "$@"
