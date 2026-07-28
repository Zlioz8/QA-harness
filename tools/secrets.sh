#!/usr/bin/env bash
# Secrets dimension. Two failure modes this script exists to prevent, both seen on a
# multi-repo target with no top-level .git (finding: MOVIL = zajuna-frontend + zajuna-backend,
# each its own repo, mounted under a parent that is not a repo):
#
#   1. gitleaks `detect` on a non-repo scans 0 commits and reports "no leaks found" —
#      a FALSE PASS. `skip` is not `PASS`, and neither is "scanned nothing".
#   2. trufflehog `git file:///repo` on a non-repo exits 128 and aborts `make secrets`,
#      taking the whole dimension down over an environment shape.
#
# So: discover every git repo under SRC_PATH (the parent itself, or one level of
# children), scan each repo's HISTORY, and ALWAYS add a working-tree filesystem pass so a
# source with no git at all is still scanned instead of silently passing. Results merge
# into the single reports/<t>/gitleaks.sarif that gate/dashboard already read.
set -uo pipefail
TARGET="${1:?usage: secrets.sh <target>}"
ENVFILE="targets/$TARGET/target.env"
REPORTS="reports/$TARGET"
DC="docker compose --env-file $ENVFILE -f docker-compose.yml"
envget() { sed -n "s/^${1}=//p" "$ENVFILE" 2>/dev/null | tail -1 \
  | sed -E 's/[[:space:]]+#.*$//; s/^[[:space:]]+//; s/[[:space:]]+$//; s/^"//; s/"$//'; }
SRC_PATH="$(envget SRC_PATH)"

GL_ARGS="--report-format sarif --exit-code 0 --redact --config /config/gitleaks.toml"

# Discover repos as paths RELATIVE to SRC_PATH (which the container sees as /repo).
mapfile -t rels < <(
  if [ -d "$SRC_PATH/.git" ]; then echo "."; else
    for d in "$SRC_PATH"/*/; do [ -d "$d.git" ] && basename "$d"; done
  fi
)

# Clear stale partials AND a previous merged report. The old report may be root-owned
# (written by the compose gitleaks service in a pre-fix run); rm works because the reports
# directory itself is host-user-owned, so the merge below can recreate it.
rm -f "$REPORTS"/_gl_*.sarif "$REPORTS/gitleaks.sarif" "$REPORTS/trufflehog.txt"

if [ "${#rels[@]}" -eq 0 ]; then
  # No repo: fall back to a working-tree scan so the dimension still scans real bytes
  # (a clean report means "clean", never "nothing ran"). `dir` ignores .gitignore, so
  # keep it off the dependency trees — 2.78 GB of node_modules is 6 minutes of noise.
  # `dir` ignores .gitignore and has no path-exclude flag; keep node_modules/vendor out
  # via the target's gitleaks.toml [allowlist] paths, or this scan drowns in dependencies.
  echo "secrets: no git repo under SRC_PATH — working-tree scan (no history available)"
  $DC run --rm gitleaks dir /repo $GL_ARGS \
      --report-path /reports/_gl_worktree.sarif || true
else
  # Git history covers every tracked file across all revisions (a superset of the current
  # tree). Untracked working-tree secrets are covered by Trivy's fs secret scanner.
  echo "secrets: git repos: ${rels[*]}"
  for rel in "${rels[@]}"; do
    name="$(echo "$rel" | tr '/.' '__')"
    $DC run --rm gitleaks git "/repo/$rel" $GL_ARGS \
        --log-opts=--all --report-path "/reports/_gl_$name.sarif" || true
  done
fi

# Merge every partial SARIF into the one file gate.sh / dashboard.py consume.
python3 - "$REPORTS" <<'PY'
import glob, json, os, sys
rep = sys.argv[1]
parts = sorted(glob.glob(os.path.join(rep, "_gl_*.sarif")))
base, results = None, []
for f in parts:
    try:
        d = json.load(open(f))
    except Exception:
        continue
    run = (d.get("runs") or [{}])[0]
    results.extend(list(run.get("results") or []))   # copy BEFORE base may alias d
    if base is None:
        base = d
if base is None:
    base = {"version": "2.1.0",
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [{"tool": {"driver": {"name": "gitleaks", "rules": []}}, "results": []}]}
base["runs"][0]["results"] = results
json.dump(base, open(os.path.join(rep, "gitleaks.sarif"), "w"), indent=2)
for f in parts:
    os.remove(f)
print(f"secrets: merged {len(parts)} pass(es) -> gitleaks.sarif ({len(results)} findings)")
PY

# trufflehog is the corroborating pass (live-verifies a subset). It is NOT on the gate's
# critical path — only gitleaks.sarif is — and its git-history scan is slow on large repos,
# so it runs LAST and time-boxed. Killing it never costs the merged gitleaks result.
TH_TIMEOUT="${SECRETS_TRUFFLEHOG_TIMEOUT:-90}"
if [ "${#rels[@]}" -eq 0 ]; then
  timeout "$TH_TIMEOUT" $DC run --rm trufflehog \
      filesystem /repo --json --no-update >> "$REPORTS/trufflehog.txt" 2>/dev/null || true
else
  for rel in "${rels[@]}"; do
    timeout "$TH_TIMEOUT" $DC run --rm trufflehog \
        git "file:///repo/$rel" --json --no-update >> "$REPORTS/trufflehog.txt" 2>/dev/null || true
  done
fi
echo "secrets: trufflehog corroboration in $REPORTS/trufflehog.txt ($(wc -l < "$REPORTS/trufflehog.txt" 2>/dev/null || echo 0) hits)"
