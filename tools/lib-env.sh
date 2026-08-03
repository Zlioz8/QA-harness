# shellcheck shell=bash
# The one reader of target.env. Source it; do not copy it.
#
# It existed six times, identical by hand, in doctor / tier / gate / run-manifest / secrets /
# require-live. Six copies of a parser are six chances to drift, and drift here is invisible:
# every consumer keeps answering, just about a slightly different file.
#
# NEVER `source` a target.env. Values contain unquoted spaces — SRC_PATH is literally
# `/opt/MANUALES DE DESPLIEGUE WITH REPORT/...` — and sourcing turns the tail of that path into
# a command. A target profile is data, not code, and one written by someone else is untrusted data.
#
# THE PART THAT BITES: this strips ` # trailing comments`; `docker compose --env-file` does NOT.
# So `QODANA_IMAGE=  # not applicable` reads as empty here and as the literal string
# `# not applicable` inside compose, which then tries to pull an image by that name. Same file,
# two meanings. Until compose changes, the rule is: no inline comments in target.env. doctor.sh
# enforces it, and this is the reason.
#
# OVERRIDE LOCAL: <archivo>.local gana, si existe y si trae la clave con un valor no vacío.
# Es la contraparte de los dos `--env-file` que pasa el Makefile — sin esto, compose y las
# herramientas leerían perfiles distintos, que es exactamente el desacuerdo que este módulo
# existe para impedir. Un valor VACÍO en el .local no anula: `QODANA_IMAGE=` en el contrato
# significa "no aplica, salto documentado", y un .local incompleto no debe convertir eso en otra
# cosa. Para tapar una clave, se le da valor; para heredarla, se omite.
_envget1() {
  sed -n "s/^${1}=//p" "$2" 2>/dev/null | tail -1 \
    | sed -E 's/[[:space:]]+#.*$//; s/^[[:space:]]+//; s/[[:space:]]+$//; s/^"//; s/"$//'
}

envget() {
  local f v
  f="${2:-$ENVFILE}"
  if [ -f "$f.local" ]; then
    v=$(_envget1 "$1" "$f.local")
    [ -n "$v" ] && { printf '%s\n' "$v"; return; }
  fi
  _envget1 "$1" "$f"
}

# Every line whose value carries an inline comment — the divergence above, made visible.
env_inline_comments() {
  grep -nE '^[A-Za-z_][A-Za-z0-9_]*=[^#]*[[:space:]]+#' "${1:-$ENVFILE}" 2>/dev/null \
    | cut -d: -f1,2 | sed 's/=.*//'
}
