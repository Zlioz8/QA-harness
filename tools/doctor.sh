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
envget() { sed -n "s/^${1}=//p" "$ENVFILE" | tail -1 | sed 's/^"//; s/"$//'; }
SRC_PATH=$(envget SRC_PATH)
ROLE_A_USER=$(envget ROLE_A_USER); ROLE_B_USER=$(envget ROLE_B_USER)
AUTH_ADAPTER=$(envget AUTH_ADAPTER); HEALTH_PATH=$(envget HEALTH_PATH); BASE_URL=$(envget BASE_URL)
SONAR_PORT=$(envget SONAR_PORT); APP_PORT=$(envget APP_PORT)
FRONTEND_PORT=$(envget FRONTEND_PORT); PROD_PORT=$(envget PROD_PORT); MOODLE_PORT=$(envget MOODLE_PORT)

[ -n "${SRC_PATH:-}" ] && [ -d "${SRC_PATH:-}" ] && ok "SRC_PATH: $SRC_PATH" || bad "SRC_PATH missing or not a directory: ${SRC_PATH:-<unset>}"
[ -d "${SRC_PATH:-}/.git" ] && ok "git history present (secret scanning is meaningful)" \
                            || warn "no .git in SRC_PATH — gitleaks/trufflehog will only see the working tree"

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

# Ports, bound to loopback only (lab finding L1).
for p in ${SONAR_PORT:-9000} ${APP_PORT:-} ${FRONTEND_PORT:-} ${PROD_PORT:-} ${MOODLE_PORT:-}; do
  [ -z "$p" ] && continue
  if ss -ltn 2>/dev/null | grep -q ":$p "; then warn "port $p already in use"; else ok "port $p free"; fi
done
if ss -ltn 2>/dev/null | grep -qE '0\.0\.0\.0:(9000|8000|8099|8100|5173)'; then
  bad "a lab port is listening on 0.0.0.0 — the lab may hold real data (finding L1)"
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
