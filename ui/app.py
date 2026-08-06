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

import json
import os
import re
import subprocess
import sys

from fastapi import FastAPI, Form, Request
from fastapi.responses import (HTMLResponse, RedirectResponse, StreamingResponse,
                               FileResponse, JSONResponse)

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
    import pipeline  # noqa: PLC0415 - necesita LAB en el path

    prof = contract.load(_profile_path(target))
    pipe = pipeline.build(target, _profile_path(target), os.path.join(REPORTS, target),
                          tier, live == "ok",
                          target_dir=os.path.join(TARGETS, target),
                          template_dir=os.path.join(TARGETS, "_template"))
    return render.target_page(
        target, tier, live, blocked, goal_groups(), runner.recent(target),
        msg=msg, kind=kind,
        has_report=os.path.isfile(os.path.join(REPORTS, target, "index.html")),
        pipe=pipe,
    )




@app.get("/t/{target}/outputs/{dim_id}", response_class=HTMLResponse)
def outputs(target: str, dim_id: str):
    """Los documentos en bruto de UNA dimensión: verlos y descargarlos.

    Se listan todos los del directorio de esa dimensión, no solo el que consume el gate. ZAP deja
    tres (SARIF, HTML, JSON crudo) y Sonar otros tres (SARIF, issues, hotspots): esconder los que
    el laboratorio no lee sería decidir por el operador qué evidencia le sirve.
    """
    if not valid_target(target):
        return RedirectResponse("/", status_code=303)
    sys.path.insert(0, os.path.join(LAB, "tools"))
    import dimensions  # noqa: PLC0415
    import guion as guionlib  # noqa: PLC0415
    import pipeline  # noqa: PLC0415

    dim = dimensions.by_id(dim_id)
    if dim is None:
        return RedirectResponse(f"/t/{target}?msg=Dimensión+desconocida&kind=err", status_code=303)

    rep = os.path.realpath(os.path.join(REPORTS, target))
    carpeta = os.path.dirname(dim.artifact)
    base = os.path.realpath(os.path.join(rep, carpeta)) if carpeta else rep

    ficheros = []
    if os.path.isdir(base) and base.startswith(rep):
        for raiz, _d, nombres in os.walk(base):
            for n in sorted(nombres):
                full = os.path.join(raiz, n)
                rel = os.path.relpath(full, rep)
                # Sin subcarpeta declarada (gitleaks.sarif está en la raíz de reports/) se listaría
                # el informe entero. En ese caso solo el artefacto de la dimensión y sus hermanos
                # de mismo nombre base — trufflehog.sarif junto a trufflehog.txt, por ejemplo.
                if not carpeta:
                    raiz_dim = os.path.splitext(os.path.basename(dim.artifact))[0]
                    if not os.path.basename(rel).startswith(raiz_dim):
                        continue
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                ficheros.append({
                    "rel": rel.replace(os.sep, "/"),
                    "tam": f"{st.st_size / 1024:.0f} KB" if st.st_size >= 1024 else f"{st.st_size} B",
                    "fecha": __import__("datetime").datetime.fromtimestamp(
                        st.st_mtime).strftime("%m-%d %H:%M"),
                    "canonico": rel.replace(os.sep, "/") == dim.artifact,
                })
    ficheros.sort(key=lambda f: (not f["canonico"], f["rel"]))

    valores = pipeline.overlay(_profile_path(target))
    g = guionlib.analizar(dim, valores, os.path.join(TARGETS, target),
                          os.path.join(TARGETS, "_template"))
    return render.outputs_page(target, {"label": dim.label, "tool": dim.tool or dim.id,
                                        "guion": g}, ficheros)


@app.get("/t/{target}/artifact/{path:path}")
def artifact(target: str, path: str, download: int = 0):
    """El artefacto CRUDO, tal como lo dejó la herramienta. Sin pasar por esta interfaz.

    Dos cosas dependen de que esta ruta exista y de que las rutas RELATIVAS funcionen desde ella:

    1. El operador tiene que poder comprobar por sí mismo que lo que dice el informe está de
       verdad en el fichero. Si «el artefacto» es solo una palabra en una tabla, la interfaz se
       convierte en la única fuente de verdad — exactamente lo que este laboratorio evita en todo
       lo demás.
    2. El informe generado (index.html) enlaza sus artefactos con rutas RELATIVAS
       (`zap/zap-report.html`, `qodana/report/index.html`) para que funcione también al abrirlo
       desde el disco o adjunto en un correo. Servido desde otra ruta, esos enlaces daban 404.
       Sirviendo el informe TAMBIÉN por aquí, las relativas resuelven y los dos modos funcionan.

    `?download=1` fuerza la descarga en vez de que el navegador lo muestre — un SARIF de medio
    mega abierto en una pestaña no lo lee nadie.
    """
    if not valid_target(target):
        return RedirectResponse("/", status_code=303)
    rep = os.path.realpath(os.path.join(REPORTS, target))
    full = os.path.realpath(os.path.join(rep, path))
    # El path viene de la URL: sin esta comprobación, `../../` serviría cualquier archivo del host.
    if not full.startswith(rep + os.sep) or not os.path.isfile(full):
        return RedirectResponse(f"/t/{target}?msg=Artefacto+no+encontrado&kind=err",
                                status_code=303)
    if download:
        return FileResponse(full, filename=os.path.basename(full),
                            media_type="application/octet-stream")
    # `.md` y `.sarif` los sirve FileResponse como descarga o como texto según el navegador; se
    # fuerza texto plano para que el manifiesto se lea en pantalla, que es para lo que se abre.
    if full.endswith((".md", ".sarif", ".json", ".txt", ".jtl", ".xml", ".properties", ".toml")):
        return FileResponse(full, media_type="text/plain; charset=utf-8")
    return FileResponse(full)


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


@app.post("/t/{target}/run-selected")
async def run_selected(target: str, request: Request):
    """Correr SOLO las dimensiones marcadas, como una tubería de CI/CD.

    El caso que esto resuelve: el operador QA devuelve observaciones, el equipo de desarrollo
    arregla tres cosas del código y nada del despliegue. Reejecutar las diecisiete dimensiones
    para comprobar tres arreglos cuesta media hora de máquina y varias JVM — así que no se
    reejecuta, y el informe envejece hasta dejar de describir el sistema.

    Se lanza como UN trabajo con varios objetivos (`make semgrep sonar TARGET=x`): make los corre
    en orden y para en el primero que falle, que es el comportamiento que se quiere — si el SAST
    revienta, no tiene sentido seguir midiendo encima.
    """
    if not valid_target(target):
        return RedirectResponse("/", status_code=303)
    form = await request.form()
    pedidos = [str(v).strip() for v in form.getlist("dim") if str(v).strip()]
    if not pedidos:
        return RedirectResponse(f"/t/{target}?msg=No+marcaste+ninguna&kind=err", status_code=303)

    # Solo objetivos que `make help` anuncia: nada que venga del formulario llega al shell.
    conocidos = {g for items in goal_groups().values() for g, _ in items}
    malos = [g for g in pedidos if g not in conocidos]
    if malos:
        return RedirectResponse(f"/t/{target}?msg=Objetivo+desconocido:+{malos[0]}&kind=err",
                                status_code=303)

    # Sin duplicados y en el orden del registro: las de código antes que las que necesitan la
    # aplicación en pie, para que un fallo temprano no deje a medias una medición en vivo.
    sys.path.insert(0, os.path.join(LAB, "tools"))
    import dimensions  # noqa: PLC0415
    orden = [d.goal for d in dimensions.load()]
    goals = sorted(set(pedidos), key=lambda g: orden.index(g) if g in orden else 999)

    try:
        job = runner.start(target, " ".join(goals))
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


@app.get("/t/{target}/triage")
def triage_redirect(target: str):
    """La pantalla de triaje con listas desplegables se retiró: había DOS formas de juzgar el
    mismo hallazgo, con dos listas de fuentes distintas (fue el bug que se comía ZAP entero) y dos
    conjuntos de controles. Ahora hay una sola, a un clic, en /findings."""
    if not valid_target(target):
        return RedirectResponse("/", status_code=303)
    return RedirectResponse(f"/t/{target}/findings", status_code=303)


@app.get("/t/{target}/findings", response_class=HTMLResponse)
def findings_get(target: str, msg: str = ""):
    if not valid_target(target):
        return RedirectResponse("/", status_code=303)
    import findings as findlib  # noqa: PLC0415 - needs LAB on the path

    return render.findings_page(target, findlib.collect(os.path.join(REPORTS, target)), msg)


@app.post("/t/{target}/judge")
async def judge(target: str, request: Request):
    """Guarda UN juicio y devuelve los contadores. El triaje a un clic se apoya en esto.

    Antes el triaje era un formulario con un `<select>` y un campo de texto por hallazgo, enviado
    entero. Con 942 hallazgos eso son ~2.800 interacciones y una recarga de la página completa,
    así que en la práctica nadie triajeaba: el laboratorio acumuló 941 sin juzgar y el gate los
    contaba todos como si nadie los hubiera mirado — que era exactamente el caso.

    Un veredicto vacío DEVUELVE el hallazgo a la pila: juzgar tiene que ser reversible mientras
    nadie haya firmado el informe.
    """
    if not valid_target(target):
        return JSONResponse({"ok": False, "error": "target inválido"}, status_code=400)
    sys.path.insert(0, os.path.join(LAB, "tools"))
    import triage as triagelib  # noqa: PLC0415

    try:
        body = await request.json()
    except ValueError:
        return JSONResponse({"ok": False, "error": "cuerpo ilegible"}, status_code=400)

    key = str(body.get("key") or "").strip()
    verdict = str(body.get("verdict") or "").strip()
    if not key:
        return JSONResponse({"ok": False, "error": "falta la clave del hallazgo"}, status_code=400)
    if verdict and verdict not in triagelib.VERDICTS:
        return JSONResponse({"ok": False, "error": f"criterio desconocido: {verdict}"},
                            status_code=400)

    entrada = {"verdict": verdict, "note": str(body.get("note") or ""),
               "dueno": str(body.get("dueno") or ""), "hasta": str(body.get("hasta") or "")}

    # Lo que el criterio exige se comprueba también AQUÍ, no solo en el navegador: la validación
    # de cliente evita un viaje, no protege el registro. Un `aceptado` sin dueño ni fecha
    # entrando por la API sería el mismo agujero con otro camino.
    if verdict:
        faltan = triagelib.falta(verdict, entrada)
        if faltan:
            return JSONResponse({"ok": False, "error": f"falta {', '.join(faltan)}"},
                                status_code=400)

    rep = os.path.join(REPORTS, target)
    triagelib.save(rep, {key: entrada})

    import findings as findlib  # noqa: PLC0415
    datos = findlib.collect(rep)
    pend = sum(1 for f in datos["findings"] if not f.get("verdict"))
    return JSONResponse({"ok": True, "pendientes": pend,
                         "juzgados": datos["total"] - pend})


@app.get("/t/{target}/report")
def report(target: str):
    """Redirige al informe SERVIDO COMO ARTEFACTO, no lo sirve aquí.

    El informe enlaza sus artefactos con rutas relativas para poder abrirse desde el disco. Al
    servirlo en `/t/<t>/report`, `zap/zap-report.html` resolvía a `/t/<t>/zap/zap-report.html`
    —una ruta que no existe— y los cinco enlaces de «Artefactos originales» daban 404.
    Sirviéndolo bajo `/t/<t>/artifact/`, las mismas relativas caen en `/t/<t>/artifact/zap/...`,
    que sí existe. Un cambio de dónde se sirve, no de qué genera el informe: sigue siendo un
    archivo que se puede adjuntar en un correo y abrir sin servidor.
    """
    if not valid_target(target):
        return RedirectResponse("/", status_code=303)
    if not os.path.isfile(os.path.join(REPORTS, target, "index.html")):
        return RedirectResponse(f"/t/{target}?msg=Aún+no+hay+informe&kind=err", status_code=303)
    return RedirectResponse(f"/t/{target}/artifact/index.html", status_code=303)


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
