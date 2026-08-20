#!/usr/bin/env bash
# Fetch a project's DEPLOY.md and check the repository against what it promises.
#
# DEPLOY.md is what the factory's developers were asked to deliver: the document that says how
# their project is deployed. Until now the lab never looked at it. That is a waste twice over —
# it is the best description of the runtime anyone will write, and it is also *testable*: a
# deployment document is a set of claims about a repository, and a repository either backs them
# or it does not.
#
# The failure this catches is the expensive one. ADI's own DEPLOY.md states, in writing, that
# composer.json and composer.lock are gitignored (so a clean clone cannot install dependencies)
# and that migration 008 was never committed (so login fails with an opaque 500). A team can
# read that document, believe the project is deployable, and lose a day discovering otherwise.
# Worse for an audit: without the manifest there is no dependency-CVE dimension at all, and a
# silent absence looks exactly like a clean result.
#
# So the rule here: report only what can be VERIFIED against the repository, never an opinion
# about the prose. Every check below is a file that exists or does not, is ignored or is not.
#
#   tools/ingest-deploy.sh <target> [repo-url]
#
# The branch order is the convention the QA lead set with the teams: DEPLOY.md lives on `dev`,
# and if it is not there, on `dev2`.
set -uo pipefail

TARGET="${1:?usage: ingest-deploy.sh <target> [repo-url]}"
TDIR="targets/$TARGET"
ENVFILE="$TDIR/target.env"
[ -f "$ENVFILE" ] || { echo "no $ENVFILE — run: make new TARGET=$TARGET"; exit 2; }
. "$(dirname "$0")/lib-env.sh"

REPO_URL="${2:-$(envget REPO_URL)}"

# DEPLOY_BRANCHES sale del PERFIL, no solo del entorno.
#
# Antes esto era `${DEPLOY_BRANCHES:-dev dev2}` a secas, y `envget` lee el fichero: la variable
# de shell nunca se rellenaba desde target.env, así que una declaración en el perfil se ignoraba
# EN SILENCIO. No se notó porque el único perfil que la declaraba (adi) le puso justo el valor
# por defecto. En anuncios_de_plataforma el remoto no tiene `dev` ni `dev2` —sus ramas son main,
# feature/slider-form_Carlos y feature_test/slider-form_Carlos— de modo que la búsqueda fallaba
# y la ausencia del documento parecía del equipo cuando era del laboratorio.
BRANCHES="${DEPLOY_BRANCHES:-$(envget DEPLOY_BRANCHES)}"
BRANCHES="${BRANCHES:-dev dev2}"

# Dónde vive el documento DENTRO del repositorio. Por defecto en la raíz, que es el caso normal.
#
# Un repositorio puede contener VARIOS componentes desplegables y entregar un DEPLOY.md por
# cada uno: anuncios_de_plataforma trae `slider/` y `slider_form/`, y el documento está en
# `slider_form/DEPLOY.md`. Sin esto, la comprobación miraba la raíz, no encontraba nada y
# emitía un CRÍTICO «el equipo no ha entregado el documento» sobre un equipo que sí lo entregó
# — la peor clase de hallazgo, porque es falso y comprobable.
DEPLOY_DOC="${DEPLOY_DOC:-$(envget DEPLOY_DOC)}"
DEPLOY_DOC="${DEPLOY_DOC:-DEPLOY.md}"
OUT="reports/$TARGET"
mkdir -p "$OUT"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# ---- 1. get a tree to inspect ---------------------------------------------------------------
#
# Prefer a local checkout: it costs nothing and no key enters a container (lab finding L2).
# Fall back to a bare shallow clone when the code is not on this machine yet.
# envget ya aplica el override de target.env.local (ver tools/lib-env.sh).
SRC=$(envget SRC_PATH)
FOUND_BRANCH=""; COMMIT=""; MODE=""

git_at() { git -C "$1" "${@:2}"; }

if [ -n "$SRC" ] && [ -d "$SRC/.git" ]; then
  MODE="checkout local"
  REPO="$SRC"
  for b in $BRANCHES; do
    if git_at "$REPO" cat-file -e "origin/$b:$DEPLOY_DOC" 2>/dev/null; then
      FOUND_BRANCH="origin/$b"; break
    elif git_at "$REPO" cat-file -e "$b:$DEPLOY_DOC" 2>/dev/null; then
      FOUND_BRANCH="$b"; break
    fi
  done
elif [ -n "$REPO_URL" ]; then
  MODE="clon bare superficial"
  REPO="$WORK/bare.git"
  for b in $BRANCHES; do
    if git clone --bare --depth 1 --branch "$b" "$REPO_URL" "$REPO" >/dev/null 2>&1; then
      FOUND_BRANCH="$b"; break
    fi
    rm -rf "$REPO"
  done
  [ -n "$FOUND_BRANCH" ] || { echo "no se pudo clonar $REPO_URL en ninguna de: $BRANCHES"; exit 2; }
  git_at "$REPO" cat-file -e "HEAD:$DEPLOY_DOC" 2>/dev/null || FOUND_BRANCH="${FOUND_BRANCH}:sin-DEPLOY.md"
  REF=HEAD
else
  echo "ingest-deploy: ni SRC_PATH con .git ni REPO_URL en $ENVFILE — nada que inspeccionar"
  exit 2
fi

REF="${FOUND_BRANCH%%:*}"
[ "$MODE" = "clon bare superficial" ] && REF=HEAD
COMMIT=$(git_at "$REPO" rev-parse --short "$REF" 2>/dev/null || echo '?')

has()  { git_at "$REPO" cat-file -e "$REF:$1" 2>/dev/null; }
show() { git_at "$REPO" show "$REF:$1" 2>/dev/null; }
tree() { git_at "$REPO" ls-tree -r --name-only "$REF" 2>/dev/null; }

# ---- 2. freeze the document -----------------------------------------------------------------
DEPLOY_PRESENT=no
if has "$DEPLOY_DOC"; then
  DEPLOY_PRESENT=yes
  show "$DEPLOY_DOC" > "$TDIR/DEPLOY.md"
fi

# ---- 3. the contrast ------------------------------------------------------------------------
#
# Findings accumulate as: SEVERITY<TAB>ID<TAB>title<TAB>evidence
FIND=$WORK/findings.tsv
: > "$FIND"

# The ID is assigned HERE, inside add, and not by a helper called as `$(nid)`. Command
# substitution runs in a subshell, so a counter incremented there is lost the moment it
# returns: the first version of this script numbered all thirteen findings "D1".
n=0
add() {
  n=$((n + 1))
  printf '%s\tD%d\t%s\t%s\n' "$1" "$n" "$2" "$3" >> "$FIND"
}

# Phrases a document uses to say "this is not here". Shared by the two citation checks below,
# which are mirror images of each other and must agree on what counts as declaring an absence.
# Vocabulario ampliado con anuncios_de_plataforma, que encabeza su enumeración con
# «**Ausencias verificadas** (búsqueda explícita, sin resultados):». El patrón traía `ausente`
# en singular y `sin evidencia`, así que no reconocía ninguna de las dos formas y toda la lista
# de tecnologías que el proyecto NO usa se reportaba como ficheros prometidos y no entregados.
ABSENCE_RE='no (hay|est|existe|se us|trae|viene)|NO están|sin (evidencia|resultados)|gitignore|no versionad|ausencias?|ausente|no se usan|sin commitear|no llegará|inexistentes?|no aplica'

# Files already reported by the manifest check, so the citation check does not repeat them.
REPORTED=""

IGNORED=""
has .gitignore && IGNORED=$(show .gitignore)
is_ignored() { printf '%s\n' "$IGNORED" | grep -qE "^[[:space:]]*/?$(printf '%s' "$1" | sed 's/[.[\*^$]/\\&/g')[[:space:]]*$"; }

if [ "$DEPLOY_PRESENT" = no ]; then
  add CRITICO "No hay $DEPLOY_DOC en ninguna rama de $BRANCHES" \
      "buscado en: $BRANCHES · el equipo no ha entregado el documento de despliegue"
fi

# --- dependency manifests: the check that catches ADI ---
#
# A manifest without its lock is a build that cannot be reproduced. A manifest that is
# GITIGNORED is worse: a clean clone does not even contain it, so `install` fails outright and
# the dependency-CVE dimension of this audit has nothing to read. That absence must never be
# mistaken for "no vulnerable dependencies".
check_manifest() {
  local manifest="$1" lock="$2" ecosystem="$3"
  local anywhere; anywhere=$(tree | grep -E "(^|/)$manifest$" | head -1)
  if [ -z "$anywhere" ]; then
    if is_ignored "$manifest"; then
      add CRITICO "$manifest está en .gitignore y no existe en el repositorio" \
          "ecosistema $ecosystem · un clon limpio no lo trae: 'install' falla y NO hay dimensión de CVE de dependencias"
      REPORTED="$REPORTED $manifest $lock"
    fi
    return
  fi
  local dir; dir=$(dirname "$anywhere"); [ "$dir" = "." ] && dir=""
  local lockpath="${dir:+$dir/}$lock"
  if ! has "$lockpath"; then
    if is_ignored "$lock"; then
      add CRITICO "$lock está en .gitignore" \
          "$anywhere existe pero su lock no se versiona: las versiones instaladas no son reproducibles ni auditables"
      REPORTED="$REPORTED $lock"
    else
      add ALTO "$anywhere sin su $lock" \
          "sin lock, cada instalación resuelve versiones distintas: el CVE que se mida no es el que corre en producción"
      REPORTED="$REPORTED $lock"
    fi
  fi
}
check_manifest composer.json    composer.lock      PHP/Composer
check_manifest package.json     package-lock.json  Node/npm
check_manifest requirements.txt requirements.txt   Python/pip
check_manifest pyproject.toml   poetry.lock        Python/poetry
check_manifest go.mod           go.sum             Go

# --- files DEPLOY.md names but the repository does not contain ---
#
# A false accusation here is worse than a miss: it sends a developer hunting for a problem that
# does not exist, and teaches them to skim this section. Two refinements earned by ADI:
#
#  1. Generated artifacts are excluded outright. `vendor/autoload.php` is produced by
#     `composer install`; a repository that contained it would be the finding.
#
#  2. A citation is not automatically a claim of presence. ADI's DEPLOY.md names
#     `package.json` precisely to state that the project has none ("No hay package.json en
#     ningún nivel del repo — no hay paso de build"). Reporting that as a contradiction is
#     misreading the document. So: when the citing line already declares the absence, this is
#     a gap the team has DOCUMENTED — real, worth listing, but not the same defect as a
#     document that assumes a file which is not there.
if [ "$DEPLOY_PRESENT" = yes ]; then
  while IFS= read -r cand; do
    [ -z "$cand" ] && continue
    case "$cand" in
      /*|*" "*|http*|*.com*|*@*) continue ;;
      vendor/*|*/vendor/*|node_modules/*|*/node_modules/*) continue ;;   # generated, never committed

      # --- artefactos que NO son del repositorio y nunca deberían estarlo -------------------
      #
      # Tercera correccion, ganada con anuncios_de_plataforma. Su DEPLOY.md produjo CINCO
      # hallazgos ALTO falsos, y los cinco por ser un documento BUENO: un manual de despliegue
      # minucioso cita el fichero de configuracion del servidor web, el del motor de base de
      # datos y las librerias del framework sobre el que corre. Ninguno de esos vive en el
      # repositorio del proyecto, ni debe.
      #
      #   admin/cli/checks.php   Moodle core, en un checklist de verificacion
      #   excellib.class.php     Moodle core, bajo $CFG->libdir
      #   apache2.conf           configuracion del sistema
      #   postgresql.conf        configuracion del motor
      #
      # El incentivo que esto invertia es el peligroso: cuanto mejor documentaba un equipo su
      # despliegue, mas defectos falsos se le imputaban. Un revisor que ve cinco acusaciones
      # falsas deja de leer la seccion entera — y ahi es donde estan los hallazgos de verdad.
      config|*/config)                       continue ;;
      *.conf)                                continue ;;   # apache2.conf, postgresql.conf, nginx.conf, php.ini-*
      admin/*|lib/*|*/lib/*.class.php)       continue ;;   # arbol de Moodle core
      *.class.php)                           continue ;;   # convencion de librerias de Moodle core
      config.php|*/config.php)               continue ;;   # config.php de Moodle: NUNCA se versiona
    esac
    has "$cand" && continue
    tree | grep -qE "^$(printf '%s' "$cand" | sed 's|[.[\*^$]|\\&|g')/" && continue
    # Match by basename too: DEPLOY.md says `phpunit.xml`, the repo has dashboard/phpunit.xml.
    tree | grep -qE "(^|/)$(basename "$cand" | sed 's|[.[\*^$]|\\&|g')$" && continue

    # Already reported by the manifest check above, with better evidence. Saying it twice at
    # two severities makes the reader distrust both entries.
    case " $REPORTED " in *" $cand "*) continue ;; esac

    # A documented absence is documentation, not a defect. ADI's DEPLOY.md names `package.json`
    # to say the project has none — correct for a server-rendered PHP app with no build step,
    # and reporting it would be inventing a problem. What matters is only the CONTRADICTION:
    # the document assuming a file that is not there and not saying so. Absences that genuinely
    # block a deployment are caught by check_manifest above, which can tell the difference
    # because it fires on a manifest that is gitignored — present in someone's working tree,
    # missing from every clone.
    # -B2: la declaracion de ausencia puede estar en la linea ANTERIOR cuando el documento
    # enumera. anuncios_de_plataforma lo hace: una frase «Verificado por busqueda explicita:
    # ... inexistentes» y a continuacion la lista, envuelta a varias lineas, donde cae
    # `pom.xml`. Mirando solo la linea de la cita, la enumeracion parecia una afirmacion de
    # presencia y se reportaba como contradiccion.
    ctx=$(grep -B2 -F -- "\`$cand\`" "$TDIR/DEPLOY.md" | head -9)
    printf '%s' "$ctx" | grep -qiE "$ABSENCE_RE" && continue
    add ALTO "DEPLOY.md cita \`$cand\` como si estuviera, pero no está en el repositorio" \
        "commit $COMMIT de $REF · un clon limpio no lo trae y el documento no advierte de ello"
  done <<< "$(grep -oE '`[A-Za-z0-9_][A-Za-z0-9_./-]*\.(sql|php|json|lock|ya?ml|env|sh|ini|conf|xml)`' \
              "$TDIR/DEPLOY.md" 2>/dev/null | tr -d '`' | sort -u)"

  # --- DELIBERATELY NOT AUTOMATED: "the document warns about something already fixed" ---
  #
  # A real and valuable signal — ADI's DEPLOY.md says migration 008_users_username.sql "no está
  # en ningún commit" and tells the reader to obtain it separately, when it IS committed on
  # `dev`; the warning went stale and costs someone a chase for a file they already have.
  #
  # It was implemented here and removed. Detecting it means deciding whether a negation in the
  # prose refers to the cited file, and a regex cannot: on ADI it produced four false positives
  # out of five, flagging `dashboard/config/define.php` (the nearby "no existe un segundo
  # archivo" is about a config file, not this one), `phpunit.xml` (the document says the test
  # RUNNER is not installed, not that the file is missing) and `docker/apache2.conf` (listed
  # under files that exist but are not used).
  #
  # This file's stated rule is that every check is a file that exists or does not — never an
  # opinion about the prose. Judging staleness is reading comprehension, so it belongs to the
  # person writing the report, not to this script. Three sound findings beat eight where four
  # are wrong: a section that cries wolf is one developers learn to skip.
  :
fi

# --- .env.example, the only safe way to state what configuration is needed ---
#
# Salvo cuando el proyecto NO USA variables de entorno y lo dice con evidencia. Un plugin de
# Moodle toma su configuracion de `config.php` y de `mdl_config_plugins`, no del entorno:
# exigirle un `.env.example` es exigirle una plantilla de algo que no tiene. El DEPLOY.md de
# anuncios_de_plataforma lo declara en su seccion 6 («No aplica: este plugin no usa variables
# de entorno») y lo respalda con el grep que lo comprueba — y aun asi se le imputaba el
# hallazgo. Un documento que responde a la pregunta no puede puntuar como si la hubiera
# ignorado.
if has .env.example || has .env.sample || has .env.dist; then
  :
elif [ "$DEPLOY_PRESENT" = yes ] && \
     grep -qiE 'no (usa|hay|existen?) (ninguna )?variables? de entorno|no environment variables|\.env\*?: *inexistentes' \
          "$TDIR/DEPLOY.md" 2>/dev/null; then
  :
else
  add MEDIO "No hay .env.example" \
      "no existe una plantilla versionada de configuración: cada despliegue adivina qué variables hacen falta"
fi

# --- CI: is any of this checked automatically, ever ---
if has .gitlab-ci.yml || tree | grep -q '^\.github/workflows/' || has Jenkinsfile; then
  :
else
  add MEDIO "Sin integración continua" \
      "ni .gitlab-ci.yml ni .github/workflows ni Jenkinsfile: nada verifica el proyecto salvo esta auditoría"
fi

# --- things that should never be committed, checked against what IS committed ---
while IFS= read -r bad; do
  [ -z "$bad" ] && continue
  add CRITICO "Archivo sensible versionado: \`$bad\`" \
      "commit $COMMIT · presente en el árbol del repositorio"
done <<< "$(tree | grep -E '(^|/)(\.env|\.env\.local|\.env\.production)$|\.(pem|key|p12|pfx)$|(^|/)id_rsa$' | head -10)"

# A dump in the repository is both a deployment smell and, usually, personal data.
#
# Decided by CONTENT, not by filename. The first version matched `*.sql` minus a denylist of
# words and accused ADI's five `dashboard/Consultas/integracion-00*.sql` of being dumps — they
# are plain SELECT queries the application runs. A false accusation is worse than a miss here:
# it sends a developer hunting for a leak that does not exist, and it teaches them to skim past
# this section. A dump carries rows (INSERT/COPY); a query and a migration do not.
while IFS= read -r d; do
  [ -z "$d" ] && continue
  # Row-carrying statements, and enough of them that a lone INSERT in a seed is not a dump.
  rows=$(show "$d" 2>/dev/null | grep -ciE '^[[:space:]]*(INSERT INTO|COPY .* FROM stdin)' )
  [ "${rows:-0}" -ge 20 ] || continue
  add ALTO "Volcado de base de datos versionado: \`$d\`" \
      "commit $COMMIT · ${rows} sentencias de inserción: suele contener datos personales reales y queda en la historia para siempre"
done <<< "$(tree | grep -iE '\.(sql|dump)$' | head -40)"

# ---- 4. report ------------------------------------------------------------------------------
TOTAL=$(wc -l < "$FIND" | tr -d ' ')
# `grep -c` ALREADY prints 0 when nothing matches — it just exits 1 while doing it. The obvious
# `|| echo 0` therefore printed a SECOND zero, and C became the two-line string "0\n0", which
# then rendered as "altos 0\n0" in the summary. Exactly the failure tools/gate.sh documents at
# length in sarif_count: a fallback that is reachable from a perfectly healthy input.
count_sev() { grep -c "^$1" "$FIND" 2>/dev/null; true; }
C=$(count_sev CRITICO)
A=$(count_sev ALTO)
M=$(count_sev MEDIO)

{
  echo "# Contrato de despliegue — $TARGET"
  echo
  echo "- fecha: $(date -Is)"
  echo "- origen: \`${REPO_URL:-$SRC}\` · rama \`${FOUND_BRANCH:-—}\` · commit \`$COMMIT\` ($MODE)"
  echo "- DEPLOY.md: $([ "$DEPLOY_PRESENT" = yes ] && echo "presente, congelado en \`$TDIR/DEPLOY.md\`" || echo '**AUSENTE**')"
  echo "- ramas consultadas, en orden: \`$(echo "$BRANCHES" | tr ' ' '/')\`"
  echo
  echo "## Pregunta que responde este documento"
  echo
  echo "¿Se puede desplegar este proyecto **a partir de su propio repositorio**, siguiendo su"
  echo "propio DEPLOY.md? Cada punto de abajo se verifica contra el árbol del commit auditado —"
  echo "es un archivo que está o no está, ignorado o no. Ninguno es una opinión sobre el texto."
  echo
  echo "| Severidad | Cantidad |"
  echo "|---|---|"
  echo "| Crítico | $C |"
  echo "| Alto | $A |"
  echo "| Medio | $M |"
  echo
  if [ "$TOTAL" -eq 0 ]; then
    echo "**Sin hallazgos.** El repositorio respalda lo que su DEPLOY.md promete."
  else
    echo "## Hallazgos"
    echo
    echo "| ID | Sev | Hallazgo | Evidencia |"
    echo "|---|---|---|---|"
    while IFS=$'\t' read -r sev id title ev; do
      [ -z "$id" ] && continue
      echo "| $id | $sev | $title | $ev |"
    done < "$FIND"
    echo
    echo "## Qué significa para esta auditoría"
    echo
    echo "Un insumo que el repositorio no aporta **no bloquea** la auditoría: se declara insumo"
    echo "del perfil y se le pide al equipo responsable. Pero la dimensión que dependía de él"
    echo "queda marcada **NO AUTORITATIVA** en \`RUN.md\` — medir una reconstrucción del"
    echo "laboratorio y presentarla como medida de la aplicación sería peor que no medir."
  fi
} > "$OUT/deploy-contract.md"

# SARIF, so the gate and the dashboard read this dimension with the machinery they already have
# instead of a second, divergent path.
python3 - "$FIND" "$OUT/deploy-contract.sarif" <<'PY'
import json, sys
sev = {"CRITICO": "error", "ALTO": "error", "MEDIO": "warning"}
rows = []
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        for line in fh:
            p = line.rstrip("\n").split("\t")
            if len(p) == 4:
                rows.append(p)
except OSError:
    pass
json.dump({
    "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
    "version": "2.1.0",
    "runs": [{
        "tool": {"driver": {"name": "deploy-contract", "informationUri":
                            "https://github.com/Zlioz8/QA-harness"}},
        "results": [{
            "ruleId": r[1],
            "level": sev.get(r[0], "note"),
            "message": {"text": f"{r[2]} — {r[3]}"},
            "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": "DEPLOY.md"},
                "region": {"startLine": 1}}}],
        } for r in rows],
    }],
}, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
PY

# Procedencia: contra qué midió esta dimensión. Sin ella su artefacto no se puede atribuir a un
# blanco y el gate no puede marcarlo VIEJO cuando el perfil cambia de commit o de despliegue.
tools/stamp.sh "$TARGET" deploy-contract 2>/dev/null || true

echo "== contrato de despliegue: $TARGET =="
echo "   documento buscado  : $DEPLOY_DOC"
echo "   rama con DEPLOY.md : ${FOUND_BRANCH:-NINGUNA de ($BRANCHES)}"
echo "   commit             : $COMMIT"
echo "   hallazgos          : $TOTAL  (críticos $C · altos $A · medios $M)"
echo "   informe            : $OUT/deploy-contract.md"
[ "$DEPLOY_PRESENT" = yes ] && echo "   documento congelado: $TDIR/DEPLOY.md"
exit 0
