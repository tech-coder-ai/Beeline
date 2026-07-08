#!/bin/bash
# Wrapper around the apache/hive image entrypoint.
#
# Persists the embedded Derby metastore on a Docker volume and avoids re-running
# schematool -initSchema on every restart (which fails once the schema exists).
# Runs briefly as root so the hive user can write to the named volume mount.
set -e

METASTORE_ROOT=/opt/hive/metastore
mkdir -p "$METASTORE_ROOT"
chown -R hive:hive "$METASTORE_ROOT"

if [ -d "$METASTORE_ROOT/derby/seg0" ]; then
  export IS_RESUME=true
fi

exec runuser -u hive -- /entrypoint.sh
