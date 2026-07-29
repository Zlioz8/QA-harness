#!/bin/bash
# Restore the platform baseline into the ephemeral database.
#
# Runs from the postgres image's /docker-entrypoint-initdb.d, which executes ONLY when the data
# directory is empty. So a `make up` on a fresh volume restores; a restart reuses what is there.
# `make down` drops the volume, and the next `up` restores again — which is the whole point of an
# ephemeral baseline: nothing an audit does to it survives.
set -euo pipefail

DUMP=/baseline/moodle.dump
[ -f "$DUMP" ] || { echo "[baseline] FATAL: no dump at $DUMP"; exit 1; }

echo "[baseline] restoring $(du -h "$DUMP" | cut -f1) into $POSTGRES_DB — several minutes"
# -j: the restore is the slowest step of `make up` and it is pure CPU on an idle container.
# --no-owner/--no-privileges: the dump's roles do not exist here and are irrelevant to an audit.
pg_restore -j 4 --no-owner --no-privileges \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$DUMP" 2>&1 | tail -20 || true

# pg_restore exits non-zero over ignorable noise (missing roles, comments on absent objects), so
# the success criterion is the data, not the exit code — same rule the lab applies to ZAP.
n=$(psql -tAc "SELECT count(*) FROM mdl_course" -U "$POSTGRES_USER" -d "$POSTGRES_DB" 2>/dev/null || echo 0)
[ "${n:-0}" -gt 0 ] || { echo "[baseline] FATAL: restore left no courses — refusing to serve an empty Moodle as if it were the platform"; exit 1; }
echo "[baseline] restored: $n courses"
