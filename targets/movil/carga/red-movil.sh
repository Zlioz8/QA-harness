#!/usr/bin/env bash
# Red móvil emulada entre el equipo de pruebas y el teléfono.
#
# El teléfono del laboratorio llega a la API por el Wi-Fi del equipo de pruebas: unos 40-80 ms de ida
# y vuelta y sin pérdida. Una persona con datos móviles tiene más retardo, variación y algo de
# pérdida. Esto se lo añade a lo que SALE hacia el teléfono por la interfaz que se indique (netem):
# es una aproximación de un solo sentido, y se dice así en el informe.
#
#   carga/red-movil.sh poner     RED_RETARDO=80ms RED_VARIACION=20ms RED_PERDIDA=1% RED_TASA=10mbit
#   carga/red-movil.sh quitar
#   carga/red-movil.sh ver
#
# RED_IF: la interfaz por la que sale el tráfico hacia el teléfono (la del punto de acceso). Va en el
# target.env del perfil, que no se versiona. Pide sudo: cambia la cola de esa interfaz y nada más;
# `quitar` la deja como estaba.
set -uo pipefail
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; LAB="$(cd "$AQUI/../../.." && pwd)"
envget() { grep -E "^$1=" "$LAB/targets/movil/target.env" 2>/dev/null | tail -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*$//'; }
IF="${RED_IF:-$(envget RED_IF)}"
[ -n "$IF" ] || { echo "red-movil: falta RED_IF (la interfaz hacia el teléfono), en el entorno o en target.env" >&2; exit 2; }
case "${1:-ver}" in
  poner)
    sudo -n tc qdisc replace dev "$IF" root netem delay "${RED_RETARDO:-80ms}" "${RED_VARIACION:-20ms}" loss "${RED_PERDIDA:-1%}" rate "${RED_TASA:-10mbit}" \
      || { echo "red-movil: no se pudo poner (¿sudo? ¿tc?)" >&2; exit 1; }
    tc qdisc show dev "$IF" ;;
  quitar)
    sudo -n tc qdisc del dev "$IF" root 2>/dev/null || true
    tc qdisc show dev "$IF" ;;
  ver) tc qdisc show dev "$IF" ;;
  *) echo "uso: red-movil.sh poner|quitar|ver" >&2; exit 2 ;;
esac
