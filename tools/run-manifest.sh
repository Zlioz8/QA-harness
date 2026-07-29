#!/usr/bin/env bash
# Write reports/<target>/RUN.md: what was audited, with what, on what hardware, and —
# the part that is usually missing — what did NOT run.
#
# Why it exists: the previous run's RESULTS.md buried "Sonar/Qodana: wired, not executed"
# in a table cell, so the report read as complete coverage. Absence of a finding is only
# meaningful if you can tell it apart from absence of a scan.
set -uo pipefail
TARGET="${1:?usage: run-manifest.sh <target>}"
R="reports/$TARGET"; mkdir -p "$R"
ENVFILE="targets/$TARGET/target.env"
# Read the profile WITHOUT sourcing it. `. target.env` breaks on any unquoted value containing
# spaces — a path like /opt/MANUALES DE DESPLIEGUE/... silently becomes a command, SRC_PATH ends
# up empty, and the manifest then records "(not a git checkout)" for a perfectly normal git repo.
# A manifest that misreports which commit was audited is worse than no manifest.
. "$(dirname "$0")/lib-env.sh"   # one parser for target.env — see the file for why
SRC_PATH=$(envget SRC_PATH)
PERF_CPUS=$(envget PERF_CPUS)
PERF_MEM=$(envget PERF_MEM)
OUT="$R/RUN.md"

commit="(not a git checkout)"
[ -d "${SRC_PATH:-}/.git" ] && commit=$(git -C "$SRC_PATH" log -1 --format='%H %s' 2>/dev/null)
branch=$(git -C "${SRC_PATH:-.}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '-')

{
  echo "# Run manifest — $TARGET"
  echo
  echo "- date: $(date -Is)"
  echo "- host: $(hostname) · $(nproc) cpu · $(free -g | awk '/^Mem:/{print $2}')G RAM"
  echo "- source: \`${SRC_PATH:-?}\` @ \`$branch\`"
  echo "- commit: \`$commit\`"
  echo "- declared envelope (perf comparability): cpus=${PERF_CPUS:-unset} memory=${PERF_MEM:-unset}"
  echo
  echo "## Coverage"
  echo
  echo "| Dimension | Artifact | Ran |"
  echo "|---|---|---|"
  chk() { if [ -s "$R/$2" ]; then echo "| $1 | \`$2\` | yes |"; else echo "| $1 | \`$2\` | **NO** |"; fi; }
  chk "Secrets (git history)" "gitleaks.sarif"
  chk "Dependencies / CVE"    "trivy/trivy-fs.sarif"
  chk "IaC / container config" "trivy/trivy-config.sarif"
  chk "Image CVE"             "trivy/trivy-image.sarif"
  chk "SBOM"                  "sbom/sbom.spdx.json"
  chk "SAST (semgrep)"        "semgrep/semgrep.sarif"
  chk "Quality (SonarQube)"   "sonar/sonar.sarif"
  chk "Quality (qodana)"      "qodana/report/index.html"
  chk "API contract (Spectral)" "api/spectral.sarif"
  chk "API fuzz (Schemathesis)" "api/schemathesis.xml"
  chk "DAST (ZAP)"            "zap/zap-report.html"
  chk "Load (k6)"             "k6/summary.json"
  chk "Load (JMeter)"         "jmeter/results.jtl"
  chk "E2E / authz"           "playwright/results.json"
  echo
  echo "## Tool images (pin these to digests for a reproducible re-run)"
  echo '```'
  docker images --digests --format '{{.Repository}}:{{.Tag}} {{.Digest}}' 2>/dev/null \
    | grep -E 'gitleaks|trufflehog|trivy|semgrep|syft|sonar|qodana|zap|k6|playwright' | sort
  echo '```'
  echo
  echo "## Not covered by any tool here (needs human analysis)"
  echo
  echo "- Authorization *policy*: a 200 is only a finding if the policy said 403."
  echo "- Business-logic abuse: scenarios must be written after reading the code."
  echo "- Severity in institutional context (personal data, regulated processes)."
} > "$OUT"
echo "wrote $OUT"
