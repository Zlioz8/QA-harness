#!/usr/bin/env bash
# Freeze the current contents of reports/<target>/ as one immutable run under runs/<stamp>/.
#
# WHY RUNS ARE KEPT AT ALL. reports/<target>/ is flat and every audit overwrites the previous
# one. That is survivable for a one-shot scan and useless for a factory, because the question a
# RE-audit exists to answer is not "how many findings are there" — it is "did they fix what we
# reported, and did a fix break something else". Neither is answerable without the earlier run
# to compare against. Worse, a bare total actively misleads: a project that closed six findings
# and introduced two regressions shows a SMALLER number and a worse state.
#
# WHY ARCHIVE INSTEAD OF WRITING STRAIGHT INTO runs/. Twenty services in docker-compose.yml
# mount `./reports/${TARGET_NAME}/<tool>` by hand. Redirecting them all at a per-run directory
# would mean twenty edits plus trusting how the daemon resolves a symlinked bind mount — a lot
# of new failure surface for a directory name. Copying afterwards costs a few MB and touches
# nothing: gate, dashboard, status and the web UI keep reading the exact paths they always did.
#
# WHAT IS DELIBERATELY NOT ARCHIVED.
#   triage.json  a triage verdict judges a FINDING, not an execution, and must apply to every
#                run. It stays at the target root so re-auditing never discards the human work.
#   runs/        no recursion.
set -uo pipefail
TARGET="${1:?usage: run-archive.sh <target>}"
R="reports/$TARGET"
ENVFILE="targets/$TARGET/target.env"
. "$(dirname "$0")/lib-env.sh"

[ -d "$R" ] || { echo "run-archive: nothing at $R"; exit 2; }

SRC_PATH=$(src_path_of)
commit=$(git -C "${SRC_PATH:-.}" rev-parse --short HEAD 2>/dev/null || echo nocommit)
STAMP="$(date +%Y%m%d-%H%M%S)-${commit}"
DEST="$R/runs/$STAMP"

mkdir -p "$DEST"
# Everything except the run store itself and the cross-run triage.
find "$R" -mindepth 1 -maxdepth 1 \
     ! -name runs ! -name triage.json ! -name latest \
     -exec cp -r {} "$DEST/" \; 2>/dev/null

# A run with no artifacts is a bookkeeping error, not a result. Refuse to record it: an empty
# run in the history would later read as "we measured and found nothing".
if [ -z "$(find "$DEST" -type f -size +0 2>/dev/null | head -1)" ]; then
  rm -rf "$DEST"
  echo "run-archive: $R holds no artifacts — nothing archived (did the run actually execute?)"
  exit 1
fi

ln -sfn "runs/$STAMP" "$R/latest"   # convenience pointer; relative so the tree stays movable

# Retention. Re-auditing ~30 repositories several rounds each fills a disk otherwise.
# KEEP_RUNS del perfil (target.env[.local]) o del entorno. Antes llamaba a `lab_get`, que vivía en
# un lab.env por máquina que nunca llegó a la rama principal: la llamada fallaba en silencio.
KEEP=$(envget KEEP_RUNS); KEEP=${KEEP:-${KEEP_RUNS:-5}}
if [ "$KEEP" -gt 0 ] 2>/dev/null; then
  # Newest first, drop everything past the Nth. `ls -1` on stamped names sorts chronologically
  # because the stamp leads with the date.
  ls -1 "$R/runs" 2>/dev/null | sort -r | tail -n +$((KEEP + 1)) | while IFS= read -r old; do
    [ -n "$old" ] && rm -rf "$R/runs/${old:?}"
  done
fi

echo "$STAMP"
