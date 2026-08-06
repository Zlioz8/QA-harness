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
MAX_VERIFIED_SECRETS=$(envget MAX_VERIFIED_SECRETS)
MAX_DEP_FINDINGS=$(envget MAX_DEP_FINDINGS)
MAX_SAST_FINDINGS=$(envget MAX_SAST_FINDINGS)
MAX_QUALITY_FINDINGS=$(envget MAX_QUALITY_FINDINGS)
MAX_DAST_FINDINGS=$(envget MAX_DAST_FINDINGS)
MAX_MOBILE_FINDINGS=$(envget MAX_MOBILE_FINDINGS)
K6_P95_MS=$(envget K6_P95_MS)
K6_ERR_RATE=$(envget K6_ERR_RATE)

FAIL=0
pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAIL=1; }
skip() { printf '  \033[90mskip\033[0m  %s\n' "$1"; }

# Cuenta hallazgos de un SARIF. Antes era esto:
#
#     grep -o '"ruleId"' "$1" | wc -l
#
# Es decir: un lector de SARIF hecho con grep, mientras tools/dashboard.py tenía uno bueno. Dos
# lectores del mismo formato acaban discrepando, y discrepaban justo en lo que importa — el
# informe pintaba severidades que este veredicto ignoraba por completo. Ahora los dos pasan por
# tools/sarif.py, que es el único.
#
# El contrato NO cambia y es el que sostiene el resto del archivo:
#   * un entero por stdout
#   * -1 cuando el archivo NO EXISTE, que abajo se lee como `skip` = NO EJECUTADO
#   * nunca falla: un SARIF ilegible cuenta 0 en vez de tumbar la corrida entera
#
# (La trampa histórica que motivó el `-1`: `[ -f x ] && grep ... | wc -l || echo -1` imprimía
# 0 Y -1 a la vez para un informe limpio, y toda comparación posterior moría con "integer
# expression expected" y caía en FAIL. Un análisis sin hallazgos se reportaba como incumplimiento,
# la inversión exacta del trabajo de este script. Se conserva la advertencia porque el modo de
# fallo sigue siendo posible en cualquier función nueva que se añada aquí.)
sarif_count() {
  # El conteo que consume el presupuesto: confirmados-a-corregir MÁS los que nadie ha mirado.
  # `--dedup` porque la misma regla en el mismo archivo es UN problema, no quince (en
  # reports/movil/semgrep, 185 resultados sobre 109 pares únicos). `--triage` porque el juicio
  # humano tiene que llegar al veredicto: sin eso el operador juzga 900 hallazgos y el número no
  # se mueve, así que deja de juzgar.
  tools/gate-count.py "$1" --dedup --triage "$R" "$2"
}

# Hallazgos marcados BLOQUEANTE por una persona. No admiten umbral: alguien miró esto y dijo que
# no puede pasar a producción. Un presupuesto que permitiera «tres bloqueantes» sería una
# contradicción en los términos.
bloqueantes() {
  tools/gate-count.py "$1" --triage "$R" "$2" --gate-class fail
}

# Cuántas horas lleva este artefacto en disco. La frescura importa porque el veredicto SUMA
# artefactos de corridas distintas sin decirlo: medido en este mismo laboratorio, un `GATE FAILED`
# mezclaba cinco dimensiones de hace minutos con sonar y playwright de hacía TRES DÍAS, contra otro
# despliegue. Las diez salían como `yes` en la tabla de cobertura. Un veredicto sobre evidencia de
# procedencias distintas no es un veredicto, es un collage.
edad_h() {
  [ -f "$1" ] || { echo -1; return; }
  echo $(( ( $(date +%s) - $(stat -c %Y "$1") ) / 3600 ))
}

MAX_EDAD_H="$(envget MAX_ARTIFACT_AGE_H)"; MAX_EDAD_H="${MAX_EDAD_H:-24}"
STALE=0

# ---- procedencia: ¿este artefacto midió el sistema que el perfil describe HOY? ----------------
# Se AVISA y se EXCLUYE del veredicto; NO se falla. Un artefacto sobre otro sistema no es un fallo
# de este sistema: es que no hay evidencia sobre este. Es `NO EJECUTADO` con otra causa, y merece
# el mismo trato — no contar, y decirlo en voz alta.
#
# Lo que se compara depende de qué toca la dimensión (ver tools/provenance.py): las de código
# comparan COMMIT, las de red comparan URL. Comparar ambas en todas excluiría dimensiones válidas,
# y un aviso que salta cuando no toca se aprende a ignorar.
declare -A PROV_ESTADO PROV_DETALLE
EXCLUIDAS=0
while IFS=$'\t' read -r _id _est _det; do
  [ -z "${_id:-}" ] && continue
  PROV_ESTADO["$_id"]="$_est"; PROV_DETALLE["$_id"]="$_det"
done < <(LAB_DIR="$PWD" tools/provenance.py "$TARGET" 2>/dev/null)

# ¿Se excluye esta dimensión del veredicto? Devuelve 0 (sí) e imprime la razón.
excluida() {   # $1 = id de dimensión   $2 = nombre para el mensaje
  if [ "${PROV_ESTADO[$1]:-ok}" = "excluida" ]; then
    printf '  \033[35mEXCL\033[0m  %s: %s — no cuenta para este veredicto\n' \
      "$2" "${PROV_DETALLE[$1]}"
    EXCLUIDAS=$((EXCLUIDAS + 1))
    return 0
  fi
  return 1
}
stale_check() {   # $1 = ruta   $2 = nombre para el mensaje
  local h; h=$(edad_h "$1")
  [ "$h" -lt 0 ] && return
  if [ "$h" -gt "$MAX_EDAD_H" ]; then
    printf '  \033[33mVIEJO\033[0m %s: %sh (máximo %sh) — se mide junto a artefactos recientes\n' \
      "$2" "$h" "$MAX_EDAD_H"
    STALE=$((STALE + 1))
  fi
}

echo "== gate: $TARGET =="

# ---- lo que una persona marcó como BLOQUEANTE ------------------------------------------------
# Va PRIMERO y no admite umbral. El resto del archivo compara conteos contra presupuestos; esto
# no compara nada: alguien miró el hallazgo y dijo que no puede pasar a producción.
NBLOQ=0
for _d in gitleaks:gitleaks.sarif trufflehog:trufflehog.sarif trivy-fs:trivy/trivy-fs.sarif \
          trivy-config:trivy/trivy-config.sarif semgrep:semgrep/semgrep.sarif \
          sonar:sonar/sonar.sarif qodana:qodana/qodana.sarif mobsf:mobile/mobsf.sarif \
          api-lint:api/spectral.sarif zap:zap/zap.sarif; do
  _id="${_d%%:*}"; _f="$R/${_d#*:}"
  _n=$(bloqueantes "$_f" "$_id")
  [ "$_n" -gt 0 ] 2>/dev/null && { NBLOQ=$((NBLOQ + _n)); \
    fail "BLOQUEANTE en $_id: $_n hallazgo(s) que alguien marcó como impedimento para producción"; }
done
[ "$NBLOQ" -eq 0 ] && pass "sin hallazgos marcados como bloqueantes"


stale_check "$R/gitleaks.sarif" "secrets"
if excluida gitleaks "secrets"; then n=-1; else n=$(sarif_count "$R/gitleaks.sarif" gitleaks); fi
if [ "$n" -lt 0 ]; then skip "gitleaks not run"
elif [ "$n" -le "${ALLOW_SECRETS:-0}" ]; then pass "secrets: $n (allowed ${ALLOW_SECRETS:-0})"
else fail "secrets: $n found in git history (allowed ${ALLOW_SECRETS:-0})"; fi

# TruffleHog. La dimensión que este laboratorio llevaba ejecutando y TIRANDO: tools/secrets.sh
# volcaba su JSON en reports/<t>/trufflehog.txt y no lo leía nadie — ni este gate, ni RUN.md, ni
# el informe, ni el triaje. Y es la única herramienta del lab que VERIFICA: llama a la API del
# proveedor para comprobar si la credencial sigue viva.
#
# Se juzgan SOLO las verificadas (--min-sev critical; tools/trufflehog-sarif.py las etiqueta así),
# porque son las únicas sobre las que no cabe discusión: una credencial que responde hoy hay que
# rotarla hoy. Las no verificadas quedan en el informe y en el triaje como lo que son, señal sin
# confirmar, y no se cuelan en un umbral que exigiría juicio.
n=$(tools/gate-count.py "$R/trufflehog.sarif" --min-sev critical)
if [ "$n" -lt 0 ]; then skip "trufflehog no ejecutado"
elif [ "$n" -le "${MAX_VERIFIED_SECRETS:-0}" ]; then
  pass "secretos VERIFICADOS VIVOS: $n (permitidos ${MAX_VERIFIED_SECRETS:-0})"
else
  fail "secretos VERIFICADOS VIVOS: $n (permitidos ${MAX_VERIFIED_SECRETS:-0}) — credenciales que responden AHORA; rotar antes que triajear"
fi

stale_check "$R/trivy/trivy-fs.sarif" "dependencias"
if excluida trivy-fs "dependencias"; then n=-1; else n=$(sarif_count "$R/trivy/trivy-fs.sarif" trivy-fs); fi
if [ "$n" -lt 0 ]; then skip "trivy fs not run"
elif [ "$n" -le "${MAX_DEP_FINDINGS:-999}" ]; then pass "dependency findings: $n (max ${MAX_DEP_FINDINGS:-999})"
else fail "dependency findings: $n (max ${MAX_DEP_FINDINGS:-999})"; fi

stale_check "$R/semgrep/semgrep.sarif" "SAST"
if excluida semgrep "SAST"; then n=-1; else n=$(sarif_count "$R/semgrep/semgrep.sarif" semgrep); fi
if [ "$n" -lt 0 ]; then skip "semgrep not run"
elif [ "$n" -le "${MAX_SAST_FINDINGS:-999}" ]; then pass "SAST findings: $n (max ${MAX_SAST_FINDINGS:-999})"
else fail "SAST findings: $n (max ${MAX_SAST_FINDINGS:-999})"; fi

# Calidad = SonarQube + Qodana, SUMADOS contra un solo presupuesto. Son dos motores haciendo la
# misma pregunta (defectos en el código que escribió este equipo), y dos presupuestos separados
# dejarían pasar un proyecto repartiendo sus hallazgos entre ambos. Se informa el desglose para
# que un número alto se pueda atribuir, pero el umbral es uno.
#
# Cada motor conserva su propio -1: "sonar corrió y qodana no" no puede leerse como si la mitad
# ausente valiera cero. Si NINGUNO corrió, la dimensión entera es skip.
stale_check "$R/sonar/sonar.sarif" "sonar"
if excluida sonar "sonar"; then nsonar=-1; else nsonar=$(sarif_count "$R/sonar/sonar.sarif" sonar); fi
stale_check "$R/qodana/qodana.sarif" "qodana"
if excluida qodana "qodana"; then nqodana=-1; else nqodana=$(sarif_count "$R/qodana/qodana.sarif" qodana); fi
if [ "$nsonar" -lt 0 ] && [ "$nqodana" -lt 0 ]; then
  skip "quality not run (neither SonarQube nor Qodana)"
else
  n=0; detail=""
  if [ "$nsonar" -ge 0 ]; then n=$((n + nsonar)); detail="sonar=$nsonar"; else detail="sonar=NOT RUN"; fi
  if [ "$nqodana" -ge 0 ]; then n=$((n + nqodana)); detail="$detail qodana=$nqodana"; else detail="$detail qodana=NOT RUN"; fi
  if [ "$n" -le "${MAX_QUALITY_FINDINGS:-500}" ]; then
    pass "quality findings: $n (max ${MAX_QUALITY_FINDINGS:-500}) [$detail]"
  else
    fail "quality findings: $n (max ${MAX_QUALITY_FINDINGS:-500}) [$detail]"
  fi
fi

# El artefacto distribuible (APK/IPA). Umbral propio y no sumado al SAST a propósito: son
# preguntas distintas —"qué escribimos" contra "qué entregamos"— y un binario con hallazgos no
# debe poder esconderse dentro del presupuesto de otra dimensión.
stale_check "$R/mobile/mobsf.sarif" "mobsf"
if excluida mobsf "mobsf"; then n=-1; else n=$(sarif_count "$R/mobile/mobsf.sarif" mobsf); fi
if [ "$n" -lt 0 ]; then skip "mobile artifact not scanned (MobSF)"
elif [ "$n" -le "${MAX_MOBILE_FINDINGS:-100}" ]; then pass "mobile artifact findings: $n (max ${MAX_MOBILE_FINDINGS:-100})"
else fail "mobile artifact findings: $n (max ${MAX_MOBILE_FINDINGS:-100})"; fi

stale_check "$R/zap/zap.sarif" "DAST"
if excluida zap "DAST"; then n=-1; else n=$(sarif_count "$R/zap/zap.sarif" zap); fi
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
if [ "$EXCLUIDAS" -gt 0 ]; then
  echo "  $EXCLUIDAS dimensión(es) EXCLUIDA(S): su artefacto midió otro sistema. No cuentan a favor"
  echo "  ni en contra — vuelve a correrlas contra el blanco actual si las necesitas cubiertas."
  echo
fi

if [ "$STALE" -gt 0 ]; then
  echo "  $STALE artefacto(s) por encima de ${MAX_EDAD_H}h. El veredicto los mezcla con los"
  echo "  recientes sin distinguirlos: comprueba que midieron el MISMO despliegue."
  echo "  Ajusta el margen con MAX_ARTIFACT_AGE_H en target.env, o vuelve a correr esas dimensiones."
  echo
fi

if [ "$FAIL" -eq 0 ]; then
  echo "GATE PASSED — note: 'skip' lines are NOT passes. See reports/$TARGET/RUN.md for coverage."
else
  echo "GATE FAILED"
fi
exit "$FAIL"
