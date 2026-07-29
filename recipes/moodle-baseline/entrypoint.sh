#!/bin/bash
# Unpack the baseline, point it at the ephemeral database, install the plugin under audit,
# and let Moodle upgrade itself.
set -euo pipefail

WWW=/var/www/html/zajuna
DATA=/var/www/zajunadata

if [ ! -f "$WWW/version.php" ]; then
  echo "[baseline] unpacking code.tar.zst"
  mkdir -p /var/www/html
  # The tarball holds a top-level `zajuna/` directory (tar -C /var/www zajuna on the source).
  zstd -dc /baseline/code.tar.zst | tar -xf - -C /var/www/html
  echo "[baseline] $(grep -oP "release\s*=\s*'\K[^']+" "$WWW/version.php" | head -1)"
fi

mkdir -p "$DATA"

# config.php is written here, never taken from the snapshot: the original carries the production
# database credentials, the production wwwroot and its salt. It is excluded from the tarball for
# that reason, and rebuilt with only what this copy needs.
cat > "$WWW/config.php" <<PHP
<?php
unset(\$CFG);
global \$CFG;
\$CFG = new stdClass();
\$CFG->dbtype    = 'pgsql';
\$CFG->dblibrary = 'native';
\$CFG->dbhost    = '${DB_HOST:-db}';
\$CFG->dbname    = '${DB_NAME}';
\$CFG->dbuser    = '${DB_USER}';
\$CFG->dbpass    = '${DB_PASSWORD}';
\$CFG->prefix    = 'mdl_';
\$CFG->dboptions = array('dbpersist' => 0, 'dbport' => 5432, 'dbsocket' => '');
\$CFG->wwwroot   = '${MOODLE_WWWROOT}';
\$CFG->dataroot  = '${DATA}';
\$CFG->admin     = 'admin';
\$CFG->directorypermissions = 0777;
// The gate and the report want the real error, not a friendly page. This copy never leaves
// loopback; that is the trade this whole recipe is built on.
\$CFG->debug = 32767;
\$CFG->debugdisplay = 1;
// Belt and braces with the DB-side neutering: if anything ever re-enables mail in mdl_config,
// this line still wins.
\$CFG->noemailever = true;
require_once(__DIR__ . '/lib/setup.php');
PHP

echo "[baseline] waiting for ${DB_HOST:-db}"
for _ in $(seq 1 120); do
  pg_isready -h "${DB_HOST:-db}" -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1 && break
  sleep 2
done

# The plugins under audit are copied in, never mounted: the audited checkout stays read-only and
# Moodle gets a tree it owns. Destination derived from each version.php's own component, so a
# repository holding several plugins installs all of them.
if [ -d /plugin-src ]; then
  while IFS= read -r vfile; do
    comp=$(sed -n "s/.*plugin->component[[:space:]]*=[[:space:]]*'\([^']*\)'.*/\1/p" "$vfile" | head -1)
    [ -z "$comp" ] && continue
    type="${comp%%_*}"; name="${comp#*_}"
    case "$type" in
      block) sub="blocks" ;; qtype) sub="question/type" ;; *) sub="$type" ;;
    esac
    dest="$WWW/$sub/$name"
    echo "[baseline] installing $comp -> $dest"
    rm -rf "$dest"; mkdir -p "$(dirname "$dest")"; cp -a "$(dirname "$vfile")" "$dest"
  done < <(find /plugin-src -maxdepth 2 -name version.php -type f | sort)
fi

chown -R www-data:www-data /var/www/html "$DATA"

# Let Moodle create the plugin's tables through its own upgrade path. Hand-writing that schema
# would mean the audit measures a fiction instead of the real installation.
echo "[baseline] running Moodle upgrade"
su -s /bin/bash www-data -c "php $WWW/admin/cli/upgrade.php --non-interactive --allow-unstable" || \
  echo "[baseline] upgrade reported errors — continuing; check the log above"

su -s /bin/bash www-data -c "php $WWW/admin/cli/purge_caches.php" >/dev/null 2>&1 || true
chown -R www-data:www-data "$DATA"

echo "[baseline] ready at ${MOODLE_WWWROOT}"
exec "$@"
