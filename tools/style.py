"""Shared look for everything the lab renders: the generated report and the web UI.

They are the same product and must not look like two. Kept as a plain Python string with no
template engine and no CSS build — same reason the rest of the lab has no build step.
"""

# Palette and primitives. Light and dark both first-class: the report gets emailed and opened
# on machines we do not control.
BASE = """
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
table{width:100%;border-collapse:collapse;font-size:14px;background:var(--card);
border:1px solid var(--line);border-radius:9px;overflow:hidden}
th,td{text-align:left;padding:10px 13px;border-bottom:1px solid var(--line)}
th{font-weight:620;font-size:12.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
tr:last-child td{border-bottom:none}
.num{font-variant-numeric:tabular-nums;text-align:right}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 0}
.chip{font-size:12px;padding:3px 9px;border-radius:20px;border:1px solid var(--line);color:var(--muted)}
.chip b{color:var(--fg);font-variant-numeric:tabular-nums}
.note{border-left:3px solid var(--accent);background:var(--card);padding:13px 16px;
border-radius:0 8px 8px 0;font-size:13.5px;color:var(--muted);margin:14px 0}
.note b{color:var(--fg)}
.sev{font-size:10.5px;font-weight:700;padding:2px 6px;border-radius:4px;color:#fff;letter-spacing:.03em}
.sev.critical{background:var(--crit)}.sev.high{background:var(--high)}
.sev.medium{background:var(--med)}.sev.low{background:var(--low)}.sev.unranked{background:var(--unranked)}
a{color:var(--accent)}
footer{margin-top:44px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:12.5px}
"""

# Report-only pieces.
REPORT = """
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
.ran-yes{color:var(--pass);font-weight:600}
.ran-no{color:var(--fail);font-weight:700}
.ran-na{color:var(--muted);font-weight:600}
.sevbar{display:flex;height:9px;border-radius:5px;overflow:hidden;background:var(--line);min-width:130px}
.sevbar i{display:block;height:100%}
.s-critical{background:var(--crit)}.s-high{background:var(--high)}.s-medium{background:var(--med)}
.s-low{background:var(--low)}.s-unranked{background:var(--unranked)}
details{border:1px solid var(--line);border-radius:9px;margin:10px 0;background:var(--card);overflow:hidden}
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
.more{color:var(--muted);font-size:12.5px;padding:9px 0 2px}
.verdictline{font-size:11px;font-weight:700;padding:2px 7px;border-radius:4px;letter-spacing:.03em;
border:1px solid var(--line);color:var(--muted)}
.verdictline.confirmed{background:var(--crit);color:#fff;border-color:transparent}
.verdictline.false-positive{background:var(--pass);color:#fff;border-color:transparent}
.verdictline.inconclusive{background:var(--med);color:#fff;border-color:transparent}
.triage{margin-top:6px;font-size:12.5px;color:var(--fg);background:var(--bg);border:1px dashed var(--line);
padding:7px 10px;border-radius:6px}
"""

# UI-only pieces: navigation, action buttons, live log pane, forms.
UI = """
nav{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);z-index:9;
padding:10px 20px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
nav .brand{font-weight:700;letter-spacing:-.01em}
nav a{color:var(--muted);text-decoration:none;font-size:14px;padding:4px 8px;border-radius:6px}
nav a:hover,nav a.on{color:var(--fg);background:var(--line)}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(260px,1fr))}
.card{border:1px solid var(--line);border-radius:10px;background:var(--card);padding:16px;
box-shadow:var(--shadow)}
.card h3{margin:0 0 6px;font-size:16px;font-weight:620}
.card p{margin:0;color:var(--muted);font-size:13px}
.btn{display:inline-block;font:inherit;font-size:13.5px;font-weight:560;padding:7px 13px;
border-radius:7px;border:1px solid var(--line);background:var(--card);color:var(--fg);
cursor:pointer;text-decoration:none}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary:hover{opacity:.9;color:#fff}
.btn.danger{border-color:var(--fail);color:var(--fail)}
.btn:disabled{opacity:.45;cursor:not-allowed}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 0}
.group{margin:22px 0}
.group>.head{display:flex;align-items:baseline;gap:10px;margin-bottom:4px}
.group>.head b{font-size:15px}
.group>.head span{color:var(--muted);font-size:13px}
.rung{display:inline-block;font-size:11.5px;font-weight:700;padding:3px 9px;border-radius:20px;
background:var(--accent);color:#fff;letter-spacing:.02em}
.rung.r1{background:var(--muted)}.rung.r2{background:var(--pass)}.rung.r3{background:var(--accent)}
.blocked{color:var(--med);font-size:13px;margin:6px 0 0}
#log{background:#0b0e12;color:#d6dde6;font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
padding:14px;border-radius:9px;height:420px;overflow:auto;white-space:pre-wrap;word-break:break-word;
border:1px solid var(--line)}
label{display:block;margin:14px 0 0;font-size:13.5px;font-weight:560}
label .help{display:block;font-weight:400;color:var(--muted);font-size:12.5px;margin:3px 0 5px;
white-space:pre-wrap}
input[type=text],input[type=password],textarea,select{width:100%;font:inherit;font-size:13.5px;
padding:8px 10px;border:1px solid var(--line);border-radius:7px;background:var(--bg);color:var(--fg)}
input:focus,textarea:focus,select:focus{outline:2px solid var(--accent);outline-offset:-1px}
fieldset{border:1px solid var(--line);border-radius:10px;padding:8px 16px 18px;margin:18px 0;
background:var(--card)}
legend{font-size:12.5px;font-weight:700;color:var(--muted);text-transform:uppercase;
letter-spacing:.05em;padding:0 6px}
.req{color:var(--fail);font-weight:700}
.flash{padding:11px 15px;border-radius:8px;border:1px solid var(--line);background:var(--card);
margin:0 0 16px;font-size:13.5px}
.flash.ok{border-left:3px solid var(--pass)}
.flash.err{border-left:3px solid var(--fail)}
"""


def css(*parts: str) -> str:
    """BASE plus whichever slices the page needs."""
    return BASE + "".join(parts)


# Estilos de la vista de TUBERÍA (ui/pipeline.py). Cuatro columnas — entrada, herramienta, salida,
# análisis — para que se lea de izquierda a derecha como el diagrama conceptual, en vez de como una
# rejilla de botones de `make`.
PIPELINE = """
.stage-head{display:grid;grid-template-columns:1.4fr 1.5fr 1.2fr 1.6fr;gap:0;
  border:1px solid var(--line);border-bottom:none;border-radius:10px 10px 0 0;overflow:hidden}
.stage-head>div{padding:10px 14px;background:var(--card);font-size:12px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--muted);border-right:1px solid var(--line)}
.stage-head>div:last-child{border-right:none}
.stage-head b{display:block;color:var(--fg);font-size:13px;letter-spacing:0;text-transform:none}
.dim{display:grid;grid-template-columns:1.4fr 1.5fr 1.2fr 1.6fr;gap:0;
  border:1px solid var(--line);border-top:none}
.dim:last-child{border-radius:0 0 10px 10px}
.dim>div{padding:12px 14px;border-right:1px solid var(--line);min-width:0}
.dim>div:last-child{border-right:none}
.dim.na{opacity:.55}
.dim .name{font-weight:600}
.dim .tool{color:var(--muted);font-size:12px}
.key{display:inline-block;font-family:ui-monospace,monospace;font-size:11px;padding:1px 6px;
  border-radius:4px;background:var(--line);margin:2px 3px 2px 0}
.key.no{background:#7f1d1d;color:#fff}
.key.si{background:#14532d;color:#fff}
.st{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px}
.st.ok{background:#14532d;color:#fff}
.st.norun{background:#7f1d1d;color:#fff}
.st.na{background:var(--line);color:var(--muted)}
.why{font-size:12px;color:var(--muted);margin-top:6px}
.cost{font-size:11px;color:var(--muted);margin-top:6px}
.art{font-family:ui-monospace,monospace;font-size:11px;word-break:break-all}
.who{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
.who button{font-size:11px;padding:4px 9px;border-radius:6px;border:1px solid var(--line);
  background:transparent;color:var(--fg);cursor:pointer}
.who button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.who button:disabled{opacity:.4;cursor:not-allowed}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin:10px 0 18px}
@media(max-width:1100px){.stage-head{display:none}
  .dim{grid-template-columns:1fr;gap:0}
  .dim>div{border-right:none;border-bottom:1px solid var(--line)}}
"""


def sev_bar(sev: dict) -> str:
    """La barra de severidad. Compartida por el informe y por la interfaz a proposito: dos
    implementaciones acabarian pintando proporciones distintas del mismo dato."""
    import html as _h  # noqa: PLC0415
    del _h
    orden = ["critical", "high", "medium", "low", "unranked"]
    total = sum(sev.values()) or 1
    partes = "".join(
        f'<i class="s-{k}" style="width:{sev[k] / total * 100:.1f}%"></i>'
        for k in orden if sev.get(k)
    )
    return f'<div class="sevbar">{partes}</div>'


def sev_chips(sev: dict) -> str:
    orden = ["critical", "high", "medium", "low", "unranked"]
    chips = "".join(
        f'<span class="chip">{k} <b>{sev[k]}</b></span>' for k in orden if sev.get(k)
    )
    return f'<div class="chips">{chips}</div>' if chips else ""


# Triaje a UN CLIC. Sin `select`: seis botones por hallazgo, y el hallazgo juzgado se retira de la
# pila. Los colores no son decoración — separan «frena el despliegue» de «no lo frena» de un
# vistazo, que es la decisión que se está tomando.
TRIAGE = """
.row{border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:10px;
  background:var(--card)}
.row .top{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:4px}
.row .loc{font-family:ui-monospace,monospace;font-size:12px;color:var(--muted)}
.row .msg{font-size:13px;margin:6px 0 10px;white-space:pre-wrap;word-break:break-word}
.jb{display:flex;gap:6px;flex-wrap:wrap}
.jb .j{font-size:12px;padding:6px 11px;border-radius:7px;cursor:pointer;border:1px solid var(--line);
  background:transparent;color:var(--fg);font-weight:600}
.jb .j:hover{filter:brightness(1.25)}
.jb .j:disabled{opacity:.4;cursor:wait}
/* Con `.jb` delante A PROPOSITO: `.jb .j` ya fija background:transparent y tiene DOS clases de
   especificidad, asi que una regla de una sola clase (`.j-bloqueante`) no la pisaba y los seis
   botones salian identicos — justo lo contrario de lo que el color existe para hacer. */
/* Frena el despliegue */
.jb .j-bloqueante{background:#7f1d1d;border-color:#b91c1c;color:#fff}
/* Real, no frena */
.jb .j-corregir{background:#78350f;border-color:#b45309;color:#fff}
/* La herramienta se equivoco */
.jb .j-falso-positivo{background:#14532d;border-color:#15803d;color:#fff}
/* Real y no se persigue: gris a proposito, no es una victoria */
.jb .j-deuda,.jb .j-aceptado,.jb .j-fuera-de-alcance{background:transparent;color:var(--muted)}
details.arch{border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin-bottom:8px;
  background:var(--card)}
details.arch summary{cursor:pointer;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
details.arch ul{margin:10px 0 4px;padding-left:18px}
details.arch li{font-size:12px;margin-bottom:4px}
button.undo{font-size:11px;padding:2px 7px;border-radius:5px;border:1px solid var(--line);
  background:transparent;color:var(--muted);cursor:pointer}
"""


# Barra de ejecución selectiva: la tubería como un CI/CD, no como una lista de botones.
RUNBAR = """
.runbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:14px 0 10px;
  padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--card)}
.runbar .btn.sel{font-size:12px;padding:4px 10px}
.pick{display:inline-flex;gap:6px;align-items:center;font-size:12px;color:var(--muted);
  cursor:pointer;user-select:none}
.pick input{cursor:pointer}
"""


# Barra de ejecución selectiva: la tubería como un CI/CD, no como una lista de botones sueltos.
RUNBAR = """
.runbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:14px 0 10px;
  padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--card)}
.runbar .btn.sel{font-size:12px;padding:4px 10px}
.pick{display:inline-flex;gap:6px;align-items:center;font-size:12px;color:var(--muted);
  cursor:pointer;user-select:none}
.pick input{cursor:pointer;width:15px;height:15px}
"""
