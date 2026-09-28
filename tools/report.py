#!/usr/bin/env python3
"""Genera INFORME_TECNICO_VERIFICACION_R<n>_<PROYECTO>.md con la estructura madura de la fábrica.

EL FORMATO NO SE INVENTA AQUÍ. Sale de la serie R3–R10 de Costos Web, que es donde se decantó:

    cabecera        dirigido a · proyecto · rama y commit · componentes · herramientas · fecha
    Alcance         se ejecutó / NO se ejecutó / NO disponible
    Reproducibilidad
    §1  Resumen para el responsable            veredicto en prosa + LA TABLA MAESTRA
    §2  Verificado en esta ronda (sin acción)  ✅ lo que está bien, con su responsable
    §3  Hallazgos                              §3.n con emoji de severidad
    §4  Cobertura real de esta ronda           dimensión · herramienta · corrió · resultado
    §5  Observaciones sobre la herramienta     SOLO las que cambian cómo se lee esta ronda
    §6  Orden recomendado de ejecución
    §7  Reproducción

La tabla maestra de §1 es la pieza central: `# | Hallazgo | Severidad | Estado | Responsable |
Esfuerzo`, donde `#` es el §3.n. Permite priorizar sin leer el informe entero, y es lo que hace
que «seguimos con §3.20» siga significando algo tres rondas después.

DÓNDE VIVE LA PROSA. Lo mecánico —cobertura, conteos, identidades, antigüedad, diff entre rondas,
veredicto— lo compone este archivo. El juicio —qué está pasando, por qué es un riesgo AQUÍ, cómo
se remedia, cómo se verifica— lo escribe una persona en `targets/<t>/hallazgos/<ID>.md`, que se
versiona junto al perfil y sobrevive a las rondas. Un hallazgo confirmado sin ese archivo sale
marcado con ⟨FALTA⟩, no en silencio: un informe con huecos visibles es honesto; uno que los
rellena con generalidades, no.

Uso:  tools/report.py <target> [--ronda-nueva] [--pendientes]
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime

LAB = os.environ.get("LAB_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(LAB, "tools"))
sys.path.insert(0, os.path.join(LAB, "ui"))

import dimensions           # noqa: E402
import hallazgos as reg     # noqa: E402
import triage as triagelib  # noqa: E402
import findings as findlib  # noqa: E402

FALTA = "⟨FALTA: {}⟩"

SEV = {"critical": ("🔴", "Crítico"), "high": ("🟠", "Alto"), "medium": ("🟡", "Medio"),
       "low": ("🔵", "Bajo"), "unranked": ("⚪", "Sin graduar")}
ORDEN = ["critical", "high", "medium", "low", "unranked"]


def clave_orden(f: dict) -> tuple:
    """Severidad primero, y dentro de ella por §3.n numérico.

    Ordenar por `id` dentro de la severidad mezclaba H1, H2, I1, I2… y descolocaba la
    numeración §3.n, que es justo lo que el lector usa para navegar y para citar.
    """
    sub = (f.get("sub") or "").strip()
    partes = tuple(int(x) for x in sub.split(".") if x.isdigit()) if sub else (999,)
    return (ORDEN.index(f.get("severidad", "unranked")), partes, f.get("id", ""))

_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_es() -> str:
    """Fecha en español sin depender del locale: LC_TIME no siempre acompaña a LC_MESSAGES."""
    h = datetime.now()
    return f"{h.day} de {_MESES[h.month - 1]} de {h.year}"


def sh(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, cwd=LAB, capture_output=True, text=True,
                              timeout=90).stdout.strip()
    except Exception:
        return ""


def envget(target: str, key: str) -> str:
    base = os.path.join(LAB, "targets", target, "target.env")
    for path in (base + ".local", base):
        if not os.path.exists(path):
            continue
        val = ""
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith(key + "="):
                    val = line.split("=", 1)[1].split(" #")[0].strip().strip('"')
        if val:
            return val
    return ""


# ---------------------------------------------------------------- prosa por hallazgo

SECCIONES = ["que_pasa", "por_que", "remediacion", "verificacion"]
TITULOS = {"que_pasa": "Qué está pasando", "por_que": "Por qué es un riesgo",
           "remediacion": "Recomendación de remediación", "verificacion": "Verificación"}


def prosa(target: str, hid: str) -> dict:
    """`targets/<t>/hallazgos/<ID>.md`: el juicio humano, versionado junto al perfil."""
    p = os.path.join(LAB, "targets", target, "hallazgos", f"{hid}.md")
    out: dict[str, str] = {}
    if not os.path.exists(p):
        return out
    actual = None
    for linea in open(p, encoding="utf-8"):
        m = re.match(r"^##\s+(.+?)\s*$", linea)
        if m:
            t = m.group(1).lower()
            actual = next((k for k, v in TITULOS.items() if v.lower() in t), None)
            if actual:
                out[actual] = ""
            continue
        if actual is not None:
            out[actual] = out.get(actual, "") + linea
    return {k: v.strip() for k, v in out.items() if v.strip()}


def fragmento(target: str, nombre: str) -> str:
    p = os.path.join(LAB, "targets", target, "hallazgos", nombre)
    return open(p, encoding="utf-8").read().strip() if os.path.exists(p) else ""


# ---------------------------------------------------------------- cobertura

def cobertura(target: str, rep: str) -> list[dict]:
    filas = []
    no_aplica = {x.strip() for x in (envget(target, "GUION_NO_APLICA") or "").split(",") if x.strip()}
    for d in dimensions.load():
        art = getattr(d, "artifact", "") or ""
        if not art:
            continue
        p = os.path.join(rep, art)
        hay = os.path.exists(p) and os.path.getsize(p) > 0
        inputs = (getattr(d, "inputs", "") or "").split(",")
        faltan = [i.strip() for i in inputs
                  if i.strip() and not any(envget(target, k.strip()) for k in i.split("|"))]
        if hay:
            estado, razon = "✅", ""
        elif d.id in no_aplica:
            estado, razon = "⛔ NO APLICABLE", "declarado no aplicable en el perfil"
        elif faltan:
            estado, razon = "⛔ NO DISPONIBLE", f"falta `{', '.join(faltan)}`"
        else:
            estado, razon = "⛔ **NO EJECUTADO**", "podía medirse y no se hizo"
        filas.append({"id": d.id, "label": getattr(d, "label", d.id),
                      "tool": getattr(d, "tool", "") or d.id,
                      "estado": estado, "razon": razon, "faltan": faltan})
    return filas


def _repos_bajo(src: str) -> list[str]:
    """Repos git bajo SRC_PATH: el propio SRC_PATH, o sus hijos de un nivel. Una sola regla,
    la misma que tools/lib-repos.sh, para que la cabecera del informe no mienta sobre qué se
    auditó cuando SRC_PATH es un directorio padre."""
    if not src or not os.path.isdir(src):
        return []
    if os.path.isdir(os.path.join(src, ".git")):
        return [src]
    hijos = []
    for n in sorted(os.listdir(src)):
        d = os.path.join(src, n)
        if os.path.isdir(os.path.join(d, ".git")):
            hijos.append(d)
    return hijos


# ---------------------------------------------------------------- bloques

def cabecera(target: str, ronda: int, src: str, cob: list[dict]) -> str:
    # El commit se lee de los REPOSITORIOS bajo SRC_PATH, no del directorio que los contiene.
    # SRC_PATH apunta al padre en un proyecto multi-repo (contrato del perfil), y `git -C <padre>`
    # falla ahí: la cabecera decía "(sin checkout git)" sobre un proyecto perfectamente versionado
    # — el mismo agujero que ya se tapó en tools/stamp.sh. `_repos_bajo` replica la única regla de
    # descubrimiento (tools/lib-repos.sh) en Python, sin dependencias nuevas.
    repos = _repos_bajo(src)
    if len(repos) == 1:
        commit = sh(["git", "-C", repos[0], "log", "-1", "--format=%h — «%s»"]) or "(sin checkout git)"
        rama = sh(["git", "-C", repos[0], "rev-parse", "--abbrev-ref", "HEAD"]) or "-"
    elif len(repos) > 1:
        # Varios repos: se nombran todos. Un commit único cuando se auditaron dos árboles miente.
        partes = []
        for r in repos:
            h = sh(["git", "-C", r, "rev-parse", "--short", "HEAD"]) or "?"
            partes.append(f"{os.path.basename(r)}@{h}")
        commit = " · ".join(partes)
        rama = ", ".join(sorted({sh(["git", "-C", r, "rev-parse", "--abbrev-ref", "HEAD"]) or "-" for r in repos}))
    else:
        commit = "(sin checkout git)"
        rama = "-"
    ejec = [c for c in cob if c["estado"] == "✅"]
    noej = [c for c in cob if "NO EJECUTADO" in c["estado"]]
    nodis = [c for c in cob if "NO DISPONIBLE" in c["estado"] or "NO APLICABLE" in c["estado"]]
    subt = envget(target, "INFORME_SUBTITULO") or FALTA.format(
        "la pregunta concreta que responde esta ronda — INFORME_SUBTITULO en target.env")

    out = [f"""# Informe Técnico — Verificación {ronda}.ª Ronda (R{ronda}) · {target.upper()}
## {subt}

**Dirigido a:** responsables de implementación (Backend · Frontend · DevOps/Infra · Líder Técnico).
**Proyecto:** `{envget(target, 'REPO_URL') or '(repositorio no declarado en el perfil)'}`
**Rama y commit auditados:** `{rama}` @ `{commit}`
**Componentes:** {envget(target, 'LANGS') or FALTA.format('stack, una línea')}
**Herramientas:** SECURITY-LAB — {', '.join(c['tool'] for c in ejec) or 'ninguna'}; más `make gate` y `make run-manifest`.
**Entorno de verificación:** {envget(target, 'BASE_URL') or FALTA.format('dónde se midió')}
**Envelope declarado:** cpus={envget(target, 'PERF_CPUS') or '?'} · memoria={envget(target, 'PERF_MEM') or '?'} — las cifras de carga solo son comparables contra estos límites.
**Fecha:** {fecha_es()}.

**Alcance.**
"""]
    out.append(f"- **Se ejecutó:** {', '.join(c['label'] for c in ejec) or 'nada'}.\n")
    if noej:
        out.append("- **NO se ejecutó** (podía medirse y no se hizo): "
                   + ", ".join(c["label"] for c in noej) + ".\n")
    if nodis:
        out.append("- **NO DISPONIBLE / NO APLICABLE:** "
                   + ", ".join(f"{c['label']} — {c['razon']}" for c in nodis) + ".\n")
    out.append("\n> `NO EJECUTADO` no es `sin hallazgos`, y `NO DISPONIBLE` tampoco: lo primero es\n"
               "> cobertura que se dejó de tomar; lo segundo, cobertura que aún no existe porque\n"
               "> falta un insumo. Ninguno de los dos es un aprobado. Detalle en §4.\n")
    out.append(f"""
**Reproducibilidad:**
```bash
cd SECURITY-LAB/
make ingest-deploy TARGET={target}
make static        TARGET={target}
make live          TARGET={target}
make gate run-manifest informe TARGET={target}
```

---

""")
    return "".join(out)


def resumen(target: str, conf: list[dict], cerrados: list[dict], ronda: int, veredicto: str) -> str:
    conf = sorted(conf, key=clave_orden)
    intro = fragmento(target, "resumen.md")

    out = ["## 1. Resumen para el responsable\n\n"]
    out.append((intro if intro else FALTA.format(
        "dos o tres párrafos: en qué estado está el proyecto y por qué, en lenguaje llano — "
        f"escríbelo en targets/{target}/hallazgos/resumen.md")) + "\n\n")

    out.append("| # | Hallazgo | Severidad | Estado | Responsable | Esfuerzo |\n")
    out.append("|---|----------|-----------|--------|-------------|----------|\n")
    for f in conf:
        emoji, nombre = SEV.get(f.get("severidad", "unranked"), ("⚪", "?"))
        ant = reg.antiguedad(f, ronda)
        if f.get("estado") == "reabierto":
            estado = "**Reabierto**"
        elif ant == 0:
            estado = "Nuevo"
        else:
            estado = f"Abierto (desde R{f['abierto_en']} · {ant} ronda(s))"
        out.append(f"| {f.get('sub') or f['id']} | {f['titulo']} | {emoji} {nombre} | {estado} "
                   f"| {f.get('responsable') or FALTA.format('quién')} "
                   f"| {f.get('esfuerzo') or FALTA.format('bajo/medio/alto')} |\n")
    for f in cerrados:
        out.append(f"| — | {f['titulo']} | ✅ | **Cerrado en R{ronda}** (abierto en "
                   f"R{f['abierto_en']}) | {f.get('responsable') or '—'} | — |\n")
    if not conf and not cerrados:
        out.append("| — | Ningún hallazgo confirmado todavía | ⚪ | — | — | — |\n")

    out.append(f"\n**Veredicto de la compuerta (`make gate`): {veredicto}**\n\n---\n\n")
    return "".join(out)


def verificado(target: str) -> str:
    """§2 — lo que está BIEN, con su responsable.

    No es cortesía: un informe que solo enumera lo que falta se lee como una queja y deja de ser
    un canal. Y sin esta sección no hay forma de notar que algo que estaba bien dejó de estarlo.
    """
    cuerpo = fragmento(target, "verificado.md")
    return ("## 2. Verificado en esta ronda (sin acción)\n\n"
            + (cuerpo if cuerpo else FALTA.format(
                "qué se comprobó y salió BIEN, con su responsable — "
                f"targets/{target}/hallazgos/verificado.md"))
            + "\n\n---\n\n")


def detalle(target: str, conf: list[dict], ronda: int, sin_triar: list[dict],
            aparte: list[dict] | None = None) -> str:
    conf = sorted(conf, key=clave_orden)
    aparte = aparte or []
    out = ["## 3. Hallazgos\n\n"]
    if not conf:
        out.append("Ninguno confirmado en esta ronda. Conviene leer §4 antes de celebrarlo: "
                   "un informe sin hallazgos sobre dimensiones que no se ejecutaron no dice nada.\n\n")

    for f in conf:
        emoji, nombre = SEV.get(f.get("severidad", "unranked"), ("⚪", "?"))
        num = f.get("sub") or f["id"]
        ant = reg.antiguedad(f, ronda)
        estado = "Nuevo" if ant == 0 else f"Abierto desde R{f['abierto_en']}"
        out.append(f"### {num} {emoji} {f['titulo']}\n\n")
        out.append(f"**Estado:** {estado} · **Severidad:** {nombre} · "
                   f"**Responsable:** {f.get('responsable') or FALTA.format('quién')} · "
                   f"**Esfuerzo:** {f.get('esfuerzo') or FALTA.format('bajo/medio/alto')}\n\n")
        if ant >= 3:
            out.append(f"> Lleva **{ant} rondas** abierto. A partir de aquí deja de ser un problema "
                       "técnico y pasa a ser uno de priorización: conviene decidir explícitamente si "
                       "se corrige o se acepta como riesgo, con nombre y fecha.\n\n")
        txt = prosa(target, f["id"])
        for k in SECCIONES:
            if txt.get(k):
                out.append(f"**{TITULOS[k]}.**\n\n{txt[k]}\n\n")
            else:
                out.append(f"**{TITULOS[k]}.** "
                           + FALTA.format(f"targets/{target}/hallazgos/{f['id']}.md") + "\n\n")
        # Enlace a la ficha de FUNDAMENTACIÓN del riesgo (make riesgos): dónde/cómo/medios +
        # OWASP/MITRE/STRIDE/CVSS/ISO 27001. Es la mitad probatoria y formativa del hallazgo.
        ficha = os.path.join(LAB, "targets", target, "riesgos", f"{f['id']}.md")
        if os.path.exists(ficha):
            out.append(f"**Fundamentación (marcos + prueba de tangibilidad):** "
                       f"`targets/{target}/riesgos/{f['id']}.md` — clasificado en OWASP, MITRE/CWE, "
                       f"STRIDE, CVSS e ISO/IEC 27001.\n\n")

    if sin_triar:
        # ANÁLISIS antes que la tabla. Una tabla de reglas con ocurrencias es el vertido de la
        # herramienta, no un informe: no deduce nada. Si el analista escribió
        # `hallazgos/analisis-senal.md`, ESE es el mensaje de §3.x —qué dice la señal en conjunto,
        # qué patrón, qué priorizar— y el desglose por regla queda plegado como respaldo. Sin él,
        # se cae al texto genérico de siempre.
        analisis = fragmento(target, "analisis-senal.md")
        if analisis:
            out.append(f"### 3.x Señal sin triar ({len(sin_triar)}) — análisis\n\n{analisis}\n\n"
                       "<details><summary>Desglose por regla (respaldo de la señal)</summary>\n\n"
                       "| Dimensión | Regla | Ocurrencias | Severidad |\n|---|---|---|---|\n")
        else:
            out.append(f"### 3.x Señal sin triar ({len(sin_triar)})\n\n"
                   "Producida por las herramientas y **todavía sin juicio humano**. No se detalla "
                   "arriba porque una lista sin triar no es un informe: buena parte de la señal de un "
                   "escáner es ruido en su contexto, y decidir cuál lo es resulta trabajo de una "
                   "persona. Se agrupa por regla para poder despacharla en bloque.\n\n"
                   "| Dimensión | Regla | Ocurrencias | Severidad |\n|---|---|---|---|\n")
        grupos: dict[tuple, list] = {}
        for f in sin_triar:
            grupos.setdefault((f.get("dimension", ""), f["titulo"]), []).append(f)
        for (dim, tit), fs in sorted(grupos.items(), key=lambda kv: -len(kv[1])):
            emoji, nombre = SEV.get(fs[0].get("severidad", "unranked"), ("⚪", "?"))
            out.append(f"| {dim} | `{tit}` | {len(fs)} | {emoji} {nombre} |\n")
        out.append("</details>\n\n" if analisis else "\n")

    if aparte:
        out.append(f"### 3.y Juzgados sin acción en esta ronda ({len(aparte)})\n\n"
                   "Una persona los leyó y decidió no perseguirlos ahora: riesgo **aceptado** (con quién lo "
                   "asume y hasta cuándo), **deuda técnica** (real, no prioritaria) o **fuera de alcance** (es de "
                   "otro equipo, y se dice de cuál). No suman al veredicto; un aceptado vencido vuelve a contar.\n\n"
                   "| # | Hallazgo | Veredicto | Razón | Quién | Hasta |\n|---|---|---|---|---|---|\n")
        for f in sorted(aparte, key=lambda x: (x.get("_juicio", {}).get("verdict", ""), x["id"])):
            j = f.get("_juicio", {})
            out.append(f"| {f['id']} | `{f['titulo']}` | {triagelib.LABELS.get(j.get('verdict', ''), j.get('verdict', ''))} | "
                       f"{j.get('note', '')} | {j.get('dueno', '') or '—'} | {j.get('hasta', '') or '—'} |\n")
        out.append("\n")

    out.append("---\n\n")
    return "".join(out)


def cobertura_tabla(target: str, cob: list[dict], conf: list[dict],
                    sin_triar: list[dict]) -> str:
    por_dim: dict[str, list[str]] = {}
    for f in conf:
        por_dim.setdefault(f.get("dimension", ""), []).append(f.get("sub") or f["id"])
    crudo: dict[str, int] = {}
    for f in sin_triar:
        crudo[f.get("dimension", "")] = crudo.get(f.get("dimension", ""), 0) + 1
    no_autoritativas = {}
    for par in (envget(target, "DIMENSION_NO_AUTORITATIVA") or "").split(";"):
        if ":" in par:
            k, _, v = par.partition(":")
            no_autoritativas[k.strip()] = v.strip()
    out = ["## 4. Cobertura real de esta ronda\n\n",
           "| Dimensión | Herramienta | Corrió | Resultado |\n|---|---|---|---|\n"]
    for c in cob:
        refs = por_dim.get(c["id"], [])
        if c["estado"] == "✅":
            # Tres estados distintos, y confundirlos es lo que hace que un informe mienta:
            # hallazgos confirmados · señal producida pero SIN JUZGAR · nada encontrado.
            # «sin hallazgos confirmados» junto a un ✅ se lee como «limpio», y sobre una
            # dimensión con 307 incidencias sin triar eso es sencillamente falso.
            partes = []
            if refs:
                partes.append("→ " + ", ".join(("§" + r) if r[0].isdigit() else r
                                               for r in refs[:8]))
            n = crudo.get(c["id"], 0)
            if n:
                partes.append(f"**{n} sin triar** → §3.x")
            res = " · ".join(partes) if partes else "sin hallazgos"
            # NO AUTORITATIVA: la dimensión corrió, pero sobre algo que no describe al sistema
            # —un manifiesto reconstruido por el laboratorio, un esquema deducido, una semilla
            # sintética—. Es el caso más peligroso de todos, porque produce un cero con un ✅
            # al lado. Se declara en el perfil y se dice AQUÍ, en la casilla que el lector mira.
            if c["id"] in no_autoritativas:
                res = f"⚠️ **NO AUTORITATIVA** — {no_autoritativas[c['id']]}" + (
                    f" ({res})" if res != "sin hallazgos" else " · el 0 NO significa limpio")
        else:
            res = c["razon"]
        out.append(f"| {c['label']} | {c['tool']} | {c['estado']} | {res} |\n")
    out.append("\n> Una dimensión NO DISPONIBLE se cierra entregando su insumo; una NO EJECUTADA, "
               "ejecutándola. Ninguna de las dos es un aprobado.\n\n---\n\n")
    return "".join(out)


def observaciones(target: str) -> str:
    """§5 — solo lo que cambia CÓMO SE LEE esta ronda.

    R7 de Costos Web fija el criterio en su primera línea: «se registran porque afectan a cómo debe
    leerse esta ronda». Eso NO es la lista de tareas de QA sobre su propio instrumental —eso vive en
    la bitácora interna—: aquí entra únicamente lo que altera la interpretación de una cifra que el
    lector tiene delante. Un umbral que coincidía con un tope de exportación, un artefacto de otra
    corrida contado como propio, una dimensión que no pudo completarse.
    """
    cuerpo = fragmento(target, "observaciones.md")
    if not cuerpo:
        return ""
    return ("## 5. Observaciones sobre la herramienta (SECURITY-LAB) — "
            "Responsable: Líder Técnico / QA\n\n"
            "Se registran porque **afectan a cómo debe leerse esta ronda**.\n\n"
            + cuerpo + "\n\n---\n\n")


def cierre(target: str) -> str:
    orden = fragmento(target, "orden.md") or FALTA.format(
        f"agrupar por responsable — targets/{target}/hallazgos/orden.md")
    # Rastro de validación por navegador (MCP), si existe: red, consola y sesión de cada paso,
    # con un índice cronológico y un documento que enlaza cada aserción con su prueba observada.
    ev = os.path.join(LAB, "reports", target, "mcp-evidencia")
    evidencia_mcp = ""
    if os.path.isdir(ev) and os.listdir(ev):
        evidencia_mcp = (f"\n\nValidación por flujo (navegador MCP): `reports/{target}/mcp-evidencia/` "
                         f"— red, consola y sesión de cada paso, con `VALIDACION_R2_POR_FLUJO.md` "
                         f"correlacionando cada hallazgo observable con lo medido en vivo.")
    return f"""## 6. Orden recomendado de ejecución

{orden}

---

## 7. Reproducción

```bash
cd SECURITY-LAB/
make siguiente TARGET={target}      # dónde está el proyecto y qué toca ahora
make guiones   TARGET={target}      # ¿cada herramienta aplicada a ESTE proyecto?
make ingest-deploy static live TARGET={target}
make gate run-manifest informe TARGET={target}
```

Artefactos: `reports/{target}/` — uno por dimensión, más `.provenance/` con contra qué midió cada una.{evidencia_mcp}

---

## 8. Lo que ninguna herramienta de aquí cubre

- **La política de autorización.** Un 200 solo es hallazgo si la política decía 403, y esa política
  la escribe una persona en `playwright/authz-matrix.json`.
- **La auditoría sin oráculo.** Que un login «se registró» solo lo dice la tabla de auditoría, no la
  respuesta 200: sin `AAA_DB_URL` en `target.env.local`, nadie lo afirma.
- **El abuso de lógica de negocio.** Esos guiones se escriben después de leer el código.
- **La severidad en contexto institucional** (datos personales, procesos regulados).
- **Distinguir un fallo del proyecto de uno del entorno.** Si una dimensión no corrió por falta de
  memoria, eso no dice nada sobre el proyecto.
"""


# ---------------------------------------------------------------- STRIDE y AAA
#
# Dos secciones SEPARADAS, porque son dos preguntas: el modelo de amenazas dice qué puede pasar
# (seis letras); los controles AAA dicen qué hace el sistema con la identidad (tres pilares). El
# único cruce es una columna de la tabla STRIDE con los controles medidos por letra. Cada función
# devuelve "" si su artefacto no existe: un perfil sin estas dimensiones produce el mismo informe
# de siempre.

_STRIDE_RE = {
    "S": r"spoofing|suplantaci",
    "T": r"tampering|manipulaci",
    "R": r"repudiation|repudio",
    "I": r"information[ -]disclosure|revelaci|divulgaci",
    "D": r"denial[ -]of[ -]service|denegaci",
    "E": r"elevation[ -]of[ -]privilege|elevaci",
}
_STRIDE_NOMBRE = {"S": "Spoofing", "T": "Tampering", "R": "Repudiation", "I": "Information disclosure",
                  "D": "Denial of service", "E": "Elevation of privilege"}


def _leer_json(p: str):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _fichas_por_letra(target: str) -> dict[str, list[str]]:
    """Fichas riesgos/<ID>.md por letra, leyendo la sección `## STRIDE` de cada una."""
    out: dict[str, list[str]] = {c: [] for c in "STRIDE"}
    d = os.path.join(LAB, "targets", target, "riesgos")
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        if not f.endswith(".md"):
            continue
        txt = open(os.path.join(d, f), encoding="utf-8", errors="replace").read()
        m = re.search(r"^## STRIDE\s*$(.*?)(?=^## |\Z)", txt, re.M | re.S)
        if not m:
            continue
        for c, rx in _STRIDE_RE.items():
            if re.search(rx, m.group(1), re.I):
                out[c].append(f[:-3])
    return out


def _amenazas_por_letra(rep: str):
    """{letra: {severidad: n}} desde el SARIF de Threagile, o None si no existe."""
    doc = _leer_json(os.path.join(rep, "amenazas", "threagile.sarif"))
    if doc is None:
        return None
    out: dict[str, dict[str, int]] = {c: {} for c in "STRIDE"}
    for run in doc.get("runs", []):
        reglas = {r.get("id"): r for r in run.get("tool", {}).get("driver", {}).get("rules", [])}
        for res in run.get("results", []):
            tags = [str(t) for t in reglas.get(res.get("ruleId"), {}).get("properties", {}).get("tags", [])]
            letra = next((t.split(":", 1)[1] for t in tags if t.startswith("stride:")), "?")
            sev = next((t for t in tags if t in ("critical", "high", "medium", "low")), "unranked")
            out.setdefault(letra, {})
            out[letra][sev] = out[letra].get(sev, 0) + 1
    return out


def _sin_titulo(p: str) -> str:
    """Un .md generado, sin su `# título`, para inlinearlo bajo <details>."""
    try:
        lineas = open(p, encoding="utf-8").read().splitlines()
    except OSError:
        return ""
    if lineas and lineas[0].startswith("# "):
        lineas = lineas[1:]
    return "\n".join(lineas).strip()


def amenazas_stride(target: str, rep: str) -> str:
    por = _amenazas_por_letra(rep)
    if por is None:
        return ""
    aaa = _leer_json(os.path.join(rep, "aaa", "aaa.json")) or {}
    fichas = _fichas_por_letra(target)
    total = sum(sum(v.values()) for v in por.values())
    out = [f"## 4. Modelo de amenazas (STRIDE)\n\n",
           f"Threagile evaluó `targets/{target}/amenazas/threagile.yaml` y derivó **{total}** riesgos; cada uno "
           "lleva la letra de su regla y se juzga en el triaje como cualquier otro hallazgo. La tabla cruza las "
           "seis letras con las fichas de riesgo escritas a mano y con los controles AAA medidos en vivo.\n\n",
           "| STRIDE | Amenazas modeladas | Fichas `riesgos/` con esa letra | Controles AAA medidos con esa letra |\n",
           "|---|---|---|---|\n"]
    for c in "STRIDE":
        sevs = por.get(c, {})
        n = sum(sevs.values())
        desglose = " · ".join(f"{s} {sevs[s]}" for s in ("critical", "high", "medium", "low", "unranked") if sevs.get(s))
        amen = f"**{n}** ({desglose})" if n else "0"
        fich = ", ".join(fichas[c]) or "—"
        p = f = 0
        for pilar in ("authn", "authz", "acct"):
            pl = (aaa.get(pilar) or {}).get("por_letra", {}).get(c, {})
            p += pl.get("pass", 0)
            f += pl.get("fail", 0)
        ctrl = (f"pass {p} / fail {f}" if (p or f) else "—") if aaa else "— (AAA no medida)"
        out.append(f"| **{c}** {_STRIDE_NOMBRE[c]} | {amen} | {fich} | {ctrl} |\n")
    if por.get("?"):
        out.append(f"| sin letra | {sum(por['?'].values())} | | |\n")
    out.append("\nUna letra con amenazas modeladas y sin sondas es un control que se da por supuesto; una letra con "
               "sondas y sin amenazas es una medición sin modelo detrás. Ninguna regla builtin de Threagile es "
               "Repudiation: la **R** sale de `individual_risk_categories` del modelo y se mide con la auditoría de AAA.\n\n")
    cuerpo = _sin_titulo(os.path.join(rep, "amenazas", "amenazas.md"))
    if cuerpo:
        out.append(f"<details><summary>Riesgos derivados del modelo (`reports/{target}/amenazas/amenazas.md`)</summary>\n\n{cuerpo}\n\n</details>\n\n")
    out.append("---\n\n")
    return "".join(out)


def aaa_pilares(target: str, rep: str) -> str:
    aaa = _leer_json(os.path.join(rep, "aaa", "aaa.json"))
    if not aaa:
        return ""
    a, z, c = aaa.get("authn") or {}, aaa.get("authz") or {}, aaa.get("acct") or {}
    db = c.get("db", "sin-oraculo")
    out = ["## 4. AAA: autenticación · autorización · auditoría\n\n",
           "Tres pilares, tres guiones del perfil, tres veredictos con presupuesto 0: un control que falla no se "
           "administra por umbral, se corrige o se acepta con razón. `pass` es un control que se sostiene; `no aplica`, "
           "una sonda que este stack no puede ejecutar; `no disponible`, una medición que no se hizo.\n\n",
           "| Pilar | Guion | Medido | Pass | Fail | No aplica / no disponible |\n|---|---|---|---|---|---|\n",
           f"| Autenticación | `aaa/authn.json` | {'sí' if a.get('guion') else '**NO**'} | {a.get('pass', 0)} | {a.get('fail', 0)} | "
           f"{a.get('no_aplica', 0)} no aplica · {a.get('no_ejecutada', 0)} no ejecutada |\n",
           f"| Autorización | `playwright/authz-matrix.json` | {'sí' if z.get('guion') else '**NO**'} | {z.get('pass', 0)} | {z.get('fail', 0)} | "
           f"{z.get('no_ejecutada', 0)} no ejecutada |\n",
           f"| Auditoría | `aaa/acct.json` (oráculo: {db}) | {'sí' if db == 'disponible' else '**NO**'} | {c.get('pass', 0)} | "
           f"{c.get('fail', 0)} | {c.get('error', 0)} error · {c.get('no_disponible', 0)} no disponible |\n\n"]
    if db != "disponible":
        out.append("> ⚠️ **La auditoría (repudio) no se midió**: sin `AAA_DB_URL` en `target.env.local` no hay oráculo "
                   "que confirme que un login, un intento fallido o un cierre de sesión dejaron rastro. Que la "
                   "aplicación «registra» no lo afirma nadie en esta ronda.\n\n")
    cuerpo = _sin_titulo(os.path.join(rep, "aaa", "AAA.md"))
    if cuerpo:
        out.append(f"<details><summary>Sondas, reglas y eventos (`reports/{target}/aaa/AAA.md`)</summary>\n\n{cuerpo}\n\n</details>\n\n")
    out.append("---\n\n")
    return "".join(out)


# ---------------------------------------------------------------- ensamblado

def build(target: str, nueva_ronda: bool = False):
    rep = os.path.join(LAB, "reports", target)
    tdir = os.path.join(LAB, "targets", target)
    src = envget(target, "SRC_PATH")

    datos = findlib.collect(rep)
    juicios = triagelib.load(rep)
    # Ni el falso positivo ni el mitigado (control medido que pasa) siguen abiertos: el registro
    # los cierra en esta ronda, con su nota, y si reaparecen sin juicio volverán a abrirse.
    presentes = {f["key"]: f for f in datos["findings"]
                 if (juicios.get(f["key"]) or {}).get("verdict") not in ("falso-positivo", "mitigado")}

    filas_prev = reg.cargar(tdir)
    ronda = reg.ronda_actual(filas_prev) + (1 if nueva_ronda else 0)
    filas, res = reg.sincronizar(tdir, presentes, ronda)

    def confirmado(f):
        # Sin clave de triaje = fila escrita a mano en el registro: no viene de un escáner, la
        # redactó una persona que ya la verificó. Pedirle que confirme su propio hallazgo, y
        # mandarlo mientras tanto a la tabla de señal cruda, es donde nadie lo iba a leer.
        if not (f.get("clave") or "").strip():
            return True
        return (juicios.get(f["clave"]) or {}).get("verdict") in ("bloqueante", "corregir")

    def juicio(f):
        return juicios.get((f.get("clave") or "").strip()) or {}

    abiertos = [f for f in filas if f.get("estado") in ("abierto", "reabierto")]
    conf = [f for f in abiertos if confirmado(f) and not f["id"].startswith("L")]
    # Juzgado SIN acción (aceptado, deuda, fuera de alcance): no es señal sin triar —alguien ya lo
    # miró y dijo por qué no se persigue— y no puede ir a la tabla de «sin juicio humano» como
    # si nadie lo hubiera leído. Va en su propia tabla, con la nota, el dueño y la fecha.
    aparte = [f for f in abiertos if not confirmado(f) and not f["id"].startswith("L")
              and triagelib.VERDICT_INFO.get(juicio(f).get("verdict", ""), {}).get("gate") == "aparte"]
    ids_aparte = {f["id"] for f in aparte}
    sin_triar = [f for f in abiertos if not confirmado(f) and not f["id"].startswith("L")
                 and f["id"] not in ids_aparte]
    for f in aparte:
        f["_juicio"] = juicio(f)
    cerrados = [f for f in res["cerrados"] if not f["id"].startswith("L")]

    cob = cobertura(target, rep)
    # Buscar la LÍNEA del veredicto por su texto, no por su posición. `tail -3 | head -1`
    # capturaba «skip playwright not run» cuando el gate terminaba con líneas de skip: el
    # informe anunciaba como veredicto una dimensión no ejecutada.
    ver = sh(["bash", "-c",
              f"tools/gate.sh {target} 2>/dev/null | grep -aE 'GATE (PASSED|FAILED)' | tail -1"])
    ver = re.sub(r"\033\[[0-9;]*m", "", ver).strip() or "(sin ejecutar)"

    doc = "".join([
        cabecera(target, ronda, src, cob),
        resumen(target, conf, cerrados, ronda, ver),
        verificado(target),
        detalle(target, conf, ronda, sin_triar, aparte),
        amenazas_stride(target, rep),
        aaa_pilares(target, rep),
        cobertura_tabla(target, cob, conf, sin_triar),
        observaciones(target),
        cierre(target),
    ])

    # Renumerar al ensamblar: §5 solo se emite si hay observaciones, y un salto en la numeración
    # hace dudar de si falta una sección.
    n = [0]

    def _renum(m):
        n[0] += 1
        return f"## {n[0]}. {m.group(2)}"

    doc = re.sub(r"^## (\d+)\. (.+)$", _renum, doc, flags=re.M)
    faltan = [l.strip() for l in doc.splitlines() if "⟨FALTA" in l]
    return doc, ronda, faltan


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    target = argv[1]
    doc, ronda, faltan = build(target, nueva_ronda="--ronda-nueva" in argv)

    if "--pendientes" in argv:
        print(f"{len(faltan)} hueco(s) que exigen una persona:\n")
        for f in faltan:
            print("  ·", f[:170])
        return 0

    nombre = f"INFORME_TECNICO_VERIFICACION_R{ronda}_{target.upper()}.md"
    destino = os.path.join(LAB, "reports", target, nombre)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as fh:
        fh.write(doc)
    print(f"escrito {destino}")
    print(f"ronda R{ronda} · {len(faltan)} hueco(s) ⟨FALTA⟩")
    if faltan:
        print(f"\nNO está listo para enviar. Detalle: tools/report.py {target} --pendientes")
        print(f"La prosa de cada hallazgo va en targets/{target}/hallazgos/<ID>.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
