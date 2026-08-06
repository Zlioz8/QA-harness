#!/usr/bin/env bash
# La ÚNICA indirección por la que pasa la ejecución de una herramienta.
#
# Hoy hace exactamente lo que ya se hacía: `docker compose --profile X run --rm <servicio>`.
# No añade capacidad. Añade UN SITIO.
#
# Por qué existe si no cambia nada todavía: el día que haya un segundo servidor —k6 en una máquina
# que no compita con nada, ZAP cerca de la aplicación, un SonarQube compartido— la alternativa a
# esto es reescribir el Makefile, los diecinueve servicios de compose y la interfaz. Con esto es
# mirar el campo `runner:` del registro aquí dentro. Declarar el puerto cuesta este archivo;
# retrofitearlo cuesta el laboratorio entero.
#
# Lo que decide si una dimensión PUEDE moverse no es el balanceo de carga, es `needs:`:
#   source          trivy, semgrep, gitleaks, syft, qodana. Van donde está el código: mandar
#                   2,78 GB de node_modules a un runner remoto es peor que analizarlo aquí.
#   target-network  zap, k6, jmeter, playwright, schemathesis. Van donde alcanzan la aplicación.
#   nothing         sonarqube, mobsf. Son servicios REST y su host YA es una variable
#                   (docker-compose.yml:67 pasa SONAR_HOST_URL) — pueden vivir donde sea.
#   device          device-e2e. El teléfono está enchufado a esta máquina. No se mueve nunca.
#
# Uso:  run-dimension.sh <target> <dimensión> [args del servicio...]
#
# Se le pasa la DIMENSIÓN, no el servicio: qué servicio de compose y qué perfil le corresponden
# están en el registro, no en el Makefile. Los dos difieren más de lo que parece — la dimensión
# `sbom` corre el servicio `syft`, y `trivy-fs` corre el servicio `trivy`.
set -uo pipefail

TARGET="${1:?uso: run-dimension.sh <target> <dimensión> [args...]}"
DIM="${2:?falta la dimensión}"
shift 2

# Una consulta por campo, y no un `read` de tres columnas. Motivo medido: `read` DESCARTA los
# campos vacíos iniciales aunque se fije IFS=$'\t', porque el tabulador es espacio en blanco y
# POSIX manda colapsar secuencias de IFS-blanco. Para una dimensión sin servicio propio la línea
# es "\t\tlocal" y SERVICE acababa valiendo "local": el guard de abajo no saltaba y se invocaba
# `docker compose run --rm local` con el perfil vacío. Fallo silencioso, y encima con cara de
# problema de compose. Tres llamadas de 10 ms no justifican volver a arriesgar eso.
field() { tools/dimensions.py --list "$1" --where id="$DIM" 2>/dev/null | head -1; }
SERVICE=$(field service)
PROFILE=$(field profile)
RUNNER=$(field runner)
if [ -z "${SERVICE:-}" ]; then
  echo "run-dimension: la dimensión '$DIM' no tiene servicio de compose propio." >&2
  echo "               La conduce un script de tools/ — invócalo desde el Makefile." >&2
  exit 2
fi

ENVFILE="targets/$TARGET/target.env"
ENVLOCAL="targets/$TARGET/target.env.local"
RUNTIME="targets/$TARGET/compose.runtime.yml"

# Mismo ensamblado que el Makefile: el override local gana porque va después.
ARGS=(--env-file "$ENVFILE")
[ -f "$ENVLOCAL" ] && ARGS+=(--env-file "$ENVLOCAL")
ARGS+=(-f docker-compose.yml)
[ -f "$RUNTIME" ] && ARGS+=(-f "$RUNTIME")

case "${RUNNER:-local}" in
  local)
    docker compose "${ARGS[@]}" --profile "$PROFILE" run --rm "$SERVICE" "$@"
    rc=$?
    # Sellar SIEMPRE, tambien si la herramienta salio != 0: casi todas salen distinto de cero
    # cuando ENCUENTRAN algo (zap, qodana, spectral, schemathesis), y ese es justo el artefacto
    # que hay que poder atribuir a un blanco. Sellar solo en el camino feliz dejaria sin
    # procedencia precisamente las corridas con hallazgos.
    tools/stamp.sh "$TARGET" "$DIM" 2>/dev/null || true
    exit $rc
    ;;
  ssh://*|context:*|url:*)
    # Documentado y SIN IMPLEMENTAR a propósito. Morir aquí con la razón escrita es mejor que
    # ejecutar en local fingiendo que se respetó el `runner:` del perfil — una corrida que dice
    # haber medido desde otro sitio y no lo hizo es un informe que miente sobre su propio método.
    #
    # Lo que falta para implementarlo, por si alguien lo retoma:
    #   1. Los bind mounts NO viajan: un daemon remoto resuelve `./reports/...` en SU host. La
    #      herramienta escribe en un volumen suyo y aquí se recoge (docker cp / scp). Por eso la
    #      fase 1 impuso "una dimensión = UN artefacto en UNA ruta canónica".
    #   2. La fuente se CLONA, no se comparte. El servicio `clone` (--profile clone) ya existe.
    #   3. tools/admit.sh debe preguntar por la memoria del host que va a ejecutar, no del local.
    echo "run-dimension: runner='$RUNNER' aún no implementado (solo 'local')." >&2
    echo "               La dimensión '$SERVICE' NO se ejecutó. No es un PASS ni 'sin hallazgos'." >&2
    exit 3
    ;;
  *)
    echo "run-dimension: runner desconocido '$RUNNER' para '$SERVICE'." >&2
    exit 2
    ;;
esac
