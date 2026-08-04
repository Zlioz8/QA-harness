#!/usr/bin/env bash
# Take a platform baseline from a running Moodle server. READ-ONLY on the source: it runs
# pg_dump and tar, nothing else. The server is never modified, and that is not a convention
# here — it is the condition under which the owner of a shared server agrees to this at all.
#
#   tools/moodle-snapshot.sh <ssh-target> <name> [db] [code-dir]
#   tools/moodle-snapshot.sh usuario@<host-de-la-plataforma> moodle-zajuna-20260729
#
# Produces baselines/<name>/{moodle.dump,code.tar.zst,MANIFEST.md}, consumed by
# recipes/moodle-baseline.yml.
#
# Authentication is left to ssh: put the host in ~/.ssh/config with a key. This script must not
# grow a password argument — it would end up in shell history and in CI logs.
set -euo pipefail

SSH_TARGET="${1:?usage: moodle-snapshot.sh <ssh-target> <name> [db] [code-dir]}"
NAME="${2:?missing baseline name, e.g. moodle-zajuna-$(date +%Y%m%d)}"
DB="${3:-zajunadb}"
CODE_DIR="${4:-/var/www/zajuna}"
OUT="baselines/$NAME"

command -v zstd >/dev/null || { echo "zstd required locally"; exit 2; }
mkdir -p "$OUT"

CODE_PARENT=$(dirname "$CODE_DIR")
CODE_BASE=$(basename "$CODE_DIR")

echo "== baseline $NAME from $SSH_TARGET =="

# ---- database ---------------------------------------------------------------------------
# The activity log is excluded by DATA only: the table and its indexes still exist, so the
# schema is complete and Moodle upgrades cleanly. On the platform this was built against, that
# one table was 64 of the 65 GB — and it is also the table that records who did what and when,
# which a laboratory copy has no business holding.
echo "-- pg_dump (log rows excluded)"
ssh "$SSH_TARGET" "PGPASSWORD=\${PGPASSWORD:-sena123} pg_dump -h localhost -U \${PGUSER:-postgres} \
  -Fc --no-owner --no-privileges \
  --exclude-table-data='public.mdl_logstore_standard_log' \
  '$DB'" > "$OUT/moodle.dump"

# ---- code -------------------------------------------------------------------------------
# `--exclude=config.php` would be a bug, and a quiet one: tar matches that pattern at EVERY
# depth, so it also removes cache/classes/config.php and a dozen other legitimate files. The
# resulting tree serves its login page perfectly and then dies on the first CLI command with
# `Class "cache" not found`, pointing nowhere near the cause. Anchor the path.
echo "-- tar code (root config.php excluded — it carries production DB credentials and salt)"
ssh "$SSH_TARGET" "tar -cf - --exclude='$CODE_BASE/config.php' --exclude='$CODE_BASE/.git' \
  -C '$CODE_PARENT' '$CODE_BASE'" | zstd -3 -T0 -o "$OUT/code.tar.zst" -f

# ---- provenance -------------------------------------------------------------------------
RELEASE=$(ssh "$SSH_TARGET" "grep -oP \"release\\s*=\\s*'\\K[^']+\" '$CODE_DIR/version.php' | head -1")
read -r COURSES USERS PLUGINS <<<"$(ssh "$SSH_TARGET" "PGPASSWORD=\${PGPASSWORD:-sena123} psql -h localhost -U \${PGUSER:-postgres} -d '$DB' -tAc \
  \"SELECT (SELECT count(*) FROM mdl_course), (SELECT count(*) FROM mdl_user), (SELECT count(*) FROM mdl_config_plugins WHERE name='version');\"" | tr '|' ' ')"

cat > "$OUT/MANIFEST.md" <<EOF
# Baseline: $NAME

Read-only snapshot. The source server was not modified.

| | |
|---|---|
| Origen | \`$SSH_TARGET\` · \`$CODE_DIR\` + PostgreSQL \`$DB\` |
| Fecha | $(date -Iseconds) |
| Moodle | \`$RELEASE\` |
| Plugins instalados | $PLUGINS |
| Cursos | $COURSES |
| Usuarios | $USERS |
| sha256 del volcado | $(sha256sum "$OUT/moodle.dump" | cut -c1-32) |

## Excluido

- \`mdl_logstore_standard_log\` — sólo el esquema, ninguna fila.
- \`config.php\` raíz — credenciales de producción, wwwroot real y salt del sitio.
- \`moodledata\` — archivos subidos; se trae aparte si alguna dimensión lo necesita.

## Neutralización

Se aplica al restaurar, antes de que el puerto responda: correo saliente apagado, tokens de
webservice borrados, sesiones eliminadas, wwwroot reescrito, tareas programadas desactivadas.
Ver \`recipes/moodle-baseline/db-init/02-neuter.sh\`.

## Caducidad

Una línea base miente en cuanto la plataforma cambia. Volver a tomarla tras cada despliegue
mayor. \`RUN.md\` registra cuál se usó: dos auditorías contra baselines distintos no son
comparables.
EOF

echo
ls -lh "$OUT"
echo
echo "Listo. En el perfil:  MOODLE_BASELINE=$NAME"
