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

ANSI = re.compile(r"\x1b\[[0-9;]*m")

# ---------------------------------------------------------------- data loading


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


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


# ---------------------------------------------------------------- SARIF parsing

SEV_ORDER = ["critical", "high", "medium", "low", "unranked"]
LEVEL_MAP = {"error": "high", "warning": "medium", "note": "low", "none": "low"}


def severity_of(result, rule):
    """Resolve severity across tools that each put it somewhere different.

    Trivy tags it (CRITICAL/HIGH/...) and also gives CVSS; semgrep tags it; ZAP uses the SARIF
    `level`; gitleaks says nothing at all. Order matters: an explicit tag beats a derived score,
    and a score beats the generic level, because `level` collapses distinctions the tool made.
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


def load_sarif(path):
    """-> {'count': n, 'sev': {...}, 'findings': [...]} or None when the file is absent.

    None means NOT RUN and is rendered as such. It is never coerced to zero."""
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
                "rule": res.get("ruleId", "?"),
                "name": (rule.get("name") or rule.get("shortDescription", {}).get("text") or ""),
                "sev": sev,
                "msg": (res.get("message", {}) or {}).get("text", "")[:400],
                "loc": loc,
                "line": line,
            })
    out["findings"].sort(key=lambda f: SEV_ORDER.index(f["sev"]))
    return out


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

CSS = """
:root{--bg:#fff;--fg:#1a1d21;--muted:#5c6570;--line:#e2e6ea;--card:#fff;--accent:#0b5fff;
--crit:#b3001b;--high:#d4380d;--med:#b06a00;--low:#3d7a3d;--unranked:#6b7280;
--pass:#1a7f37;--fail:#b3001b;--skip:#6b7280;--shadow:0 1px 3px rgba(0,0,0,.06)}
@media (prefers-color-scheme:dark){:root{--bg:#0f1216;--fg:#e6e9ee;--muted:#9aa4b1;
--line:#242a31;--card:#151a20;--crit:#ff6b6b;--high:#ff9151;--med:#ffc75a;--low:#6ee7a8;
--unranked:#9aa4b1;--pass:#4ade80;--fail:#ff6b6b;--shadow:none}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,
"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:32px 20px 72px}
h1{font-size:26px;margin:0 0 4px;font-weight:650;letter-spacing:-.02em}
h2{font-size:18px;margin:36px 0 12px;font-weight:620;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:13.5px;margin-bottom:24px}
.sub code{background:var(--line);padding:1px 6px;border-radius:4px;font-size:12.5px}
.verdict{display:flex;align-items:center;gap:14px;padding:18px 20px;border-radius:10px;
border:1px solid var(--line);background:var(--card);box-shadow:var(--shadow);margin-bottom:8px}
.badge{font-size:19px;font-weight:700;letter-spacing:.02em;padding:6px 14px;border-radius:7px;color:#fff}
.badge.FAILED{background:var(--fail)}.badge.PASSED{background:var(--pass)}
.badge.UNKNOWN{background:var(--skip)}
.vtext{color:var(--muted);font-size:13.5px}
.gate{list-style:none;padding:0;margin:14px 0 0;display:grid;gap:6px}
.gate li{display:flex;gap:10px;align-items:baseline;font-size:14px;padding:7px 12px;
border:1px solid var(--line);border-radius:7px;background:var(--card)}
.tag{font-size:11px;font-weight:700;padding:2px 7px;border-radius:4px;color:#fff;min-width:42px;
text-align:center;letter-spacing:.03em}
.tag.PASS{background:var(--pass)}.tag.FAIL{background:var(--fail)}.tag.skip{background:var(--skip)}
table{width:100%;border-collapse:collapse;font-size:14px;background:var(--card);
border:1px solid var(--line);border-radius:9px;overflow:hidden}
th,td{text-align:left;padding:10px 13px;border-bottom:1px solid var(--line)}
th{font-weight:620;font-size:12.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
tr:last-child td{border-bottom:none}
.num{font-variant-numeric:tabular-nums;text-align:right}
.ran-yes{color:var(--pass);font-weight:600}
.ran-no{color:var(--fail);font-weight:700}
.sevbar{display:flex;height:9px;border-radius:5px;overflow:hidden;background:var(--line);min-width:130px}
.sevbar i{display:block;height:100%}
.s-critical{background:var(--crit)}.s-high{background:var(--high)}.s-medium{background:var(--med)}
.s-low{background:var(--low)}.s-unranked{background:var(--unranked)}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 0}
.chip{font-size:12px;padding:3px 9px;border-radius:20px;border:1px solid var(--line);color:var(--muted)}
.chip b{color:var(--fg);font-variant-numeric:tabular-nums}
details{border:1px solid var(--line);border-radius:9px;margin:10px 0;background:var(--card);
overflow:hidden}
summary{cursor:pointer;padding:13px 16px;font-weight:600;font-size:14.5px;display:flex;
justify-content:space-between;align-items:center;gap:12px;user-select:none}
summary::-webkit-details-marker{display:none}
summary:after{content:"›";transform:rotate(90deg);color:var(--muted);font-size:17px;transition:.15s}
details[open] summary:after{transform:rotate(-90deg)}
.body{padding:0 16px 14px;border-top:1px solid var(--line)}
.f{padding:11px 0;border-bottom:1px dashed var(--line);font-size:13.5px}
.f:last-child{border-bottom:none}
.f .top{display:flex;gap:9px;align-items:baseline;flex-wrap:wrap}
.f .rule{font-weight:600}
.f .loc{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:var(--muted);
word-break:break-all}
.f .msg{color:var(--muted);margin-top:3px}
.sev{font-size:10.5px;font-weight:700;padding:2px 6px;border-radius:4px;color:#fff;letter-spacing:.03em}
.sev.critical{background:var(--crit)}.sev.high{background:var(--high)}
.sev.medium{background:var(--med)}.sev.low{background:var(--low)}.sev.unranked{background:var(--unranked)}
.note{border-left:3px solid var(--accent);background:var(--card);padding:13px 16px;
border-radius:0 8px 8px 0;font-size:13.5px;color:var(--muted);margin:14px 0}
.note b{color:var(--fg)}
.more{color:var(--muted);font-size:12.5px;padding:9px 0 2px}
a{color:var(--accent)}
footer{margin-top:44px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:12.5px}
"""


def sev_bar(sev):
    total = sum(sev.values()) or 1
    parts = "".join(
        f'<i class="s-{k}" style="width:{sev[k] / total * 100:.1f}%"></i>'
        for k in SEV_ORDER if sev.get(k)
    )
    return f'<div class="sevbar">{parts}</div>'


def sev_chips(sev):
    chips = "".join(
        f'<span class="chip">{k} <b>{sev[k]}</b></span>' for k in SEV_ORDER if sev.get(k)
    )
    return f'<div class="chips">{chips}</div>' if chips else ""


def findings_block(data, limit=25):
    rows = []
    for f in data["findings"][:limit]:
        loc = f'{E(f["loc"])}:{f["line"]}' if f["loc"] else ""
        # Several tools set `name` to the rule id verbatim (semgrep does). Printing both just
        # doubles a long identifier and pushes the actual message out of view.
        show_name = f["name"] and f["name"] != f["rule"]
        name = f' <span class="rule">{E(f["name"])}</span>' if show_name else ""
        rows.append(
            f'<div class="f"><div class="top"><span class="sev {f["sev"]}">{f["sev"].upper()}</span>'
            f'<span class="rule">{E(f["rule"])}</span>{name}</div>'
            f'<div class="loc">{loc}</div>'
            f'<div class="msg">{E(f["msg"])}</div></div>'
        )
    if data["count"] > limit:
        rows.append(f'<div class="more">… y {data["count"] - limit} más. '
                    f'El detalle completo está en el SARIF crudo.</div>')
    return "".join(rows)


def build(target, root):
    rep = os.path.join(root, "reports", target)
    env = os.path.join(root, "targets", target, "target.env")

    gate = run_gate(target, root)

    dims = [
        ("Secretos en la historia git", "gitleaks", load_sarif(f"{rep}/gitleaks.sarif"),
         "gitleaks.sarif"),
        ("Dependencias / CVE", "Trivy fs", load_sarif(f"{rep}/trivy/trivy-fs.sarif"),
         "trivy/trivy-fs.sarif"),
        ("Configuración de contenedores", "Trivy config",
         load_sarif(f"{rep}/trivy/trivy-config.sarif"), "trivy/trivy-config.sarif"),
        ("CVE de imágenes", "Trivy image", load_sarif(f"{rep}/trivy/trivy-image.sarif"),
         "trivy/trivy-image.sarif"),
        ("SAST", "semgrep", load_sarif(f"{rep}/semgrep/semgrep.sarif"), "semgrep/semgrep.sarif"),
        ("Superficie runtime (DAST)", "OWASP ZAP", load_sarif(f"{rep}/zap/zap-report.json"),
         "zap/zap-report.html"),
    ]
    pw = load_playwright(f"{rep}/playwright/results.json")
    k6 = load_k6(f"{rep}/k6/summary.json")
    sbom = os.path.exists(f"{rep}/sbom/sbom.spdx.json")
    qodana = os.path.exists(f"{rep}/qodana/report/index.html")

    # ---- header
    commit = "—"
    run_md = os.path.join(rep, "RUN.md")
    if os.path.exists(run_md):
        with open(run_md, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("- commit:"):
                    commit = line.split("`")[1] if "`" in line else line.split(":", 1)[1].strip()
                    break
    src = env_get(env, "SRC_PATH", "—")

    parts = [f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>QA-harness · {E(target)}</title><style>{CSS}</style></head><body><div class="wrap">
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
                 'haya hallazgos.</div>')

    # ---- coverage
    parts.append("<h2>Cobertura</h2><table><tr><th>Dimensión</th><th>Herramienta</th>"
                 '<th class="num">Hallazgos</th><th>Severidad</th><th>Ejecutado</th></tr>')
    for title, tool, data, _ in dims:
        if data is None:
            parts.append(f'<tr><td>{E(title)}</td><td>{E(tool)}</td><td class="num">—</td>'
                         f'<td></td><td class="ran-no">NO EJECUTADO</td></tr>')
        else:
            parts.append(f'<tr><td>{E(title)}</td><td>{E(tool)}</td>'
                         f'<td class="num">{data["count"]}</td><td>{sev_bar(data["sev"])}</td>'
                         f'<td class="ran-yes">sí</td></tr>')
    if pw is None:
        parts.append('<tr><td>Autorización y flujos</td><td>Playwright</td><td class="num">—</td>'
                     '<td></td><td class="ran-no">NO EJECUTADO</td></tr>')
    else:
        t = pw["tally"]
        parts.append(f'<tr><td>Autorización y flujos</td><td>Playwright</td>'
                     f'<td class="num">{t.get("failed", 0)} fallan / {sum(t.values())}</td>'
                     f'<td></td><td class="ran-yes">sí</td></tr>')
    parts.append(f'<tr><td>Carga</td><td>k6</td><td class="num">{"—" if not k6 else "ver abajo"}'
                 f'</td><td></td><td class="{"ran-yes" if k6 else "ran-no"}">'
                 f'{"sí" if k6 else "NO EJECUTADO"}</td></tr>')
    parts.append(f'<tr><td>Inventario (SBOM)</td><td>Syft</td><td class="num">—</td><td></td>'
                 f'<td class="{"ran-yes" if sbom else "ran-no"}">'
                 f'{"sí" if sbom else "NO EJECUTADO"}</td></tr>')
    parts.append(f'<tr><td>Calidad</td><td>Qodana</td><td class="num">—</td><td></td>'
                 f'<td class="{"ran-yes" if qodana else "ran-no"}">'
                 f'{"sí" if qodana else "NO EJECUTADO"}</td></tr>')
    parts.append("</table>")

    # ---- detail per dimension
    parts.append("<h2>Hallazgos</h2>")
    for title, tool, data, artifact in dims:
        if data is None:
            continue
        parts.append(
            f'<details><summary><span>{E(title)} · {E(tool)}</span>'
            f'<span class="chip"><b>{data["count"]}</b></span></summary>'
            f'<div class="body">{sev_chips(data["sev"])}{findings_block(data)}'
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
