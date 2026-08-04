#!/usr/bin/env python3
"""Qodana -> SARIF normalizado, para que el gate y el informe puedan leerlo.

Mismo fallo que tenían ZAP y SonarQube, y por la misma razón: Qodana dejaba `report/index.html`
y `qodana.sarif.json` en su propio formato, y ningún consumidor del laboratorio los miraba. El
gate no contaba ni un hallazgo, el informe pintaba la dimensión con un enlace al HTML, y una
corrida con cientos de inspecciones era indistinguible de una limpia.

Qodana ya escribe SARIF, así que esto no es una traducción de dialecto: es una *normalización*.
Su archivo trae, junto a los resultados, el catálogo de inspecciones del linter y bloques que el
laboratorio no consume; medido sobre antiplagio, 704 KB de los que el informe usa 62. Aquí se
emite solo eso: un resultado por hallazgo, con severidad en el vocabulario del laboratorio (ver
sonar-sarif.py) y archivo:línea, que es lo que el gate cuenta y lo que el informe pinta.

Sobre el conteo: en la versión medida (qodana-python-community, agosto 2026) contar `"ruleId"`
sobre el archivo crudo daba el mismo 134 que sobre el normalizado, así que la reducción no
arregla un conteo roto *hoy*. Lo que sí garantiza es que siga siendo el número de hallazgos si
una versión futura del linter empieza a serializar su catálogo con esa misma clave — el gate
cuenta sin jq, a propósito, y no tiene forma de distinguirlos.

Uso: qodana-sarif.py <reports_dir>/qodana
"""
from __future__ import annotations

import json
import os
import sys

# Qodana usa los niveles de SARIF; el laboratorio usa sus propias palabras (ver sonar-sarif.py).
SEV = {"error": "high", "warning": "medium", "note": "low", "none": "low"}

# El linter escribe uno de estos, según versión. Se busca en orden.
CANDIDATES = ("qodana.sarif.json", "report/results/qodana.sarif.json", "results/qodana.sarif.json")


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: qodana-sarif.py <dir de reportes de qodana>", file=sys.stderr)
        return 2
    d = sys.argv[1]

    src = next((p for p in (os.path.join(d, c) for c in CANDIDATES) if os.path.isfile(p)), None)
    if not src:
        # Un archivo ausente significa NO EJECUTADO. Escribir un SARIF vacío aquí lo convertiría
        # en "corrió y no encontró nada", que es exactamente la mentira que el gate debe evitar.
        print(f"qodana: no hay qodana.sarif.json en {d} — no se escribe SARIF "
              "(ausente = NO EJECUTADO; vacío significaría 'limpio')", file=sys.stderr)
        return 1

    try:
        with open(src, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"qodana: {src} ilegible ({exc}) — no se escribe SARIF", file=sys.stderr)
        return 1

    results, rules = [], {}
    for run in raw.get("runs", []):
        for res in run.get("results", []):
            rid = res.get("ruleId") or "qodana"
            level = str(res.get("level", "warning")).lower()
            sev = SEV.get(level, "medium")
            msg = (res.get("message") or {}).get("text", "")

            uri, line = "", 1
            locs = res.get("locations") or []
            if locs:
                phys = locs[0].get("physicalLocation") or {}
                uri = (phys.get("artifactLocation") or {}).get("uri", "")
                line = (phys.get("region") or {}).get("startLine", 1)

            results.append({
                "ruleId": rid,
                "level": level if level in ("error", "warning", "note") else "warning",
                "message": {"text": msg},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": uri},
                    "region": {"startLine": line},
                }}],
            })
            rules[rid] = {
                "id": rid,
                "name": rid,
                "shortDescription": {"text": msg[:120]},
                "properties": {"tags": [sev]},
            }

    sarif = {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{
            "tool": {"driver": {"name": "Qodana", "rules": list(rules.values())}},
            "results": results,
        }],
    }
    out = os.path.join(d, "qodana.sarif")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(sarif, fh, indent=1, ensure_ascii=False)
    print(f"qodana: {len(results)} hallazgos -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
