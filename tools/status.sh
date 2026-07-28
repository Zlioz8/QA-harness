#!/usr/bin/env bash
# What is up, what has been run, what is still missing for this target.
set -uo pipefail
TARGET="${1:?usage: status.sh <target>}"
R="reports/$TARGET"
echo "== status: $TARGET =="
echo
echo "-- containers --"
docker compose --env-file "targets/$TARGET/target.env" -f docker-compose.yml \
  $( [ -f "targets/$TARGET/compose.runtime.yml" ] && echo "-f targets/$TARGET/compose.runtime.yml" ) \
  ps 2>/dev/null | tail -n +1
echo
echo "-- reports --"
if [ -d "$R" ]; then find "$R" -type f -size +0 -printf '  %-52p %6s bytes\n' 2>/dev/null | sort; else echo "  (none)"; fi
echo
echo "-- missing --"
for f in gitleaks.sarif trivy/trivy-fs.sarif trivy/trivy-config.sarif semgrep/semgrep.sarif \
         sbom/sbom.spdx.json zap/zap-report.html k6/summary.json playwright/results.json RUN.md; do
  [ -s "$R/$f" ] || echo "  $f"
done
