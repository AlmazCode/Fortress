#!/bin/sh
# Actual API client. No service startup, model loading or virtualization.
set -u
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for candidate in "${FORTRESS_PYTHON:-}" python3 python; do
  if [ -n "$candidate" ] && command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys,jsonschema,referencing; assert sys.version_info[:2] == (3,11)' >/dev/null 2>&1; then
    exec "$candidate" "$script_dir/../../tests/performance/benchmark.py" "$@"
  fi
done
printf '%s\n' '{"status":"blocked","reason":"Python 3.11 with the locked application dependencies is required","external_access_verified":false}'
exit 2
