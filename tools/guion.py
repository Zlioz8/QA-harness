#!/usr/bin/env python3
"""Qué dice el GUION de una dimensión: existe, quién lo escribió, y qué ejercita.

EL PROBLEMA QUE RESUELVE. La cadena real de una auditoría es:

    proyecto ──┬─ perfil (.env)  ─┐
               ├─ GUION (archivo) ├──→ herramienta ──→ artefacto ──→ veredicto
               └─ objeto (APK…)  ─┘         ↑
                                            └─ el guion decide QUÉ se mira

El guion no es una entrada más: es el TECHO de la cobertura. Y hasta ahora era invisible.

Medido sobre los perfiles de este laboratorio, antes de escribir esto:

  · antiplagio corrió la carga con k6/smoke.js — TRES peticiones. El informe dijo
    «Carga (k6): p95 30 ms · PASS». Es verdad, y casi no significa nada: midió un humo de dos
    endpoints, no el sistema bajo carga.
  · costos_web tiene DIEZ guiones de carga (stress_ramp, capacity_multiuser, import_stress,
    abuse_search…). Una campaña de verdad.
  · Las dos se pintaban idénticas: «Carga (k6) · ejecutada».

  · Y SEIS archivos de configuración en tres perfiles eran la plantilla SIN TOCAR
    (antiplagio/spectral.yaml, antiplagio/qodana.yaml, costos_web/spectral.yaml,
    anuncios/gitleaks.toml, anuncios/spectral.yaml, anuncios/qodana.yaml). Esas dimensiones
    corrieron con reglas genéricas y el informe no lo decía en ninguna parte.

«Corrió con el guion de ejemplo» no es lo mismo que «corrió con el guion de este sistema». Es la
misma familia que `NO EJECUTADO ≠ 0 hallazgos`, aplicada a la profundidad en vez de a la presencia.

QUÉ EXTRAE Y POR QUÉ ASÍ. Un conteo y una lista de lo que el guion toca. No pretende entender el
archivo: cuenta la unidad significativa de cada formato y saca las rutas. Eso basta para que otro
operador —o un agente— sepa, sin abrir nada, si el guion cubre el sistema o solo lo saluda.
"""
from __future__ import annotations

import os
import re

# La unidad que importa en cada formato, y cómo se llama al leerla.
UNIDAD = {
    "script": "peticiones", "plan": "peticiones", "specs": "pruebas",
    "reglas": "reglas", "config": "ajustes",
}

# Ruido que no es una ruta del sistema auditado.
_NO_RUTA = re.compile(r"^(https?://)?(localhost|127\.0\.0\.1|example\.|schema|www\.)", re.I)


def _rutas(texto: str, limite: int = 8) -> list[str]:
    """Las rutas HTTP que el guion toca, en orden de aparición y sin repetir."""
    vistas: list[str] = []
    for m in re.finditer(r"""['"`]([/][A-Za-z0-9._~\-/{}$]*)['"`]""", texto):
        r = m.group(1)
        if len(r) < 2 or r.startswith("//") or _NO_RUTA.match(r):
            continue
        if r not in vistas:
            vistas.append(r)
        if len(vistas) >= limite:
            break
    return vistas


def _medir(path: str, kind: str) -> tuple[int, list[str]]:
    """(cuántas unidades, qué toca). Nunca lanza: un guion ilegible cuenta 0, no rompe la pantalla."""
    try:
        if os.path.isdir(path):
            # Playwright: el guion es un DIRECTORIO de specs. La unidad es el test, no el archivo:
            # un solo spec con veinte `test()` cubre más que cinco con uno cada uno.
            n, rutas = 0, []
            for raiz, _d, ficheros in os.walk(path):
                for f in sorted(ficheros):
                    if not f.endswith((".spec.ts", ".spec.js")):
                        continue
                    t = open(os.path.join(raiz, f), encoding="utf-8", errors="replace").read()
                    n += len(re.findall(r"\btest\s*\(", t))
                    for r in _rutas(t, 4):
                        if r not in rutas:
                            rutas.append(r)
            return n, rutas[:8]

        texto = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return 0, []

    if kind in ("script",):          # k6 y compañía: la unidad es la petición HTTP
        return len(re.findall(r"\bhttp\.(get|post|put|patch|del|request)\b", texto)), _rutas(texto)
    if kind == "plan":
        if path.endswith(".jmx"):    # JMeter
            return texto.count("HTTPSampler"), _rutas(texto)
        # Plan de ZAP: la unidad es el job, y lo que toca son sus contextos y URLs.
        jobs = re.findall(r"^\s*-\s*type:\s*(\S+)", texto, re.M)
        urls = re.findall(r"(\$\{[A-Z_]+\}[^\s\"']*|https?://[^\s\"']+)", texto)
        return len(jobs), list(dict.fromkeys(jobs + urls))[:8]
    if kind == "reglas":
        # Cada formato nombra su unidad de otra forma. Se cuentan todas y se toma la que aplique;
        # medir un gitleaks.toml (TOML, [[rules]]) con el patron de un ruleset de Spectral (YAML)
        # daba cero y lo reportaba como "vacio" teniendo tres reglas propias.
        toml_rules = len(re.findall(r"^\s*\[\[rules\]\]", texto, re.M))
        yaml_rules = len(re.findall(r"^\s*-\s*(?:id|rule|description):", texto, re.M))
        yaml_keys = len(re.findall(r"^\s{2,}[\w.-]+:\s*$", texto, re.M))
        extiende = bool(re.search(r"useDefault\s*=\s*true|^extends:", texto, re.M))
        n = toml_rules or yaml_rules or yaml_keys
        toca = ["+ reglas por defecto de la herramienta"] if extiende else []
        return n, toca
    if kind == "config":
        return len(re.findall(r"^\s*[\w.-]+\s*[:=]", texto, re.M)), []
    return 0, []


def analizar(dim, valores: dict, target_dir: str, template_dir: str) -> dict | None:
    """El estado del guion de una dimensión, o None si esa herramienta no lleva guion."""
    if not dim.script:
        return None

    # El guion puede elegirse desde el perfil: k6/${K6_SCRIPT}, jmeter/${JMETER_PLAN}.
    def _sub(m):
        var, _, defecto = m.group(1).partition(":-")
        return valores.get(var, "") or defecto or var
    rel = re.sub(r"\$\{([^}]+)\}", _sub, dim.script)
    path = os.path.join(target_dir, rel)
    plantilla = os.path.join(template_dir, rel)

    if not os.path.exists(path):
        return {"rel": rel, "kind": dim.script_kind, "estado": "ausente", "n": 0, "toca": [],
                "nota": "la herramienta no tiene qué interpretar: la dimensión no puede medir nada"}

    # ¿Lo escribió alguien para ESTE proyecto, o sigue siendo el ejemplo?
    de_plantilla = False
    if os.path.isfile(path) and os.path.isfile(plantilla):
        try:
            de_plantilla = (open(path, "rb").read() == open(plantilla, "rb").read())
        except OSError:
            de_plantilla = False

    n, toca = _medir(path, dim.script_kind)
    if de_plantilla:
        estado = "de plantilla"
        nota = ("nadie lo escribió para este proyecto: corre con el ejemplo genérico. "
                "«Corrió con el guion de ejemplo» no es «corrió con el guion de este sistema».")
    elif n == 0:
        estado = "vacío"
        nota = "existe pero no define ninguna unidad ejecutable: no ejercita nada"
    else:
        estado = "propio"
        nota = ""

    return {"rel": rel, "kind": dim.script_kind, "estado": estado,
            "n": n, "unidad": UNIDAD.get(dim.script_kind, "unidades"),
            "toca": toca, "nota": nota}


# ---------------------------------------------------------------- salida para el informe

def _cli(argv):
    """Sección de guiones para RUN.md.

    Va en el informe, no solo en la pantalla: quien lee el informe —otro operador QA, o un agente
    que tenga que entender a la vez el proyecto y la herramienta— necesita saber CON QUÉ se midió.
    «Carga: p95 30 ms · PASS» junto a «guion: smoke.js, 3 peticiones» dice algo muy distinto que
    la misma línea sola.

    Uso: guion.py <target>
    """
    import sys as _s
    if len(argv) != 1:
        print("uso: guion.py <target>", file=_s.stderr)
        return 2
    target = argv[0]
    lab = os.environ.get("LAB_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _s.path.insert(0, os.path.join(lab, "tools"))
    _s.path.insert(0, os.path.join(lab, "ui"))
    import dimensions          # noqa: PLC0415
    import pipeline            # noqa: PLC0415

    tdir = os.path.join(lab, "targets", target)
    valores = pipeline.overlay(os.path.join(tdir, "target.env"))
    tpl = os.path.join(lab, "targets", "_template")

    filas = []
    for dim in dimensions.load():
        g = analizar(dim, valores, tdir, tpl)
        if not g:
            continue
        alcance = f"{g['n']} {g.get('unidad', '')}" if g["n"] else "—"
        toca = ", ".join(g["toca"][:5]) if g["toca"] else ""
        filas.append(f"| {dim.label} | `{g['rel']}` | {g['estado']} | {alcance} | {toca} |")

    if not filas:
        return 0
    print("## Guiones — con qué se midió cada dimensión")
    print()
    print("El guion es el archivo que la herramienta interpreta, y es el **techo de la cobertura**:")
    print("una dimensión no puede encontrar nada fuera de lo que su guion ejercita. `de plantilla`")
    print("significa que nadie lo escribió para este proyecto — corrió con el ejemplo genérico, que")
    print("NO es lo mismo que haber corrido con el guion de este sistema.")
    print()
    print("| Dimensión | Guion | Origen | Alcance | Ejercita |")
    print("|---|---|---|---|---|")
    for f in filas:
        print(f)
    print()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_cli(sys.argv[1:]))
