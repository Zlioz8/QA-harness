#!/usr/bin/env bash
# Recoge en UN rastro legible lo que un recorrido de navegador MCP deja disperso: red, consola,
# snapshots y estado de sesión. Nació de la R2 de anuncios_de_plataforma, donde validar el
# informe contra el flujo exigía correlacionar a mano archivos de tres tipos en .playwright-mcp/.
#
# QUÉ RESUELVE. El MCP de Playwright ya expone las tres capas que hacen falta para diagnosticar
# "qué pasa a nivel de red y de sesión":
#   · red      -> browser_network_requests  (método, URL, código, Set-Cookie, redirecciones)
#   · consola  -> browser_console_messages  (errores JS, 404/403 que el front registra)
#   · sesión   -> el sesskey y las cookies que aparecen en el HTML servido / storageState
# pero las deja en ficheros sueltos con marca de tiempo. Esto los une por sesión y los deja junto
# al target, no en el sandbox del navegador.
#
# Uso:  tools/mcp-traza.sh <target> [etiqueta]
#   recoge los .log y .yml recientes del directorio del MCP en
#   reports/<target>/mcp-evidencia/, y produce un índice cronológico.
set -uo pipefail
TARGET="${1:?usage: mcp-traza.sh <target> [etiqueta]}"
ETQ="${2:-$(date +%H%M%S)}"
# El MCP escribe bajo su raíz permitida (el workspace del navegador), no bajo SECURITY-LAB.
MCP_DIR="${MCP_DIR:-$HOME/MANUALES DE DESPLIEGUE WITH REPORT/ANALITICA NOTIFICACIONES/.playwright-mcp}"
DST="reports/$TARGET/mcp-evidencia"
mkdir -p "$DST"

[ -d "$MCP_DIR" ] || { echo "no existe $MCP_DIR — ¿corrió algún flujo MCP?"; exit 2; }

# Traer los artefactos de la última hora (una sesión de validación típica).
n=0
while IFS= read -r f; do cp "$f" "$DST/" && n=$((n+1)); done < <(find "$MCP_DIR" -maxdepth 1 \( -name '*.log' -o -name '*.yml' -o -name '*.txt' \) -mmin -60 2>/dev/null)

# Índice cronológico: qué se capturó y cuándo. Es el "log de acciones" legible.
IDX="$DST/INDICE_$ETQ.md"
{
  echo "# Rastro MCP — $TARGET — $ETQ ($(date -Is))"
  echo
  echo "| Hora | Tipo | Archivo | Primera línea / pista |"
  echo "|---|---|---|---|"
  for f in $(ls -t "$DST"/*.log "$DST"/*.yml "$DST"/*.txt 2>/dev/null); do
    b=$(basename "$f")
    case "$b" in console-*) t="consola";; page-*) t="snapshot";; *) t="dato";; esac
    hora=$(echo "$b" | grep -oE 'T[0-9]{2}-[0-9]{2}-[0-9]{2}' | head -1 | tr '-' ':' | sed 's/T//')
    pista=$(head -c 90 "$f" 2>/dev/null | tr '\n' ' ' | sed 's/|/ /g')
    printf '| %s | %s | `%s` | %s |\n' "${hora:-—}" "$t" "$b" "$pista"
  done
} > "$IDX"

echo "recogidos $n artefacto(s) en $DST"
echo "índice: $IDX"
