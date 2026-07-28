#!/usr/bin/env bash
# The gate. Every tool in this lab is deliberately configured NOT to fail its own run
# (gitleaks --exit-code=0, semgrep --error=false, `|| true` in boot commands) so that one
# noisy dimension never aborts the others. The consequence is that a run is always
# "green" and means nothing. This script is where a run gets a verdict.
#
# Thresholds live in target.env so each project declares its own risk appetite.
set -uo pipefail
TARGET="${1:?usage: gate.sh <target>}"
R="reports/$TARGET"
ENVFILE="targets/$TARGET/target.env"
# Read thresholds WITHOUT sourcing: a value containing spaces would be executed as a command
# (see the note in run-manifest.sh), and a target profile is data, not code.
envget() { sed -n "s/^${1}=//p" "$ENVFILE" 2>/dev/null | tail -1 | sed 's/^"//; s/"$//'; }
ALLOW_SECRETS=$(envget ALLOW_SECRETS)
MAX_DEP_FINDINGS=$(envget MAX_DEP_FINDINGS)
MAX_SAST_FINDINGS=$(envget MAX_SAST_FINDINGS)
MAX_DAST_FINDINGS=$(envget MAX_DAST_FINDINGS)
K6_P95_MS=$(envget K6_P95_MS)
K6_ERR_RATE=$(envget K6_ERR_RATE)

FAIL=0
pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAIL=1; }
skip() { printf '  \033[90mskip\033[0m  %s\n' "$1"; }

# Count SARIF results without pulling in jq: SARIF is one "ruleId" per result.
sarif_count() { [ -f "$1" ] && grep -o '"ruleId"' "$1" | wc -l || echo -1; }

echo "== gate: $TARGET =="

n=$(sarif_count "$R/gitleaks.sarif")
if [ "$n" -lt 0 ]; then skip "gitleaks not run"
elif [ "$n" -le "${ALLOW_SECRETS:-0}" ]; then pass "secrets: $n (allowed ${ALLOW_SECRETS:-0})"
else fail "secrets: $n found in git history (allowed ${ALLOW_SECRETS:-0})"; fi

n=$(sarif_count "$R/trivy/trivy-fs.sarif")
if [ "$n" -lt 0 ]; then skip "trivy fs not run"
elif [ "$n" -le "${MAX_DEP_FINDINGS:-999}" ]; then pass "dependency findings: $n (max ${MAX_DEP_FINDINGS:-999})"
else fail "dependency findings: $n (max ${MAX_DEP_FINDINGS:-999})"; fi

n=$(sarif_count "$R/semgrep/semgrep.sarif")
if [ "$n" -lt 0 ]; then skip "semgrep not run"
elif [ "$n" -le "${MAX_SAST_FINDINGS:-999}" ]; then pass "SAST findings: $n (max ${MAX_SAST_FINDINGS:-999})"
else fail "SAST findings: $n (max ${MAX_SAST_FINDINGS:-999})"; fi

n=$(sarif_count "$R/zap/zap-report.json")
if [ "$n" -lt 0 ]; then skip "ZAP not run"
elif [ "$n" -le "${MAX_DAST_FINDINGS:-999}" ]; then pass "DAST alerts: $n (max ${MAX_DAST_FINDINGS:-999})"
else fail "DAST alerts: $n (max ${MAX_DAST_FINDINGS:-999})"; fi

# k6: a p95 or error rate outside the SLO is a failure, not a note in a log.
S="$R/k6/summary.json"
if [ -f "$S" ]; then
  p95=$(grep -o '"p(95)":[0-9.]*' "$S" | head -1 | cut -d: -f2 | cut -d. -f1)
  err=$(grep -o '"http_req_failed"[^}]*"value":[0-9.]*' "$S" | grep -o '[0-9.]*$')
  [ -n "${p95:-}" ] && { [ "$p95" -le "${K6_P95_MS:-1500}" ] && pass "k6 p95: ${p95}ms (max ${K6_P95_MS:-1500})" || fail "k6 p95: ${p95}ms (max ${K6_P95_MS:-1500})"; }
  [ -n "${err:-}" ] && { awk -v e="$err" -v m="${K6_ERR_RATE:-0.01}" 'BEGIN{exit !(e<=m)}' \
      && pass "k6 error rate: $err (max ${K6_ERR_RATE:-0.01})" || fail "k6 error rate: $err (max ${K6_ERR_RATE:-0.01})"; }
else skip "k6 not run"; fi

if [ -f "$R/playwright/results.json" ]; then
  # Match with optional whitespace: Playwright writes `"status": "failed"`. A pattern without
  # the space silently counts zero, and the gate then reports a clean run over a failing suite —
  # the exact failure mode this whole script exists to prevent.
  bad=$(grep -oE '"status":[[:space:]]*"failed"' "$R/playwright/results.json" | wc -l)
  [ "$bad" -eq 0 ] && pass "playwright: no failed specs" || fail "playwright: $bad failed specs"
else skip "playwright not run"; fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "GATE PASSED — note: 'skip' lines are NOT passes. See reports/$TARGET/RUN.md for coverage."
else
  echo "GATE FAILED"
fi
exit "$FAIL"
