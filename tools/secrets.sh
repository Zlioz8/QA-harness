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
# Un solo lector del perfil, y los DOS --env-file.
#
# Este archivo llevaba su propia copia de envget — la misma que lib-env.sh existe para que no se
# repita — y esa copia se quedó atrás cuando envget aprendió el override target.env.local. El
# perfil dice ahora que los valores que no salen de la máquina viven ahí, así que un SRC_PATH
# puesto en el .local era invisible EXACTAMENTE aquí: SRC_PATH salía vacío, docker rechazaba el
# montaje ":/repo:ro", gitleaks no llegaba a arrancar, y el merge de más abajo escribía un
# informe limpio igualmente. Medido sobre adi, un repositorio que tiene un token de SonarQube
# commiteado: la corrida dijo "0 secretos".
#
# Y el mismo desacuerdo en compose: el Makefile pasa los dos --env-file y este script solo uno,
# de modo que las herramientas y el contenedor leían perfiles distintos del mismo target.
. "$(dirname "$0")/lib-env.sh"
# Y el único descubridor de repositorios. Esta regla vivía aquí, copiada a mano en otros tres
# scripts; ahora vive en un sitio. Ver la cabecera de tools/lib-repos.sh.
. "$(dirname "$0")/lib-repos.sh"
ENVLOCAL=""
[ -f "$ENVFILE.local" ] && ENVLOCAL="--env-file $ENVFILE.local"
DC="docker compose --env-file $ENVFILE $ENVLOCAL -f docker-compose.yml"
SRC_PATH="$(envget SRC_PATH)"

# Fallar ruidosamente antes que escanear nada. Sin esto la corrida sigue, produce un informe
# vacío y el gate estampa PASS sobre un repositorio que nadie miró.
[ -n "$SRC_PATH" ] && [ -d "$SRC_PATH" ] || {
  echo "secrets: SRC_PATH no resuelve a un directorio: '${SRC_PATH:-<vacío>}'"
  echo "         Revísalo en $ENVFILE (o en $ENVFILE.local, que gana sobre él)."
  exit 2
}

GL_ARGS="--report-format sarif --exit-code 0 --redact --config /config/gitleaks.toml"

# Discover repos as paths RELATIVE to SRC_PATH (which the container sees as /repo).
mapfile -t rels < <(discover_repos "$SRC_PATH")

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
#
# El fusionador vivía AQUÍ, incrustado, y con él la regla más importante de todo esto: si ningún
# pase produjo resultados legibles, NO se escribe el archivo. Ahora vive en tools/sarif-merge.py
# porque las dimensiones de código también corren una vez por repositorio y necesitaban la misma
# regla — y una regla así copiada dos veces es una regla que en algún momento solo se cumple una.
# El razonamiento completo (y el «0 secretos» sobre un repositorio con un token commiteado que la
# motivó) está en la cabecera de ese archivo.
tools/sarif-merge.py "$REPORTS/gitleaks.sarif" "$REPORTS"/_gl_*.sarif

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

# Sin esta conversión, todo lo anterior se perdía. El .txt no lo leía NADIE: ni tools/gate.sh, ni
# la tabla de cobertura de run-manifest.sh, ni el informe, ni las pantallas de triaje. Una
# dimensión que se ejecuta, deja artefacto y no llega al veredicto es exactamente el modo de fallo
# que este laboratorio existe para no cometer — el mismo que motivó zap-sarif.py y sonar-export.
#
# Y aquí duele más que en ningún otro sitio: TruffleHog es la única herramienta del lab que
# VERIFICA contra la API del proveedor si la credencial sigue viva. Al convertir por primera vez
# los .txt que ya había en disco aparecieron DOS credenciales de Azure verificadas vivas en
# costos_web (.env y .env.testing), que llevaban ahí sin que las viera nadie.
tools/trufflehog-sarif.py "$REPORTS" || true

# Procedencia: contra que midio esta dimension. Sin esto, su artefacto no se puede
# atribuir a un blanco y el gate no puede excluirlo cuando el perfil cambia de sistema.
tools/stamp.sh "$TARGET" gitleaks 2>/dev/null || true
tools/stamp.sh "$TARGET" trufflehog 2>/dev/null || true
