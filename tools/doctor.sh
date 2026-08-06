#!/usr/bin/env bash
# Preflight. Catches the failures that otherwise surface halfway through a run as an
# unreadable tool error: no disk, port taken, reports/ not writable by a tool's UID.
set -uo pipefail
TARGET="${1:?usage: doctor.sh <target>}"
ENVFILE="targets/$TARGET/target.env"
FAIL=0
ok()   { printf '  \033[32mok\033[0m    %s\n' "$1"; }
warn() { printf '  \033[33mwarn\033[0m  %s\n' "$1"; }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAIL=1; }

echo "== doctor: $TARGET =="

docker --version >/dev/null 2>&1 && ok "docker: $(docker --version | cut -d, -f1)" || bad "docker not available"
docker compose version >/dev/null 2>&1 && ok "compose: $(docker compose version --short 2>/dev/null)" || bad "docker compose v2 not available"

# Read target.env WITHOUT sourcing it. Sourcing breaks on any unquoted value containing
# spaces (a path like /opt/MANUALES DE DESPLIEGUE/... silently becomes a command), and it
# would also execute whatever a target profile happens to contain.
. "$(dirname "$0")/lib-env.sh"   # one parser for target.env — see the file for why
SRC_PATH=$(envget SRC_PATH)
ROLE_A_USER=$(envget ROLE_A_USER); ROLE_B_USER=$(envget ROLE_B_USER)
AUTH_ADAPTER=$(envget AUTH_ADAPTER); HEALTH_PATH=$(envget HEALTH_PATH); BASE_URL=$(envget BASE_URL)
SONAR_PORT=$(envget SONAR_PORT); APP_PORT=$(envget APP_PORT)
FRONTEND_PORT=$(envget FRONTEND_PORT); PROD_PORT=$(envget PROD_PORT); MOODLE_PORT=$(envget MOODLE_PORT)

[ -n "${SRC_PATH:-}" ] && [ -d "${SRC_PATH:-}" ] && ok "SRC_PATH: $SRC_PATH" || bad "SRC_PATH missing or not a directory: ${SRC_PATH:-<unset>}"
# A project is not always one checkout. MOVIL is two repos under a parent that is not one, and a
# check that only asked for `$SRC_PATH/.git` warned "no git history" about a fully versioned
# project — sending the operator to fix something that was not broken. Same discovery rule as
# tools/secrets.sh and tools/run-manifest.sh: the parent, or one level of children.
if [ -d "${SRC_PATH:-}/.git" ]; then
  ok "git history present (secret scanning is meaningful)"
else
  _repos=(); for _d in "${SRC_PATH:-.}"/*/; do [ -d "$_d.git" ] && _repos+=("$(basename "$_d")"); done
  if [ "${#_repos[@]}" -gt 0 ]; then
    ok "git history present in ${#_repos[@]} sub-repos: ${_repos[*]}"
  else
    warn "no .git in SRC_PATH nor in its subdirectories — gitleaks/trufflehog will only see the working tree"
  fi
fi

# Two accounts of different privilege. Without them the authorization matrix is untestable,
# and an audit that skips authorization is not an audit.
if [ -n "${ROLE_A_USER:-}" ] && [ -n "${ROLE_B_USER:-}" ] && [ "${ROLE_A_USER:-}" != "${ROLE_B_USER:-}" ]; then
  ok "two roles configured (${ROLE_A_USER} / ${ROLE_B_USER})"
else
  warn "ROLE_A_/ROLE_B_ not both set — static analysis still runs; authz testing cannot"
fi
[ -n "${AUTH_ADAPTER:-}" ] && [ "${AUTH_ADAPTER}" != none ] && ok "auth adapter: $AUTH_ADAPTER" \
  || warn "AUTH_ADAPTER=none — e2e/perf will run unauthenticated only"
[ -n "${HEALTH_PATH:-}" ] && ok "health path: ${BASE_URL:-}${HEALTH_PATH}" \
  || warn "HEALTH_PATH unset — nothing tells you the runtime is really up"

# Disk, in BOTH units — they fail for different reasons and one does not imply the other.
#  - absolute: the tool images are ~8 GB and a run that hits 100% leaves half-written reports.
#  - percentage: SonarQube's embedded Elasticsearch applies a "flood stage watermark" at 95%
#    USED and marks every index read-only, so the scan dies with an opaque 408 even when
#    ~10 GB are still free. Learned the hard way; without this check the failure is a
#    30-minute detour into Elasticsearch stack traces.
AVAIL=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
PCT=$(df --output=pcent / | tail -1 | tr -dc '0-9')
[ "${AVAIL:-0}" -ge 20 ] && ok "disk free: ${AVAIL}G" \
  || warn "disk free: ${AVAIL}G — tool images need ~8G; consider 'docker system prune'"
if [ "${PCT:-0}" -lt 90 ]; then ok "disk used: ${PCT}%"
elif [ "${PCT:-0}" -lt 95 ]; then
  bad "disk used: ${PCT}% — SonarQube WILL fail: its Elasticsearch high watermark (90%) stops"
  echo "        shard allocation, the index never turns yellow, and the scanner dies with an"
  echo "        opaque '408 Request Timeout'. Free space until below 90%; extra GB do not help."
else
  bad "disk used: ${PCT}% — past the flood-stage watermark (95%): indices go read-only. Any"
  echo "        SonarQube run is futile until the filesystem drops below 90%."
fi

# ---- memory ---------------------------------------------------------------------------------
# Added after a run froze the operator's desktop for ~21 minutes (PSI full stall) and the kernel
# OOM-killed VSCode and Chrome — not the tools. The lab's heavy dimensions are servers and JVMs
# (SonarQube runs three processes, MobSF is a Django app with analysers, ZAP and Gradle are JVMs),
# and they compete for RAM with whatever the operator is working in. Disk was checked here from
# the start; memory was not, and memory is what actually stops the machine.
MEM_AVAIL=$(awk '/MemAvailable/{printf "%d", $2/1048576}' /proc/meminfo 2>/dev/null)
MEM_TOTAL=$(awk '/MemTotal/{printf "%d", $2/1048576}' /proc/meminfo 2>/dev/null)
if [ "${MEM_AVAIL:-0}" -ge 6 ]; then
  ok "memory available: ${MEM_AVAIL}G of ${MEM_TOTAL}G"
elif [ "${MEM_AVAIL:-0}" -ge 3 ]; then
  warn "memory available: ${MEM_AVAIL}G of ${MEM_TOTAL}G — run the heavy dimensions ONE at a time"
  echo "        (static, mobile-scan and dast each hold a server or a JVM; together they do not fit)"
else
  bad "memory available: ${MEM_AVAIL}G of ${MEM_TOTAL}G — not enough to run a dimension safely."
  echo "        Below ~3G the machine thrashes and the OOM killer picks the biggest process, which"
  echo "        is usually the editor or the browser, not the tool. Close something, or run"
  echo "        'make down TARGET=<other>' on profiles you are not auditing right now."
fi

# Swap already in use is the better warning sign: it means the machine has been over its RAM for
# a while. On a zram setup the compressed pages live in RAM, so heavy swap costs RAM *and* CPU.
SWAP_USED=$(free -g 2>/dev/null | awk '/^Swap:/{print $3}')
SWAP_TOTAL=$(free -g 2>/dev/null | awk '/^Swap:/{print $2}')
if [ "${SWAP_TOTAL:-0}" -gt 0 ] && [ "${SWAP_USED:-0}" -ge $((SWAP_TOTAL / 2)) ]; then
  warn "swap in use: ${SWAP_USED}G of ${SWAP_TOTAL}G — the host is already over its RAM budget"
  [ -e /sys/block/zram0 ] && echo "        (zram: those pages sit compressed in RAM, so they cost memory and CPU both)"
fi

# ---- other profiles still running -------------------------------------------------------------
# A dimension that finished can leave a server up (SonarQube, MobSF), and a session that ended
# badly leaves containers running for days. Both are invisible until the machine runs out of
# memory mid-audit, so name them here while there is still a choice.
if command -v docker >/dev/null 2>&1; then
  others=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -E '^seclab_' | grep -v "^seclab_${TARGET}-" | tr '\n' ' ')
  [ -n "${others// }" ] && warn "lab containers of OTHER profiles are up: ${others}— 'make down TARGET=<profile>' frees their memory"
  # Long-lived tool containers with no compose project: typically a script that ran outside the
  # Makefile and whose session is gone. Three of these (Playwright, two days old) were behind the
  # freeze that motivated this check.
  strays=$(docker ps --format '{{.Names}}\t{{.Image}}\t{{.RunningFor}}' 2>/dev/null \
    | grep -E 'playwright|zap|k6|mobsf|semgrep|trivy' | grep -vE '^seclab_' | grep -E 'days|day' | cut -f1 | tr '\n' ' ')
  [ -n "${strays// }" ] && warn "tool containers running for days outside any profile: ${strays}— likely orphans from a finished session"
fi

# Ports, bound to loopback only (lab finding L1).
#
# Two listeners, two ways of seeing them. `ss` reports this namespace's sockets: right on the
# host, blind in a container — and `make doctor` DOES run inside one when the web UI launches it,
# where `ss` is not even installed. The old check read that silence as "free" and cheerfully
# cleared a port already held by another target's SonarQube; the run then died later, in Sonar,
# looking like a Sonar bug. So ask Docker too: published ports are visible through the socket
# from anywhere, and a residual container from another profile is the common case.
docker_holds_port() {
  docker ps --format '{{.Ports}}' 2>/dev/null | grep -qE ":$1->"
}
HAVE_SS=0; command -v ss >/dev/null 2>&1 && HAVE_SS=1
for p in ${SONAR_PORT:-9000} ${APP_PORT:-} ${FRONTEND_PORT:-} ${PROD_PORT:-} ${MOODLE_PORT:-}; do
  [ -z "$p" ] && continue
  holder=""
  [ "$HAVE_SS" = 1 ] && ss -ltn 2>/dev/null | grep -q ":$p " && holder="a local process"
  if docker_holds_port "$p"; then
    holder=$(docker ps --format '{{.Names}}\t{{.Ports}}' 2>/dev/null \
             | grep -E ":$p->" | cut -f1 | head -1)
    holder="container '$holder'"
  fi
  if [ -n "$holder" ]; then warn "port $p already in use by $holder — 'make down TARGET=<other>'"
  elif [ "$HAVE_SS" = 1 ]; then ok "port $p free"
  else warn "port $p: cannot verify from here (no 'ss'); only published containers were checked"
  fi
done
if ss -ltn 2>/dev/null | grep -qE '0\.0\.0\.0:(9000|8000|8099|8100|5173)'; then
  bad "a lab port is listening on 0.0.0.0 — the lab may hold real data (finding L1)"
fi

# ---- archivos de configuración del perfil que docker convertirá en DIRECTORIOS ---------------
# docker-compose monta estos cuatro archivos uno a uno desde targets/<t>/. Cuando el origen de un
# bind mount NO EXISTE, el demonio de Docker no falla: CREA UN DIRECTORIO VACÍO en su lugar y lo
# monta. La herramienta recibe entonces un directorio donde esperaba un archivo.
#
# Medido: targets/antiplagio/ no traía spectral.yaml. Docker creó el directorio (root:root), lo
# montó en /spectral.yaml, y Spectral murió con
#     Error #1: EISDIR: illegal operation on a directory, read
# un mensaje que no nombra ni el archivo ni la variable ni el perfil. La dimensión del contrato de
# API se reportaba como "NO EJECUTADA" y nadie sabía por qué. El directorio además queda en el
# perfil, así que el siguiente intento falla igual.
for _f in sonar-project.properties qodana.yaml gitleaks.toml spectral.yaml; do
  _p="targets/$TARGET/$_f"
  if [ -d "$_p" ]; then
    bad "$_p es un DIRECTORIO — lo creó docker al no encontrar el archivo"
    echo "        La herramienta que lo monte morirá con un error que no nombra este archivo."
    echo "        Arréglalo:  rmdir '$_p' && cp targets/_template/$_f '$_p'"
  elif [ ! -f "$_p" ]; then
    warn "falta $_p — docker creará un DIRECTORIO en su lugar en la próxima corrida"
    echo "        Cópialo antes:  cp targets/_template/$_f '$_p'"
  fi
done

# ---- umbrales del gate que el perfil NO declara ----------------------------------------------
# Una clave de umbral ausente NO desactiva la comprobación: tools/gate.sh aplica un defecto
# interno y estampa un veredicto con él. Medido antes de escribir esto: de las nueve claves que
# el gate consulta, CINCO no existían ni en la plantilla, así que ningún perfil las declaraba —
# MAX_QUALITY_FINDINGS=500 se aplicaba en tres proyectos sin que nadie hubiera elegido ese 500.
# Un presupuesto que nadie decidió no se puede leer como un presupuesto aceptado.
_missing=""
while IFS=$'\t' read -r _key _def; do
  [ -z "$_key" ] && continue
  grep -q "^${_key}=" "$ENVFILE" 2>/dev/null || _missing="$_missing $_key(=$_def)"
done < <(tools/dimensions.py --list gate,default 2>/dev/null | grep -v '^	' | sort -u)
if [ -n "${_missing// }" ]; then
  warn "umbrales que el gate usará con un defecto NO declarado en el perfil:"
  for _m in $_missing; do echo "          $_m"; done
  echo "        Decláralos en $ENVFILE aunque sea con ese mismo valor: así el número"
  echo "        que juzga el proyecto es uno que alguien eligió."
else
  ok "todos los umbrales del gate están declarados en el perfil"
fi

# Inline comments: the one place where this lab's own tools disagree with each other.
# lib-env.sh strips ` # ...`; `docker compose --env-file` keeps it as part of the value. So
# `QODANA_IMAGE=  # not applicable` is empty to doctor/tier/gate and a literal image name to
# compose, which then fails with "invalid reference format" from a file that looks correct.
BADLINES=$(env_inline_comments "$ENVFILE")
if [ -n "$BADLINES" ]; then
  warn "inline comments in target.env — compose reads them as part of the VALUE:"
  echo "$BADLINES" | sed 's/^/          line /'
  echo "        Move the comment to its own line above the variable."
fi

mkdir -p "reports/$TARGET" 2>/dev/null
[ -w "reports/$TARGET" ] && ok "reports/$TARGET writable" || bad "reports/$TARGET not writable"

# --- which rung of the ladder, and what that leaves blocked ---------------------------------
echo
TIER_OUT=$(tools/tier.sh "$TARGET" 2>/dev/null)
TIER=$(echo "$TIER_OUT" | sed -n 's/^TIER=//p')
LIVE=$(echo "$TIER_OUT" | sed -n 's/^LIVE=//p')
case "${TIER:-0}" in
  1) echo "  rung 1 — source only. Everything under 'make static' is available right now."
     echo "           Point BASE_URL/HEALTH_PATH at your own deployment to unlock DAST," ;
     echo "           authorization and load. You do not need a recipe for that." ;;
  2) echo "  rung 2 — source + your own deployment (the lab points at it, never manages it)." ;;
  3) echo "  rung 3 — source + a runtime recipe: the lab brings the app up itself, ephemeral." ;;
  *) echo "  rung 0 — not analysable yet." ;;
esac
[ "${LIVE:-}" = "ok" ] && ok "the application answers: every [live] dimension is available"
echo "$TIER_OUT" | sed -n 's/^BLOCKED=//p' | while IFS='|' read -r goal reason; do
  warn "blocked: $goal — $reason"
done

echo
[ "$FAIL" -eq 0 ] && echo "preflight passed" || { echo "preflight FAILED"; exit 1; }
