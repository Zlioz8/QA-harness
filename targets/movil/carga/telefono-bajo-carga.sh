#!/usr/bin/env bash
# El teléfono real mientras N personas sintéticas cargan el servidor: qué siente la persona.
#
#   carga/telefono-bajo-carga.sh <etiqueta> <pasos> [recorridos] [repeticiones]
#   p. ej. carga/telefono-bajo-carga.sh 1proc "100 200"
#
# Lanza la escalera de carga en segundo plano y, en la meseta de cada paso, conduce el teléfono
# (carga/telefono.sh). Deja reports/movil/telefono/<fecha>/<etiqueta>-<paso>vus/ por paso.
set -uo pipefail
ETIQUETA="${1:?uso: telefono-bajo-carga.sh <etiqueta> <pasos> [recorridos] [repeticiones]}"
PASOS="${2:?faltan los pasos}"
RECORRIDOS="${3:-arranque,inicio,cursos,curso,calificaciones,calendario,notificaciones}"
REPES="${4:-3}"
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB="$(cd "$AQUI/../../.." && pwd)"
cd "$LAB"
FECHA="$(date +%Y%m%d)"
OUT="reports/movil/telefono/$FECHA"
mkdir -p "$OUT"
LOG="$OUT/escalera-$ETIQUETA.log"

# La meseta tiene que dar para las repeticiones del teléfono (unos 40 s cada vuelta completa).
ESCALERA_PASOS="$PASOS" ESCALERA_MESETA="${ESCALERA_MESETA:-4m}" ESCALERA_SIGUE="${ESCALERA_SIGUE:-9}" \
  ESCALERA_NOTA="${ESCALERA_NOTA:-Escalera con el teléfono real conduciendo recorridos en cada meseta ($ETIQUETA)}" \
  make perf-escalera TARGET=movil >"$LOG" 2>&1 &
ESC=$!
trap 'kill $ESC 2>/dev/null' INT TERM

for VUS in $PASOS; do
  # Esperar a que empiece el paso, y luego a que pase la rampa (setup + 30 s + margen).
  for _ in $(seq 1 600); do grep -q "── paso $VUS usuarios" "$LOG" && break; sleep 2; done
  sleep $(( 45 + VUS / 20 ))
  echo "── teléfono en la meseta de $VUS personas ($(date +%H:%M:%S))"
  targets/movil/carga/telefono.sh "$OUT/$ETIQUETA-$(printf '%05d' "$VUS")vus" "$RECORRIDOS" "$REPES" 2>&1 | grep -v "^  [0-9]*/[0-9]* "
done
wait $ESC
echo "escalera terminada: $(grep -E 'QUIEBRE|terminó' "$LOG" | tail -1)"
