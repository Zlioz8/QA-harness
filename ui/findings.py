"""One flat, filterable list of every finding every tool produced.

The problem this solves: five tools, five dialects, five places to look. The operator ends up
reading SARIF by hand or trusting a summary that already threw away the detail. Each tool has a
perfectly good filter — semgrep by rule, Trivy by severity, gitleaks by path — and each one lives
inside that tool. This module brings those filters into a single view.

Two rules it must never break:

1. **The artifact on disk is the original and stays untouched.** Everything here is derived and
   regenerable; delete this module's output and re-run the collector and you get the same thing.
   A filter is a way of looking, never a way of editing.
2. **A filter hides, it does not discard.** The raw total is always on screen next to the filtered
   one. The moment "13 secrets" can silently become "2 secrets" because someone left a checkbox
   ticked, the report stops meaning anything.

Judgements come from tools/triage.py — the same store the report reads, so a verdict recorded
here shows up there unchanged.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.environ.get("LAB_DIR", os.getcwd()), "tools"))
import dashboard  # noqa: E402  — the one SARIF parser; a second would drift from the report
import triage as triagelib  # noqa: E402

# (id, label, path relative to the target's report dir). Order is the reading order on screen.
SOURCES = [
    ("gitleaks",     "Secretos en la historia git",     "gitleaks.sarif"),
    ("trivy-fs",     "Dependencias / CVE",              "trivy/trivy-fs.sarif"),
    ("trivy-config", "Configuración de contenedores",   "trivy/trivy-config.sarif"),
    ("trivy-image",  "CVE de imágenes",                 "trivy/trivy-image.sarif"),
    ("semgrep",      "SAST",                            "semgrep/semgrep.sarif"),
    ("sonar",        "Calidad (SonarQube)",             "sonar/sonar.sarif"),
    ("api-lint",     "Contrato de API (Spectral)",      "api/spectral.sarif"),
    ("zap",          "Superficie runtime (DAST)",       "zap/zap.sarif"),
]

TOOL_LABEL = {tid: label for tid, label, _ in SOURCES}

VERDICT_LABEL = {
    "": "Sin juzgar",
    "confirmed": "Confirmado",
    "false-positive": "Falso positivo",
    "inconclusive": "Inconcluso",
}

SEV_LABEL = {
    "critical": "Crítica", "high": "Alta", "medium": "Media",
    "low": "Baja", "unranked": "Sin graduar",
}


def _strip_src(loc: str) -> str:
    loc = (loc or "").lstrip("/")
    return loc[4:] if loc.startswith("src/") else loc


def _top_dir(loc: str) -> str:
    """First path segment — the coarse 'where' facet.

    Coarse on purpose: a checkbox per file is a list, not a filter. Whole directories are what
    someone actually wants to set aside ('todo lo de docs/ es documentación, no código')."""
    loc = _strip_src(loc)
    if not loc:
        return "(sin ruta)"
    head, sep, _ = loc.partition("/")
    return head if sep else "(raíz)"


def collect(reports_dir: str) -> dict:
    """-> {findings, facets, ran, total, judged}

    `ran` distinguishes the three states the lab insists on keeping apart: a tool that ran and
    found nothing (0), one that never ran (None), and one whose findings are listed.
    """
    recorded = triagelib.load(reports_dir)
    findings: list[dict] = []
    ran: dict[str, int | None] = {}

    for tool, _label, rel in SOURCES:
        data = dashboard.load_sarif(os.path.join(reports_dir, rel), tool)
        if data is None:
            ran[tool] = None          # NOT RUN — never coerced to zero
            continue
        ran[tool] = data["count"]
        for f in data["findings"]:
            key = triagelib.key_for(tool, f["rule"], f["loc"])
            rec = recorded.get(key, {})
            findings.append({
                **f,
                "key": key,
                # `loc` stays exactly as the tool wrote it — it is what the triage key is built
                # from. `path` is the same thing made readable: containers mount the checkout at
                # /src, and nobody has a /src in their repository.
                "path": _strip_src(f["loc"]),
                "dir": _top_dir(f["loc"]),
                "verdict": rec.get("verdict", ""),
                "note": rec.get("note", ""),
            })

    findings.sort(key=lambda f: (dashboard.SEV_ORDER.index(f["sev"]), f["tool"], f["loc"]))

    def facet(field: str, labels: dict | None = None, order: list | None = None) -> list[dict]:
        counts: dict[str, int] = {}
        for f in findings:
            counts[f[field]] = counts.get(f[field], 0) + 1
        keys = [k for k in (order or []) if k in counts] if order else sorted(counts)
        if order:
            keys += sorted(k for k in counts if k not in keys)
        return [{"value": k, "label": (labels or {}).get(k, k) or k, "count": counts[k]}
                for k in keys]

    return {
        "findings": findings,
        "total": len(findings),
        "ran": ran,
        "judged": triagelib.summary(recorded),
        "facets": {
            "sev": facet("sev", SEV_LABEL, dashboard.SEV_ORDER),
            "tool": facet("tool", TOOL_LABEL, [t for t, _, _ in SOURCES]),
            "verdict": facet("verdict", VERDICT_LABEL, ["", "confirmed",
                                                        "false-positive", "inconclusive"]),
            "rule": facet("rule"),
            "dir": facet("dir"),
        },
    }
