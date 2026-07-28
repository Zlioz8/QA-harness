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
<title>{E(title)}</title><style>{style.css(style.REPORT, style.UI)}</style></head><body>
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


def target_page(name: str, tier: int, live: str, blocked: list[tuple[str, str]],
                groups: dict[str, list[tuple[str, str]]], jobs: list, msg: str = "",
                kind: str = "ok", has_report: bool = False) -> str:
    cls, rung_name, rung_help = RUNGS.get(tier, ("r1", "Peldaño ?", ""))

    blocked_goals: dict[str, str] = {}
    for goals, reason in blocked:
        for g in goals.split(","):
            blocked_goals[g.strip()] = reason

    def group_html(key: str, heading: str, sub: str) -> str:
        items = groups.get(key, [])
        if not items:
            return ""
        btns = "".join(_action_button(name, g, d, blocked_goals.get(g, "")) for g, d in items)
        note = ""
        if key == "live" and blocked_goals:
            reasons = "<br>".join(E(r) for r in dict.fromkeys(blocked_goals.values()))
            note = f'<p class="blocked">{reasons}</p>'
        return f"""<div class="group"><div class="head"><b>{E(heading)}</b>
<span>{E(sub)}</span></div><div class="actions">{btns}</div>{note}</div>"""

    rows = "".join(
        f'<tr><td><a href="/job/{E(j.id)}">{E(j.goal)}</a></td>'
        f'<td>{E(j.status)}</td>'
        f'<td class="num">{"" if j.exit_code is None else j.exit_code}</td></tr>'
        for j in jobs[:12]
    ) or '<tr><td colspan="3">Sin corridas todavía.</td></tr>'

    report = (f'<a class="btn primary" href="/t/{E(name)}/report">Ver informe</a>'
              f'<a class="btn" href="/t/{E(name)}/triage">Triar hallazgos</a>'
              if has_report else
              '<span class="chip">aún no hay informe — corre algún análisis</span>')

    return page(f"QA-harness · {name}", f"""{flash(msg, kind)}
<h1>{E(name)}</h1>
<p class="sub"><span class="rung {cls}">{E(rung_name)}</span></p>
<div class="note">{E(rung_help)}</div>

{group_html("code", "Análisis del código", "no necesita la aplicación corriendo")}
{group_html("live", "Medición en vivo", "necesita la aplicación respondiendo")}
{group_html("admin", "Mantenimiento", "")}

<h2>Informe</h2>
<div class="actions">{report}
<a class="btn" href="/t/{E(name)}/config">Configuración</a></div>

<h2>Últimas corridas</h2>
<table><tr><th>Objetivo</th><th>Estado</th><th class="num">Código</th></tr>{rows}</table>""",
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
            req = f'<span class="req" title="{E(f.requirement)}">*</span>' if f.requirement else ""
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


def triage_page(name: str, blocks: list[dict], counts: dict, msg: str = "") -> str:
    """`blocks` = [{tool, title, findings:[{key, sev, rule, loc, msg, verdict, note}]}]"""
    if not blocks:
        return page(f"QA-harness · {name} · triaje", f"""<h1>Triaje · {E(name)}</h1>
<p class="sub">Todavía no hay hallazgos que juzgar. Corre algún análisis primero.</p>
<a class="btn" href="/t/{E(name)}">Volver</a>""", "home")

    sections = []
    for b in blocks:
        rows = []
        for f in b["findings"]:
            opts = "".join(
                f'<option value="{v}"{" selected" if f["verdict"] == v else ""}>{E(lbl)}</option>'
                for v, lbl in [("", "— sin juzgar —"), ("confirmed", "Confirmado"),
                               ("false-positive", "Falso positivo"),
                               ("inconclusive", "Inconcluso")]
            )
            loc = f'{E(f["loc"])}' + (f':{f["line"]}' if f.get("line") else "")
            rows.append(f"""<div class="f">
<div class="top"><span class="sev {f['sev']}">{f['sev'].upper()}</span>
<span class="rule">{E(f['rule'])}</span></div>
<div class="loc">{loc}</div>
<div class="msg">{E(f['msg'][:240])}</div>
<div style="display:flex;gap:8px;margin-top:7px;flex-wrap:wrap">
<select name="v__{E(f['key'])}" style="max-width:190px">{opts}</select>
<input type="text" name="n__{E(f['key'])}" value="{E(f['note'])}"
 placeholder="Por qué. Ej.: falso positivo, Content-Type fijado en la línea 3"
 style="flex:1;min-width:260px"></div></div>""")
        sections.append(f"""<details open><summary><span>{E(b['title'])}</span>
<span class="chip">{len(b['findings'])}</span></summary>
<div class="body">{''.join(rows)}</div></details>""")

    chips = " ".join(
        f'<span class="chip">{E(lbl)} <b>{counts.get(v, 0)}</b></span>'
        for v, lbl in [("confirmed", "confirmados"), ("false-positive", "falsos positivos"),
                       ("inconclusive", "inconclusos")]
    )
    return page(f"QA-harness · {name} · triaje", f"""{flash(msg)}
<h1>Triaje · {E(name)}</h1>
<p class="sub">Un hallazgo no es un riesgo hasta que alguien decide que lo es.</p>
<div class="note">Lo que escribas aquí queda junto a los artefactos y aparece en el informe. Sin
esto, el razonamiento que convierte una lista de hallazgos crudos en una lista de hallazgos
juzgados se pierde en cuanto quien lo hizo cierra la sesión.</div>
<div class="chips">{chips}</div>
<form method="post">{''.join(sections)}
<div class="actions"><button class="btn primary" type="submit">Guardar triaje</button>
<a class="btn" href="/t/{E(name)}">Volver</a></div></form>""", "home")


def detect_page(name: str, output: str) -> str:
    return page(f"QA-harness · {name}", f"""
<h1>Qué se dedujo de {E(name)}</h1>
<p class="sub">Propuesta, no aplicada. Revísala y confírmala: adivinar en silencio es como una
auditoría acaba midiendo lo que no es.</p>
<div id="log">{E(output)}</div>
<div class="actions">
<a class="btn primary" href="/t/{E(name)}/config">Completar configuración</a>
<a class="btn" href="/t/{E(name)}">Ir al proyecto</a></div>""", "new")
