#!/bin/sh
# This client speaks only the explicit infra harness protocol, not the real API.
set -u
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for candidate in "${FORTRESS_PYTHON:-}" python3 python; do
  if [ -n "$candidate" ] && command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import json,sys' >/dev/null 2>&1; then
    exec "$candidate" "$script_dir/../smoke_server.py" client "$@"
  fi
done
printf '%s\n' '{"status":"blocked","reason":"No working Python recorder","external_access_verified":false}'
exit 2
