#!/usr/bin/env python3
"""El único lector de SARIF del laboratorio.

Vivía dentro de tools/dashboard.py y llegaba a ui/findings.py y a ui/app.py por
`sys.path.insert` desde tres sitios distintos. Peor: NO era el único. tools/gate.sh contaba con
`grep -o '"ruleId"' | wc -l`, así que el informe y el veredicto leían el mismo archivo con dos
lectores diferentes — y el conteo del gate era ciego a la severidad que el informe sí pintaba.
Dos lectores del mismo formato acaban discrepando; el único remedio es que haya uno.

La regla que este módulo sostiene por encima de todo: **un archivo ausente devuelve None, y None
significa NO EJECUTADO. Jamás se convierte en cero.** Un informe que dibuja una barra vacía
tranquilizadora para un análisis que nadie corrió es peor que no tener informe.
"""
from __future__ import annotations

import json

SEV_ORDER = ["critical", "high", "medium", "low", "unranked"]
LEVEL_MAP = {"error": "high", "warning": "medium", "note": "low", "none": "low"}


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def severity_of(result, rule):
    """Resuelve la severidad entre herramientas que la ponen cada una en otro sitio.

    Trivy la etiqueta (CRITICAL/HIGH/...) y además da CVSS; semgrep la etiqueta; ZAP usa el
    `level` de SARIF; gitleaks no dice nada. El orden importa: una etiqueta explícita gana a una
    puntuación derivada, y la puntuación gana al `level` genérico, porque `level` colapsa
    distinciones que la herramienta sí había hecho.
    """
    props = (rule or {}).get("properties", {}) or {}
    for tag in props.get("tags", []) or []:
        t = str(tag).strip().lower()
        if t in ("critical", "high", "medium", "low"):
            return t
    score = props.get("security-severity")
    if score is not None:
        try:
            s = float(score)
            if s >= 9.0:
                return "critical"
            if s >= 7.0:
                return "high"
            if s >= 4.0:
                return "medium"
            return "low"
        except (TypeError, ValueError):
            pass
    lvl = result.get("level") or (rule or {}).get("defaultConfiguration", {}).get("level")
    if lvl:
        return LEVEL_MAP.get(str(lvl).lower(), "unranked")
    return "unranked"


def load_sarif(path, tool=""):
    """-> {'count': n, 'sev': {...}, 'findings': [...]} o None cuando el archivo no existe.

    None es NO EJECUTADO y se pinta como tal. Nunca se coerciona a cero."""
    doc = read_json(path)
    if not doc:
        return None
    out = {"count": 0, "sev": {k: 0 for k in SEV_ORDER}, "findings": []}
    for run in doc.get("runs", []):
        rules = {r.get("id"): r for r in run.get("tool", {}).get("driver", {}).get("rules", [])}
        for res in run.get("results", []):
            rule = rules.get(res.get("ruleId"), {})
            sev = severity_of(res, rule)
            out["count"] += 1
            out["sev"][sev] = out["sev"].get(sev, 0) + 1
            loc, line = "", ""
            locs = res.get("locations") or []
            if locs:
                phys = locs[0].get("physicalLocation", {})
                loc = phys.get("artifactLocation", {}).get("uri", "")
                line = phys.get("region", {}).get("startLine", "")
            out["findings"].append({
                "tool": tool,
                "rule": res.get("ruleId", "?"),
                "name": (rule.get("name") or rule.get("shortDescription", {}).get("text") or ""),
                "sev": sev,
                "msg": (res.get("message", {}) or {}).get("text", "")[:400],
                "loc": loc,
                "line": line,
            })
    out["findings"].sort(key=lambda f: SEV_ORDER.index(f["sev"]))
    return out


def is_graded(data) -> bool:
    """¿La herramienta graduó ESTOS hallazgos, o salieron todos sin severidad?

    No es una propiedad de la herramienta sino de los datos: reports/movil/semgrep/semgrep.sarif
    trae 185 resultados y NINGUNO con severidad. Un umbral de conteo sobre eso compara un entero
    contra otro entero sin saber si son tres críticos o ciento ochenta y cinco cuestiones de
    estilo — es una cifra inventada con forma de medición, y hay que poder decirlo.
    """
    return bool(data) and data["count"] > 0 and data["sev"].get("unranked", 0) < data["count"]


def dedup_key(finding) -> tuple[str, str]:
    """(regla, archivo) — sin el número de línea, a propósito.

    La misma regla disparando quince veces en el mismo archivo es UN problema que arreglar, no
    quince. En reports/movil/semgrep son 185 resultados sobre 109 pares únicos: el umbral de 50 se
    comparaba contra un número inflado un 70%. Se deja fuera la línea por la misma razón que
    triage.key_for: las líneas se mueven entre corridas y el hallazgo sigue siendo el mismo.
    """
    return (finding.get("rule", "?"), finding.get("loc", ""))
