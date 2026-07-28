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
