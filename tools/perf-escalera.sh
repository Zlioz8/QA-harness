#!/usr/bin/env bash
# Escalera de carga: sube la concurrencia por pasos y se detiene en el primero que incumple.
#
#   perf-escalera.sh <target> [nombre]      nombre = archivo targets/<target>/carga/<nombre>.env
#                                           (por omisión `escalera`)
#
# POR QUÉ UNA ESCALERA Y NO UNA CORRIDA GRANDE. Una sola corrida a 500 usuarios dice «a 500 va
# mal». No dice desde cuándo, ni qué se llenó primero. La escalera da la curva: en qué paso deja
# de escalar (la rodilla), en cuál incumple (el quiebre) y —con la telemetría— qué pieza llegó
# a su techo en ese paso. Esa es la diferencia entre un número y una capacidad.
#
# LA REGLA DE AVANCE. Solo se sube si el paso actual cumple el SLO. Seguir cargando un sistema
# que ya no cumple no enseña nada nuevo y, contra un servidor compartido, es hacer daño.
# ESCALERA_SIGUE=N permite N pasos más allá del primer fallo, para dibujar la curva de la
# degradación; solo tiene sentido contra un despliegue propio.
#
# Cada paso es una corrida de k6 por la dimensión `k6` (tools/run-dimension.sh), con la
# telemetría del sistema alrededor. Todo queda en reports/<target>/k6/runs/<corrida>/<paso>/.
# Al terminar, el último paso que cumple se copia a k6/summary.json: gate, tablero e informe
# siguen leyendo el mismo sitio de siempre.
set -uo pipefail

TARGET="${1:?uso: perf-escalera.sh <target> [nombre]}"
NOMBRE="${2:-escalera}"
ENVFILE="targets/$TARGET/target.env"
ESC="targets/$TARGET/carga/$NOMBRE.env"
. "$(dirname "$0")/lib-env.sh"

[ -f "$ENVFILE" ] || { echo "perf-escalera: no existe $ENVFILE" >&2; exit 2; }
[ -f "$ESC" ] || { echo "perf-escalera: no existe $ESC — la escalera la declara el perfil (ver targets/_template/carga/)." >&2; exit 2; }

# El entorno del shell gana sobre el archivo: `ESCALERA_PASOS="10 20" make perf-escalera …`.
esc() { local v="${!1:-}"; [ -n "$v" ] && { printf '%s\n' "$v"; return; }; _envget1 "$1" "$ESC"; }
def() { local v; v="$(esc "$1")"; printf '%s\n' "${v:-$2}"; }

TIPO="$(def ESCALERA_TIPO carga)"
PASOS="$(def ESCALERA_PASOS "5 10")"
RAMPA="$(def ESCALERA_RAMPA 30s)"
MESETA="$(def ESCALERA_MESETA 2m)"
BAJADA="$(def ESCALERA_BAJADA 15s)"
SCRIPT="$(def ESCALERA_SCRIPT "$(envget K6_SCRIPT)")"; SCRIPT="${SCRIPT:-smoke.js}"
PAUSA="$(def ESCALERA_PAUSA_S 20)"
SIGUE="$(def ESCALERA_SIGUE 0)"
MODELO="$(def ESCALERA_MODELO cerrado)"
IPS="$(def ESCALERA_IPS "$(envget CARGA_IPS)")"
ABORTA="$(def ESCALERA_ABORTA "")"
NOTA="$(def ESCALERA_NOTA "")"
# El SLO sale del perfil (los mismos umbrales que juzga `make gate`) salvo que la escalera
# declare otro: una escalera de humo puede querer uno imposible para probar que sabe fallar.
SLO_P95="$(def SLO_P95_MS "$(envget K6_P95_MS)")"; SLO_P95="${SLO_P95:-1500}"
SLO_P99="$(def SLO_P99_MS "$(envget K6_P99_MS)")"
SLO_ERR="$(def SLO_ERR_RATE "$(envget K6_ERR_RATE)")"; SLO_ERR="${SLO_ERR:-0.01}"
SLO_CHK="$(def SLO_CHECKS_MIN "$(envget K6_CHECKS_MIN)")"

[ -f "targets/$TARGET/k6/$SCRIPT" ] || { echo "perf-escalera: no existe targets/$TARGET/k6/$SCRIPT" >&2; exit 2; }

# `class: load` es exclusiva: otra carga a la vez anula la comparabilidad en silencio.
if docker ps --format '{{.Image}} {{.Names}}' | grep -qiE '(grafana/k6|jmeter)'; then
  echo "perf-escalera: ya hay un generador de carga corriendo en esta máquina. Dos a la vez no miden nada." >&2
  exit 2
fi

RUN="$(date +%Y%m%d-%H%M%S)-$TIPO${NOMBRE:+-$NOMBRE}"
REP="reports/$TARGET/k6"
DIR="$REP/runs/$RUN"
mkdir -p "$DIR"

# ---- manifiesto: contra qué se midió y en qué sobre, tomado del sistema y no de un documento --
python3 - "$DIR/RUN.json" <<PY
import hashlib, json, os, subprocess, sys
def sh(*a):
    try: return subprocess.run(a, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception: return ""
cont = {}
for n in """$(envget PERF_WATCH_CONTAINERS)""".replace(",", " ").split():
    raw = sh("docker", "inspect", n)
    try: i = json.loads(raw)[0]
    except Exception: cont[n] = {"error": "no existe"}; continue
    hc, cfg = i.get("HostConfig", {}), i.get("Config", {})
    # Todos los procesos del contenedor, no solo el primero: cuántos hay ES el dato (un proceso
    # de un solo hilo no pasa de un núcleo por mucho límite que tenga el contenedor).
    top = [" ".join(l.split()[1:]) for l in sh("docker", "top", n, "-o", "pid,args").splitlines()[1:]]
    cont[n] = {
        "imagen": cfg.get("Image"), "imagen_id": (i.get("Image") or "")[:19], "creado": i.get("Created", "")[:19],
        "cpus": (hc.get("NanoCpus") or 0) / 1e9 or None, "cpuset": hc.get("CpusetCpus") or None,
        "mem_mb": (hc.get("Memory") or 0) / 1048576 or None, "proceso": top[0] if top else None, "procesos": len(top),
    }
script = "targets/$TARGET/k6/$SCRIPT"
prov = {}
try: prov = json.load(open("reports/$TARGET/.provenance/k6.json"))
except Exception: pass
mem = 0
for l in open("/proc/meminfo"):
    if l.startswith("MemTotal"): mem = int(l.split()[1]) // 1048576
json.dump({
    "corrida": "$RUN", "fecha": sh("date", "-Is"),
    "host": f"{os.uname().nodename} · {os.cpu_count()} hilos · {mem} GB",
    "base_url": """$(envget APP_INTERNAL_URL)""", "tipo": "$TIPO", "modelo": "$MODELO",
    "pasos": "$PASOS".split(), "rampa": "$RAMPA", "meseta": "$MESETA", "bajada": "$BAJADA", "ips": "$IPS",
    "script": script, "script_sha256": hashlib.sha256(open(script, "rb").read()).hexdigest(),
    "k6": sh("docker", "run", "--rm", """${K6_IMAGE:-$(sed -n 's/^ *image: *\${K6_IMAGE:-\(.*\)}$/\1/p' docker-compose.yml | head -1)}""", "version").split(" (")[0],
    "slo": {"p95": "$SLO_P95", "p99": "$SLO_P99", "err": "$SLO_ERR", "checks": "$SLO_CHK"},
    "sobre_declarado": {"PERF_CPUS": """$(envget PERF_CPUS)""", "PERF_MEM": """$(envget PERF_MEM)"""},
    # Los techos van con la corrida: cambian con el sobre (dos procesos = dos núcleos de techo) y el
    # informe debe juzgar cada corrida con los techos que tenía, no con los del perfil de hoy.
    "techos": """${PERF_TECHOS:-$(envget PERF_TECHOS)}""",
    "contenedores": cont, "nota_sobre": """$NOTA""", "commit": "(se sella al correr el primer paso)",
}, open(sys.argv[1], "w"), indent=1, ensure_ascii=False)
PY

echo "paso,vus,peticiones,rps,p50,p95,p99,error,checks,veredicto,motivos" > "$DIR/escalera.csv"
echo "perf-escalera: $TARGET · $TIPO · pasos: $PASOS · rampa $RAMPA, meseta $MESETA · guion $SCRIPT"
echo "               SLO: p95 ≤ ${SLO_P95} ms${SLO_P99:+, p99 ≤ ${SLO_P99} ms}, error ≤ ${SLO_ERR}${SLO_CHK:+, checks ≥ ${SLO_CHK}}"
echo "               corrida: $DIR"

HOOK_ANTES="targets/$TARGET/carga/hook-antes.sh"
HOOK_DESPUES="targets/$TARGET/carga/hook-despues.sh"
ULTIMO_OK=""; ULTIMO=""; PRIMER_FALLO=""; EXTRA=0; ANTERIOR=0

for VUS in $PASOS; do
  PASO="$(printf '%05d' "$VUS")vus"
  PD="$DIR/$PASO"
  mkdir -p "$PD"
  rm -f "$REP/summary.json" "$REP/detalle.json"
  [ -x "$HOOK_ANTES" ] && "$HOOK_ANTES" "$PD" "$VUS" >"$PD/hook-antes.log" 2>&1

  tools/perf-telemetria.sh start "$TARGET" "$PD"
  echo
  echo "── paso $VUS usuarios ──────────────────────────────────────────────────────────"
  CARGA_TIPO="$TIPO" CARGA_VUS="$VUS" CARGA_RAMPA="$RAMPA" CARGA_MESETA="$MESETA" CARGA_BAJADA="$BAJADA" \
  CARGA_MODELO="$MODELO" CARGA_IPS="$IPS" CARGA_RUN="$RUN" CARGA_ABORTA="$ABORTA" \
  K6_P95_MS="$SLO_P95" K6_P99_MS="$SLO_P99" K6_ERR_RATE="$SLO_ERR" K6_CHECKS_MIN="$SLO_CHK" K6_SCRIPT="$SCRIPT" \
    tools/run-dimension.sh "$TARGET" k6 >"$PD/k6.log" 2>&1
  RC=$?
  tools/perf-telemetria.sh stop "$TARGET" "$PD"
  tail -4 "$PD/k6.log" | sed 's/^/  /'

  # El código de salida de k6 NO decide: sale 99 cuando cruza un umbral, que es justo el dato que
  # se busca. Decide que exista el resumen. Sin resumen, el paso no midió y la escalera para.
  [ -f "$REP/summary.json" ] && mv "$REP/summary.json" "$PD/summary.json"
  [ -f "$REP/detalle.json" ] && mv "$REP/detalle.json" "$PD/detalle.json"
  [ -f "reports/$TARGET/.provenance/k6.json" ] && cp "reports/$TARGET/.provenance/k6.json" "$PD/sello.json"
  [ -x "$HOOK_DESPUES" ] && "$HOOK_DESPUES" "$PD" "$VUS" >"$PD/hook-despues.log" 2>&1

  if [ ! -f "$PD/summary.json" ]; then
    echo "  paso $VUS: k6 no dejó resumen (exit $RC) — NO MEDIDO. Ver $PD/k6.log"
    echo "$PASO,$VUS,,,,,,,,NO-MEDIDO,k6 no dejó resumen (exit $RC)" >> "$DIR/escalera.csv"
    PRIMER_FALLO="${PRIMER_FALLO:-$VUS}"
    break
  fi

  tools/perf-capacidad.py paso "$PD" --vus "$VUS" --p95 "$SLO_P95" ${SLO_P99:+--p99 "$SLO_P99"} --err "$SLO_ERR" ${SLO_CHK:+--checks "$SLO_CHK"}
  VER=$?
  python3 - "$PD/paso.json" "$PASO" >> "$DIR/escalera.csv" <<'PY'
import json, sys
p = json.load(open(sys.argv[1]))
f = lambda v: "" if v is None else (f"{v:.4f}" if isinstance(v, float) else str(v))
print(",".join([sys.argv[2], f(p["vus"]), f(p["peticiones"]), f(p["rps"]), f(p["p50"]), f(p["p95"]), f(p["p99"]),
                f(p["error"]), f(p["checks"]), p["veredicto"], "; ".join(p["motivos"]).replace(",", " ")]))
PY
  ULTIMO="$PD"
  if [ "$VER" -eq 0 ]; then
    ULTIMO_OK="$PD"; ANTERIOR="$VUS"
  elif [ "$VER" -eq 2 ]; then
    break
  else
    PRIMER_FALLO="${PRIMER_FALLO:-$VUS}"
    if [ "$EXTRA" -ge "$SIGUE" ]; then break; fi
    EXTRA=$((EXTRA + 1))
  fi
  sleep "$PAUSA"
done

# El sello del primer paso dice contra qué commit se midió: va al manifiesto de la corrida.
python3 - "$DIR" <<'PY'
import glob, json, os, sys
d = sys.argv[1]
sellos = sorted(glob.glob(os.path.join(d, "*", "sello.json")))
if sellos:
    m = json.load(open(os.path.join(d, "RUN.json")))
    m["commit"] = json.load(open(sellos[0])).get("commit", "desconocido")
    json.dump(m, open(os.path.join(d, "RUN.json"), "w"), indent=1, ensure_ascii=False)
PY

echo
# Lo que leen gate, tablero e informe: el último paso que cumple; si ninguno cumple, el último
# que corrió —que el veredicto vea el incumplimiento es mejor que ver un hueco.
FUENTE="${ULTIMO_OK:-$ULTIMO}"
if [ -n "$FUENTE" ]; then
  cp "$FUENTE/summary.json" "$REP/summary.json"
  [ -f "$FUENTE/detalle.json" ] && cp "$FUENTE/detalle.json" "$REP/detalle.json"
fi

if grep -q ',NO-MEDIDO,' "$DIR/escalera.csv"; then
  # Un paso que no midió NO es un punto de quiebre: es un instrumento que falló. Decirlo con
  # otras palabras evita que alguien apunte «se rompe a N usuarios» por un guion roto.
  echo "perf-escalera: un paso NO SE MIDIÓ (ver $DIR/*/k6.log). No hay conclusión sobre el sistema."
elif [ -n "$PRIMER_FALLO" ]; then
  echo "perf-escalera: PUNTO DE QUIEBRE entre $ANTERIOR y $PRIMER_FALLO usuarios."
else
  echo "perf-escalera: la escalera terminó sin incumplir. El techo está por encima de $ANTERIOR usuarios."
fi
echo "               siguiente: make capacidad TARGET=$TARGET     (lee $DIR)"
[ -n "$ULTIMO" ] || exit 1
exit 0
