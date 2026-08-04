#!/usr/bin/env bash
# Libera el puerto de SonarQube cuando lo ocupa el servidor de OTRO perfil del laboratorio.
#
# El fallo medido: cada perfil arranca su propio SonarQube (un proyecto compose por target, con su
# propia base y su propio volumen) y todos publican el mismo SONAR_PORT. Auditar un segundo
# proyecto sin haber apagado el primero muere así:
#
#   Bind for 127.0.0.1:9000 failed: port is already allocated
#
# El mensaje no dice que el culpable es otro target del propio laboratorio, ni cuál. `make doctor`
# ya lo advertía, pero avisar en un preflight que nadie vuelve a mirar no evita que la dimensión de
# calidad se pierda en la corrida siguiente: Sonar es la única herramienta del lab que necesita un
# servidor, y por tanto la única que no era indiferente al proyecto.
#
# Qué hace: si el puerto lo tiene un `sonarqube` de otro proyecto compose `seclab_*`, lo PARA
# (no lo borra: su volumen y su análisis siguen ahí, y vuelve con `make sonar` en ese target).
# Si lo tiene cualquier otra cosa, no toca nada y falla diciendo qué es — apagar procesos ajenos
# no es asunto de este laboratorio.
set -uo pipefail

TARGET="${1:?uso: sonar-free-port.sh <target>}"
. "$(dirname "$0")/lib-env.sh"   # un solo parser de target.env — ver el archivo
ENVFILE="targets/$TARGET/target.env"

PORT=$(envget SONAR_PORT); PORT="${PORT:-9000}"
MINE=$(envget COMPOSE_PROJECT_NAME); MINE="${MINE:-seclab_$TARGET}"

# Quién publica el puerto, según Docker (visible también desde dentro de un contenedor, que es
# como corre esto cuando lo lanza la interfaz web).
HOLDER=$(docker ps --format '{{.Names}}\t{{.Ports}}\t{{.Label "com.docker.compose.project"}}\t{{.Label "com.docker.compose.service"}}' 2>/dev/null \
         | grep -E ":$PORT->" | head -1)

[ -z "$HOLDER" ] && exit 0                      # libre: nada que hacer

NAME=$(echo "$HOLDER" | cut -f1)
PROJ=$(echo "$HOLDER" | cut -f3)
SVC=$(echo  "$HOLDER" | cut -f4)

if [ "$PROJ" = "$MINE" ]; then exit 0; fi       # es el nuestro, ya está arriba

case "$PROJ:$SVC" in
  seclab_*:sonarqube)
    echo "sonar: el puerto $PORT lo tiene el SonarQube del perfil '$PROJ' ($NAME)."
    echo "       Se para para dejar sitio a '$TARGET'. Su volumen y su análisis se conservan:"
    echo "       vuelve a levantarlo con 'make sonar TARGET=<ese perfil>'."
    docker stop "$NAME" >/dev/null 2>&1 \
      && echo "       parado." \
      || { echo "       NO se pudo parar $NAME. Hazlo a mano: docker stop $NAME"; exit 1; }
    ;;
  *)
    echo "sonar: el puerto $PORT lo ocupa '$NAME' (proyecto '$PROJ', servicio '$SVC'), que NO es"
    echo "       un servidor de este laboratorio. No se toca."
    echo "       Libéralo tú, o dale a este perfil un puerto propio: SONAR_PORT=<otro> en"
    echo "       targets/$TARGET/target.env"
    exit 1
    ;;
esac
exit 0
