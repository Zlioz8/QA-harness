#!/usr/bin/env bash
# Contempla la dimensión de flujos en navegador (MCP) dentro del recorrido live.
#
# POR QUÉ EXISTE. Las dimensiones automáticas (ZAP, k6, Playwright) miden la aplicación desde
# fuera o desde la API. Pero varios modos de fallo solo aparecen recorriendo el flujo REAL con un
# navegador: la vista previa que devuelve 502, el token de sesión que acaba en localStorage, un
# reporte que depende de un esquema de BD no documentado. Eso lo conduce el servidor MCP del
# navegador que corre en esta máquina, no un contenedor.
#
# Este script NO ejecuta la navegación (el laboratorio no puede invocar el MCP): la CONTEMPLA.
# Igual que require-live/require-auth son precondiciones, esto avisa —al correr `make live`— de si
# los flujos de navegador se recorrieron y dejaron evidencia, para que su ausencia no pase por
# «sin hallazgos». No bloquea el resto del live; deja constancia.
set -uo pipefail
TARGET="${1:?uso: require-mcp.sh <target>}"
ENVFILE="targets/$TARGET/target.env"
[ -f "$ENVFILE" ] || { echo "no $ENVFILE"; exit 2; }
. "$(dirname "$0")/lib-env.sh"

# Declarable no-aplica, como cualquier dimensión (un backend sin interfaz de navegador).
NOAP=$(envget GUION_NO_APLICA)
case ",$NOAP," in *,mcp-journey,*)
  echo "mcp: dimensión de flujos en navegador declarada NO APLICA en el perfil — ok."; exit 0;;
esac

GUION="targets/$TARGET/mcp/flows.md"
ART="reports/$TARGET/mcp/journeys.md"

if [ ! -s "$GUION" ]; then
  cat <<EOF

  mcp: NO hay guion de flujos en 'targets/$TARGET/mcp/flows.md'.

  Esta dimensión recorre los FLUJOS reales del usuario con el servidor MCP del navegador y
  contrasta los hallazgos contra lo que pasa en vivo. Escribe la lista de flujos a recorrer
  (login/SSO, listar, vista previa, generar, descargar, programar) en ese archivo, o declara
  GUION_NO_APLICA=mcp-journey en el perfil si esta aplicación no tiene interfaz de navegador.

EOF
  exit 1
fi

if [ ! -s "$ART" ]; then
  cat <<EOF

  mcp: hay guion de flujos pero NO hay evidencia en 'reports/$TARGET/mcp/journeys.md'.

  Los flujos de navegador NO se han recorrido en esta ronda. No es «sin hallazgos»: es una
  dimensión viva no ejecutada. Recórrela con el servidor MCP (la conduce el operador/agente) y
  guarda la evidencia —logs de consola y de red, hallazgos por flujo— en ese archivo.
  'make mcp-journey TARGET=$TARGET' explica el procedimiento.

EOF
  exit 1
fi

echo "mcp: flujos de navegador recorridos — evidencia en $ART"
exit 0
