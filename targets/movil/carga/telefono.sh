#!/usr/bin/env bash
# El teléfono como instrumento: engancha el WebView de la app por CDP y conduce recorridos
# reales mientras anota cada petición vista DESDE EL TELÉFONO (inicio, fin, estado, tiempo del
# servidor). Con el mismo `rid`, el log de nginx y el `[ws]` del backend completan la cadena.
#
#   carga/telefono.sh <salida> [recorridos] [repeticiones]      p. ej. carga/telefono.sh reports/movil/telefono/idle "arranque,curso,calificaciones" 5
#   carga/telefono.sh <salida> dom                             vuelca qué hay en pantalla (para escribir recorridos)
#
# Solo para el destino LOCAL de la app (WEBVIEW_DEBUG=true). El teléfono tiene que estar en la
# red del backend (hotspot 10.42.0.1) y con la app instalada.
set -uo pipefail
SALIDA="${1:?uso: telefono.sh <salida> [recorridos|dom] [repeticiones]}"
RECORRIDOS="${2:-arranque,inicio,cursos,curso,calificaciones,calendario,notificaciones}"
REPES="${3:-3}"
APP="${MOBILE_PACKAGE:-io.ionic.starter.local}"
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SERIAL="${ANDROID_SERIAL:-$(adb devices | awk -F'\t' 'NR>1 && $2=="device" {print $1}' | head -1)}"
[ -n "$SERIAL" ] || { echo "telefono: no hay dispositivo (adb devices)" >&2; exit 2; }
adb() { command adb -s "$SERIAL" "$@"; }

mkdir -p "$SALIDA"
PID=$(adb shell pidof "$APP" 2>/dev/null | tr -d '\r' | awk '{print $1}')
if [ -z "$PID" ]; then
  # Traer la app al frente sin tocar la pantalla: quien tenga Ajustes abierto no quiere sorpresas.
  adb shell monkey -p "$APP" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
  for _ in $(seq 1 20); do PID=$(adb shell pidof "$APP" 2>/dev/null | tr -d '\r' | awk '{print $1}'); [ -n "$PID" ] && break; sleep 1; done
  sleep 4
fi
[ -n "$PID" ] || { echo "telefono: la app $APP no arranca" >&2; exit 2; }

adb forward --remove tcp:9223 >/dev/null 2>&1 || true
adb forward tcp:9223 "localabstract:webview_devtools_remote_$PID" >/dev/null || { echo "telefono: sin socket de depuración (¿WEBVIEW_DEBUG=true?)" >&2; exit 2; }
WS=$(curl -s --max-time 5 http://127.0.0.1:9223/json | python3 -c '
import json,sys
for p in json.load(sys.stdin):
    if p.get("type")=="page" and p.get("webSocketDebuggerUrl"): print(p["webSocketDebuggerUrl"]); break')
[ -n "$WS" ] || { echo "telefono: el WebView no expone ninguna página por CDP" >&2; exit 2; }

{
  echo "modelo: $(adb shell getprop ro.product.model | tr -d '\r') · android $(adb shell getprop ro.build.version.release | tr -d '\r')"
  echo "app: $APP $(adb shell dumpsys package "$APP" | grep -m1 versionName | tr -d ' \r') instalada $(adb shell dumpsys package "$APP" | grep -m1 lastUpdateTime | sed 's/.*=//' | tr -d '\r')"
  echo "red: $(adb shell ip -4 addr show wlan0 2>/dev/null | grep -o 'inet [0-9.]*' | tr -d '\r')"
  echo "hora teléfono: $(adb shell date -Is | tr -d '\r') · hora host: $(date -Is)"
} > "$SALIDA/telefono.txt"

# La cuenta del teléfono: la de aprendiz del perfil (ROLE_B), la misma de la matriz de autorización.
ENVFILE="$AQUI/../target.env"; . "$AQUI/../../../tools/lib-env.sh"
TEL_USUARIO="${TEL_USUARIO:-$(envget ROLE_B_USER)}" TEL_CLAVE="${TEL_CLAVE:-$(envget ROLE_B_PASS)}" \
CDP_WS="$WS" SALIDA="$SALIDA" RECORRIDOS="$RECORRIDOS" REPES="$REPES" node "$AQUI/telefono.js"
