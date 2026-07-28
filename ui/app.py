"""QA-harness — local web interface.

SCOPE, deliberately: this binds to 127.0.0.1 and has no authentication, because it holds the
Docker socket. Anything that reaches it can start arbitrary containers, which is root on this
host. On loopback that is a single-operator tool and needs no login; published on a network it
would be a remote code execution service handed out for free. The bind is checked at startup and
the process refuses to run otherwise — see main().

Sharing it with a team is a different product (accounts, RBAC, an audit trail, a vault for the
credentials every target.env carries) and is documented as not built.

What this file may do: invoke `make`, read files under the lab directory. Nothing else. It must
never grow its own analysis, its own verdict, or its own list of tools — those exist once, in the
Makefile and tools/, and a second copy would eventually contradict the first.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, FileResponse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract          # noqa: E402
import jobs as jobslib   # noqa: E402
import render            # noqa: E402

LAB = os.environ.get("LAB_DIR", os.getcwd())
TARGETS = os.path.join(LAB, "targets")
REPORTS = os.path.join(LAB, "reports")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")

app = FastAPI(title="QA-harness")


def _profile_path(target: str) -> str:
    return os.path.join(TARGETS, target, "target.env")


def _secrets_for(target: str) -> list[str]:
    try:
        return contract.load(_profile_path(target)).secret_values()
    except OSError:
        return []


runner = jobslib.Runner(redactor=_secrets_for)


def _sh(script: str, *args: str, timeout: int = 60) -> str:
    """Run one of the lab's own scripts and return its output. Never a docker command."""
    try:
        proc = subprocess.run([os.path.join(LAB, "tools", script), *args],
                              cwd=LAB, capture_output=True, text=True, timeout=timeout)
        return jobslib.ANSI.sub("", proc.stdout + proc.stderr)
    except Exception as exc:
        return f"no se pudo ejecutar {script}: {exc}"


def valid_target(target: str) -> bool:
    """Guard every path parameter: it is interpolated into filesystem paths and a make call."""
    return bool(NAME_RE.match(target)) and os.path.isfile(_profile_path(target))


def list_targets() -> list[str]:
    if not os.path.isdir(TARGETS):
        return []
    return sorted(d for d in os.listdir(TARGETS)
                  if not d.startswith("_") and os.path.isfile(_profile_path(d)))


def tier_of(target: str) -> tuple[int, str, list[tuple[str, str]]]:
    """(tier, live-state, blocked) — straight from tools/tier.sh, never recomputed here."""
    out = _sh("tier.sh", target, timeout=30)
    tier, live, blocked = 1, "unconfigured", []
    for line in out.splitlines():
        if line.startswith("TIER="):
            tier = int(line[5:] or 1)
        elif line.startswith("LIVE="):
            live = line[5:]
        elif line.startswith("BLOCKED="):
            goals, _, reason = line[8:].partition("|")
            blocked.append((goals, reason))
    return tier, live, blocked


def goal_groups() -> dict[str, list[tuple[str, str]]]:
    """Actions, grouped, parsed from `make help`.

    The taxonomy lives in the Makefile as `##[code|live|admin]` tags. Reading it back means a new
    goal appears here on its own, in the right group, with no change to this file.
    """
    try:
        out = subprocess.run(["make", "help"], cwd=LAB, capture_output=True,
                             text=True, timeout=30).stdout
    except Exception:
        return {}
    out = jobslib.ANSI.sub("", out)
    groups: dict[str, list[tuple[str, str]]] = {}
    current = ""
    skip = {
        "help", "list", "new", "detect",     # driven by dedicated screens instead
        "ui", "ui-stop", "ui-logs",          # the interface does not offer to stop itself
        "purge",                             # prompts on stdin: from here it would hang forever
    }
    for line in out.splitlines():
        head = line.strip()
        # Headers are bracketed (`[code]`) so they cannot be confused with a goal whose name
        # happens to be `live` — which is exactly what swallowed that goal before.
        if head.startswith("[code]"):
            current = "code"
        elif head.startswith("[live]"):
            current = "live"
        elif head.startswith("[admin]"):
            current = "admin"
        elif current and line.startswith("    ") and head:
            parts = head.split(None, 1)
            goal = parts[0]
            if goal not in skip:
                groups.setdefault(current, []).append((goal, parts[1] if len(parts) > 1 else ""))
    return groups


# ---------------------------------------------------------------- routes


@app.get("/", response_class=HTMLResponse)
def home():
    rows = []
    for name in list_targets():
        tier, live, _ = tier_of(name)
        rows.append({"name": name, "tier": tier, "live": live})
    return render.home(rows)


@app.get("/new", response_class=HTMLResponse)
def new_form():
    return render.new_page("")


@app.post("/new", response_class=HTMLResponse)
def new_submit(name: str = Form(...), src: str = Form(...)):
    name = name.strip()
    src = src.strip()
    if not NAME_RE.match(name):
        return render.new_page("Nombre inválido: minúsculas, dígitos, guiones y guiones bajos.")
    if os.path.exists(os.path.join(TARGETS, name)):
        return render.new_page(f"Ya existe un perfil llamado «{name}».")
    if not os.path.isdir(src):
        return render.new_page(
            f"«{src}» no es un directorio accesible. Debe ser una ruta ABSOLUTA a un checkout "
            f"en esta máquina, y debe existir tal cual dentro del contenedor de la interfaz.")

    out = _sh("new-target.sh", name)
    if not os.path.isfile(_profile_path(name)):
        return render.new_page(f"No se pudo crear el perfil:\n{out}")

    prof = contract.load(_profile_path(name))
    contract.save(prof, {"SRC_PATH": src})
    return RedirectResponse(f"/t/{name}/detect", status_code=303)


@app.get("/t/{target}/detect", response_class=HTMLResponse)
def detect(target: str):
    if not valid_target(target):
        return RedirectResponse("/", status_code=303)
    return render.detect_page(target, _sh("detect.sh", target, timeout=120))


@app.get("/t/{target}", response_class=HTMLResponse)
def target_page(target: str, msg: str = "", kind: str = "ok"):
    if not valid_target(target):
        return RedirectResponse("/", status_code=303)
    tier, live, blocked = tier_of(target)
    return render.target_page(
        target, tier, live, blocked, goal_groups(), runner.recent(target),
        msg=msg, kind=kind,
        has_report=os.path.isfile(os.path.join(REPORTS, target, "index.html")),
    )


@app.post("/t/{target}/run")
def run_goal(target: str, goal: str = Form(...)):
    if not valid_target(target):
        return RedirectResponse("/", status_code=303)
    # Only goals `make help` actually advertises: no arbitrary string reaches the shell.
    known = {g for items in goal_groups().values() for g, _ in items}
    if goal not in known:
        return RedirectResponse(f"/t/{target}?msg=Objetivo+desconocido&kind=err", status_code=303)
    try:
        job = runner.start(target, goal)
    except RuntimeError as exc:
        busy = runner.running_for(target)
        if busy:
            return RedirectResponse(f"/job/{busy.id}", status_code=303)
        return RedirectResponse(f"/t/{target}?msg={exc}&kind=err", status_code=303)
    return RedirectResponse(f"/job/{job.id}", status_code=303)


@app.get("/job/{job_id}", response_class=HTMLResponse)
def job_page(job_id: str):
    job = runner.get(job_id)
    if not job:
        return RedirectResponse("/", status_code=303)
    return render.job_page(job, jobslib.read_log(job_id))


@app.get("/job/{job_id}/stream")
def job_stream(job_id: str):
    return StreamingResponse(runner.stream(job_id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/t/{target}/config", response_class=HTMLResponse)
def config_get(target: str, msg: str = "", kind: str = "ok"):
    if not valid_target(target):
        return RedirectResponse("/", status_code=303)
    return render.config_page(target, contract.load(_profile_path(target)), msg, kind)


@app.post("/t/{target}/config", response_class=HTMLResponse)
async def config_post(target: str, request: Request):
    if not valid_target(target):
        return RedirectResponse("/", status_code=303)
    form = await request.form()
    prof = contract.load(_profile_path(target))
    known = {f.key: f for f in prof.fields if not f.commented}

    updates: dict[str, str] = {}
    for key, value in form.items():
        f = known.get(key)
        if f is None:
            continue
        # An empty password field means "leave it as it is", not "erase it" — the form never
        # received the current value, so submitting blank must not wipe a working credential.
        if f.secret and not str(value).strip():
            continue
        updates[key] = str(value).strip()

    changed = contract.save(prof, updates)
    msg = (f"Guardado. Campos modificados: {', '.join(changed)}."
           if changed else "Sin cambios que guardar.")
    return render.config_page(target, contract.load(_profile_path(target)), msg, "ok")


def _triage_blocks(target: str) -> tuple[list[dict], dict]:
    """Findings to judge, from the artifacts already on disk.

    Loaded through tools/dashboard.py rather than re-parsed here: SARIF severity lives in a
    different place per tool, and a second parser would eventually disagree with the report.
    """
    sys.path.insert(0, os.path.join(LAB, "tools"))
    import dashboard  # noqa: PLC0415 - imported lazily; needs LAB on the path
    import triage as triagelib  # noqa: PLC0415

    rep = os.path.join(REPORTS, target)
    sources = [
        ("gitleaks", "Secretos en la historia git", f"{rep}/gitleaks.sarif"),
        ("trivy-fs", "Dependencias / CVE", f"{rep}/trivy/trivy-fs.sarif"),
        ("trivy-config", "Configuración de contenedores", f"{rep}/trivy/trivy-config.sarif"),
        ("semgrep", "SAST", f"{rep}/semgrep/semgrep.sarif"),
        ("zap", "Superficie runtime (DAST)", f"{rep}/zap/zap-report.json"),
    ]
    recorded = triagelib.load(rep)
    blocks = []
    for tool, title, path in sources:
        data = dashboard.load_sarif(path, tool)
        if not data or not data["findings"]:
            continue
        items = []
        # Capped: a page with 165 secrets is not a page anyone triages. Highest severity first,
        # which is also the order in which judging them is worth the time.
        for f in data["findings"][:60]:
            key = triagelib.key_for(tool, f["rule"], f["loc"])
            rec = recorded.get(key, {})
            items.append({**f, "key": key,
                          "verdict": rec.get("verdict", ""), "note": rec.get("note", "")})
        blocks.append({"tool": tool, "title": f"{title} · {data['count']}", "findings": items})
    return blocks, triagelib.summary(recorded)


@app.get("/t/{target}/triage", response_class=HTMLResponse)
def triage_get(target: str, msg: str = ""):
    if not valid_target(target):
        return RedirectResponse("/", status_code=303)
    blocks, counts = _triage_blocks(target)
    return render.triage_page(target, blocks, counts, msg)


@app.post("/t/{target}/triage", response_class=HTMLResponse)
async def triage_post(target: str, request: Request):
    if not valid_target(target):
        return RedirectResponse("/", status_code=303)
    sys.path.insert(0, os.path.join(LAB, "tools"))
    import triage as triagelib  # noqa: PLC0415

    form = await request.form()
    entries: dict[str, dict] = {}
    for field, value in form.items():
        if field.startswith("v__"):
            entries.setdefault(field[3:], {})["verdict"] = str(value)
        elif field.startswith("n__"):
            entries.setdefault(field[3:], {})["note"] = str(value)

    triagelib.save(os.path.join(REPORTS, target), entries)
    # Rebuild the report immediately: a verdict the operator cannot see reflected is a verdict
    # they will not trust, and will re-enter.
    subprocess.run(["make", "dashboard", f"TARGET={target}"], cwd=LAB,
                   capture_output=True, timeout=120)
    blocks, counts = _triage_blocks(target)
    return render.triage_page(target, blocks, counts, "Triaje guardado e informe regenerado.")


@app.get("/t/{target}/report")
def report(target: str):
    if not valid_target(target):
        return RedirectResponse("/", status_code=303)
    path = os.path.join(REPORTS, target, "index.html")
    if not os.path.isfile(path):
        return RedirectResponse(f"/t/{target}?msg=Aún+no+hay+informe&kind=err", status_code=303)
    return FileResponse(path)


def main() -> None:
    import uvicorn

    # Binding 0.0.0.0 *inside the container* is correct: the container has its own network
    # namespace, so this is not the host's 0.0.0.0. The confinement that matters is the published
    # port mapping in docker-compose.yml, which is hardcoded to 127.0.0.1 and must stay that way.
    # It is verified from the host after startup by tools/ui-check-bind.sh, because that is the
    # only place the real binding can be observed — a check in here would be theatre.
    uvicorn.run(app, host="0.0.0.0", port=7777, log_level="warning")  # noqa: S104


if __name__ == "__main__":
    main()
