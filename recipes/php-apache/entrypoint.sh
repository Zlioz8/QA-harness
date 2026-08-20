#!/bin/bash
# Bring a plain PHP/Apache project up from a read-only checkout.
#
# The audited source is mounted at /src read-only and stays that way — the lab observes, it
# never modifies the project. Everything that has to be writable (vendor/, caches, session
# files, the .env the app reads) is created on a container-local copy, which `make down`
# destroys along with the rest.
set -euo pipefail

SRC_DIRECTORY="${SRC_DIRECTORY:-}"
APP_SUBDIR="${APP_SUBDIR:-}"
SRC="/src${APP_SUBDIR:+/$APP_SUBDIR}"
DEST="/var/www/html${SRC_DIRECTORY}"

echo "php-apache: copiando $SRC -> $DEST"
mkdir -p "$DEST"
# .git IS copied, on purpose. A previous audit of this stack found the repository history
# downloadable over HTTP from the real server; excluding it here would make that finding
# untestable and the scan would come back clean over a hole that exists in production.
cp -a "$SRC/." "$DEST/"

# The URL prefix has to reach Apache's config, which cannot read environment variables in a
# <Directory> block. Substituted here rather than baked into the image so one image serves
# every project on this stack.
if [ -n "$SRC_DIRECTORY" ]; then
  sed -i "s|DocumentRoot /var/www/html|DocumentRoot /var/www/html|; \
          s|<Directory /var/www/html>|<Directory /var/www/html>|" \
      /etc/apache2/sites-enabled/000-default.conf
fi

# --- dependencies -----------------------------------------------------------------------------
#
# Three cases, and they must stay distinguishable in the report. A dependency scan that finds
# nothing because there was no manifest to read is NOT a clean dependency scan.
if [ -f "$DEST/composer.json" ]; then
  echo "php-apache: composer.json del repositorio"
  ( cd "$DEST" && composer install --no-interaction --no-progress --prefer-dist 2>&1 | tail -5 ) || \
    echo "php-apache: AVISO composer install falló — ver arriba"
  echo "DEPS_SOURCE=repositorio" > /var/www/deps-provenance
elif [ -f /deps/composer.json ]; then
  # Supplied by the profile because the repository gitignores it (ADI's deployment-contract
  # finding D1). Perfectly workable for bringing the app up — but the CVE numbers then describe
  # THIS manifest, not the one the team deploys, and the report must say so in those words.
  echo "php-apache: composer.json aportado por el perfil (el repositorio no lo trae)"
  cp /deps/composer.json "$DEST/"
  [ -f /deps/composer.lock ] && cp /deps/composer.lock "$DEST/"
  ( cd "$DEST" && composer install --no-interaction --no-progress --prefer-dist 2>&1 | tail -5 ) || \
    echo "php-apache: AVISO composer install falló — ver arriba"
  echo "DEPS_SOURCE=perfil-del-laboratorio" > /var/www/deps-provenance
  echo "php-apache: *** la dimensión CVE de dependencias NO ES AUTORITATIVA para este proyecto ***"
else
  echo "php-apache: sin composer.json en el repositorio ni en el perfil — sin vendor/"
  echo "DEPS_SOURCE=ninguno" > /var/www/deps-provenance
fi

# --- configuration ----------------------------------------------------------------------------
#
# The profile's .env wins; otherwise fall back to the repository's template so the app at least
# boots and its own error handling is what gets audited, rather than a blank page.
if [ -f /deps/.env ]; then
  cp /deps/.env "$DEST/.env"
  echo "php-apache: .env aportado por el perfil"
elif [ -f "$DEST/.env.example" ] && [ ! -f "$DEST/.env" ]; then
  cp "$DEST/.env.example" "$DEST/.env"
  echo "php-apache: .env generado desde .env.example (valores de plantilla, no de producción)"
fi

# Point the app at the compose network's database.
#
# Everything is driven by names the PROFILE supplies, never by a pattern this script invents.
# The tempting shortcut — rewrite every `*HOST=` that is empty or localhost — is wrong on this
# stack: ADI's .env also carries CRONJOB_HOST (an SSH server) and SOFIA_HOST (Oracle), and
# pointing those at postgres produces confusing failures deep inside unrelated modules that
# then look like application defects.
#
#   DB_HOST_VARS   comma-separated names that should all become the compose db host
#   ENV_OVERRIDES  semicolon-separated KEY=VALUE pairs written verbatim (credentials, database
#                  names, anything else the template leaves blank)
#
# When a profile supplies its own /deps/.env, which is the documented path, none of this fires.
set_env_var() {
  local key="$1" val="$2"
  if grep -qE "^${key}=" "$DEST/.env"; then
    # `|` as the delimiter and the value escaped: a password containing `/` or `&` would
    # otherwise be mangled by sed into something that fails to authenticate, and the app would
    # report a database error that has nothing to do with the application.
    local esc; esc=$(printf '%s' "$val" | sed -e 's/[\\|&]/\\&/g')
    sed -i -E "s|^${key}=.*|${key}=${esc}|" "$DEST/.env"
  else
    printf '%s=%s\n' "$key" "$val" >> "$DEST/.env"
  fi
}

if [ -f "$DEST/.env" ]; then
  if [ -n "${DB_HOST_VARS:-}" ]; then
    for v in ${DB_HOST_VARS//,/ }; do set_env_var "$v" "$DB_HOST"; done
    echo "php-apache: apuntadas a '${DB_HOST}' las variables: ${DB_HOST_VARS}"
  fi
  if [ -n "${ENV_OVERRIDES:-}" ]; then
    # Split on ';' only, so a value may legitimately contain '=' (passwords do).
    old_ifs=$IFS; IFS=';'
    for pair in $ENV_OVERRIDES; do
      [ -z "$pair" ] && continue
      set_env_var "${pair%%=*}" "${pair#*=}"
    done
    IFS=$old_ifs
    echo "php-apache: aplicadas $(echo "$ENV_OVERRIDES" | tr ';' '\n' | grep -c '=') sustituciones de ENV_OVERRIDES"
  fi
fi

# Apache runs PHP as www-data. Files owned by root break session and cache writes; permissions
# that are too open expose the .env. Same numbers the project's own deployment guide uses.
chown -R www-data:www-data "$DEST"
find "$DEST" -type d -exec chmod 755 {} + 2>/dev/null || true
find "$DEST" -type f -exec chmod 644 {} + 2>/dev/null || true
[ -f "$DEST/.env" ] && chmod 640 "$DEST/.env"

echo "php-apache: listo en http://localhost${SRC_DIRECTORY}/"
exec "$@"
