#!/usr/bin/env bash
# Scaffold targets/<name>/ from the template. Refuses to overwrite an existing profile.
set -euo pipefail
NAME="${1:?usage: new-target.sh <name>}"
DST="targets/$NAME"
[ -e "$DST" ] && { echo "ERROR: $DST already exists"; exit 1; }
cp -r targets/_template "$DST"
sed -i "s/__TARGET__/$NAME/g" "$DST/target.env" "$DST/sonar-project.properties"
mkdir -p "reports/$NAME"
cat <<EOF
created $DST

next:
  1. edit $DST/target.env          -> SRC_PATH (or REPO_URL+BRANCH)
  2. make detect TARGET=$NAME      -> proposes LANGS / QODANA_IMAGE / AUTH_ADAPTER / recipes
  3. make doctor TARGET=$NAME      -> preflight
  4. make static TARGET=$NAME      -> already produces findings, no running app needed

runtime (ZAP / k6 / Playwright) additionally needs:
  - $DST/compose.runtime.yml  composed from recipes/  (must serve 200 on HEALTH_PATH)
  - $DST/playwright/tests/_auth.ts and $DST/k6/lib/session.js re-exporting an adapter
    from lib/auth/ — pick one with AUTH_ADAPTER, or write a new adapter if your stack
    logs in some other way (that new adapter then serves every future project).
EOF
