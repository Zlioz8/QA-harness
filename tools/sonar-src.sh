#!/usr/bin/env bash
# Imprime el árbol que el scanner de Sonar debe montar para un target, y avisa por stderr
# cuando la decisión no es obvia.
#
# POR QUÉ EXISTE. Sonar era la ÚLTIMA dimensión de código ciega al multi-repo. L-R3-01 convirtió
# a todas las demás pasándolas por tools/run-dimension.sh, que resuelve el árbol con
# tools/lib-repos.sh; Sonar no pasa por ahí —necesita servidor, token y export, así que el
# Makefile lo invoca directo— y se quedó montando ${SRC_PATH} ENTERO.
#
# Lo que costó, medido en portafolio_del_aprendiz (2026-08-25): su SRC_PATH es el directorio
# padre (contrato del perfil para multi-repo) y ahí, junto a los manuales, había una carpeta
# `Qodana/` con 285 MB de caché y 8.366 ficheros .go de OTRO análisis. El scanner se puso a
# analizar dependencias de Go, reventó con `java.lang.OutOfMemoryError: Java heap space` a los
# 5 minutos, y el export declaró **0 issues**. Cero, para un plugin PHP que nunca llegó a mirar.
# Es el caso que abre METODOLOGIA §4: «0 secretos» porque la herramienta no había arrancado.
#
# POR QUÉ UN SCRIPT Y NO TRES LÍNEAS EN EL MAKEFILE: cada línea de una receta corre bajo `sh`,
# y tanto `src_roots` como este resolvedor usan bash (`< <(...)`). El primer intento se escribió
# en línea y murió con «/bin/sh: Syntax error: redirection unexpected». Es la misma razón por la
# que existe tools/envget.sh.
#
# Uso:  tools/sonar-src.sh <target>     -> imprime UNA ruta absoluta en stdout
set -uo pipefail

TARGET="${1:?uso: sonar-src.sh <target>}"
LAB_DIR="${LAB_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$LAB_DIR" || exit 1

# shellcheck source=lib-repos.sh
. tools/lib-repos.sh

SRC="$(tools/envget.sh "$TARGET" SRC_PATH)"
if [ -z "$SRC" ] || [ ! -d "$SRC" ]; then
  # Sin SRC_PATH utilizable no se decide nada aquí: se devuelve lo que había y que falle donde
  # el error sea legible, en vez de inventar una ruta.
  printf '%s\n' "$SRC"
  exit 0
fi

mapfile -t ROOTS < <(src_roots "$SRC")

case "${#ROOTS[@]}" in
  1)
    if [ "${ROOTS[0]}" != "$SRC" ]; then
      echo "sonar: analiza el repositorio, no el directorio que lo contiene:" >&2
      echo "       ${ROOTS[0]}" >&2
    fi
    printf '%s\n' "${ROOTS[0]}"
    ;;
  0)
    printf '%s\n' "$SRC"
    ;;
  *)
    # Varios repositorios bajo el mismo padre. Las demás dimensiones dan un pase por repositorio
    # y fusionan el artefacto; Sonar NO puede, porque publica contra UNA projectKey y el segundo
    # pase reemplazaría el análisis del primero en el servidor. Así que se monta el padre y se
    # acota con las exclusiones del guion — pero se DICE, porque una cobertura acotada en
    # silencio es el mismo defecto que analizar de más en silencio.
    echo "sonar: AVISO — ${#ROOTS[@]} repositorios bajo SRC_PATH y una sola projectKey." >&2
    printf '       %s\n' "${ROOTS[@]}" >&2
    echo "       Se monta el padre: acota con sonar.sources/sonar.exclusions en el guion," >&2
    echo "       y declara en el informe qué quedó dentro y qué fuera." >&2
    printf '%s\n' "$SRC"
    ;;
esac
