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
. "$(dirname "$0")/lib-repos.sh"

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

# MULTI-REPO: este script era el ÚNICO consumidor de SRC_PATH que no pasaba por
# lib-repos.sh. Exigía `$SRC/.git`, y el contrato del perfil dice que en un proyecto de
# VARIOS repositorios SRC_PATH apunta al DIRECTORIO PADRE — que por definición no es un
# repositorio. El resultado era «ni SRC_PATH con .git ni REPO_URL — nada que inspeccionar»,
# o peor: si el perfil traía REPO_URL, caía al clon bare y auditaba el contrato de despliegue
# de UN solo repositorio sin decir en ninguna parte que el otro no se miró. Le pasó a
# reportes_de_cursos (dos repos, solo se inspeccionó Analitica_cursos).
#
# La regla es la misma que la del resto del laboratorio: se recorren los repositorios
# descubiertos y se elige AQUEL QUE CONTIENE el documento. Los demás se registran, porque un
# proyecto multi-repo con un solo DEPLOY.md es un dato del cotejo, no un detalle de
# implementación.
REPOS_ALL=(); REPO_WITH_DOC=""
if [ -n "$SRC" ] && [ -d "$SRC" ]; then
  while IFS= read -r r; do [ -n "$r" ] && REPOS_ALL+=("$r"); done < <(src_roots "$SRC")
fi

if [ "${#REPOS_ALL[@]}" -gt 0 ] && [ -d "${REPOS_ALL[0]}/.git" ]; then
  MODE="checkout local"
  for cand in "${REPOS_ALL[@]}"; do
    [ -d "$cand/.git" ] || continue
    for b in $BRANCHES; do
      if git_at "$cand" cat-file -e "origin/$b:$DEPLOY_DOC" 2>/dev/null; then
        REPO="$cand"; FOUND_BRANCH="origin/$b"; break 2
      elif git_at "$cand" cat-file -e "$b:$DEPLOY_DOC" 2>/dev/null; then
        REPO="$cand"; FOUND_BRANCH="$b"; break 2
      fi
    done
  done
  # Ningún repositorio trae el documento: se inspecciona el primero de todos modos, para que
  # el cotejo se emita con su CRÍTICO «no hay documento» en vez de morir sin informe.
  REPO="${REPO:-${REPOS_ALL[0]}}"
  REPO_WITH_DOC="$([ -n "$FOUND_BRANCH" ] && basename "$REPO")"
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
#
# Sexta corrección, ganada con anuncios_del_curso (2026-08-25), y otra vez el mismo patrón:
# cuanto mejor documenta un equipo una ausencia, más defectos falsos se le imputan. Su
# DEPLOY.md §1.1 dice «**El repositorio no contiene `Dockerfile`, `docker-compose.yml`,
# `compose.yml`, …**», una negación explícita y con búsqueda declarada. La alternancia traía
# `no (hay|est|existe|se us|trae|viene)` y ninguna de esas formas es `contiene`, así que las
# DOS negaciones se reportaron como ALTO: «cita `compose.yml` como si estuviera». Faltaba un
# verbo, y el precio de que falte es una acusación al equipo por haber documentado bien.
#
# Séptima corrección, ganada con portafolio_del_aprendiz (2026-08-25). Dos cosas nuevas:
#
# (a) EL «SE» IMPERSONAL. Su DEPLOY.md §3 abre con «No se requiere Node/npm para correr el
#     plugin» y a continuación cita `npm-shrinkwrap.json`. La alternancia listaba los verbos
#     pegados a `no ` y trataba el reflexivo como casos sueltos (`no se us`, `no se usan`), así
#     que «no SE requiere» no casaba con nada. El `(se )?` opcional cubre de una vez todas las
#     formas impersonales y hace innecesarios esos parches — es la generalización que las seis
#     correcciones anteriores fueron pidiendo de una en una.
#
# (b) «ESTO EXISTE, PERO NO AQUÍ», que no es una ausencia sino una declaración de ALCANCE, y no
#     estaba contemplada como categoría. El mismo párrafo dice que esos ficheros «existen en la
#     raíz de Moodle core […], no de este plugin — fuera de alcance». Comprobado: los tres
#     están de verdad en /var/www/zajuna/. El documento era EXACTO y aun así se le imputó un
#     ALTO por no traer un fichero que nunca prometió. Un plugin vive dentro de un núcleo
#     ajeno: acotar el alcance así es lo NORMAL en este ecosistema, no un caso raro.
#
# Sobre el ANCHO, que costó una segunda pasada: el primer intento añadió también
# `pertenecen? a(l)? (núcleo|core|Moodle)` y `de(l| la) (núcleo|core) de`. Medido contra los
# seis DEPLOY.md ya congelados, eso eximía citas en adi (`docker-compose.yml`, `index.php`) y
# en reportes_de_cursos (`package.json`, `bun.lock`) — prosa corriente que menciona «del core»
# sin negar nada. Un vocabulario de exención demasiado ancho no produce un falso positivo:
# produce un falso NEGATIVO, que es peor porque nadie lo ve — se manifiesta como un informe
# más limpio. Se dejan solo las formas que nombran otro ÁRBOL de forma inequívoca.
ABSENCE_RE='no (se )?(hay|est|existe|us|trae|viene|contien|incluy|posee|requier)|NO están|sin (evidencia|resultados)|gitignore|no versionad|ausencias?|ausente|sin commitear|no llegará|inexistentes?|no aplica|fuera de (alcance|este repo)|en la ra[íi]z de Moodle|no (forma|forman) parte de este repo'

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
#
# EL LOCK NO ES UNO SOLO, y darlo por sentado produjo una acusación falsa. Quinta corrección,
# ganada con reportes_de_cursos (2026-08-21): su `vue-app/` usa **bun**, versiona `bun.lock`
# (103 KB) y el contenedor del front corre `bun install --frozen-lockfile`, o sea que el lock
# manda de verdad. El hallazgo emitido fue «vue-app/package.json sin su package-lock.json»,
# ALTO, y era falso: lo que faltaba era el lock DE OTRO gestor. El segundo argumento pasa a ser
# la lista de locks ACEPTABLES, separados por `|`; basta con que exista uno.
check_manifest() {
  local manifest="$1" locks="$2" ecosystem="$3"
  local primero="${locks%%|*}"
  local legible; legible=$(printf '%s' "$locks" | tr '|' ' ')
  local anywhere; anywhere=$(tree | grep -E "(^|/)$manifest$" | head -1)
  if [ -z "$anywhere" ]; then
    if is_ignored "$manifest"; then
      add CRITICO "$manifest está en .gitignore y no existe en el repositorio" \
          "ecosistema $ecosystem · un clon limpio no lo trae: 'install' falla y NO hay dimensión de CVE de dependencias"
      REPORTED="$REPORTED $manifest $legible"
    fi
    return
  fi
  local dir; dir=$(dirname "$anywhere"); [ "$dir" = "." ] && dir=""
  local lock encontrado="" ignorado=""
  for lock in ${locks//|/ }; do
    if has "${dir:+$dir/}$lock"; then encontrado="$lock"; break; fi
    is_ignored "$lock" && ignorado="$lock"
  done
  [ -n "$encontrado" ] && return
  if [ -n "$ignorado" ]; then
    add CRITICO "$ignorado está en .gitignore" \
        "$anywhere existe pero su lock no se versiona: las versiones instaladas no son reproducibles ni auditables"
  else
    add ALTO "$anywhere sin lock ($legible)" \
        "sin lock, cada instalación resuelve versiones distintas: el CVE que se mida no es el que corre en producción"
  fi
  REPORTED="$REPORTED $legible"
  : "$primero"
}
check_manifest composer.json    composer.lock      PHP/Composer
check_manifest package.json     'package-lock.json|yarn.lock|pnpm-lock.yaml|bun.lock|bun.lockb|npm-shrinkwrap.json'  Node
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
      *.conf)                                continue ;;   # apache2.conf, postgresql.conf, nginx.conf
      *.ini)                                 continue ;;   # php.ini y compañía: son del HOST, no del repo.
                                                           # reportes_de_cursos citaba `php.ini` para decir
                                                           # que NO se edita ("se pone en conf.d, no editando
                                                           # php.ini") y se le imputó como archivo prometido.
      admin/*|lib/*|*/lib/*.class.php)       continue ;;   # arbol de Moodle core
      *.class.php)                           continue ;;   # convencion de librerias de Moodle core
      config.php|*/config.php)               continue ;;   # config.php de Moodle: NUNCA se versiona

      # Cuarta correccion, ganada con analitica_notificaciones, y la misma leccion que las tres
      # anteriores: cuanto mejor documenta un equipo su integracion, mas defectos falsos se le
      # imputaban. Su DEPLOY.md explica el SSO citando `login/token.php` — el ENDPOINT de Moodle
      # contra el que la aplicacion hace POST para obtener el wstoken (api/moodle_auth.py:
      # f"{settings.moodle_url}/login/token.php"). No es un archivo de este repositorio, no puede
      # serlo, y exigirlo produjo un ALTO que dice, literalmente, que falta un fichero del nucleo
      # de Moodle en un proyecto que no es Moodle.
      #
      # La regla de fondo: una cita puede ser una RUTA HTTP de un sistema externo, no una
      # referencia a un archivo del arbol. El script no sabe distinguirlas en general, pero si
      # conoce los directorios de entrada de Moodle, que es contra lo que se integra media
      # fabrica.
      login/*|*/login/*)                     continue ;;   # login/token.php, login/logout.php: endpoints de Moodle
      webservice/*|*/webservice/*)           continue ;;   # webservice/rest/server.php: idem
    esac
    has "$cand" && continue
    tree | grep -qE "^$(printf '%s' "$cand" | sed 's|[.[\*^$]|\\&|g')/" && continue
    # Match by basename too: DEPLOY.md says `phpunit.xml`, the repo has dashboard/phpunit.xml.
    tree | grep -qE "(^|/)$(basename "$cand" | sed 's|[.[\*^$]|\\&|g')$" && continue

    # Septima correccion, ganada con anuncios_del_curso (2026-08-25). Hermana de la de
    # `login/*` de arriba, y por la misma razon de fondo: media fabrica se integra CONTRA
    # Moodle, y un documento de despliegue bueno cita los scripts CLI del nucleo.
    #
    # El caso `admin/*` del case de arriba ya cubria la forma con directorio, pero la cita
    # llega muchas veces por su BASENAME: DEPLOY.md escribe el comando completo
    # `sudo -u www-data php /var/www/zajuna/admin/cli/uninstall_plugins.php` y luego se refiere
    # a el en prosa como «`uninstall_plugins.php` corre en dry-run salvo que pases --run». Solo
    # el segundo entra por el extractor (el primero empieza por `/` y el patron exige
    # alfanumerico), asi que `$cand` es un basename pelado y `admin/*` no casa.
    #
    # Se decide con la evidencia del PROPIO documento en vez de con una lista de nombres: si
    # el texto muestra ese fichero bajo `admin/cli/`, es del nucleo de Moodle y no puede estar
    # en el repositorio de un plugin. Exigirlo produce un ALTO que dice, literalmente, que al
    # plugin le falta un fichero de Moodle.
    grep -qE "admin/cli/$(basename "$cand" | sed 's|[.[\*^$]|\\&|g')([^A-Za-z0-9_.-]|$)" \
      "$TDIR/DEPLOY.md" && continue

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
    #
    # -A2 desde portafolio_del_aprendiz (2026-08-25): la ventana solo miraba hacia ATRAS, y esa
    # asimetria no responde a nada — un documento puede nombrar el fichero y CALIFICARLO en la
    # frase siguiente igual de bien que en la anterior. Su §3 lo hace: cita
    # `npm-shrinkwrap.json` al final de una linea y explica dos lineas mas abajo que vive «en la
    # raiz de Moodle core […] fuera de alcance». Con -B2 la calificacion caia fuera de la
    # ventana y el ALTO salia aunque el vocabulario de ABSENCE_RE ya lo reconociera. Las dos
    # mitades del arreglo hacen falta: el verbo Y la ventana.
    # LA VENTANA SE QUEDA EN -B2, y esto se midió antes de tocarla. Al arreglar el falso
    # positivo de portafolio_del_aprendiz pareció natural mirar también hacia ADELANTE (-A1),
    # porque ahí la calificación va después de la cita. Medido sobre los seis DEPLOY.md ya
    # congelados, ese solo cambio eximía TRECE citas que hoy se reportan: `docker-compose.yml`
    # e `index.php` en adi, `pg_hba.conf` en analitica_notificaciones, `package.json`,
    # `bun.lock`, `ci.yml`, `setup.sh` y dos `version.php` en reportes_de_cursos. Ninguna por
    # una negación: por arrastrar la primera línea del párrafo siguiente, que en un documento de
    # despliegue casi siempre contiene un «no hay» sobre OTRA cosa.
    #
    # Ampliar la ventana no produce un falso positivo, produce un falso NEGATIVO — y ese nadie
    # lo ve, porque se manifiesta como un informe más limpio. El caso que motivó todo esto se
    # resuelve en el VOCABULARIO (ver ABSENCE_RE), que es preciso, y no en la ventana, que no
    # distingue de qué habla la frase que arrastra.
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
# Segunda pasada del mismo defecto, con portafolio_del_aprendiz (2026-08-25). Su DEPLOY.md §6
# dice: «Este proyecto **no usa archivos `.env`** (no existe `.env`, `.env.example` ni
# `.env.template` en el repo)» — y a continuacion documenta la configuracion REAL en dos tablas
# (config.php de Moodle, y mdl_config_plugins via settings.php del plugin). Es exactamente la
# respuesta que esta comprobacion busca, dada con mas precision que el ejemplo que la exime:
# nombra `.env.example` LITERALMENTE para decir que no existe. Y aun asi se emitia el MEDIO,
# porque la alternancia exigia la palabra «variables de entorno» y este documento habla de los
# FICHEROS. La pregunta que importa es «¿el documento declara como se configura esto?», no con
# que sustantivo lo declara. Se acepta tambien la negacion sobre los ficheros.
elif [ "$DEPLOY_PRESENT" = yes ] && \
     grep -qiE 'no (usa|hay|existen?) (ninguna )?variables? de entorno|no environment variables|\.env\*?: *inexistentes|no (usa|hay|existen?|se usan) .{0,20}(archivos?|ficheros?) `?\.env|no existe `?\.env' \
          "$TDIR/DEPLOY.md" 2>/dev/null; then
  :
else
  add MEDIO "No hay .env.example" \
      "no existe una plantilla versionada de configuración: cada despliegue adivina qué variables hacen falta"
fi

# --- CI: is any of this checked automatically, ever ---
#
# EL `grep -q` DE UNA TUBERÍA NO SE PUEDE PROBAR CON `pipefail`, y esto emitió una acusación
# falsa. Medido el 2026-08-21 sobre reportes_de_cursos, que SÍ trae `.github/workflows/ci.yml` y
# `gate.yml`: `grep -q` cierra la tubería en la primera coincidencia, `git ls-tree` muere con
# SIGPIPE, y con `set -o pipefail` (línea 24) la tubería entera devuelve 141. La condición se lee
# como «no hay CI» justo cuando SÍ la hay, y cuantos más archivos tenga el repositorio —más
# probable que git aún estuviera escribiendo— más seguro es el fallo.
#
#   $ bash -c 'set -o pipefail; git ls-tree -r --name-only dev | grep -q "^\.github/"; echo $?'
#   141
#
# La salida del árbol se materializa ANTES de filtrarla. `.gitea/workflows/` va incluido porque
# la fábrica se aloja en Gitea, y acusar de «sin CI» a quien usa las acciones de su propio
# servidor sería la misma clase de error.
ARBOL_CI="$(tree)"
if has .gitlab-ci.yml || has Jenkinsfile \
   || grep -q -e '^\.github/workflows/' -e '^\.gitea/workflows/' -e '^\.circleci/' <<< "$ARBOL_CI"; then
  :
else
  add MEDIO "Sin integración continua" \
      "ni .gitlab-ci.yml ni .github/.gitea/workflows ni Jenkinsfile: nada verifica el proyecto salvo esta auditoría"
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
  echo "- origen: \`${REPO_URL:-$REPO}\` · rama \`${FOUND_BRANCH:-—}\` · commit \`$COMMIT\` ($MODE)"
  echo "- documento buscado: \`$DEPLOY_DOC\`"
  echo "- DEPLOY.md: $([ "$DEPLOY_PRESENT" = yes ] && echo "presente, congelado en \`$TDIR/DEPLOY.md\`" || echo '**AUSENTE**')"
  echo "- ramas consultadas, en orden: \`$(echo "$BRANCHES" | tr ' ' '/')\`"
  # Multi-repo: qué árbol se cotejó y cuáles NO. Sin esta línea, un cotejo sobre uno de dos
  # repositorios se lee como un cotejo sobre el proyecto entero.
  if [ "${#REPOS_ALL[@]}" -gt 1 ]; then
    echo "- **proyecto multi-repositorio** ($((${#REPOS_ALL[@]})) repos bajo \`$SRC\`):"
    for r in "${REPOS_ALL[@]}"; do
      if [ "$r" = "$REPO" ]; then
        echo "  - \`$(basename "$r")\` — **cotejado** (es el que trae \`$DEPLOY_DOC\`)"
      else
        echo "  - \`$(basename "$r")\` — NO cotejado: no contiene \`$DEPLOY_DOC\` en \`$(echo "$BRANCHES" | tr ' ' '/')\`. El contrato de despliegue de este componente NO está verificado por este documento."
      fi
    done
  fi
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
