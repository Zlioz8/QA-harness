#!/usr/bin/env bash
# Qué imagen de Qodana aplica a este perfil, resuelta desde LANGS.
#
# El problema que arregla: `QODANA_IMAGE` nace vacío en la plantilla, y vacío significa "salto
# declarado". Consecuencia medida: los CUATRO perfiles versionados lo tenían vacío y la dimensión
# de calidad de Qodana nunca corrió en ningún proyecto — reports/*/qodana/report/ vacío desde el
# primer día. Un campo que hay que rellenar a mano, con el nombre exacto de una imagen que además
# depende de la licencia, no se rellena nunca.
#
# Así que el perfil ya no tiene que saberlo: declara LANGS (que `make detect` propone) y aquí se
# resuelve el linter. QODANA_IMAGE sigue existiendo y sigue ganando: es el escape para fijar una
# imagen concreta o para desactivar la dimensión a propósito (QODANA_IMAGE=none).
#
# La otra mitad del problema es la licencia. JetBrains publica DOS familias:
#
#   *-community  corren sin token. Solo existen para python, jvm y android.
#   release      php, js, go, dotnet... rechazan arrancar sin QODANA_TOKEN (Qodana Cloud).
#
# Por eso un proyecto PHP no puede "simplemente correr Qodana": no hay imagen gratuita que lo
# analice. Eso NO es un fallo del laboratorio y no debe reportarse como salto silencioso — es
# NO DISPONIBLE con su razón, y la calidad de ese proyecto la cubren SonarQube y semgrep, que sí
# son agnósticos. Decirlo en voz alta es la diferencia entre una cobertura conocida y un hueco.
#
# STDOUT: el nombre de la imagen, o nada.   STDERR: la razón, siempre.
#   0  hay imagen que correr
#   3  NO DISPONIBLE (no hay linter aplicable con la licencia disponible)
#   4  desactivado a propósito por el perfil (QODANA_IMAGE=none)
set -uo pipefail

TARGET="${1:?uso: qodana-image.sh <target>}"
ENVFILE="targets/$TARGET/target.env"
[ -f "$ENVFILE" ] || { echo "qodana: no existe $ENVFILE" >&2; exit 3; }

. "$(dirname "$0")/lib-env.sh"   # un solo parser de target.env — ver el archivo

IMAGE=$(envget QODANA_IMAGE)
LANGS=$(envget LANGS)
TOKEN=$(envget QODANA_TOKEN)
[ -n "${QODANA_TOKEN:-}" ] && TOKEN="$QODANA_TOKEN"   # el entorno del operador también vale

log() { echo "qodana: $*" >&2; }

# 1) El perfil manda, en los dos sentidos.
if [ "$IMAGE" = "none" ]; then
  log "QODANA_IMAGE=none — dimensión desactivada a propósito en este perfil."
  exit 4
fi
if [ -n "$IMAGE" ]; then
  log "QODANA_IMAGE fijado en el perfil: $IMAGE"
  printf '%s' "$IMAGE"
  exit 0
fi

# 2) Resolver por lenguaje. El orden es la preferencia cuando el proyecto es poliglota, y está
#    puesto a propósito: primero lo que corre sin licencia. Una imagen que arranca y analiza medio
#    proyecto vale más que una que no arranca porque falta un token que nadie va a comprar hoy.
#
#    formato: <lang>:<imagen>:<community|licensed>
LINTERS="
py:jetbrains/qodana-python-community:latest:community
java:jetbrains/qodana-jvm-community:latest:community
kt:jetbrains/qodana-jvm-community:latest:community
android:jetbrains/qodana-android-community:latest:community
php:jetbrains/qodana-php:latest:licensed
js:jetbrains/qodana-js:latest:licensed
ts:jetbrains/qodana-js:latest:licensed
go:jetbrains/qodana-go:latest:licensed
cs:jetbrains/qodana-dotnet:latest:licensed
"

if [ -z "$LANGS" ]; then
  log "LANGS vacío y QODANA_IMAGE sin fijar: no hay con qué elegir linter."
  log "      Ejecuta 'make detect TARGET=$TARGET' y copia el LANGS que propone. NO DISPONIBLE."
  exit 3
fi

# Normaliza "py, php , js" -> " py php js "
WANTED=" $(echo "$LANGS" | tr ',' ' ' | tr -s ' ' | sed 's/^ //; s/ $//') "

pick() {   # $1 = community | licensed
  echo "$LINTERS" | while IFS= read -r row; do
    [ -z "$row" ] && continue
    lang=${row%%:*}; rest=${row#*:}
    kind=${rest##*:}; img=${rest%:*}
    [ "$kind" = "$1" ] || continue
    case "$WANTED" in *" $lang "*) echo "$img:$lang"; return 0;; esac
  done | head -1
}

HIT=$(pick community)
if [ -n "$HIT" ]; then
  img=${HIT%:*}; lang=${HIT##*:}
  log "linter community para '$lang' (sin token): $img"
  # Un proyecto poliglota queda cubierto a medias por Qodana. Callarlo convierte una cobertura
  # parcial en una aparentemente total, que es el modo de fallo que este laboratorio persigue.
  case "$WANTED" in *" "*" "*" "*)
    log "      Proyecto poliglota: Qodana inspecciona UN lenguaje por imagen ('$lang')."
    log "      El resto lo cubren SonarQube y semgrep. Decláralo así en el informe." ;;
  esac
  printf '%s' "$img"
  exit 0
fi

HIT=$(pick licensed)
if [ -n "$HIT" ]; then
  img=${HIT%:*}; lang=${HIT##*:}
  if [ -n "$TOKEN" ]; then
    log "linter con licencia para '$lang' (usa QODANA_TOKEN): $img"
    printf '%s' "$img"
    exit 0
  fi
  log "el único linter de Qodana para '$lang' es de pago ($img) y no hay QODANA_TOKEN."
  log "      JetBrains no publica imagen community para ese lenguaje: no es algo que el"
  log "      laboratorio pueda sortear. NO DISPONIBLE — no es un PASS ni un 'sin hallazgos'."
  log "      La calidad de este proyecto la cubren 'make sonar' y 'make semgrep'."
  log "      Con licencia de Qodana Cloud: pon QODANA_TOKEN en targets/$TARGET/target.env.local"
  exit 3
fi

log "ningún linter de Qodana cubre LANGS='$LANGS'. NO DISPONIBLE."
exit 3
