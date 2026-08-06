#!/usr/bin/env bash
# Device dimension: the app on real hardware, driven by a person, with the evidence captured.
#
# Why it is not Playwright. `make e2e` drives the API with a headless browser; a hybrid mobile app
# runs its UI in an Android WebView, on a device that has its own clock, its own cookie jar, its
# own idea of when to kill a background process, and a user who leaves the app open for twenty
# minutes. Whole failure families live only there: a session that dies while idle, a persisted
# cookie restored without checking it is still alive, a rate limit on re-login, state that only a
# "clear data" fixes. No container reproduces that, so the lab does not pretend to: it runs the
# journeys with a human and keeps the log.
#
# adb is host tooling on purpose — the device is physically attached to this machine, and no
# container gets to hold that. This is the one dimension of the lab that is not hermetic, and
# RUN.md says so.
set -uo pipefail
TARGET="${1:?usage: device-e2e.sh <target>}"
ENVFILE="targets/$TARGET/target.env"
[ -f "$ENVFILE" ] || { echo "no $ENVFILE"; exit 2; }
OUT="reports/$TARGET/device"
mkdir -p "$OUT"

. "$(dirname "$0")/lib-env.sh"
BASE_URL=$(envget BASE_URL)
PKG=$(envget MOBILE_PACKAGE)
SERIAL=$(envget DEVICE_SERIAL)
JOURNEYS=$(envget DEVICE_JOURNEYS); JOURNEYS="${JOURNEYS:-J1 J2 J3 J4 J5 J6 J7}"
ADB=(adb); [ -n "$SERIAL" ] && ADB=(adb -s "$SERIAL")

command -v adb >/dev/null || { echo "device-e2e: adb not installed on this host — dimension NOT AVAILABLE"; exit 2; }

n_dev=$("${ADB[@]}" devices | awk 'NR>1 && $2=="device"' | wc -l)
if [ "$n_dev" -eq 0 ]; then
  cat <<EOF

  device-e2e: no device attached — the dimension did NOT run (this is not a pass).

  Needed:
    · phone connected by USB with debugging authorised  (adb devices -> "device", not "unauthorized")
    · the build under audit installed, pointing at the deployment being audited ($BASE_URL)
    · the phone on the network from which that address resolves

EOF
  exit 2
fi
[ "$n_dev" -gt 1 ] && [ -z "$SERIAL" ] && {
  echo "device-e2e: more than one device attached; set DEVICE_SERIAL in $ENVFILE"; "${ADB[@]}" devices; exit 2; }

MODEL=$("${ADB[@]}" shell getprop ro.product.model 2>/dev/null | tr -d '\r')
REL=$("${ADB[@]}" shell getprop ro.build.version.release 2>/dev/null | tr -d '\r')

# Which build is actually installed. Auditing journeys on a package the profile did not name is
# how a report ends up describing the other flavour — the one pointing at a different backend.
if [ -z "$PKG" ]; then
  echo "device-e2e: MOBILE_PACKAGE not set. Installed candidates:"
  "${ADB[@]}" shell pm list packages 2>/dev/null | sed 's/package://' | grep -viE '^(com.google|com.android|android)' | head -20
  echo "  Set MOBILE_PACKAGE in $ENVFILE to the one under audit."
  exit 2
fi
"${ADB[@]}" shell pm list packages 2>/dev/null | tr -d '\r' | grep -qx "package:$PKG" || {
  echo "device-e2e: $PKG is not installed on $MODEL. Install the build under audit first."; exit 2; }

VER=$("${ADB[@]}" shell dumpsys package "$PKG" 2>/dev/null | grep -m1 versionName | tr -d '\r ' | cut -d= -f2)
DBG=$("${ADB[@]}" shell dumpsys package "$PKG" 2>/dev/null | grep -c "flags=.*DEBUGGABLE" | tr -d '\r')

echo "device-e2e: $MODEL (Android $REL) · $PKG ${VER:+v$VER}"
[ "${DBG:-0}" -gt 0 ] && echo "  note: the installed build is DEBUGGABLE — findings about hardening describe a debug build, not what ships."

LOG="$OUT/logcat.txt"
"${ADB[@]}" logcat -c 2>/dev/null
"${ADB[@]}" logcat -v time > "$LOG" 2>/dev/null &
LOGPID=$!
trap 'kill "$LOGPID" 2>/dev/null' EXIT
echo "  capturing logcat -> $LOG"

# The canonical journeys. Each one exists because a real failure escaped every other dimension:
# see the zajuna-movil-flujo-usuario skill for the incident behind each.
declare -A J=(
  [J1]="Clean install -> login -> dashboard -> open one resource of each type|basic regressions, cold pass"
  [J2]="Idle 15-30 min, then open a resource with the session open|dead LMS session + cookie restored without validating it"
  [J3]="Logout -> log in as the SAME user -> open a resource|reuse of a persisted cookie, state not cleared"
  [J4]="Kill the app (swipe) -> reopen -> open a resource|in-memory vs persisted state, cookie restore"
  [J5]="Open two resources less than 6 min apart|re-login rate limit budget, reuse of a live cookie"
  [J6]="Change user (logout A -> login B) -> open a resource|cross-user leak of cookie/caches (must fail closed)"
  [J7]="Clear app data -> login -> open a resource|cold baseline. If ONLY this fixes something, the state was poisoned: say which"
  [J8]="Restart the backend mid-session -> keep using the app|zombie session, refresh, backend caches after restart"
  [J9]="Offline / flaky network -> dashboard|offline cache serving another environment's or user's data"
)

MD="$OUT/jornadas.md"
{
  echo "# Device journeys — $TARGET"
  echo
  echo "- date: $(date -Is)"
  echo "- device: $MODEL · Android $REL"
  echo "- package: \`$PKG\`${VER:+ v$VER}$([ "${DBG:-0}" -gt 0 ] && echo ' · **debuggable build**')"
  echo "- deployment under test: \`${BASE_URL:-?}\`"
  echo "- evidence: \`logcat.txt\` (this run), plus whatever the operator attached per journey"
  echo
  echo "| Journey | What it stresses | Result | Evidence / note |"
  echo "|---|---|---|---|"
} > "$MD"

interactive=0; [ -t 0 ] && interactive=1
for j in $JOURNEYS; do
  desc="${J[$j]%%|*}"; why="${J[$j]##*|}"
  if [ "$interactive" -eq 0 ]; then
    echo "| $j | $why | **PENDING** | $desc |" >> "$MD"
    continue
  fi
  echo
  echo "── $j ─────────────────────────────────────────────"
  echo "   do:      $desc"
  echo "   watches: $why"
  "${ADB[@]}" shell log -p i -t SECLAB "$j START $desc" >/dev/null 2>&1
  printf '   result [ok/fail/skip]: '; read -r res
  printf '   note (what you saw, evidence): '; read -r note
  "${ADB[@]}" shell log -p i -t SECLAB "$j END $res" >/dev/null 2>&1
  case "$res" in
    ok)   mark="OK" ;;
    fail) mark="**FAIL**" ;;
    *)    mark="skip" ;;
  esac
  echo "| $j | $why | $mark | ${note:-—} |" >> "$MD"
done

if [ "$interactive" -eq 0 ]; then
  {
    echo
    echo "> Written non-interactively: every journey is **PENDING**. A pending journey is an"
    echo "> unmeasured dimension, never a pass. Re-run this goal from a terminal to conduct them."
  } >> "$MD"
  echo "device-e2e: no TTY — wrote the journey template to $MD with everything PENDING"
else
  {
    echo
    echo "## Not answered by this dimension"
    echo
    echo "- Whether a failure is the app's or the environment's: correlate with the backend logs"
    echo "  for the same window before writing it up."
  } >> "$MD"
fi

kill "$LOGPID" 2>/dev/null
lines=$(wc -l < "$LOG" 2>/dev/null || echo 0)
echo "device-e2e: $MD written · logcat $lines lines"

# Procedencia: contra que midio esta dimension. Sin esto, su artefacto no se puede
# atribuir a un blanco y el gate no puede excluirlo cuando el perfil cambia de sistema.
tools/stamp.sh "$TARGET" device 2>/dev/null || true
