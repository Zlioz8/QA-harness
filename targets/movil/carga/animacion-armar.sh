#!/usr/bin/env bash
# Arma la animación autocontenida: la plantilla + los datos de las corridas elegidas.
#   carga/animacion-armar.sh <salida.html> <paso:etiqueta> [<paso:etiqueta> ...]
#   p. ej. carga/animacion-armar.sh reports/movil/animacion/animacion.html "reports/movil/k6/runs/X/00200vus:1 proceso · 200 personas"
# Variable TELEFONO: carpeta de una corrida del teléfono (carga/telefono.sh) para la vista «una persona».
set -uo pipefail
SALIDA="${1:?uso: animacion-armar.sh <salida.html> <dir-del-paso:etiqueta> ...}"; shift
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp)"
{ echo "["; primero=1
  for par in "$@"; do d="${par%%:*}"; e="${par#*:}"
    [ $primero -eq 1 ] || echo ","; primero=0
    python3 "$AQUI/animacion-datos.py" "$d" "$e" ${TELEFONO:+--telefono "$TELEFONO"}
  done; echo "]"; } > "$TMP"
python3 - "$AQUI/animacion.html" "$TMP" "$SALIDA" <<'PY'
import sys
plantilla, datos, salida = sys.argv[1:4]
html = open(plantilla, encoding="utf-8").read().replace("/*DATOS*/", open(datos, encoding="utf-8").read().replace("</", "<\\/"))
open(salida, "w", encoding="utf-8").write(html)
print(f"animación: {salida} ({len(html)//1024} KB)")
PY
rm -f "$TMP"
