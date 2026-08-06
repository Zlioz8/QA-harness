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

# Which repositories were audited. A project is not always one checkout: MOVIL is
# zajuna-frontend + zajuna-backend under a parent that is NOT a repo, and asking only for
# `$SRC_PATH/.git` recorded `commit: (not a git checkout)` for a perfectly versioned project —
# the manifest then proves nothing about what was measured. Same discovery rule as
# tools/secrets.sh: the parent itself, or one level of children.
#
# Per repo we also state whether the tree was clean and how far it sits from its upstream,
# because "audited commit abc123" is worth little if the working tree carried uncommitted
# changes or the branch was behind the remote. NOTHING here touches the network: `git fetch`
# is the operator's call, and a manifest that silently fetched would report a comparison the
# auditor never authorised.
mapfile -t repo_rels < <(
  if [ -d "${SRC_PATH:-}/.git" ]; then echo "."; else
    for d in "${SRC_PATH:-.}"/*/; do [ -d "$d.git" ] && basename "$d"; done
  fi
)

repo_row() {   # $1 = path relative to SRC_PATH
  local rel="$1" dir head branch dirty up ahead behind sync
  dir="$SRC_PATH/$rel"
  head=$(git -C "$dir" log -1 --format='%h %s' 2>/dev/null) || return
  branch=$(git -C "$dir" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '-')
  dirty=$(git -C "$dir" status --porcelain 2>/dev/null | wc -l)
  if up=$(git -C "$dir" rev-parse --abbrev-ref '@{u}' 2>/dev/null); then
    read -r behind ahead < <(git -C "$dir" rev-list --left-right --count "@{u}...HEAD" 2>/dev/null)
    if [ "${ahead:-0}" = 0 ] && [ "${behind:-0}" = 0 ]; then sync="aligned with \`$up\`"
    else sync="**${ahead:-?} ahead / ${behind:-?} behind** \`$up\`"; fi
  else
    sync="no upstream"
  fi
  [ "$dirty" -eq 0 ] && dirty="clean" || dirty="**$dirty uncommitted**"
  echo "| \`${rel/#./$(basename "${SRC_PATH:-.}")}\` | \`$branch\` | \`$head\` | $dirty | $sync |"
}

{
  echo "# Run manifest — $TARGET"
  echo
  echo "- date: $(date -Is)"
  echo "- host: $(hostname) · $(nproc) cpu · $(free -g | awk '/^Mem:/{print $2}')G RAM"
  echo "- source: \`${SRC_PATH:-?}\`"
  echo "- declared envelope (perf comparability): cpus=${PERF_CPUS:-unset} memory=${PERF_MEM:-unset}"
  echo
  echo "## Audited code"
  echo
  if [ "${#repo_rels[@]}" -eq 0 ]; then
    echo "\`${SRC_PATH:-?}\` holds no git repository: there is no commit to pin this run to."
    echo "Whatever the tools measured, it cannot be reproduced from a revision."
  else
    echo "| Repository | Branch | HEAD | Working tree | Upstream (no fetch performed) |"
    echo "|---|---|---|---|---|"
    for rel in "${repo_rels[@]}"; do repo_row "$rel"; done
    echo
    echo "Upstream distance is read from the last \`git fetch\` **this machine** performed; the"
    echo "manifest never fetches. Run \`git fetch\` before the audit if the comparison must be current."
  fi
  echo
  echo "## Coverage"
  echo
  echo "| Dimension | Artifact | Ran |"
  echo "|---|---|---|"
  # La tabla se GENERA del registro (lib/dimensions.yml). Antes estaba escrita a mano aquí, y era
  # una de las seis copias de la misma lista — la que quedó más desactualizada: declaraba el
  # artefacto de ZAP como `zap/zap-report.html` mientras el gate y el informe leían `zap.sarif`,
  # y no mencionaba a trufflehog, que llevaba ejecutándose desde siempre.
  #
  # El artefacto que cuenta es el que consume el gate, no el HTML para personas. Una corrida que
  # dejó report/index.html pero no SARIF es una dimensión que se perdió por el camino.
  #
  # La dimensión de dispositivo la conduce una persona contra hardware real; su artefacto es la
  # tabla de jornadas con su logcat, no el SARIF de un escáner. Aparece aquí para que "nadie corrió
  # la app en un teléfono" sea visible en vez de implícito.
  chk() { if [ -s "$R/$2" ]; then echo "| $1 | \`$2\` | yes |"; else echo "| $1 | \`$2\` | **NO** |"; fi; }
  while IFS=$'\t' read -r label artifact; do
    [ -n "$artifact" ] && chk "$label" "$artifact"
  done < <(tools/dimensions.py --list label,artifact)
  echo
  # El guion es el TECHO de la cobertura: una dimension no encuentra nada fuera de lo que su
  # guion ejercita. Sin esta seccion, «Carga: p95 30 ms · PASS» se lee igual midiendo un humo de
  # tres peticiones que una campana de diez guiones. Quien reciba este informe —otra persona de
  # QA, o un agente que deba entender a la vez el proyecto y la herramienta— necesita saber CON
  # QUE se midio, no solo QUE se midio.
  LAB_DIR="$PWD" tools/guion.py "$TARGET" 2>/dev/null || true
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
