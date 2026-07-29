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
. "$(dirname "$0")/lib-env.sh"   # one parser for target.env — see the file for why
ALLOW_SECRETS=$(envget ALLOW_SECRETS)
MAX_DEP_FINDINGS=$(envget MAX_DEP_FINDINGS)
MAX_SAST_FINDINGS=$(envget MAX_SAST_FINDINGS)
MAX_QUALITY_FINDINGS=$(envget MAX_QUALITY_FINDINGS)
MAX_DAST_FINDINGS=$(envget MAX_DAST_FINDINGS)
K6_P95_MS=$(envget K6_P95_MS)
K6_ERR_RATE=$(envget K6_ERR_RATE)

FAIL=0
pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAIL=1; }
skip() { printf '  \033[90mskip\033[0m  %s\n' "$1"; }

# Count SARIF results without pulling in jq: SARIF is one "ruleId" per result.
#
# The `|| echo -1` must never be reachable from a file that EXISTS. `grep` exits 1 when it
# matches nothing, so the obvious one-liner
#     [ -f "$1" ] && grep -o '"ruleId"' "$1" | wc -l || echo -1
# printed BOTH "0" (from wc) and "-1" (from the fallback) for a clean report, and every
# comparison downstream then died with "integer expression expected" and fell through to FAIL.
# A tool that found nothing was reported as a breach — the precise inversion of this file's job.
sarif_count() {
  [ -f "$1" ] || { echo -1; return; }
  grep -o '"ruleId"' "$1" 2>/dev/null | wc -l
}

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

# Sonar counts against the SAST budget on purpose: it is the same question (defects in the code
# this team wrote) asked by a second engine, and two separate budgets would let a project pass
# by splitting its findings across them.
n=$(sarif_count "$R/sonar/sonar.sarif")
if [ "$n" -lt 0 ]; then skip "sonar not run"
elif [ "$n" -le "${MAX_QUALITY_FINDINGS:-500}" ]; then pass "quality findings: $n (max ${MAX_QUALITY_FINDINGS:-500})"
else fail "quality findings: $n (max ${MAX_QUALITY_FINDINGS:-500})"; fi

n=$(sarif_count "$R/zap/zap.sarif")
if [ "$n" -lt 0 ]; then skip "ZAP not run"
elif [ "$n" -le "${MAX_DAST_FINDINGS:-999}" ]; then pass "DAST alerts: $n (max ${MAX_DAST_FINDINGS:-999})"
else fail "DAST alerts: $n (max ${MAX_DAST_FINDINGS:-999})"; fi

# k6: a p95 or error rate outside the SLO is a failure, not a note in a log.
S="$R/k6/summary.json"
if [ -f "$S" ]; then
  # Tolerate the space after the colon. k6 writes `"p(95)": 38.9`; a pattern without `[[:space:]]*`
  # matched nothing, both variables came out empty, and the two `[ -n ... ]` guards below then
  # skipped the checks WITHOUT printing a single line — no PASS, no FAIL, no skip. A load run
  # that breached every threshold left a gate output in which k6 simply did not appear.
  #
  # `head -1` is also wrong here: the first "p(95)" in the file belongs to whichever metric k6
  # serialised first (iteration_duration, typically), not to http_req_duration.
  # Parsed as JSON, not with grep. k6 pretty-prints its summary, so "http_req_duration" and the
  # "p(95)" that belongs to it land on different LINES — and grep/sed are line-oriented, so every
  # pattern either matched nothing or matched the p(95) of whichever metric happened to be
  # serialised first. python3 is already a hard dependency of this lab (tools/dashboard.py).
  read -r p95 err <<EOF
$(python3 -c '
import json, sys
try:
    m = json.load(open(sys.argv[1])).get("metrics", {})
    d = m.get("http_req_duration", {})
    f = m.get("http_req_failed", {})
    print(int(d.get("p(95)", -1)), f.get("value", -1))
except Exception:
    print("", "")
' "$S")
EOF
  [ "${p95:--1}" = "-1" ] && p95=""
  [ "${err:--1}" = "-1" ] && err=""
  [ -n "${p95:-}" ] || skip "k6 p95: present but unparsable in $S — treat as NOT measured"
  [ -n "${err:-}" ] || skip "k6 error rate: present but unparsable in $S — treat as NOT measured"
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
