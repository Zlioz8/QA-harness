#!/usr/bin/env bash
# Deja la máquina en silencio para medir, y la devuelve a como estaba.
#
#   carga/silencio.sh poner    para los contenedores AJENOS a la prueba y la sincronización del
#                              Centro de Calificaciones, y apunta qué paró
#   carga/silencio.sh quitar   vuelve a levantar exactamente lo que paró
#   carga/silencio.sh ver      qué está parado por esta causa
#
# POR QUÉ. El generador y el sistema comparten este host. Todo lo demás que corra aquí entra en
# la cifra: el 2026-09-30, con seis usuarios, el PostgreSQL de Moodle marcaba medio núcleo… por
# `calificaciones-mongo.service`, que cada diez minutos lee esa base durante siete. Con eso
# encendido no se puede distinguir «la app satura la base» de «la sincronización coincidió».
#
# El cron de Moodle NO se para: en un servidor real también corre, y forma parte de lo medido.
# No para nada que no haya encontrado corriendo, y solo vuelve a levantar lo que él paró.
set -uo pipefail
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NOTA="$AQUI/.silencio-parados"
PROPIOS='^(movil_api-|seclab_)'
TIMER="calificaciones-mongo.timer"
SERVICIO="calificaciones-mongo.service"

case "${1:-ver}" in
  poner)
    [ -s "$NOTA" ] && { echo "silencio: ya estaba puesto (ver $NOTA). Usa 'quitar' primero." >&2; exit 1; }
    : > "$NOTA"
    for c in $(docker ps --format '{{.Names}}' | grep -Ev "$PROPIOS"); do
      docker stop "$c" >/dev/null && echo "contenedor $c" >> "$NOTA"
    done
    if systemctl is-active --quiet "$TIMER"; then
      sudo -n systemctl stop "$TIMER" "$SERVICIO" && echo "timer $TIMER" >> "$NOTA" \
        || echo "silencio: no se pudo parar $TIMER (hace falta sudo). La medición llevará ese ruido." >&2
    fi
    echo "silencio: parado —"; sed 's/^/  /' "$NOTA" ;;
  quitar)
    [ -f "$NOTA" ] || { echo "silencio: no hay nada apuntado."; exit 0; }
    while read -r clase nombre; do
      case "$clase" in
        contenedor) docker start "$nombre" >/dev/null && echo "  levantado $nombre" ;;
        timer) sudo -n systemctl start "$nombre" && echo "  reactivado $nombre" ;;
      esac
    done < "$NOTA"
    rm -f "$NOTA" ;;
  ver) [ -s "$NOTA" ] && cat "$NOTA" || echo "silencio: no está puesto." ;;
  *) echo "uso: silencio.sh poner|quitar|ver" >&2; exit 2 ;;
esac
