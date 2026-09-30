#!/usr/bin/env bash
# Pone, quita o muestra el sobre de la prueba en el despliegue LOCAL de movil_api.
#
#   carga/sobre.sh poner     recrea el contenedor `web` con sobre.compose.yml
#   carga/sobre.sh quitar    lo devuelve a como lo levanta el compose del repositorio
#   carga/sobre.sh ver       lo que hay AHORA, leído del contenedor (no de un archivo)
#
# Variables: SOBRE_CPUS, SOBRE_MEM, SOBRE_WORKERS, SOBRE_LOG_LEVEL, SOBRE_DEBUG, y
# MOVIL_API (ruta del repositorio; por omisión SRC_PATH/movil_api del perfil).
set -uo pipefail
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB="$(cd "$AQUI/../../.." && pwd)"
ENVFILE="$LAB/targets/movil/target.env"
. "$LAB/tools/lib-env.sh"
API="${MOVIL_API:-$(envget SRC_PATH)/movil_api}"
BASE="$(envget BASE_URL)"

ver() {
  docker inspect movil_api-web-1 --format 'cpus={{.HostConfig.NanoCpus}} mem={{.HostConfig.Memory}} creado={{.Created}}' 2>/dev/null \
    | awk '{gsub("cpus=","cpus="); print}' | sed -E 's/cpus=([0-9]+)/cpus=\1 (nanoCPU; 0 = sin límite)/'
  docker top movil_api-web-1 -o pid,args 2>/dev/null | sed 1d | sed 's/^/  proceso: /'
  docker exec movil_api-web-1 sh -c 'env | grep -E "^(PROXY_HOPS|LOG_LEVEL|DEBUG|WEB_CONCURRENCY|JOSSO_ENABLED)=" | sort | tr "\n" " "' 2>/dev/null; echo
}

esperar() {
  for _ in $(seq 1 60); do
    [ "$(curl -sk -o /dev/null -w '%{http_code}' "$BASE/health")" = "200" ] && return 0
    sleep 2
  done
  return 1
}

case "${1:-ver}" in
  poner)
    ( cd "$API" && docker compose -f docker-compose.yml -f "$AQUI/sobre.compose.yml" up -d --no-deps web ) || exit 1
    # nginx también se recrea: un json-log viejo con una entrada rota hace que `docker logs
    # --since` devuelva de más (L-R9-02), y la telemetría guarda ese log por paso.
    ( cd "$API" && docker compose up -d --no-deps --force-recreate nginx ) >/dev/null 2>&1
    # nginx resolvió `web` al arrancar: si el contenedor nuevo cambió de IP, responde 502 hasta recargar.
    esperar || { ( cd "$API" && docker compose restart nginx ); esperar || { echo "sobre: la API no responde en $BASE/health" >&2; exit 1; }; }
    ver ;;
  quitar)
    ( cd "$API" && docker compose up -d --no-deps web ) || exit 1
    esperar || { ( cd "$API" && docker compose restart nginx ); esperar || { echo "sobre: la API no responde en $BASE/health" >&2; exit 1; }; }
    ver ;;
  ver) ver ;;
  *) echo "uso: sobre.sh poner|quitar|ver" >&2; exit 2 ;;
esac
