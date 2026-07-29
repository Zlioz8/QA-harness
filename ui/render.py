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

    # The findings explorer is offered whether or not the report has been built: it reads the
    # artifacts directly, and it is where the raw output actually gets looked at.
    report = (f'<a class="btn primary" href="/t/{E(name)}/findings">Explorar hallazgos</a>'
              f'<a class="btn" href="/t/{E(name)}/report">Ver informe</a>'
              if has_report else
              f'<a class="btn primary" href="/t/{E(name)}/findings">Explorar hallazgos</a>'
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


_FINDINGS_CSS = """
.fx .top{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.fx .seg{display:inline-flex;border:1px solid var(--line);border-radius:7px;overflow:hidden}
.fx .seg button{background:none;border:0;border-right:1px solid var(--line);padding:5px 11px;
 font:inherit;font-size:12px;color:inherit;cursor:pointer}
.fx .seg button:last-child{border-right:0}
.fx .seg button.on{background:var(--accent,#2d6cdf);color:#fff}
.fx .chips-active{display:flex;gap:6px;flex-wrap:wrap;min-height:26px;margin-bottom:10px}
.fx .fchip{display:inline-flex;gap:6px;align-items:center;border:1px solid var(--line);
 border-radius:20px;padding:2px 6px 2px 10px;font-size:12px}
.fx .fchip b{font-weight:600}
.fx .fchip button{background:none;border:0;color:inherit;cursor:pointer;font-size:14px;
 line-height:1;opacity:.6;padding:0 3px}
.fx .g{border:1px solid var(--line);border-radius:9px;margin-bottom:10px;overflow:hidden}
.fx .g>summary{cursor:pointer;padding:9px 12px;display:flex;gap:10px;align-items:center;
 flex-wrap:wrap;list-style:none}
.fx .g>summary::-webkit-details-marker{display:none}
.fx .g>summary .gt{font-family:ui-monospace,monospace;font-size:13px;word-break:break-all}
.fx .g>summary .n{margin-left:auto;opacity:.6;font-variant-numeric:tabular-nums}
.fx .batch{display:flex;gap:6px;padding:0 12px 10px;flex-wrap:wrap;align-items:center;
 font-size:12px}
.fx .batch select,.fx .batch input{font-size:12px;padding:3px 6px}
.fx .rows{padding:0 12px 10px}
.fx .row{border-top:1px solid var(--line);padding:9px 0}
.fx .row.hid,.fx .g.hid{display:none}
.fx .row .hd{display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin-bottom:3px}
.fx .row .loc{font-family:ui-monospace,monospace;font-size:12px;opacity:.85;word-break:break-all}
.fx .row .msg{font-size:13px;opacity:.75;margin:3px 0}
.fx .row .jd{display:flex;gap:8px;margin-top:6px;flex-wrap:wrap}
.fx .row[data-verdict="false-positive"]{opacity:.5}
.fx .f{cursor:pointer;border-bottom:1px dotted transparent}
.fx .f:hover{border-bottom-color:currentColor}
.fx .save{position:sticky;bottom:0;padding:10px 0;background:var(--bg);
 border-top:1px solid var(--line);margin-top:10px;display:flex;gap:8px;align-items:center}
"""

# All state lives in the DOM. No framework, no build step — same reasoning as the rest of the UI.
_FINDINGS_JS = """
(function(){
 var wrap=document.getElementById('fx-groups');
 var rows=[].slice.call(document.querySelectorAll('.fx .row'));
 var filters=[];              // [{field, value}] — AND across fields, OR within a field
 var groupBy='rule';
 var q=document.getElementById('fx-q');
 var LBL={sev:'Severidad',tool:'Herramienta',dir:'Directorio',rule:'Regla',
          verdict:'Triaje',path:'Archivo'};

 function matches(r){
   var by={};
   filters.forEach(function(f){(by[f.field]=by[f.field]||[]).push(f.value);});
   for(var k in by){ if(by[k].indexOf(r.dataset[k])<0) return false; }
   var t=(q.value||'').toLowerCase();
   return !t || r.dataset.hay.indexOf(t)>=0;
 }

 function drawChips(){
   var c=document.getElementById('fx-chips');
   c.innerHTML='';
   filters.forEach(function(f,i){
     var el=document.createElement('span');
     el.className='fchip';
     el.innerHTML='<span>'+(LBL[f.field]||f.field)+': <b></b></span>'+
                  '<button type="button" title="Quitar">&times;</button>';
     el.querySelector('b').textContent=f.value||'(sin juzgar)';
     el.querySelector('button').onclick=function(){filters.splice(i,1);draw();};
     c.appendChild(el);
   });
   document.getElementById('fx-clear').hidden=!filters.length&&!q.value;
 }

 function draw(){
   drawChips();
   var shown=rows.filter(matches);
   // Rebuild the groups from scratch: one code path serves every grouping key, and the rows
   // themselves are moved rather than re-rendered, so the verdict/note a user has already typed
   // into an input survives regrouping.
   wrap.innerHTML='';
   var buckets={},order=[];
   shown.forEach(function(r){
     var k=r.dataset[groupBy]||'(vacío)';
     if(!buckets[k]){buckets[k]=[];order.push(k);}
     buckets[k].push(r);
   });
   order.sort(function(a,b){return buckets[b].length-buckets[a].length;});
   order.forEach(function(k){
     var d=document.createElement('details');
     d.className='g'; d.open=order.length<=6;
     var vs=['','confirmed','false-positive','inconclusive'];
     var ls=['— sin juzgar —','Confirmado','Falso positivo','Inconcluso'];
     var opts=vs.map(function(v,i){return '<option value="'+v+'">'+ls[i]+'</option>';}).join('');
     d.innerHTML='<summary><span class="gt"></span><span class="n">'+buckets[k].length+
       '</span></summary><div class="batch"><span>Juzgar los '+buckets[k].length+
       ' de una vez:</span><select class="bv">'+opts+
       '</select><input class="bn" type="text" placeholder="razón compartida" size="34">'+
       '<button type="button" class="btn ba">Aplicar</button></div><div class="rows"></div>';
     d.querySelector('.gt').textContent=k||'(sin valor)';
     var box=d.querySelector('.rows');
     buckets[k].forEach(function(r){box.appendChild(r);});
     d.querySelector('.ba').onclick=function(){
       var v=d.querySelector('.bv').value, n=d.querySelector('.bn').value;
       buckets[k].forEach(function(r){
         r.querySelector('select.v').value=v;
         if(n) r.querySelector('input.n').value=n;
         r.dataset.verdict=v;
       });
       dirty(); draw();
     };
     wrap.appendChild(d);
   });
   document.getElementById('fx-shown').textContent=shown.length;
   document.getElementById('fx-groups-n').textContent=order.length;
 }

 function dirty(){document.getElementById('fx-dirty').hidden=false;}

 function addFilter(field,value){
   if(!filters.some(function(f){return f.field===field&&f.value===value;}))
     filters.push({field:field,value:value});
   draw();
 }

 // Any value on screen is a filter. This is what replaced the checkbox rail: the facets are
 // wherever the data already is, so there is no second list to keep in sync with the first.
 document.querySelector('.fx').addEventListener('click',function(e){
   var el=e.target.closest('.f');
   if(!el) return;
   e.preventDefault();
   addFilter(el.dataset.field,el.dataset.value);
 });
 [].slice.call(document.querySelectorAll('.seg button')).forEach(function(b){
   b.onclick=function(){
     groupBy=b.dataset.group;
     [].slice.call(document.querySelectorAll('.seg button')).forEach(function(x){
       x.classList.toggle('on',x===b);});
     draw();
   };
 });
 document.getElementById('fx-clear').onclick=function(){filters=[];q.value='';draw();};
 q.addEventListener('input',draw);
 document.querySelector('.fx').addEventListener('change',function(e){
   if(e.target.matches('select.v')){e.target.closest('.row').dataset.verdict=e.target.value;
     dirty();draw();}
   else if(e.target.matches('input.n')) dirty();
 });
 draw();
})();
"""


def findings_page(name: str, data: dict, msg: str = "") -> str:
    """Every tool's findings in one place: grouped, filtered by clicking, judged in batches.

    No checkbox rail. Grouping answers "what am I looking at" (13 hits of one rule are one
    decision, not thirteen), and every value on screen doubles as a filter, so the facets live
    where the data is instead of in a second list beside it. `data` comes from findings.collect().
    """
    from findings import SEV_LABEL, TOOL_LABEL, VERDICT_LABEL  # noqa: PLC0415

    if not data["findings"]:
        pend = [TOOL_LABEL.get(t, t) for t, n in data["ran"].items() if n is None]
        why = ("Ninguna herramienta ha corrido todavía." if len(pend) == len(data["ran"])
               else "Las herramientas que corrieron no encontraron nada.")
        return page(f"QA-harness · {name} · hallazgos", f"""<h1>Hallazgos · {E(name)}</h1>
<p class="sub">{E(why)}</p>
<div class="note">Que una herramienta no encuentre nada y que no se haya ejecutado son cosas
distintas. Sin ejecutar: {E(', '.join(pend) or 'ninguna')}.</div>
<a class="btn" href="/t/{E(name)}">Volver</a>""", "home")

    def f(field: str, value: str, text: str, cls: str = "") -> str:
        """A value that is also a filter."""
        return (f'<span class="f {cls}" data-field="{field}" data-value="{E(value)}">'
                f'{E(text)}</span>')

    rows = []
    for it in data["findings"]:
        opts = "".join(
            f'<option value="{v}"{" selected" if it["verdict"] == v else ""}>{E(lbl)}</option>'
            for v, lbl in VERDICT_LABEL.items())
        line = f':{it["line"]}' if it.get("line") else ""
        hay = " ".join([it["rule"], it["path"], it.get("msg", ""), it.get("name", "")]).lower()
        rows.append(f"""<div class="row" data-sev="{it['sev']}" data-tool="{E(it['tool'])}"
 data-verdict="{E(it['verdict'])}" data-rule="{E(it['rule'])}" data-dir="{E(it['dir'])}"
 data-path="{E(it['path'])}" data-hay="{E(hay)}">
<div class="hd">{f('sev', it['sev'], SEV_LABEL.get(it['sev'], it['sev']), 'sev ' + it['sev'])}
{f('tool', it['tool'], TOOL_LABEL.get(it['tool'], it['tool']), 'chip')}
{f('rule', it['rule'], it['rule'], 'rule')}</div>
<div class="loc">{f('path', it['path'], it['path'] + line)}</div>
<div class="msg">{E((it.get('msg') or '')[:260])}</div>
<div class="jd"><select class="v" name="v__{E(it['key'])}" style="max-width:180px">{opts}</select>
<input class="n" type="text" name="n__{E(it['key'])}" value="{E(it['note'])}"
 placeholder="Por qué. Ej.: sólo aparece en docs/, no es una credencial viva"
 style="flex:1;min-width:230px"></div></div>""")

    not_run = [TOOL_LABEL.get(t, t) for t, n in data["ran"].items() if n is None]
    banner = (f'<div class="note"><b>NO EJECUTADO:</b> {E(", ".join(not_run))}. '
              'Lo que no corrió no aparece aquí, y no verlo no lo vuelve limpio.</div>'
              if not_run else "")

    def seg(g: str, lbl: str) -> str:
        on = ' class="on"' if g == "rule" else ""
        return f'<button type="button" data-group="{g}"{on}>{E(lbl)}</button>'

    segs = "".join(seg(g, lbl) for g, lbl in
                   [("rule", "Regla"), ("path", "Archivo"), ("dir", "Directorio"),
                    ("sev", "Severidad"), ("tool", "Herramienta"), ("verdict", "Triaje")])

    return page(f"QA-harness · {name} · hallazgos", f"""{flash(msg)}
<h1>Hallazgos · {E(name)}</h1>
<p class="sub">Todo lo que produjo cada herramienta, en una sola lista. Haz clic en cualquier
valor para filtrar por él. Los artefactos originales no se tocan: filtrar es una forma de mirar,
nunca de editar.</p>
{banner}
<style>{_FINDINGS_CSS}</style>
<form method="post" class="fx">
 <div class="top">
  <span>Agrupar por:</span><span class="seg">{segs}</span>
  <input type="search" id="fx-q" placeholder="Buscar…" style="flex:1;min-width:170px">
  <button type="button" id="fx-clear" class="btn" hidden>Quitar filtros</button>
 </div>
 <div class="chips-active" id="fx-chips"></div>
 <div class="top">
  <span>Mostrando <b id="fx-shown">{data['total']}</b> de <b>{data['total']}</b> hallazgos en
   bruto, en <b id="fx-groups-n">0</b> grupos</span>
  <span class="chip">confirmados {data['judged'].get('confirmed', 0)}</span>
  <span class="chip">falsos positivos {data['judged'].get('false-positive', 0)}</span>
  <span class="chip">inconclusos {data['judged'].get('inconclusive', 0)}</span>
 </div>
 <div id="fx-groups"></div>
 <div class="save">
  <button class="btn primary" type="submit">Guardar triaje y regenerar informe</button>
  <span id="fx-dirty" hidden class="chip">cambios sin guardar</span>
  <a class="btn" href="/t/{E(name)}">Volver</a>
 </div>
 <div hidden id="fx-src">{''.join(rows)}</div>
</form>
<script>{_FINDINGS_JS}</script>""", "home")


def detect_page(name: str, output: str) -> str:
    return page(f"QA-harness · {name}", f"""
<h1>Qué se dedujo de {E(name)}</h1>
<p class="sub">Propuesta, no aplicada. Revísala y confírmala: adivinar en silencio es como una
auditoría acaba midiendo lo que no es.</p>
<div id="log">{E(output)}</div>
<div class="actions">
<a class="btn primary" href="/t/{E(name)}/config">Completar configuración</a>
<a class="btn" href="/t/{E(name)}">Ir al proyecto</a></div>""", "new")
