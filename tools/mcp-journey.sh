#!/usr/bin/env bash
# Flujos de usuario en navegador, conducidos con el servidor MCP (Playwright) de esta máquina.
#
# NO es `make e2e`. Playwright (e2e) ejercita la API con specs headless y la matriz de
# autorización. Esto recorre la INTERFAZ como una persona —el SSO por el plugin, seleccionar un
# reporte, la vista previa, generar, descargar, programar— con dos objetivos:
#   1. validar que los flujos funcionan de punta a punta contra el despliegue real;
#   2. CONTRASTAR los hallazgos de las demás dimensiones con lo que de verdad ocurre en el
#      navegador (cabeceras, catch-all, token en la URL/localStorage, errores de la UI).
#
# Es CONDUCIDA: el laboratorio no puede invocar el MCP. Este script prepara el terreno (guion y
# carpeta de evidencia) y se niega a dar la dimensión por hecha sin artefacto — como device-e2e.
set -uo pipefail
TARGET="${1:?uso: mcp-journey.sh <target>}"
ENVFILE="targets/$TARGET/target.env"
[ -f "$ENVFILE" ] || { echo "no $ENVFILE"; exit 2; }
. "$(dirname "$0")/lib-env.sh"
BASE_URL=$(envget BASE_URL)
GUION="targets/$TARGET/mcp/flows.md"
OUT="reports/$TARGET/mcp"; mkdir -p "$OUT"

echo "== flujos en navegador (MCP): $TARGET =="
echo "   despliegue      : ${BASE_URL:-<sin BASE_URL>}"
echo "   guion de flujos : $GUION"
echo "   evidencia en    : $OUT/journeys.md"
echo
if [ ! -s "$GUION" ]; then
  echo "   No hay guion. Escribe los flujos a recorrer en $GUION (ver require-mcp.sh)."
  exit 1
fi
echo "   Flujos declarados en el guion:"
grep -E '^\s*[-*0-9]' "$GUION" | sed 's/^/     /' | head -30
echo
echo "   Recorre estos flujos con el servidor MCP del navegador (lo conduce el operador/agente),"
echo "   guardando por cada uno: URL, resultado, y los logs de consola/red relevantes, en"
echo "   $OUT/journeys.md. La dimensión NO cuenta como ejecutada hasta que ese archivo exista."
[ -s "$OUT/journeys.md" ] && echo "   [ya hay evidencia en $OUT/journeys.md]" || echo "   [aún sin evidencia]"
