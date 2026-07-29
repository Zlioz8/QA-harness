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

URL="${BASE_URL%/}${HEALTH_PATH}"
# -k: local deployments routinely serve a self-signed cert (the stack's own nginx does). Every
# scanner in this lab already sets ignoreHTTPSErrors; the liveness probe must match, or a healthy
# https app reads as "nothing answered" (000) and the whole live pipeline aborts on a cert.
CODE=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 10 "$URL" 2>/dev/null)

if [ "$CODE" = "200" ]; then
  echo "live check: $URL -> 200"
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
