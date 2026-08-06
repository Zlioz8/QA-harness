#!/usr/bin/env bash
# Precondition for every [live] goal: refuse to measure when there is nothing to measure.
#
# This exists because of the single worst failure mode in the whole lab: a clean ZAP report
# against an application that is DOWN looks exactly like a clean report against an application
# that is secure. Same for k6 happily reporting the latency of connection refusals. Both produce
# a green artifact, and a green artifact is what ends up in the report.
#
# So: check first, and when it fails, say which of the three causes it is — because the fix is
# different for each one, and "connection refused" alone sends people to the wrong one.
set -uo pipefail

TARGET="${1:?usage: require-live.sh <target>}"
ENVFILE="targets/$TARGET/target.env"
[ -f "$ENVFILE" ] || { echo "no $ENVFILE"; exit 2; }

# Never source a target profile: values contain spaces, and a profile is data, not code.
. "$(dirname "$0")/lib-env.sh"   # one parser for target.env — see the file for why

BASE_URL=$(envget BASE_URL)
HEALTH_PATH=$(envget HEALTH_PATH)
RUNTIME="targets/$TARGET/compose.runtime.yml"

if [ -z "$BASE_URL" ] || [ -z "$HEALTH_PATH" ]; then
  cat <<EOF

  This goal needs a running application, and the profile does not say where it is.

  Set in $ENVFILE:
    BASE_URL=http://localhost:8080     where the application answers (as seen from THIS host)
    HEALTH_PATH=/health                a path that returns 200 only when it is really serving

  Without HEALTH_PATH there is no way to tell "no findings" apart from "nothing was running",
  which is the difference between an audit and a decoration.

EOF
  exit 2
fi

HEALTH_EXPECT=$(envget HEALTH_EXPECT)

# HEALTH_PATH puede ser una URL COMPLETA. Un sistema no siempre tiene una sola puerta: en
# antiplagio, BASE_URL es el Moodle (que es lo que conduce Playwright) y el health de verdad vive
# en la API FastAPI, otro servicio en otro puerto. Concatenar a la fuerza obligaba a elegir una de
# las dos y comprobar la que no era.
case "$HEALTH_PATH" in
  http://*|https://*) URL="$HEALTH_PATH" ;;
  *)                  URL="${BASE_URL%/}${HEALTH_PATH}" ;;
esac

# -k: los despliegues locales sirven habitualmente un certificado autofirmado (el nginx de este
# stack lo hace). Todos los escáneres del lab ya ponen ignoreHTTPSErrors; la sonda de vida debe
# hacer lo mismo, o una app https sana se lee como "no respondió nada" (000) y el pipeline en vivo
# aborta por un certificado.
probe() { curl -sk --max-time 10 -w '\n%{http_code}' "$1" 2>/dev/null; }

RESP=$(probe "$URL")
CODE="${RESP##*$'\n'}"
BODY="${RESP%$'\n'*}"

if [ "$CODE" = "200" ]; then
  # UN 200 NO ES PRUEBA DE NADA POR SÍ SOLO.
  #
  # Encontrado apuntando el laboratorio al despliegue real del servidor 166: su nginx devuelve la
  # MISMA página de 37.714 bytes para /zajuna/health, para /zajuna/esto-no-existe-xyz123 y para
  # cualquier ruta inventada. La sonda daba 200, el lab declaraba "la aplicación responde: todas
  # las dimensiones en vivo disponibles", y lo habría declarado igual con la API caída.
  #
  # Es EXACTAMENTE el fallo que describe la cabecera de este archivo: un informe verde sobre una
  # aplicación que no estaba. Un catch-all convierte HEALTH_PATH en decoración.
  #
  # Se detecta solo, sin configuración nueva: se pide una ruta que no puede existir y se compara.
  # Si contesta lo mismo, la comprobación no prueba nada.
  case "$URL" in
    */) DECOY="${URL}__seclab_probe_$$_no_existe" ;;
    *)  DECOY="${URL%/*}/__seclab_probe_$$_no_existe" ;;
  esac
  DRESP=$(probe "$DECOY")
  DCODE="${DRESP##*$'\n'}"
  DBODY="${DRESP%$'\n'*}"

  if [ "$DCODE" = "200" ] && [ "$DBODY" = "$BODY" ]; then
    echo
    echo "  ABORTADO: $URL -> 200, pero NO PRUEBA NADA."
    echo
    echo "  Una ruta inventada devuelve exactamente lo mismo:"
    echo "    $DECOY -> $DCODE, cuerpo idéntico ($(printf '%s' "$BODY" | wc -c) bytes)"
    echo
    echo "  Es un catch-all: este servidor responde 200 a todo bajo esa ruta, así que la sonda"
    echo "  daría verde con la aplicación caída. Eso es justo lo que HEALTH_PATH existe para"
    echo "  evitar — sin él no se distingue «sin hallazgos» de «no había nada corriendo»."
    echo
    echo "  Arréglalo de una de estas dos formas:"
    echo "    1. Apunta HEALTH_PATH a un endpoint de salud DE VERDAD. Admite una URL completa,"
    echo "       así que puede ser otro servicio y otro puerto que BASE_URL — útil cuando el"
    echo "       sistema tiene dos puertas (un CMS y su API, por ejemplo):"
    echo "         HEALTH_PATH=http://<host-de-la-api>:<puerto>/health"
    echo "    2. Exige contenido, no solo código, con:"
    echo "         HEALTH_EXPECT={\"status\":\"ok\"}"
    echo
    exit 1
  fi

  # Comprobación de contenido, opcional pero recomendada: es la única que sobrevive a un proxy
  # que interpone su propia página de error con código 200.
  if [ -n "$HEALTH_EXPECT" ] && ! printf '%s' "$BODY" | grep -qF -- "$HEALTH_EXPECT"; then
    echo
    echo "  ABORTADO: $URL -> 200, pero el cuerpo no contiene HEALTH_EXPECT."
    echo
    echo "    esperado: $HEALTH_EXPECT"
    echo "    recibido: $(printf '%s' "$BODY" | head -c 120)"
    echo
    echo "  Un 200 con el cuerpo equivocado suele ser un proxy o una página de error que no"
    echo "  supo devolver un 5xx. La aplicación NO está sirviendo lo que dice servir."
    echo
    exit 1
  fi

  echo "live check: $URL -> 200${HEALTH_EXPECT:+ (contiene «$HEALTH_EXPECT»)}"
  echo "            ruta inventada -> ${DCODE:-000}: la comprobación distingue de verdad"
  exit 0
fi

echo
echo "  ABORTED: $URL -> ${CODE:-000}"
echo

if [ "$CODE" = "000" ]; then
  # Nothing answered. Two very different causes, and people reliably guess the wrong one.
  echo "  Nothing answered. Two possible causes:"
  echo
  if [ -f "$RUNTIME" ]; then
    echo "   a) The application is not up. This profile has a runtime recipe, so:"
    echo "        make up TARGET=$TARGET"
    echo "      A first boot can take a couple of minutes; watch it with:"
    echo "        make status TARGET=$TARGET"
  else
    echo "   a) Your deployment is not running. Start it however you normally do — the lab"
    echo "      does not manage it. This profile has no compose.runtime.yml, which is the"
    echo "      normal case when you point the lab at your own deployment."
  fi
  echo
  echo "   b) It IS running, but the tools cannot reach it from their network. ZAP and k6 run"
  echo "      inside the compose network, so 'localhost' there means the tool's own container,"
  echo "      not your machine. For an application deployed on this host, use:"
  echo "        APP_INTERNAL_URL=http://host.docker.internal:<port>"
  echo "      (BASE_URL stays as localhost: Playwright runs on the host network.)"
else
  echo "  It answered, but with ${CODE} instead of 200. Either the application is unhealthy,"
  echo "  or HEALTH_PATH points somewhere that is not a health check — a redirect or a login"
  echo "  page will happily return 302/401 forever without telling you anything."
  echo
  echo "  Verify by hand:  curl -i '$URL'"
fi
echo
exit 1
