#!/bin/bash
# Create every database in DB_NAMES except the first, which the postgres entrypoint already
# made from POSTGRES_DB. Runs once, on an empty data directory, before the profile's own seeds
# (they live in seed/ and postgres reads this directory alphabetically — hence the 00- prefix).
set -euo pipefail

: "${DB_NAMES:?postgres-multi: DB_NAMES is empty — set it in target.env}"

first=1
IFS=',' read -ra names <<< "$DB_NAMES"
for raw in "${names[@]}"; do
  db="$(echo "$raw" | tr -d '[:space:]')"
  [ -z "$db" ] && continue
  if [ "$first" = 1 ]; then first=0; continue; fi   # POSTGRES_DB, already created

  # ALWAYS double-quoted. PostgreSQL folds an unquoted identifier to lower case, so
  # `CREATE DATABASE Presencialformacion` silently produces `presencialformacion` — and the
  # application, which connects by the mixed-case name, then fails with "database does not
  # exist" while `\l` plainly shows something that looks right. ADI has exactly one such name
  # among its five, which is the worst ratio: four work, one does not, and the difference is
  # invisible.
  if psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
       -tAc "SELECT 1 FROM pg_database WHERE datname = '${db}'" | grep -q 1; then
    echo "postgres-multi: \"${db}\" already exists"
  else
    psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
         -c "CREATE DATABASE \"${db}\";"
    echo "postgres-multi: created \"${db}\""
  fi
done

# The profile's seeds sit in seed/ and postgres does NOT recurse into subdirectories of
# initdb.d — it would skip them entirely and the databases would come up empty with no error.
# Apply them here, in filename order, so a seed can target any of the databases above by
# starting with a `\connect`.
if [ -d /docker-entrypoint-initdb.d/seed ]; then
  for f in $(find /docker-entrypoint-initdb.d/seed -maxdepth 1 -name '*.sql' | sort); do
    echo "postgres-multi: applying $(basename "$f")"
    # Not ON_ERROR_STOP: a seed that targets a database this profile did not create should
    # complain loudly in the log without aborting the whole boot, which would leave the
    # healthcheck failing forever with no clue as to why.
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$f" || echo "postgres-multi: WARNING $(basename "$f") reported errors (see above)"
  done
fi
