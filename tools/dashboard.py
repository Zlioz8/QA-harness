#!/usr/bin/env python3
"""Build a single self-contained HTML dashboard from a target's reports/ directory.

Why this exists: every tool writes its own dialect (SARIF from five tools that disagree on
where severity lives, Playwright JSON, k6 JSON, a ZAP HTML page). Handing that to a team that
did not build the lab is handing them nothing. This consolidates it into one page.

Design rules, all of them load-bearing:

  * No server, no dependencies, no network. Standard library only, everything inlined. The
    output is a file you can double-click or attach to an email — a security dashboard that
    needs a service to be read is a service someone will eventually expose.
  * A dimension that did not run is rendered as NOT RUN, never as zero findings. That
    distinction is the whole point of the lab's reporting discipline; a dashboard that draws a
    reassuring empty bar chart for a scan nobody executed is worse than no dashboard.
  * The verdict is not recomputed here. tools/gate.sh is invoked and its output parsed, so the
    page and the pipeline can never disagree about whether the run passed.

Usage: tools/dashboard.py <target>      (normally: make dashboard TARGET=<target>)
"""
import html
import json
import os
import re
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import style     # shared with the web UI: the report and the interface are one product
import triage    # human verdicts recorded in the UI, shown here
import dimensions  # el registro único: la lista de dimensiones vivía copiada en seis sitios
import sarif     # el ÚNICO lector de SARIF; vivía aquí dentro y lo leían tres módulos por sys.path

ANSI = re.compile(r"\x1b\[[0-9;]*m")

# Re-exportado a propósito: ui/findings.py llega a estos nombres como `dashboard.load_sarif` y
# `dashboard.SEV_ORDER`. El parser se fue a tools/sarif.py para que gate.sh pueda usar EL MISMO
# —antes contaba con `grep -o '"ruleId"'`, así que el veredicto y el informe leían el mismo
# archivo con dos lectores distintos—, pero mover a la vez el parser y a sus consumidores habría
# hecho imposible comprobar que el informe no cambió ni un byte.
SEV_ORDER = sarif.SEV_ORDER
LEVEL_MAP = sarif.LEVEL_MAP
read_json = sarif.read_json
severity_of = sarif.severity_of
load_sarif = sarif.load_sarif

# ---------------------------------------------------------------- data loading


def env_get(env_path, key, default=""):
    """Read one key from target.env WITHOUT sourcing it: values contain spaces, and a
    target profile is data, not code we should execute."""
    try:
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return default


def load_playwright(path):
    doc = read_json(path)
    if not doc:
        return None
    tally = {"passed": 0, "failed": 0, "skipped": 0}
    failures = []

    def walk(suite):
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                for res in test.get("results", []):
                    st = res.get("status", "unknown")
                    tally[st] = tally.get(st, 0) + 1
                    if st == "failed":
                        msg = ANSI.sub("", (res.get("error", {}) or {}).get("message", ""))
                        failures.append({"title": spec.get("title", ""),
                                         "msg": " ".join(msg.split())[:300]})
                    break
        for sub in suite.get("suites", []):
            walk(sub)

    for suite in doc.get("suites", []):
        walk(suite)
    return {"tally": tally, "failures": failures}


def load_k6(path):
    doc = read_json(path)
    if not doc:
        return None
    metrics = doc.get("metrics", doc)
    out = {}
    dur = metrics.get("http_req_duration", {})
    for key in ("p(95)", "avg", "max"):
        if key in dur:
            out[key] = round(float(dur[key]), 1)
    failed = metrics.get("http_req_failed", {})
    if isinstance(failed, dict) and "value" in failed:
        out["error_rate"] = round(float(failed["value"]), 4)
    reqs = metrics.get("http_reqs", {})
    if isinstance(reqs, dict) and "count" in reqs:
        out["requests"] = reqs["count"]
    return out or None


def run_tier(target, root):
    """Which rung the profile is on — from tools/tier.sh, never recomputed here.

    Lets the coverage table separate "you could have run this and did not" from "this is not
    available yet at your rung". They look identical in a reports folder and mean opposite
    things: the first is an omission, the second is simply where the project stands.
    """
    try:
        proc = subprocess.run(["tools/tier.sh", target], cwd=root, capture_output=True,
                              text=True, timeout=60)
        out = ANSI.sub("", proc.stdout)
    except Exception:
        return 1
    for line in out.splitlines():
        if line.startswith("TIER="):
            try:
                return int(line[5:])
            except ValueError:
                return 1
    return 1


def run_gate(target, root):
    """Single source of truth for the verdict: ask gate.sh rather than reimplement it."""
    try:
        proc = subprocess.run(["tools/gate.sh", target], cwd=root, capture_output=True,
                              text=True, timeout=120)
        raw = ANSI.sub("", proc.stdout)
    except Exception as exc:
        return {"verdict": "UNKNOWN", "lines": [], "error": str(exc)}
    lines = []
    for line in raw.splitlines():
        m = re.match(r"\s*(PASS|FAIL|skip)\s+(.*)", line)
        if m:
            lines.append({"status": m.group(1), "text": m.group(2).strip()})
    verdict = "FAILED" if "GATE FAILED" in raw else ("PASSED" if "GATE PASSED" in raw else "UNKNOWN")
    return {"verdict": verdict, "lines": lines}


# ---------------------------------------------------------------- rendering

E = html.escape



sev_bar = style.sev_bar     # compartida con la interfaz: ver tools/style.py

sev_chips = style.sev_chips


def findings_block(data, limit=25, verdicts=None):
    verdicts = verdicts or {}
    rows = []
    for f in data["findings"][:limit]:
        judged = verdicts.get(triage.key_for(f.get("tool", ""), f["rule"], f["loc"]))
        loc = f'{E(f["loc"])}:{f["line"]}' if f["loc"] else ""
        # Several tools set `name` to the rule id verbatim (semgrep does). Printing both just
        # doubles a long identifier and pushes the actual message out of view.
        show_name = f["name"] and f["name"] != f["rule"]
        name = f' <span class="rule">{E(f["name"])}</span>' if show_name else ""
        mark, note = "", ""
        if judged:
            v = judged.get("verdict", "")
            if v:
                mark = (f'<span class="verdictline {E(v)}">'
                        f'{E(triage.LABELS.get(v, v))}</span>')
            if judged.get("note"):
                note = f'<div class="triage">{E(judged["note"])}</div>'
        rows.append(
            f'<div class="f"><div class="top"><span class="sev {f["sev"]}">{f["sev"].upper()}</span>'
            f'{mark}<span class="rule">{E(f["rule"])}</span>{name}</div>'
            f'<div class="loc">{loc}</div>'
            f'<div class="msg">{E(f["msg"])}</div>{note}</div>'
        )
    if data["count"] > limit:
        rows.append(f'<div class="more">… y {data["count"] - limit} más. '
                    f'El detalle completo está en el SARIF crudo.</div>')
    return "".join(rows)


def build(target, root):
    rep = os.path.join(root, "reports", target)
    env = os.path.join(root, "targets", target, "target.env")

    gate = run_gate(target, root)
    verdicts = triage.load(rep)
    tier = run_tier(target, root)
    # Dimensions that need a live application, so they can be reported as
    # unavailable rather than as skipped when the profile is still on rung 1.
    # La última de las SEIS copias de la misma lista. Ahora sale del registro
    # (lib/dimensions.yml), igual que gate.sh, run-manifest.sh, ui/findings.py y ui/app.py.
    #
    # `live` ya no se decide comparando el título contra un conjunto de cadenas escritas a mano
    # —que se rompía en cuanto alguien retocaba una etiqueta— sino leyendo el campo del registro.
    #
    # Notas que valía la pena conservar de la lista anterior:
    #   * SonarQube se exporta del servidor con `make sonar`; antes de eso analizaba y no dejaba
    #     nada detrás.
    #   * Qodana es una dimensión CON HALLAZGOS, no un enlace a un HTML. Mientras se pintó como
    #     "sí / NO EJECUTADO" con un guion en la columna de cuenta, una corrida con cientos de
    #     inspecciones se leía igual que una limpia.
    #   * El artefacto móvil es el binario que se distribuye, no el código que lo produjo: el
    #     bundle firmado lleva configuración compilada, assets y SDKs que ningún escaneo del
    #     repositorio ve.
    dimlist = [d for d in dimensions.load() if d.kind == "findings"]
    live_dims = {d.label for d in dimlist if d.live}
    dims = [(d.label, d.tool or d.id, load_sarif(d.path(rep), d.id), d.link) for d in dimlist]
    pw = load_playwright(f"{rep}/playwright/results.json")
    k6 = load_k6(f"{rep}/k6/summary.json")
    sbom = os.path.exists(f"{rep}/sbom/sbom.spdx.json")

    # ---- header
    # Which revision was audited. RUN.md carries one row per repository (a project is not always
    # one checkout), so the header summarises them: `repo@sha` joined, and whether any tree was
    # dirty or any branch out of sync — because that qualifies every number on this page.
    commit = "—"
    run_md = os.path.join(rep, "RUN.md")
    if os.path.exists(run_md):
        repos, caveat = [], False
        with open(run_md, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("- commit:"):          # manifests written before the repo table
                    commit = line.split("`")[1] if "`" in line else line.split(":", 1)[1].strip()
                    break
                if line.startswith("| `") and "|" in line[3:]:
                    cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
                    if len(cells) >= 5 and not cells[0].startswith("-"):
                        repos.append(f"{cells[0]}@{cells[2].split()[0]}")
                        caveat = caveat or "**" in line
        if repos:
            commit = ", ".join(repos) + (" ⚠ árbol sucio o rama desalineada" if caveat else "")
    src = env_get(env, "SRC_PATH", "—")

    parts = [f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>QA-harness · {E(target)}</title><style>{style.css(style.REPORT)}</style></head><body><div class="wrap">
<h1>QA-harness · {E(target)}</h1>
<div class="sub">Fuente <code>{E(src)}</code> · commit <code>{E(commit[:60])}</code>
 · generado {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>"""]

    # ---- verdict
    vtext = {
        "FAILED": "Se incumplió al menos un umbral declarado en <code>target.env</code>.",
        "PASSED": "Todos los umbrales evaluados se cumplen. Revise abajo qué quedó sin ejecutar.",
        "UNKNOWN": "No se pudo obtener el veredicto de <code>tools/gate.sh</code>.",
    }[gate["verdict"]]
    parts.append(f"""<div class="verdict"><span class="badge {gate['verdict']}">{gate['verdict']}</span>
<span class="vtext">{vtext}</span></div>""")
    if gate["lines"]:
        items = "".join(
            f'<li><span class="tag {l["status"]}">{l["status"]}</span><span>{E(l["text"])}</span></li>'
            for l in gate["lines"]
        )
        parts.append(f'<ul class="gate">{items}</ul>')
    parts.append('<div class="note"><b>skip no es PASS.</b> Una dimensión que no se ejecutó '
                 'nunca debe leerse como aprobada: significa que no hay información, no que no '
                 'haya hallazgos. <b>NO DISPONIBLE</b> es distinto de <b>NO EJECUTADO</b>: lo '
                 'primero es que este perfil aún no puede medirlo (falta indicar dónde responde '
                 'la aplicación); lo segundo es que podía y no se hizo.</div>')

    # ---- coverage
    parts.append("<h2>Cobertura</h2><table><tr><th>Dimensión</th><th>Herramienta</th>"
                 '<th class="num">Hallazgos</th><th>Severidad</th><th>Ejecutado</th></tr>')
    for title, tool, data, _ in dims:
        if data is None:
            na = tier < 2 and title in live_dims
            cell = ('<td class="ran-na" title="Requiere una aplicación respondiendo">'
                    'NO DISPONIBLE</td>' if na else '<td class="ran-no">NO EJECUTADO</td>')
            parts.append(f'<tr><td>{E(title)}</td><td>{E(tool)}</td><td class="num">—</td>'
                         f'<td></td>{cell}</tr>')
        else:
            parts.append(f'<tr><td>{E(title)}</td><td>{E(tool)}</td>'
                         f'<td class="num">{data["count"]}</td><td>{sev_bar(data["sev"])}</td>'
                         f'<td class="ran-yes">sí</td></tr>')
    if pw is None:
        cell = ('<td class="ran-na">NO DISPONIBLE</td>' if tier < 2
                else '<td class="ran-no">NO EJECUTADO</td>')
        parts.append('<tr><td>Autorización y flujos</td><td>Playwright</td>'
                     f'<td class="num">—</td><td></td>{cell}</tr>')
    else:
        t = pw["tally"]
        parts.append(f'<tr><td>Autorización y flujos</td><td>Playwright</td>'
                     f'<td class="num">{t.get("failed", 0)} fallan / {sum(t.values())}</td>'
                     f'<td></td><td class="ran-yes">sí</td></tr>')
    if k6:
        k6_cell = '<td class="ran-yes">sí</td>'
    elif tier < 2:
        k6_cell = '<td class="ran-na">NO DISPONIBLE</td>'
    else:
        k6_cell = '<td class="ran-no">NO EJECUTADO</td>'
    parts.append(f'<tr><td>Carga</td><td>k6</td>'
                 f'<td class="num">{"ver abajo" if k6 else "—"}</td><td></td>{k6_cell}</tr>')
    parts.append(f'<tr><td>Inventario (SBOM)</td><td>Syft</td><td class="num">—</td><td></td>'
                 f'<td class="{"ran-yes" if sbom else "ran-no"}">'
                 f'{"sí" if sbom else "NO EJECUTADO"}</td></tr>')
    parts.append("</table>")

    # ---- detail per dimension
    parts.append("<h2>Hallazgos</h2>")
    for title, tool, data, artifact in dims:
        if data is None:
            continue
        parts.append(
            f'<details><summary><span>{E(title)} · {E(tool)}</span>'
            f'<span class="chip"><b>{data["count"]}</b></span></summary>'
            f'<div class="body">{sev_chips(data["sev"])}{findings_block(data, verdicts=verdicts)}'
            f'<div class="more">Artefacto crudo: <code>{E(artifact)}</code></div>'
            f'</div></details>'
        )

    if pw is not None:
        t = pw["tally"]
        body = "".join(
            f'<div class="f"><div class="top"><span class="sev high">FALLA</span>'
            f'<span class="rule">{E(f["title"])}</span></div>'
            f'<div class="msg">{E(f["msg"])}</div></div>' for f in pw["failures"][:25]
        ) or '<div class="more">Sin fallos.</div>'
        parts.append(
            f'<details><summary><span>Autorización y flujos · Playwright</span>'
            f'<span class="chip">{t.get("passed", 0)} pasan · <b>{t.get("failed", 0)}</b> fallan'
            f'</span></summary><div class="body">'
            f'<div class="note">Un fallo aquí puede ser un hallazgo <b>o</b> un escenario mal '
            f'sembrado. Si el rol autorizado tampoco logra la operación, el resultado es '
            f'<b>inconcluso</b>, no negativo: la prueba nunca llegó a la decisión de '
            f'autorización.</div>{body}</div></details>'
        )

    if k6:
        rows = "".join(f"<tr><td>{E(k)}</td><td class='num'>{v}</td></tr>" for k, v in k6.items())
        parts.append(f'<details><summary><span>Carga · k6</span></summary><div class="body">'
                     f'<table>{rows}</table>'
                     f'<div class="note">Estas cifras sólo son comparables contra el sobre de '
                     f'recursos declarado: <code>PERF_CPUS={E(env_get(env, "PERF_CPUS", "?"))}</code> '
                     f'<code>PERF_MEM={E(env_get(env, "PERF_MEM", "?"))}</code>.</div>'
                     f'</div></details>')

    # ---- links
    links = []
    for label, rel in [("Reporte ZAP (HTML)", "zap/zap-report.html"),
                       ("Suite Playwright (HTML)", "playwright/html/index.html"),
                       ("Manifiesto de la corrida", "RUN.md"),
                       ("SBOM", "sbom/sbom.txt"),
                       ("Qodana", "qodana/report/index.html")]:
        if os.path.exists(os.path.join(rep, rel)):
            links.append(f'<li><a href="{rel}">{E(label)}</a></li>')
    if links:
        parts.append("<h2>Artefactos originales</h2><ul>" + "".join(links) + "</ul>")

    parts.append('<footer>Generado por <code>make dashboard TARGET=' + E(target) + '</code>. '
                 'Esta página resume; no sustituye el triaje. Un hallazgo no es un riesgo hasta '
                 'que alguien evalúa si es alcanzable, y un <code>200</code> sólo es un hallazgo '
                 'si la política decía <code>403</code>.</footer></div></body></html>')
    return "".join(parts)


def main():
    if len(sys.argv) < 2:
        sys.exit("uso: dashboard.py <target>")
    target = sys.argv[1]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(root, "reports", target)
    if not os.path.isdir(out_dir):
        sys.exit(f"no existe reports/{target} — ejecute algún análisis primero")
    out = os.path.join(out_dir, "index.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(build(target, root))
    print(f"dashboard: reports/{target}/index.html")


if __name__ == "__main__":
    main()
