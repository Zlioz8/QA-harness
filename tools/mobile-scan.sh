#!/usr/bin/env bash
# Mobile dimension: scan the ARTIFACT the project distributes (.apk / .ipa / .aab), not its source.
#
# Why this is its own dimension: on a hybrid mobile project every other tool here reads the
# repository, and the repository is not what reaches the user. The signed bundle carries compiled
# configuration, bundled assets, third-party SDKs and anything a build step baked in — a set that
# routinely differs from what the source suggests. "We fixed it in dev" and "the build people
# install is fixed" are different claims, and only this one checks the second.
#
# MobSF is a server. This script drives it over its REST API (upload -> scan -> report_json),
# leaves the raw report next to the SARIF, and never leaves the loopback interface.
set -uo pipefail
TARGET="${1:?usage: mobile-scan.sh <target>}"
ENVFILE="targets/$TARGET/target.env"
[ -f "$ENVFILE" ] || { echo "no $ENVFILE"; exit 2; }
REPORTS="reports/$TARGET/mobile"
mkdir -p "$REPORTS"

. "$(dirname "$0")/lib-env.sh"   # one parser for target.env — values may contain spaces

SRC_PATH=$(envget SRC_PATH)
APK_PATH=$(envget MOBILE_ARTIFACT)
PORT=$(envget MOBSF_PORT); PORT="${PORT:-8010}"
KEY=$(envget MOBSF_API_KEY); KEY="${KEY:-seclab-local-only-key}"
ENVLOCAL="targets/$TARGET/target.env.local"
DC="docker compose --env-file $ENVFILE $([ -f "$ENVLOCAL" ] && echo "--env-file $ENVLOCAL") -f docker-compose.yml"

if [ -z "$APK_PATH" ]; then
  cat <<EOF

  mobile-scan: MOBILE_ARTIFACT is not set — NOT AVAILABLE for this profile, not skipped.

  Point it at the distributable bundle, as a path relative to SRC_PATH:

    MOBILE_ARTIFACT=zajuna-frontend/android/app/build/outputs/apk/prod/release/app-prod-release.apk

  Audit the RELEASE build. A debug bundle is a different binary with different hardening, and a
  finding about it describes something nobody installs.

EOF
  exit 2
fi

FULL="$SRC_PATH/$APK_PATH"
if [ ! -f "$FULL" ]; then
  echo "mobile-scan: artifact not found: $FULL"
  echo "             build it first, or fix MOBILE_ARTIFACT in $ENVFILE."
  exit 2
fi

# The artifact must be newer than the code it claims to represent, or the audit describes a
# binary that no longer exists. Warn rather than refuse: sometimes an old build IS the subject.
for repo in "$SRC_PATH"/*/; do
  [ -d "$repo.git" ] || continue
  head_ts=$(git -C "$repo" log -1 --format=%ct 2>/dev/null) || continue
  apk_ts=$(stat -c %Y "$FULL")
  if [ "$apk_ts" -lt "$head_ts" ]; then
    echo "  WARNING: $(basename "$repo") HEAD ($(date -d @"$head_ts" +%F)) is newer than the artifact ($(date -d @"$apk_ts" +%F))."
    echo "           Findings will describe a bundle that predates the current code."
  fi
done

echo "mobile-scan: starting MobSF (127.0.0.1:$PORT)"
$DC --profile mobile up -d mobsf >/dev/null 2>&1 || { echo "could not start mobsf"; exit 1; }

# MobSF cold-boots in ~1-2 min. Poll its API rather than a fixed sleep: a fixed sleep is either
# a wasted minute or a race, and this one fails as "connection refused" that reads like a bug.
API="http://127.0.0.1:$PORT/api/v1"
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: $KEY" "$API/scans" 2>/dev/null)
  [ "$code" = "200" ] && break
  [ "$i" = 60 ] && { echo "mobile-scan: MobSF did not answer on $API after 5 min"; echo "  logs: docker compose logs mobsf"; exit 1; }
  sleep 5
done
echo "mobile-scan: MobSF up; uploading $(basename "$FULL") ($(du -h "$FULL" | cut -f1))"

up_json="$REPORTS/_upload.json"
curl -s -F "file=@$FULL" -H "Authorization: $KEY" "$API/upload" -o "$up_json"
HASH=$(python3 -c "import json,sys; print(json.load(open('$up_json')).get('hash',''))" 2>/dev/null)
[ -n "$HASH" ] || { echo "mobile-scan: upload failed:"; head -c 400 "$up_json"; echo; exit 1; }

echo "mobile-scan: scanning (hash $HASH) — a full APK takes a few minutes"
curl -s -X POST -H "Authorization: $KEY" --data "hash=$HASH" "$API/scan" -o "$REPORTS/_scan.json" \
  --max-time 1800
curl -s -X POST -H "Authorization: $KEY" --data "hash=$HASH" "$API/report_json" -o "$REPORTS/mobsf.json" \
  --max-time 600

if [ ! -s "$REPORTS/mobsf.json" ]; then
  echo "mobile-scan: no report produced — the dimension did NOT run"
  exit 1
fi

"$(dirname "$0")/mobsf-sarif.py" "$REPORTS" "$APK_PATH"
rm -f "$REPORTS/_upload.json" "$REPORTS/_scan.json"

# The report is on disk, so the server has no reason to keep running. Left up, MobSF is a Django
# app plus its analysers holding memory until someone remembers `make down` — and on a 15 GB
# laptop that already runs an editor and a browser, forgotten lab servers are what turns an audit
# into a 21-minute desktop freeze and an OOM kill on the operator's editor.
# `stop`, not `down`: the uploaded scan stays in the container's volume for a re-read.
# MOBSF_KEEP=1 leaves it up to browse the HTML report at 127.0.0.1:$PORT.
if [ -z "${MOBSF_KEEP:-}" ]; then
  $DC --profile mobile stop mobsf >/dev/null 2>&1 && echo "mobile-scan: MobSF stopped (MOBSF_KEEP=1 to keep it up)"
fi
echo "mobile-scan: done."

# Procedencia: contra que midio esta dimension. Sin esto, su artefacto no se puede
# atribuir a un blanco y el gate no puede excluirlo cuando el perfil cambia de sistema.
tools/stamp.sh "$TARGET" mobsf 2>/dev/null || true
