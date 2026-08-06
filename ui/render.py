"""HTML for the UI. Server-rendered f-strings, no template engine, no build step.

Same reasoning as the rest of the lab: a tool that must run anywhere Docker runs should not
also require a bundler and a `dist/` that can silently go stale.
"""
from __future__ import annotations

import html
import os
import sys

# tools/ is found through LAB_DIR, not relative to this file: in the container the UI code lives
# at /ui-src while the lab is bind-mounted elsewhere, so "../tools" would not exist.
sys.path.insert(0, os.path.join(os.environ.get("LAB_DIR", os.getcwd()), "tools"))
import style  # noqa: E402  — shared with the generated report

E = html.escape

# What each rung means, in the operator's terms. This is the single most important thing the
# interface teaches: the lab does not need to install your application.
RUNGS = {
    1: ("r1", "Peldaño 1 · solo código",
        "Solo hace falta el checkout. Ya puedes correr todo el análisis estático — sin "
        "desplegar nada, sin base de datos y sin credenciales."),
    2: ("r2", "Peldaño 2 · código + tu despliegue",
        "Tu aplicación ya corre donde sea que la despliegues. El laboratorio le apunta; "
        "no la levanta ni la administra."),
    3: ("r3", "Peldaño 3 · código + receta",
        "El laboratorio levanta la aplicación él mismo, efímera y reproducible, y la destruye "
        "al terminar."),
}


def page(title: str, body: str, active: str = "") -> str:
    def nav(href: str, label: str, key: str) -> str:
        on = " on" if key == active else ""
        return f'<a class="{on.strip()}" href="{href}">{E(label)}</a>'

    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title><style>{style.css(style.REPORT, style.UI, style.PIPELINE, style.TRIAGE, style.RUNBAR)}</style></head><body>
<nav><span class="brand">QA-harness</span>
{nav('/', 'Proyectos', 'home')}
{nav('/new', 'Añadir proyecto', 'new')}
</nav><div class="wrap">{body}</div></body></html>"""


def flash(msg: str, kind: str = "ok") -> str:
    return f'<div class="flash {kind}">{msg}</div>' if msg else ""


def home(targets: list[dict]) -> str:
    if not targets:
        return page("QA-harness", """<h1>Ningún proyecto todavía</h1>
<p class="sub">Un proyecto («target») es un perfil que dice dónde está el código y, si la hay,
dónde responde la aplicación.</p>
<a class="btn primary" href="/new">Añadir el primero</a>""", "home")

    cards = []
    for t in targets:
        cls, name, _ = RUNGS.get(t["tier"], ("r1", "Peldaño ?", ""))
        live = ('<span class="chip">app respondiendo <b>sí</b></span>'
                if t["live"] == "ok" else
                '<span class="chip">app respondiendo <b>no</b></span>')
        cards.append(f"""<div class="card">
<h3><a href="/t/{E(t['name'])}">{E(t['name'])}</a></h3>
<p><span class="rung {cls}">{E(name)}</span></p>
<div class="chips">{live}</div>
</div>""")
    return page("QA-harness", f"""<h1>Proyectos</h1>
<p class="sub">Cada uno es un perfil en <code>targets/</code>. Ninguna configuración de proyecto
vive en la interfaz.</p>
<div class="grid">{''.join(cards)}</div>
<div class="actions"><a class="btn" href="/new">Añadir proyecto</a></div>""", "home")


def _action_button(target: str, goal: str, desc: str, disabled: str) -> str:
    dis = ' disabled title="' + E(disabled) + '"' if disabled else ""
    return (f'<form method="post" action="/t/{E(target)}/run" style="display:inline">'
            f'<input type="hidden" name="goal" value="{E(goal)}">'
            f'<button class="btn" name="go" value="1"{dis} title="{E(desc)}">{E(goal)}</button>'
            f'</form>')


def _stage_input(r, target):
    """Etapa 1 — QUE PIDE esta herramienta. Cada clave del perfil, con si esta rellena o no."""
    chips = []
    for group in r["inputs"]:
        etiqueta = " o ".join(group)
        falta = etiqueta in r["missing"]
        chips.append(f'<span class="key {"no" if falta else "si"}">{E(etiqueta)}</span>')
    faltan = (f'<div class="why">Falta rellenar {len(r["missing"])} de {len(r["inputs"])} — '
              f'<a href="/t/{E(target)}/config">editar el perfil</a></div>') if r["missing"] else ""
    cuerpo = "".join(chips) or '<span class="tool">sin entradas</span>'

    # EL GUION: el archivo que la herramienta interpreta. Es el TECHO de la cobertura, no una
    # entrada mas — un k6 de tres peticiones y una campana de diez guiones se pintaban igual.
    g = r.get("guion")
    guion_html = ""
    if g:
        estado_cls = {"propio": "si", "de plantilla": "no", "vacío": "no", "ausente": "no"}
        alcance = (f' · <b>{g["n"]}</b> {E(g.get("unidad", ""))}' if g["n"] else "")
        toca = (f'<div class="why">ejercita: {E(", ".join(g["toca"][:4]))}</div>'
                if g["toca"] else "")
        nota = f'<div class="why">{E(g["nota"])}</div>' if g.get("nota") else ""
        guion_html = (
            f'<div style="margin-top:10px">'
            f'<span class="tool">guion · {E(g["kind"])}</span><br>'
            f'<span class="key {estado_cls.get(g["estado"], "no")}">{E(g["rel"])}</span>'
            f'<span class="tool"> {E(g["estado"])}{alcance}</span>'
            f'{toca}{nota}</div>')

    # EL OBJETO auditado cuando no es el codigo: el binario firmado, una imagen, el contrato.
    obj = ""
    if r.get("objeto_pide"):
        puesto = bool(r.get("objeto"))
        obj = (f'<div style="margin-top:8px"><span class="tool">objeto auditado</span><br>'
               f'<span class="key {"si" if puesto else "no"}">'
               f'{E(r["objeto"][0] if puesto else r["objeto_pide"])}</span></div>')

    return (f'<div><div class="name">{E(r["label"])}</div>'
            f'<div class="tool">{E(r["tool"])}</div>'
            f'<div style="margin-top:8px">{cuerpo}</div>'
            f'{obj}{guion_html}{faltan}</div>')


def _stage_tool(r, target, blocked_reason):
    """Etapa 2 — la herramienta: estado en TRES valores, su coste, y CÓMO se corre.

    La casilla es lo que convierte esto en una tubería de CI/CD y no en una lista de botones.
    El caso real: el operador QA devuelve observaciones al equipo de desarrollo, el dev arregla
    tres cosas del código y nada del despliegue. Reejecutar las diecisiete dimensiones para
    comprobar tres arreglos cuesta media hora de máquina y varias JVM — así que no se reejecuta,
    y el informe envejece. Marcando solo `semgrep` y `sonar` se comprueba lo que cambió.

    La procedencia se pinta aquí porque cambia lo que significa el estado: una dimensión
    `ejecutada` pero EXCLUIDA no aporta evidencia sobre este sistema, y hay que verlo antes de
    decidir si merece la pena reejecutarla.
    """
    cls = {"ejecutada": "ok", "NO EJECUTADA": "norun"}.get(r["estado"], "na")
    motivo = f'<div class="why">{E(r["motivo"])}</div>' if r["motivo"] else ""
    medido = "medido" if r["medido"] else "estimado"
    coste = f'<div class="cost">{E(r["clase"])} · {E(r["mem"])} ({medido})</div>'
    dis = blocked_reason or (", ".join(r["missing"]) if r["missing"] else "")

    prov = ""
    if r.get("prov") == "excluida":
        prov = f'<div class="why"><b>EXCLUIDA del veredicto</b> — {E(r["prov_detalle"])}</div>'

    # Sin casilla cuando le falta una entrada: marcarla para correr solo produciría un fallo.
    marca = "" if dis else (
        f'<label class="pick"><input type="checkbox" name="dim" '
        f'value="{E(r["goal"])}" form="runsel"> correr</label>')
    btn = _action_button(target, r["goal"], f'correr {r["goal"]} ahora', dis)
    return (f'<div><span class="st {cls}">{E(r["estado"])}</span>{motivo}{prov}{coste}'
            f'<div style="margin-top:8px">{marca}</div>'
            f'<div style="margin-top:6px">{btn}</div></div>')


def _stage_output(r, target):
    """Etapa 3 — la SALIDA: el artefacto por su nombre. Que 'corrio y no dejo nada' se vea."""
    if r["estado"] != "ejecutada":
        return f'<div><span class="art">{E(r["artifact"])}</span>' \
               f'<div class="why">sin artefacto</div></div>'
    n = r["count"]
    cuenta = (f'<div style="margin-top:6px"><b>{n}</b> hallazgos</div>' if n is not None
              else '<div style="margin-top:6px">presente</div>')
    barra = style.sev_bar(r["sev"]) if r["sev"] and any(r["sev"].values()) else ""
    grad = "" if r["graduado"] is not False else \
        '<div class="why">sin graduar: la herramienta no dio severidad, así que un umbral de ' \
        'conteo sobre esto es una cifra inventada</div>'
    return f'<div><a class="art" href="/t/{E(target)}/artifact/{E(r["link"])}">' \
           f'{E(r["link"])}</a>{cuenta}{barra}{grad}</div>'


def _stage_analysis(r, target, _ai=None):
    """Etapa 4 — analizar. DOS acciones, y ninguna decorativa.

    Antes había tres botones: «Ver y juzgar» más «lo analizo yo» / «que lo prepare la IA».
    Los dos últimos solo escribían una marca en un archivo: no abrían nada, no preparaban nada,
    no cambiaban el veredicto. Un botón que no hace lo que su etiqueta promete es peor que no
    tenerlo — invita a pulsarlo y enseña que la interfaz miente.

      · Ver y juzgar  → la pila de hallazgos de ESTA dimensión, a un clic por hallazgo
      · Analizar      → los documentos EN BRUTO que dejó la herramienta, con descarga

    Analizar existe porque el juicio no se puede sostener solo sobre lo que esta interfaz decide
    mostrar. El SARIF resumido aquí lleva 400 caracteres del mensaje; el crudo lleva la traza, el
    fragmento de código y la regla completa. Quien tenga que decidir si algo frena un despliegue
    necesita el documento del fabricante, no mi resumen de él.
    """
    if r["estado"] != "ejecutada":
        return '<div><span class="tool">nada que analizar todavía</span></div>'

    ver = ""
    if r["triage"] and r["count"]:
        ver = (f'<a class="btn primary" href="/t/{E(target)}/findings?tool={E(r["id"])}">'
               f'Ver y juzgar</a>')
    elif not r["triage"]:
        ver = '<span class="tool">sin triaje: es una medida, no una lista de hallazgos</span>'

    analizar = (f'<a class="btn" href="/t/{E(target)}/outputs/{E(r["id"])}">Analizar</a>')
    return f'<div><div class="actions">{ver}{analizar}</div></div>'


def target_page(name: str, tier: int, live: str, blocked: list[tuple[str, str]],
                groups: dict[str, list[tuple[str, str]]], jobs: list, msg: str = "",
                kind: str = "ok", has_report: bool = False,
                pipe: dict | None = None) -> str:
    """La pantalla de proyecto como TUBERIA, no como rejilla de botones de `make`.

    Cuatro columnas, en el orden del diagrama conceptual del que salio este diseño:
    entrada (.env) -> herramientas -> salidas -> analisis. Antes eran tres grupos de botones
    etiquetados code/live/admin: eso describe QUE NECESITAS TRAER, que es util, pero no es el
    proceso. Aqui esa taxonomia baja a nota, y lo que manda es la secuencia.

    Todo se genera del registro: una dimension nueva aparece en las cuatro columnas sin tocar
    este archivo.
    """
    cls, rung_name, rung_help = RUNGS.get(tier, ("r1", "Peldaño ?", ""))
    pipe = pipe or {"rows": [], "resumen": {}}

    blocked_goals: dict[str, str] = {}
    for goals, reason in blocked:
        for g in goals.split(","):
            blocked_goals[g.strip()] = reason

    filas = []
    for r in pipe["rows"]:
        extra = " na" if r["estado"] == "no aplica" else ""
        filas.append(
            f'<div class="dim{extra}" data-estado="{E(r["estado"])}" '
            f'data-prov="{E(r.get("prov", "ok"))}" data-live="{"1" if r["live"] else "0"}">'
            f'{_stage_input(r, name)}'
            f'{_stage_tool(r, name, blocked_goals.get(r["goal"], ""))}'
            f'{_stage_output(r, name)}'
            f'{_stage_analysis(r, name)}'
            '</div>')

    res = pipe["resumen"]
    resumen = (f'<div class="chips">'
               f'<span class="chip">ejecutadas <b>{res.get("ejecutadas",0)}</b></span>'
               f'<span class="chip">NO ejecutadas <b>{res.get("no_ejecutadas",0)}</b></span>'
               f'<span class="chip">no aplican <b>{res.get("no_aplican",0)}</b></span>'
               f'<span class="chip">hallazgos <b>{res.get("hallazgos",0)}</b></span>'
               f'<span class="chip">sin juzgar <b>{res.get("sin_juzgar",0)}</b></span>'
               f'</div>')

    admin = groups.get("admin", [])
    admin_btns = "".join(_action_button(name, g, d, "") for g, d in admin)

    rows_jobs = "".join(
        f'<tr><td><a href="/job/{E(j.id)}">{E(j.goal)}</a></td>'
        f'<td>{E(j.status)}</td>'
        f'<td class="num">{"" if j.exit_code is None else j.exit_code}</td></tr>'
        for j in jobs[:8]
    ) or '<tr><td colspan="3">Sin corridas todavía.</td></tr>'

    report = (f'<a class="btn primary" href="/t/{E(name)}/findings">Explorar hallazgos</a>'
              f'<a class="btn" href="/t/{E(name)}/report">Ver informe</a>'
              if has_report else
              f'<a class="btn primary" href="/t/{E(name)}/findings">Explorar hallazgos</a>'
              '<span class="chip">aún no hay informe — corre algún análisis</span>')

    return page(f"QA-harness · {name}", f"""{flash(msg, kind)}
<h1>{E(name)}</h1>
<p class="sub"><span class="rung {cls}">{E(rung_name)}</span></p>
<div class="note">{E(rung_help)}</div>
{resumen}

<div class="legend">
  <span><span class="st ok">ejecutada</span> hay artefacto</span>
  <span><span class="st norun">NO EJECUTADA</span> se podía correr y no se corrió</span>
  <span><span class="st na">no aplica</span> este perfil no puede medirlo — no es «sin hallazgos»</span>
</div>

<form id="runsel" method="post" action="/t/{E(name)}/run-selected"></form>
<div class="runbar">
  <button class="btn primary" type="submit" form="runsel">Correr las marcadas</button>
  <span class="tool">o marca rápido:</span>
  <button class="btn sel" type="button" data-sel="todas">todas</button>
  <button class="btn sel" type="button" data-sel="ninguna">ninguna</button>
  <button class="btn sel" type="button" data-sel="norun">las NO ejecutadas</button>
  <button class="btn sel" type="button" data-sel="excl">las excluidas</button>
  <button class="btn sel" type="button" data-sel="codigo">solo las de código</button>
</div>
<div class="stage-head">
  <div>1 · entrada<b>qué pide cada herramienta</b></div>
  <div>2 · herramienta<b>estado y coste</b></div>
  <div>3 · salida<b>el artefacto que dejó</b></div>
  <div>4 · análisis<b>juzgar, o leer el original</b></div>
</div>
{''.join(filas)}

<script>
// Selectores rapidos. El que de verdad importa es "las NO ejecutadas": es el que usa el operador
// cuando vuelve tras un arreglo del dev y no quiere repetir la corrida entera — que es justo lo
// que hacia que no la repitiera nadie.
document.querySelectorAll('button.sel').forEach(function(b) {{
  b.addEventListener('click', function() {{
    var q = b.dataset.sel;
    document.querySelectorAll('.dim').forEach(function(d) {{
      var cb = d.querySelector('input[name=dim]');
      if (!cb) return;              // sin casilla = le falta una entrada, no se puede correr
      if (q === 'todas') cb.checked = true;
      else if (q === 'ninguna') cb.checked = false;
      else if (q === 'norun') cb.checked = d.dataset.estado === 'NO EJECUTADA';
      else if (q === 'excl') cb.checked = d.dataset.prov === 'excluida';
      else if (q === 'codigo') cb.checked = d.dataset.live === '0';
    }});
  }});
}});
</script>

<h2>Informe</h2>
<div class="actions">{report}
<a class="btn" href="/t/{E(name)}/config">Configuración</a></div>

<h2>Mantenimiento</h2>
<div class="actions">{admin_btns}</div>

<h2>Últimas corridas</h2>
<table><tr><th>Objetivo</th><th>Estado</th><th class="num">Código</th></tr>{rows_jobs}</table>""",
                "home")


def job_page(job, log: str) -> str:
    done = job.status != "running"
    return page(f"QA-harness · {job.goal}", f"""
<h1>{E(job.goal)} · {E(job.target)}</h1>
<p class="sub">Estado: <b id="st">{E(job.status)}</b>
 · <a href="/t/{E(job.target)}">volver al proyecto</a></p>
<div id="log">{E(log)}</div>
<script>
// Tail the job log over SSE. The job belongs to the Docker daemon, so closing this page or
// restarting the UI does not stop it: reopening simply resumes reading the file.
const box = document.getElementById('log');
box.scrollTop = box.scrollHeight;
if (!{str(done).lower()}) {{
  const es = new EventSource('/job/{E(job.id)}/stream');
  es.onmessage = (e) => {{
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
    box.textContent += e.data + '\\n';
    if (atBottom) box.scrollTop = box.scrollHeight;
  }};
  es.addEventListener('end', (e) => {{
    document.getElementById('st').textContent = e.data.split(':')[0];
    es.close();
  }});
}}
</script>""")


def config_page(name: str, prof, msg: str = "", kind: str = "ok") -> str:
    blocks = []
    for section, fields in prof.sections():
        rows = []
        for f in fields:
            if f.commented:
                continue
            fid = f"f_{f.key}"
            # El asterisco depende de si el campo es imprescindible, NO de si queda texto que
            # añadir: `requirement` calla cuando el perfil ya lo explica, y antes de separarlos
            # los campos obligatorios de una plantilla bien documentada perdían la marca.
            req = (f'<span class="req" title="{E(f.why_required)}">*</span>'
                   if f.required else "")
            help_bits = [f.help] if f.help else []
            if f.hint:
                help_bits.append(f"({f.hint})")
            if f.requirement:
                help_bits.append(f.requirement)
            help_txt = "\n".join(help_bits)
            help_html = f'<span class="help">{E(help_txt)}</span>' if help_txt else ""
            if f.secret:
                ph = "«sin cambios»" if f.value else ""
                inp = (f'<input type="password" id="{fid}" name="{E(f.key)}" value="" '
                       f'placeholder="{ph}" autocomplete="new-password">')
            else:
                inp = f'<input type="text" id="{fid}" name="{E(f.key)}" value="{E(f.value)}">'
            rows.append(f'<label for="{fid}">{E(f.key)} {req}{help_html}{inp}</label>')
        if rows:
            blocks.append(f"<fieldset><legend>{E(section)}</legend>{''.join(rows)}</fieldset>")

    return page(f"QA-harness · {name} · configuración", f"""{flash(msg, kind)}
<h1>Configuración · {E(name)}</h1>
<p class="sub">Este formulario se genera desde <code>targets/{E(name)}/target.env</code>. Al
guardar solo cambia el valor de los campos que edites: comentarios, orden y secciones quedan
intactos.</p>
<div class="note">Los campos marcados con <span class="req">*</span> condicionan qué dimensiones
se pueden medir. Pasa el cursor por encima para ver qué se pierde si faltan. Las contraseñas se
dejan en blanco a propósito: no se devuelven al navegador.</div>
<form method="post">{''.join(blocks)}
<div class="actions"><button class="btn primary" type="submit">Guardar</button>
<a class="btn" href="/t/{E(name)}">Cancelar</a></div></form>""", "home")


def new_page(msg: str = "", kind: str = "err") -> str:
    return page("QA-harness · añadir proyecto", f"""{flash(msg, kind)}
<h1>Añadir proyecto</h1>
<p class="sub">Lo único imprescindible es la ruta a un checkout del código. Todo lo demás se
puede completar después.</p>
<form method="post">
<fieldset><legend>identidad</legend>
<label for="n">Nombre del perfil<span class="help">Minúsculas, sin espacios. Crea
<code>targets/&lt;nombre&gt;/</code>.</span>
<input type="text" id="n" name="name" placeholder="mi_proyecto" required></label>
<label for="s">Ruta al código<span class="help">Ruta ABSOLUTA a un checkout que ya tengas en
esta máquina. No se clona nada y no entra ninguna clave SSH en un contenedor.</span>
<input type="text" id="s" name="src" placeholder="/ruta/al/repositorio" required></label>
</fieldset>
<div class="note"><b>No hace falta desplegar nada todavía.</b> Con el código basta para correr
todo el análisis estático. Cuando quieras medir en vivo, indica en la configuración dónde
responde tu despliegue — el laboratorio le apuntará sin administrarlo.</div>
<div class="actions"><button class="btn primary" type="submit">Crear y analizar el stack</button>
</div></form>""", "new")


def findings_page(name: str, data: dict, msg: str = "") -> str:
    """Juzgar a UN CLIC. Sin listas desplegables, y el hallazgo juzgado desaparece de la pila.

    Lo que sustituye: un `<select>` de tres opciones más un campo de texto, por hallazgo. Para
    juzgar 942 hallazgos eso son ~2.800 interacciones, así que en la práctica nadie juzgaba —
    el laboratorio tenía 941 sin juzgar y el gate seguía contándolos todos.

    Cómo funciona ahora: seis botones por hallazgo. Un clic guarda y RETIRA la fila de la pila.
    Lo retirado se apila por criterio, plegado, y se puede devolver. Lo que queda en pantalla
    es siempre lo que falta por decidir, que es la única cifra que importa mientras se triajea.

    Los criterios y su efecto en el veredicto viven en tools/triage.py, no aquí.
    """
    import triage as tri  # noqa: PLC0415

    findings = data["findings"]
    pendientes = [f for f in findings if not f.get("verdict")]
    juzgados = [f for f in findings if f.get("verdict")]

    # Las dimensiones que NO corrieron, dichas por su nombre. Un explorador de hallazgos que
    # solo muestra lo encontrado hace parecer completo lo que está a medias.
    no_run = [TOOL_LABEL_FALLBACK(t, data) for t, n in data["ran"].items() if n is None]
    aviso = (f'<div class="note"><b>NO EJECUTADO:</b> {E(", ".join(no_run))}. '
             f'Lo que no corrió no aparece aquí, y no verlo no lo vuelve limpio.</div>'
             if no_run else "")

    def botones(key: str) -> str:
        bs = []
        for vid, info in tri.VERDICT_INFO.items():
            exige = " data-exige=\"" + ",".join(info["exige"]) + "\"" if info["exige"] else ""
            bs.append(f'<button class="j j-{E(vid)}" data-k="{E(key)}" data-v="{E(vid)}"'
                      f'{exige} title="{E(info["ayuda"])}">{E(info["label"])}</button>')
        return '<div class="jb">' + "".join(bs) + "</div>"

    def fila(f: dict) -> str:
        loc = f'{E(f["path"])}:{f["line"]}' if f["path"] else ""
        return (f'<div class="row" data-key="{E(f["key"])}" data-sev="{E(f["sev"])}" '
                f'data-tool="{E(f["tool"])}" data-rule="{E(f["rule"])}">'
                f'<div class="top"><span class="sev {E(f["sev"])}">{E(f["sev"].upper())}</span>'
                f'<span class="chip">{E(data["facets"] and f["tool"])}</span>'
                f'<code>{E(f["rule"])}</code></div>'
                f'<div class="loc">{loc}</div>'
                f'<div class="msg">{E(f["msg"])}</div>'
                f'{botones(f["key"])}</div>')

    filas = "".join(fila(f) for f in pendientes)

    # Lo ya archivado, por criterio y plegado: no estorba, pero está.
    cajas = []
    for vid, info in tri.VERDICT_INFO.items():
        grupo = [f for f in juzgados if f.get("verdict") == vid]
        if not grupo:
            continue
        items = "".join(
            f'<li><code>{E(f["rule"])}</code> <span class="loc">{E(f["path"])}</span>'
            f'{" — " + E(f["note"]) if f.get("note") else ""}'
            f' <button class="undo" data-k="{E(f["key"])}">devolver</button></li>'
            for f in grupo[:200])
        cajas.append(f'<details class="arch"><summary><b>{E(info["label"])}</b> '
                     f'<span class="chip">{len(grupo)}</span> '
                     f'<span class="tool">{E(info["ayuda"])}</span></summary>'
                     f'<ul>{items}</ul></details>')

    return page(f"QA-harness · {name} · hallazgos", f"""{flash(msg)}
<h1>Hallazgos · {E(name)}</h1>
<p class="sub">Un clic archiva el hallazgo bajo ese criterio y lo retira de la pila.
Lo que queda en pantalla es lo que falta por decidir.</p>
{aviso}

<div class="chips" id="marcador">
  <span class="chip">pendientes <b id="npend">{len(pendientes)}</b></span>
  <span class="chip">archivados <b id="njuz">{len(juzgados)}</b></span>
  <span class="chip">total {len(findings)}</span>
</div>

<div id="pila">{filas or '<div class="note">Nada pendiente. Todo está juzgado.</div>'}</div>

<h2>Archivados</h2>
{"".join(cajas) or '<div class="note">Todavía no has archivado nada.</div>'}

<script>
// Guarda y retira. `fetch` en vez de recargar: recargar 942 hallazgos por cada clic haria el
// triaje mas lento que el <select> que esto sustituye.
var TARGET = {name!r};
document.getElementById('pila').addEventListener('click', function(e) {{
  var b = e.target.closest('button.j');
  if (!b) return;
  var row = b.closest('.row');
  var exige = (b.dataset.exige || '').split(',').filter(Boolean);
  var extra = {{}};
  // Lo que el criterio EXIGE se pide aqui, no despues. Un «riesgo aceptado» sin quien lo asume
  // ni hasta cuando es «deuda tecnica» con mejor nombre: no caduca y nadie responde por el.
  var textos = {{nota: 'Razon (obligatoria):', dueno: 'Quien lo asume:', hasta: 'Hasta cuando (AAAA-MM-DD):'}};
  for (var i = 0; i < exige.length; i++) {{
    var v = prompt(textos[exige[i]] || exige[i]);
    if (!v) return;                    // cancelar no archiva: no se pierde el juicio a medias
    extra[exige[i] === 'nota' ? 'note' : exige[i]] = v;
  }}
  b.disabled = true;
  fetch('/t/' + TARGET + '/judge', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(Object.assign({{key: row.dataset.key, verdict: b.dataset.v}}, extra))
  }}).then(function(r) {{ return r.json(); }}).then(function(j) {{
    if (!j.ok) {{ b.disabled = false; alert(j.error || 'no se pudo guardar'); return; }}
    row.remove();
    document.getElementById('npend').textContent = j.pendientes;
    document.getElementById('njuz').textContent = j.juzgados;
    if (!document.querySelector('#pila .row'))
      document.getElementById('pila').innerHTML =
        '<div class="note">Nada pendiente. Recarga para ver el archivo actualizado.</div>';
  }}).catch(function() {{ b.disabled = false; }});
}});

// Devolver a la pila. Recarga a proposito: es la accion rara, y asi la pila queda ordenada.
document.addEventListener('click', function(e) {{
  var u = e.target.closest('button.undo');
  if (!u) return;
  fetch('/t/' + TARGET + '/judge', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{key: u.dataset.k, verdict: ''}})
  }}).then(function() {{ location.reload(); }});
}});
</script>""", "home")


def TOOL_LABEL_FALLBACK(tool_id: str, data: dict) -> str:
    """El nombre legible de una herramienta que no corrió; su id si no hay otra cosa."""
    for f in data.get("findings", []):
        if f.get("tool") == tool_id:
            return tool_id
    return tool_id


def detect_page(name: str, output: str) -> str:
    return page(f"QA-harness · {name}", f"""
<h1>Qué se dedujo de {E(name)}</h1>
<p class="sub">Propuesta, no aplicada. Revísala y confírmala: adivinar en silencio es como una
auditoría acaba midiendo lo que no es.</p>
<div id="log">{E(output)}</div>
<div class="actions">
<a class="btn primary" href="/t/{E(name)}/config">Completar configuración</a>
<a class="btn" href="/t/{E(name)}">Ir al proyecto</a></div>""", "new")


def outputs_page(name: str, dim: dict, ficheros: list[dict], msg: str = "") -> str:
    """Los documentos EN BRUTO que dejó una herramienta, para verlos y descargarlos.

    No los renderiza esta interfaz: los enlaza. El resumen que pinta el laboratorio recorta el
    mensaje a 400 caracteres y se queda con una localización por hallazgo; el documento del
    fabricante lleva la traza completa, el fragmento de código y la regla entera. Quien decide si
    algo frena un despliegue tiene que poder leer el original, no mi versión de él.

    Se listan TODOS los ficheros del directorio de la dimensión, no solo el canónico. Un ZAP deja
    tres (SARIF para el gate, HTML para personas, JSON crudo) y esconder dos porque el laboratorio
    solo consume uno sería decidir por el operador qué evidencia le sirve.
    """
    if not ficheros:
        cuerpo = ('<div class="note">Esta dimensión no ha dejado ningún documento todavía. '
                  'Si dice «ejecutada» y aquí no hay nada, el artefacto se perdió por el camino '
                  'y eso es un fallo, no una corrida limpia.</div>')
    else:
        filas = []
        for f in ficheros:
            marca = ('<span class="chip">el que lee el gate</span>' if f["canonico"] else "")
            filas.append(
                f'<tr><td><code>{E(f["rel"])}</code> {marca}</td>'
                f'<td class="num">{E(f["tam"])}</td>'
                f'<td class="num">{E(f["fecha"])}</td>'
                f'<td class="num">'
                f'<a class="btn" href="/t/{E(name)}/artifact/{E(f["rel"])}">ver</a> '
                f'<a class="btn" href="/t/{E(name)}/artifact/{E(f["rel"])}?download=1">descargar</a>'
                f'</td></tr>')
        cuerpo = ('<table><tr><th>Documento</th><th class="num">Tamaño</th>'
                  '<th class="num">Generado</th><th class="num"></th></tr>'
                  + "".join(filas) + "</table>")

    guion = ""
    g = dim.get("guion")
    if g:
        # Con qué se midió, junto a lo medido: un resultado sin su guion no se puede interpretar.
        alcance = f' · <b>{g["n"]}</b> {E(g.get("unidad", ""))}' if g["n"] else ""
        guion = (f'<div class="note">Se midió con <code>{E(g["rel"])}</code> '
                 f'({E(g["estado"])}{alcance}). El guion es el techo de la cobertura: esta '
                 f'herramienta no pudo encontrar nada fuera de lo que ese archivo ejercita.</div>')

    return page(f"QA-harness · {name} · {dim['label']}", f"""{flash(msg)}
<h1>{E(dim["label"])}</h1>
<p class="sub">{E(dim["tool"])} · documentos tal como los dejó la herramienta ·
<a href="/t/{E(name)}">volver a la tubería</a></p>
{guion}
{cuerpo}""", "home")
