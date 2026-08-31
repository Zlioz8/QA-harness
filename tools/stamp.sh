#!/usr/bin/env bash
# Sella una dimensión: deja constancia de CONTRA QUÉ midió, en el momento en que midió.
#
# EL PROBLEMA. Un artefacto en disco no dice qué sistema midió. `zap.sarif` es un archivo con
# alertas; nada en él distingue si salieron del despliegue del servidor 166 o de un Moodle efímero
# que se levantó hace tres días en esta laptop. El veredicto SUMA lo que encuentra, así que un
# `GATE FAILED` puede estar hecho de evidencia sobre dos sistemas distintos.
#
# Medido en este mismo laboratorio: un veredicto mezclaba cinco dimensiones de hacía minutos
# (contra el 166) con sonar y playwright de hacía TRES DÍAS (contra el despliegue local), y la
# tabla de cobertura marcaba las diez como `yes`. La edad del archivo lo insinúa; solo el sello
# lo demuestra.
#
# QUÉ SE COMPARA, Y POR QUÉ NO LO MISMO PARA TODAS. Depende de qué toca cada dimensión:
#   needs: source          -> el COMMIT auditado. Cambiar de despliegue no invalida un SAST.
#   needs: target-network  -> la URL del despliegue. Cambiar de rama no invalida un DAST.
# Comparar las dos cosas en todas haría fallar dimensiones que siguen siendo válidas, y el aviso
# que se ignora es peor que no avisar.
#
# Uso: stamp.sh <target> <dimensión>       (lo llaman run-dimension.sh y los goals con script propio)
set -uo pipefail

TARGET="${1:?uso: stamp.sh <target> <dimensión>}"
DIM="${2:?falta la dimensión}"
ENVFILE="targets/$TARGET/target.env"
[ -f "$ENVFILE" ] || exit 0
. "$(dirname "$0")/lib-env.sh"
. "$(dirname "$0")/lib-repos.sh"

DIR="reports/$TARGET/.provenance"
mkdir -p "$DIR" 2>/dev/null || exit 0

SRC_PATH=$(envget SRC_PATH)

# EL COMMIT SE LEE DE LOS REPOSITORIOS, NO DE LA CARPETA QUE LOS CONTIENE.
#
# Esto era `git -C "$SRC_PATH" rev-parse` a secas, y el contrato del perfil dice que un proyecto
# de varios repositorios apunta SRC_PATH al DIRECTORIO PADRE. Sobre un padre, `rev-parse` falla,
# el `|| echo ''` lo tapaba, y TODA dimensión `needs: source` quedaba sellada
# `commit: desconocido`. Un sello que no sabe contra qué midió no puede invalidar nada: la
# maquinaria de procedencia entera —la que existe para que un veredicto no mezcle evidencia de
# dos sistemas— se degradaba a un campo decorativo, sin que nada lo dijera.
#
# Con varios repositorios el commit NO es uno: se nombran todos. Un identificador solo sirve si
# de verdad identifica lo medido, y «abc1234» cuando se auditaron dos árboles es una media
# verdad que se lee como una entera.
COMMIT=""
while IFS= read -r _repo; do
  [ -n "$_repo" ] || continue
  _c="$(git -C "$_repo" rev-parse --short HEAD 2>/dev/null || echo '')"
  [ -n "$_c" ] || continue
  # Un árbol sucio no es el commit que dice ser: lo que se midió incluye cambios que nadie puede
  # recuperar desde esa revisión. Se marca, no se oculta.
  [ -n "$(git -C "$_repo" status --porcelain 2>/dev/null)" ] && _c="$_c+sucio"
  if [ "$_repo" = "$SRC_PATH" ]; then
    COMMIT="$_c"
  else
    COMMIT="${COMMIT:+$COMMIT }$(basename "$_repo")=$_c"
  fi
done < <(src_roots "$SRC_PATH")

GUION=$(tools/dimensions.py --list script --where id="$DIM" 2>/dev/null | head -1)
NEEDS=$(tools/dimensions.py --list needs --where id="$DIM" 2>/dev/null | head -1)

python3 - "$DIR/$DIM.json" <<PY
import json, sys
json.dump({
    "cuando": "$(date -Is)",
    "commit": "${COMMIT:-desconocido}",
    "base_url": "$(envget BASE_URL)",
    "app_internal_url": "$(envget APP_INTERNAL_URL)",
    "guion": "${GUION}",
    "needs": "${NEEDS:-source}",
}, open(sys.argv[1], "w"), indent=1, ensure_ascii=False)
PY
