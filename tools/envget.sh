#!/usr/bin/env bash
# Lee UNA clave del perfil de un target, respetando el override local. Para el Makefile.
#
# Por qué existe: tools/lib-env.sh es "el único lector de target.env" y se puede `source` desde
# cualquier script, pero el Makefile no puede — cada línea de una receta es su propio shell. Así
# que los goals `api-lint` y `api-fuzz` traían su propio `sed -n 's/^OPENAPI_SPEC=//p'` en línea,
# es decir, una SÉPTIMA copia del parser que el propio lib-env.sh existe para eliminar.
#
# Y esa copia estaba rota de la forma que más cuesta ver: leía `target.env` y NUNCA
# `target.env.local`. Encontrado apuntando el laboratorio al despliegue real del 166 — el perfil
# declaraba OPENAPI_SPEC_URL en el .local, que es exactamente donde el laboratorio documenta que
# van los valores del despliegue, y `make api-lint` respondió "este proyecto no publica ningún
# documento OpenAPI". La dimensión se reportó NO DISPONIBLE teniendo el spec delante.
#
# Uso:  tools/envget.sh <target> <CLAVE>       (imprime el valor, o nada)
set -uo pipefail
TARGET="${1:?uso: envget.sh <target> <CLAVE>}"
KEY="${2:?falta la clave}"
ENVFILE="targets/$TARGET/target.env"
[ -f "$ENVFILE" ] || exit 0
. "$(dirname "$0")/lib-env.sh"
envget "$KEY"
