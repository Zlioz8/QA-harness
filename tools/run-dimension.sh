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
PER_REPO=$(field per_repo)
ARTIFACT=$(field artifact)
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

# ---------------------------------------------------------------------------------------------
# LA ENTRADA DE UNA DIMENSIÓN DE CÓDIGO SON LOS REPOSITORIOS, NO EL DIRECTORIO QUE LOS CONTIENE
#
# El contrato del perfil (targets/_template/target.env) dice que un proyecto de VARIOS
# repositorios apunta SRC_PATH al DIRECTORIO PADRE, y que el laboratorio descubre los hijos.
# Hasta ahora eso solo era cierto para tools/secrets.sh. Las demás dimensiones que miran código
# montaban ${SRC_PATH} entero — y ese padre es una carpeta de trabajo de una persona:
#
#   ANALITICA NOTIFICACIONES/
#     analitica_notificaciones/            <- lo auditado
#     MANUAL DE INSTALACION ....docx(.pdf) <- 1,7 MB de ofimática
#     zv5-menu.png                         <- una captura
#     .playwright-mcp/                     <- logs de consola y red de OTRO proyecto
#
# Escanear eso y publicarlo como cobertura de `analitica_notificaciones` es medir otra cosa con
# el nombre de este proyecto — el modo de fallo contra el que está escrito todo este laboratorio.
#
# Aquí, y no en cada servicio de compose, porque este archivo ya es «la ÚNICA indirección por la
# que pasa la ejecución de una herramienta». Poner la regla en los diecinueve servicios sería
# reintroducir el problema que lib-repos.sh acaba de eliminar.
#
# CÓMO: la variable de entorno del shell GANA sobre --env-file en la interpolación de compose,
# así que basta invocar con SRC_PATH apuntando al repositorio de esta vuelta. Nada que tocar en
# docker-compose.yml.
. "$(dirname "$0")/lib-env.sh"
. "$(dirname "$0")/lib-repos.sh"
SRC_PATH_CFG="$(envget SRC_PATH)"

ROOTS=()
if [ "${PER_REPO:-False}" = "True" ] && [ -n "$SRC_PATH_CFG" ] && [ -d "$SRC_PATH_CFG" ]; then
  mapfile -t ROOTS < <(src_roots "$SRC_PATH_CFG")

  # Ni el propio SRC_PATH es un repositorio ni tiene hijos que lo sean. src_roots cae entonces
  # al propio SRC_PATH —un árbol de código sin git sigue siendo auditable: un tarball
  # desempaquetado, un `make clone` a medias— pero si además ese directorio es una carpeta de
  # trabajo, lo que se va a analizar son manuales y capturas.
  #
  # Medido en `movil`: su SRC_PATH apuntaba a un directorio con dos .docx, dos .md, un .apk y
  # ningún checkout. Sin este aviso, `make static TARGET=movil` habría producido hallazgos
  # sobre un documento de Word y el informe los habría presentado como calidad del código.
  # No se REHÚSA —el caso del árbol sin git es legítimo— pero no puede pasar desapercibido.
  if [ -z "$(discover_repos "$SRC_PATH_CFG")" ]; then
    echo "run-dimension: AVISO — no hay ningún repositorio git bajo SRC_PATH:" >&2
    echo "               $SRC_PATH_CFG" >&2
    echo "               Se analizará ese directorio TAL CUAL. Si es una carpeta de trabajo y no" >&2
    echo "               un checkout, los hallazgos describirán su contenido, no este proyecto." >&2
  fi
fi

REPORTS="reports/$TARGET"
ART_PATH="$REPORTS/$ARTIFACT"
ART_DIR="$(dirname "$ART_PATH")"
ART_EXT="${ARTIFACT##*.}"

case "${RUNNER:-local}" in
  local)
    if [ "${#ROOTS[@]}" -le 1 ]; then
      # Camino normal, y el de casi todos los perfiles: un solo árbol que analizar. Si
      # lib-repos descubrió UN repositorio dentro del padre, se monta ESE y no el padre —
      # que es todo el arreglo, sin fusionar nada ni renombrar ningún artefacto.
      ONE="${ROOTS[0]:-}"
      if [ -n "$ONE" ] && [ "$ONE" != "$SRC_PATH_CFG" ]; then
        echo "run-dimension: $DIM analiza el repositorio, no el directorio que lo contiene:"
        echo "               $ONE"
      fi
      if [ -n "$ONE" ]; then
        SRC_PATH="$ONE" docker compose "${ARGS[@]}" --profile "$PROFILE" run --rm "$SERVICE" "$@"
      else
        docker compose "${ARGS[@]}" --profile "$PROFILE" run --rm "$SERVICE" "$@"
      fi
      rc=$?
    else
      # Varios repositorios bajo el mismo padre (el caso `movil`: frontend y backend, cada uno
      # el suyo). Un pase por repositorio, y el artefacto canónico se compone al final: el
      # gate, el triaje y el informe leen UNA ruta, la que declara `artifact:`.
      echo "run-dimension: $DIM sobre ${#ROOTS[@]} repositorios:"
      printf '               %s\n' "${ROOTS[@]}"
      mkdir -p "$ART_DIR"
      rm -f "$ART_DIR"/_"$DIM"_*."$ART_EXT"
      rc=0
      for root in "${ROOTS[@]}"; do
        slug="$(basename "$root" | tr -c 'A-Za-z0-9_.-' '_')"
        rm -f "$ART_PATH"
        SRC_PATH="$root" docker compose "${ARGS[@]}" --profile "$PROFILE" run --rm "$SERVICE" "$@"
        prc=$?
        [ "$prc" -ne 0 ] && rc=$prc
        # El criterio de éxito de un pase es su ARTEFACTO, no su código de salida: casi todas
        # estas herramientas salen != 0 cuando ENCUENTRAN algo.
        [ -f "$ART_PATH" ] && mv "$ART_PATH" "$ART_DIR/_${DIM}_${slug}.$ART_EXT"
      done

      if [ "$ART_EXT" = "sarif" ]; then
        tools/sarif-merge.py "$ART_PATH" "$ART_DIR"/_"$DIM"_*."$ART_EXT"
      else
        # No todo lo que produce una herramienta es SARIF, y fusionar un SPDX no es concatenar
        # listas: los SPDXID colisionan y el documento resultante ya no describe nada. Se dejan
        # los documentos POR REPOSITORIO, que sí son válidos, y NO se escribe uno canónico
        # inventado. run-manifest lo lee como lo que es.
        echo "run-dimension: '$ARTIFACT' no es SARIF — se conserva un documento por repositorio:"
        ls -1 "$ART_DIR"/_"$DIM"_*."$ART_EXT" 2>/dev/null | sed 's/^/               /'
        echo "               NO se compone un artefacto canónico: sería un documento inventado."
      fi
    fi
    # Sellar SIEMPRE, tambien si la herramienta salio != 0: casi todas salen distinto de cero
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
