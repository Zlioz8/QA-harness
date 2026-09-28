#!/usr/bin/env bash
# AAA · auditoría — el oráculo: ¿lo que las sondas hicieron quedó REGISTRADO?
#
# La respuesta 200 de un login no demuestra que el login se anotó; solo lo dice la tabla de
# auditoría de la aplicación. Este script lee las ACCIONES que dejó lib/specs/authn.spec.ts
# (reports/<t>/playwright/aaa-acciones.json: qué se hizo, cuándo —t0— y con qué User-Agent
# marcador) y, por cada evento de targets/<t>/aaa/acct.json (o del preset que declare), ejecuta
# su consulta de SOLO LECTURA contra la base con AAA_DB_URL (target.env.local). Escribe
# reports/<t>/aaa/oracle.json; tools/aaa-sarif.py lo convierte a aaa/acct.sarif.
#
# Sin AAA_DB_URL cada evento sale «no-disponible». NO es un pass y el gate lo imprime aparte:
# la auditoría no se midió. Nunca se imprime la URL (lleva la contraseña del rol de lectura).
#
# Uso: tools/aaa-oracle.sh <target>          (lo llama `make aaa`)
set -uo pipefail
TARGET="${1:?usage: aaa-oracle.sh <target>}"
ENVFILE="targets/$TARGET/target.env"
ENVLOCAL="targets/$TARGET/target.env.local"
RUNTIME="targets/$TARGET/compose.runtime.yml"
. "$(dirname "$0")/lib-env.sh"

# Mismo ensamblado que run-dimension.sh: el override local gana porque va después.
ARGS=(--env-file "$ENVFILE")
[ -f "$ENVLOCAL" ] && ARGS+=(--env-file "$ENVLOCAL")
ARGS+=(-f docker-compose.yml)
[ -f "$RUNTIME" ] && ARGS+=(-f "$RUNTIME")

export TARGET
export DB_URL="$(envget AAA_DB_URL)"
export COMPOSE_ARGS="${ARGS[*]}"
mkdir -p "reports/$TARGET/aaa"

python3 - <<'PY'
import json, os, re, subprocess, sys
from datetime import datetime, timezone

T = os.environ["TARGET"]
URL = os.environ.get("DB_URL", "")
LAB = os.getcwd()
ACC = os.path.join(LAB, "reports", T, "playwright", "aaa-acciones.json")
GUION = os.path.join(LAB, "targets", T, "aaa", "acct.json")
OUT = os.path.join(LAB, "reports", T, "aaa", "oracle.json")
compose = ["docker", "compose"] + os.environ["COMPOSE_ARGS"].split() + ["--profile", "aaa", "run", "--rm", "-T"]


def ahora():
    return datetime.now(timezone.utc).isoformat()


def redactar(s: str) -> str:
    return re.sub(r"postgres(ql)?://\S+", "postgresql://<redactada>", s or "")


def escribir(doc):
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)


if not os.path.exists(GUION):
    print(f"aaa-oracle: sin targets/{T}/aaa/acct.json — auditoría NO DISPONIBLE (no se escribe oracle.json)")
    sys.exit(0)

guion = json.load(open(GUION, encoding="utf-8"))
eventos = {}
preset = (guion.get("preset") or "").strip()
if preset:
    p = os.path.join(LAB, "lib", "aaa", "presets", f"{preset}.json")
    if not os.path.exists(p):
        print(f"aaa-oracle: preset {preset!r} no existe en lib/aaa/presets/ — se ignora", file=sys.stderr)
    else:
        for e in json.load(open(p, encoding="utf-8")).get("eventos", []):
            eventos[e["id"]] = dict(e, origen=f"preset:{preset}")
for e in guion.get("eventos", []):
    eventos[e["id"]] = dict(e, origen="perfil")

oraculo = guion.get("oraculo") or {}
tipo = (oraculo.get("tipo") or "postgres").lower()

acciones = {}
if os.path.exists(ACC):
    for a in json.load(open(ACC, encoding="utf-8")).get("acciones", []):
        acciones.setdefault(a["id"], a)      # la primera acción con ese id (p.ej. el login del rol A)

doc = {"generado": ahora(), "fuente": os.path.relpath(ACC, LAB), "db": "disponible" if URL else "no-disponible",
       "tipo": tipo, "preset": preset, "eventos": []}
pasa = falla = nd = err = 0

for eid, e in eventos.items():
    fila = {"id": eid, "accion": e.get("accion", ""), "origen": e.get("origen", ""),
            "severidad": e.get("severidad", "medium"), "stride": e.get("stride", "R"),
            "titulo": e.get("titulo", ""), "sql": e.get("sql", ""), "expect_min": int(e.get("expect_min", 1)),
            "t0": "", "marker": "", "n": None, "resultado": "", "detalle": ""}
    acc = acciones.get(fila["accion"])
    if not URL:
        fila["resultado"], fila["detalle"] = "no-disponible", "AAA_DB_URL vacío en target.env.local"
        nd += 1
    elif tipo != "postgres":
        fila["resultado"], fila["detalle"] = "no-disponible", f"oráculo de tipo {tipo!r} no soportado todavía (solo postgres)"
        nd += 1
    elif not os.path.exists(ACC):
        fila["resultado"], fila["detalle"] = "error", "la suite no dejó aaa-acciones.json: no hay acciones que buscar"
        err += 1
    elif acc is None:
        fila["resultado"], fila["detalle"] = "error", f"ninguna sonda ejecutó la acción «{fila['accion']}» (¿falta en aaa/authn.json?)"
        err += 1
    elif not fila["sql"] or "<" in fila["sql"]:
        fila["resultado"], fila["detalle"] = "error", "SQL sin escribir (quedan <marcadores> de la plantilla)"
        err += 1
    else:
        fila["t0"], fila["marker"] = acc.get("t0", ""), acc.get("marker", "")
        sql = "SET default_transaction_read_only = on;\n" + fila["sql"].rstrip().rstrip(";") + ";\n"
        cmd = compose + ["-e", f"T0={fila['t0']}", "-e", f"MARKER={fila['marker']}",
                         "-e", f"USUARIO={acc.get('usuario', '')}", "-e", f"ROL={acc.get('rol', '')}", "aaa-oracle"]
        try:
            r = subprocess.run(cmd, input=sql, capture_output=True, text=True, timeout=90)
            salida = [l.strip() for l in r.stdout.splitlines() if l.strip()]
            if r.returncode != 0 or not salida:
                fila["resultado"] = "error"
                fila["detalle"] = redactar((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip() else f"psql salió {r.returncode}")[:300]
                err += 1
            else:
                n = int(salida[-1])
                fila["n"] = n
                if n >= fila["expect_min"]:
                    fila["resultado"], fila["detalle"] = "pass", f"n={n} ≥ {fila['expect_min']}"
                    pasa += 1
                else:
                    fila["resultado"], fila["detalle"] = "fail", f"n={n} < {fila['expect_min']}: la acción «{fila['accion']}» no dejó rastro"
                    falla += 1
        except subprocess.TimeoutExpired:
            fila["resultado"], fila["detalle"] = "error", "psql no respondió en 90 s"
            err += 1
        except ValueError:
            fila["resultado"], fila["detalle"] = "error", "la consulta no devolvió un entero (¿es un SELECT count(*)?)"
            err += 1
    doc["eventos"].append(fila)

escribir(doc)
print(f"aaa-oracle: {len(doc['eventos'])} eventos · pass {pasa} · fail {falla} · error {err} · no-disponible {nd} -> {os.path.relpath(OUT, LAB)}")
PY
