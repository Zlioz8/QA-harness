#!/usr/bin/env bash
# Which rung of the ladder is this profile on, and what does that leave blocked.
#
#   rung 1  a source checkout            -> secrets, deps, config, SAST, SBOM, quality
#   rung 2  + your own running app       -> + DAST, authorization, flows, load
#   rung 3  + a runtime recipe           -> same as 2, but ephemeral and reproducible
#
# The lab never needs to install the audited application. Rung 3 exists for repeatability, not
# as a requirement — a team that already deploys its project stays on rung 2 and writes no recipe.
#
# Output is machine-readable on purpose: `doctor` pretty-prints it and the web UI reads the same
# lines. One implementation, so the terminal and the browser can never tell different stories.
#
#   TIER=<1|2|3>
#   RUNTIME=<yes|no>          profile ships a compose.runtime.yml
#   LIVE=<ok|unreachable|unconfigured>
#   BLOCKED=<goal>|<reason>   zero or more
set -uo pipefail

TARGET="${1:?usage: tier.sh <target>}"
ENVFILE="targets/$TARGET/target.env"
[ -f "$ENVFILE" ] || { echo "TIER=0"; echo "BLOCKED=all|no profile at $ENVFILE"; exit 0; }

. "$(dirname "$0")/lib-env.sh"   # one parser for target.env — see the file for why

SRC_PATH=$(envget SRC_PATH)
BASE_URL=$(envget BASE_URL)
HEALTH_PATH=$(envget HEALTH_PATH)
ROLE_A=$(envget ROLE_A_USER); ROLE_B=$(envget ROLE_B_USER)
ADAPTER=$(envget AUTH_ADAPTER)
[ -f "targets/$TARGET/compose.runtime.yml" ] && RUNTIME=yes || RUNTIME=no
echo "RUNTIME=$RUNTIME"

# --- rung 1: is there source to read? ---
if [ -z "$SRC_PATH" ] || [ ! -d "$SRC_PATH" ]; then
  echo "TIER=0"
  echo "LIVE=unconfigured"
  echo "BLOCKED=static|SRC_PATH is not set or not a directory: nothing to analyse"
  exit 0
fi

# --- rung 2/3: can anything be measured live? ---
if [ -z "$BASE_URL" ] || [ -z "$HEALTH_PATH" ]; then
  LIVE=unconfigured
else
  # -k deliberado, y consistente con tools/require-live.sh, que ya lo usaba: esta sonda solo
  # responde "¿hay algo vivo ahí?". Un certificado autofirmado —lo normal en preproducción— hacía
  # que este chequeo dijera "unreachable" mientras require-live.sh decía "ok": dos medidas de lo
  # mismo en desacuerdo, y el peldaño 2 quedaba bloqueado sobre un despliegue sano.
  # La validez del TLS la juzga la dimensión DAST, que sabe reportarla como hallazgo.
  CODE=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 5 "${BASE_URL%/}${HEALTH_PATH}" 2>/dev/null)
  [ "$CODE" = "200" ] && LIVE=ok || LIVE=unreachable
fi
echo "LIVE=$LIVE"

# TIER describes what the PROFILE is configured for; LIVE describes the state right now.
# Conflating them gives the wrong advice: a profile with a recipe whose app is merely stopped
# would be told to "point BASE_URL at your deployment" when the answer is `make up`.
if [ "$RUNTIME" = "yes" ]; then
  echo "TIER=3"
elif [ -n "$BASE_URL" ] && [ -n "$HEALTH_PATH" ]; then
  echo "TIER=2"
else
  echo "TIER=1"
fi

if [ "$LIVE" != "ok" ]; then
  if [ "$RUNTIME" = "yes" ]; then
    echo "BLOCKED=dast,perf,e2e|the application is not answering — bring it up with 'make up'"
  elif [ "$LIVE" = "unconfigured" ]; then
    echo "BLOCKED=dast,perf,e2e|BASE_URL/HEALTH_PATH not set — say where your deployment answers, or add a recipe"
  else
    echo "BLOCKED=dast,perf,e2e|${BASE_URL%/}${HEALTH_PATH} does not answer 200 — run tools/require-live.sh for the diagnosis"
  fi
fi

# --- authorization needs more than a live app: it needs two unequal accounts ---
if [ -z "$ROLE_A" ] || [ -z "$ROLE_B" ] || [ "$ROLE_A" = "$ROLE_B" ]; then
  echo "BLOCKED=authz|needs ROLE_A_* and ROLE_B_* to be two DIFFERENT accounts of unequal privilege"
fi
if [ -z "$ADAPTER" ] || [ "$ADAPTER" = "none" ]; then
  echo "BLOCKED=authenticated|AUTH_ADAPTER=none — only the unauthenticated surface is covered"
fi
exit 0
