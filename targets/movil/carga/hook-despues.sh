#!/usr/bin/env bash
# Después de cada paso: (1) cuánto creció cada tabla de la base de la API; (2) cuántas llamadas a
# Moodle costó cada petición, casando por `rid` el log del proxy con el del backend.
DIR="${1:?}"
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/tablas.sh" > "$DIR/tablas-despues.csv" 2>"$DIR/tablas-despues.err"
python3 - "$DIR" <<'PY'
import csv, json, os, sys
d = sys.argv[1]
def leer(n):
    try: return {r[0]: (int(r[1]), int(r[2])) for r in csv.reader(open(os.path.join(d, n))) if len(r) == 3}
    except OSError: return {}
a, b = leer("tablas-antes.csv"), leer("tablas-despues.csv")
reqs = None
try: reqs = json.load(open(os.path.join(d, "detalle.json")))["global"]["peticiones"]
except Exception: pass
out = {"peticiones": reqs, "tablas": {}}
for t in sorted(b):
    f0, s0 = a.get(t, (0, 0)); f1, s1 = b[t]
    if f1 - f0 or s1 - s0:
        out["tablas"][t] = {"filas_nuevas": f1 - f0, "bytes_nuevos": s1 - s0,
                            "filas_por_peticion": round((f1 - f0) / reqs, 3) if reqs else None,
                            "bytes_por_peticion": round((s1 - s0) / reqs, 1) if reqs else None}
json.dump(out, open(os.path.join(d, "escrituras.json"), "w"), indent=1)
PY
if [ -f "$DIR/logs/movil_api-nginx-1.log" ] && [ -f "$DIR/logs/movil_api-web-1.log" ]; then
  mkdir -p "$DIR/grab"
  cp "$DIR/logs/movil_api-nginx-1.log" "$DIR/grab/proxy.log"
  cp "$DIR/logs/movil_api-web-1.log" "$DIR/grab/backend.log"
  # Solo la ventana del paso (el volcado del proxy puede traer pasos anteriores, L-R9-02).
  VENTANA=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); i=d.get('inicio_s'); print(f\"{i-90} {i+(d.get('duracion_ms') or 0)/1000+5}\" if i else '')" "$DIR/detalle.json" 2>/dev/null)
  python3 "$AQUI/grabacion.py" analizar "$DIR/grab" --ua k6-carga ${VENTANA:+--ventana $VENTANA} >/dev/null 2>"$DIR/grab/error.txt" || true
  rm -f "$DIR/grab/proxy.log" "$DIR/grab/backend.log" "$DIR/grab/peticiones.csv"
fi
