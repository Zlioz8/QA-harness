#!/usr/bin/env bash
# Acuña un token de análisis contra el SonarQube del lab y lo imprime por STDOUT.
#
# El bug: sonar-scanner necesita SONAR_TOKEN, pero un servidor recién arrancado no tiene ninguno
# —hay que generarlo tras el boot con las credenciales de admin—. Este script es ese "llenado de
# campo" que el agente ya no tiene que hacer a mano: es genérico (cualquier target), idempotente
# y no incrusta secretos. Si el target ya declara SONAR_TOKEN en target.env(.local), lo respeta.
#
# Todo lo informativo va a STDERR; STDOUT es SOLO el token, para poder hacer:
#   TOKEN=$(tools/sonar-token.sh costos_web)
#
# Variables (todas opcionales, con defecto de una instalación community fresca):
#   SONAR_PORT           puerto publicado del servidor        (def 9000)
#   SONAR_ADMIN_USER     usuario admin                        (def admin)
#   SONAR_ADMIN_PASS     contraseña admin ACTUAL              (def admin)
#   SONAR_NEW_ADMIN_PASS contraseña a fijar si el server obliga a cambiar la de fábrica (def admin01)
#   SONAR_TOKEN          si ya viene definido, se imprime tal cual y no se genera nada
set -euo pipefail

TARGET="${1:?uso: sonar-token.sh <target>}"
LAB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENVF="$LAB_DIR/targets/$TARGET/target.env"
ENVL="$LAB_DIR/targets/$TARGET/target.env.local"

# Lee una variable del par target.env / target.env.local (el .local gana), sin ejecutar el archivo.
readvar() {
  local key="$1" val=""
  for f in "$ENVF" "$ENVL"; do
    [ -f "$f" ] || continue
    local v; v="$(sed -n "s/^${key}=//p" "$f" | tail -1 | tr -d '\r')"
    [ -n "$v" ] && val="$v"
  done
  printf '%s' "$val"
}

log() { echo "sonar-token: $*" >&2; }

# 0) Si el target ya trae un token, no inventamos otro.
PRESET="$(readvar SONAR_TOKEN)"
if [ -n "$PRESET" ]; then log "SONAR_TOKEN ya declarado en el target — se reutiliza."; printf '%s' "$PRESET"; exit 0; fi

PORT="$(readvar SONAR_PORT)"; PORT="${PORT:-9000}"
AUSER="${SONAR_ADMIN_USER:-$(readvar SONAR_ADMIN_USER)}"; AUSER="${AUSER:-admin}"
APASS="${SONAR_ADMIN_PASS:-$(readvar SONAR_ADMIN_PASS)}"; APASS="${APASS:-admin}"
NEWPASS="${SONAR_NEW_ADMIN_PASS:-$(readvar SONAR_NEW_ADMIN_PASS)}"; NEWPASS="${NEWPASS:-admin01}"
H="http://127.0.0.1:${PORT}"

# 1) Esperar a que el servidor esté operativo (el depends_on:service_healthy del scanner cubre el
#    caso normal, pero este script puede invocarse suelto). Máx ~3 min, igual que el healthcheck.
log "esperando a que $H esté UP ..."
for _ in $(seq 1 90); do
  st="$(curl -sf "$H/api/system/status" 2>/dev/null || true)"
  echo "$st" | grep -q '"status":"UP"' && break
  sleep 2
done
echo "$st" | grep -q '"status":"UP"' || { log "el servidor no llegó a UP"; exit 1; }

# Prueba unas credenciales admin: 200 => válidas.
auth_ok() { curl -s -o /dev/null -w '%{http_code}' -u "$1:$2" "$H/api/authentication/validate" | grep -q 200; }

# 2) Resolver la contraseña de admin utilizable.
CUR=""
if auth_ok "$AUSER" "$APASS"; then
  CUR="$APASS"
elif auth_ok "$AUSER" "$NEWPASS"; then
  # Ya se había fijado en una corrida anterior (idempotencia).
  CUR="$NEWPASS"; log "admin ya usaba la contraseña nueva."
else
  log "credenciales admin inválidas ($AUSER)."; exit 1
fi

# 3) SonarQube obliga a cambiar la contraseña de fábrica antes de dejar operar. Si seguimos con la
#    de fábrica, la cambiamos a NEWPASS (idempotente: si ya estaba, el paso 2 usó NEWPASS).
if [ "$CUR" = "admin" ] && [ "$AUSER" = "admin" ]; then
  code="$(curl -s -o /dev/null -w '%{http_code}' -u "admin:admin" -X POST \
        "$H/api/users/change_password" \
        --data-urlencode "login=admin" \
        --data-urlencode "previousPassword=admin" \
        --data-urlencode "password=$NEWPASS" || true)"
  if [ "$code" = "204" ] || [ "$code" = "200" ]; then CUR="$NEWPASS"; log "contraseña de fábrica cambiada."; fi
fi

# 4) Generar el token. El nombre se revoca antes para poder re-emitir sin colisión (idempotente).
NAME="seclab-${TARGET}"
curl -s -o /dev/null -u "$AUSER:$CUR" -X POST \
     "$H/api/user_tokens/revoke" --data-urlencode "name=$NAME" || true
RESP="$(curl -s -u "$AUSER:$CUR" -X POST \
        "$H/api/user_tokens/generate" --data-urlencode "name=$NAME")"
TOKEN="$(printf '%s' "$RESP" | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')"
[ -n "$TOKEN" ] || { log "no se pudo generar el token. Respuesta: $RESP"; exit 1; }

log "token acuñado ($NAME)."
printf '%s' "$TOKEN"
