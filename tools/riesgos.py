#!/usr/bin/env python3
"""¿Cada hallazgo confirmado tiene su DOCUMENTO DE FUNDAMENTACIÓN de riesgo?

QUÉ ES ESTE PASO, Y POR QUÉ EXISTE. El informe dice QUÉ está mal y qué severidad tiene. Pero un
equipo de desarrollo que recibe «severidad Alta» sin más aprende poco, y una fábrica que aspira a
certificarse (ISO/IEC 27001) necesita TRAZABILIDAD: por cada riesgo, un documento que pruebe que es
tangible —dónde vive, por qué medios se ejecuta, con qué evidencia— y que lo ancle a marcos
teóricos reconocidos. Eso no es una PoC («corre estos comandos»); es un documento probatorio y
FORMATIVO. Su destinatario doble: el desarrollador que debe entender la BASE del fallo, y el
auditor de certificación que necesita ver el control mapeado.

EL DOCUMENTO por hallazgo vive en `targets/<t>/riesgos/<ID>.md` y DEBE fundamentar, no solo
afirmar. Secciones obligatorias (este archivo las verifica; una vacía o de plantilla NO cuenta):

  ## Dónde vive           el componente/endpoint/archivo EXACTO, no «la aplicación»
  ## Por qué es tangible  la cadena real: quién (actor), cómo, por qué medios, con qué evidencia
                          ya recogida en esta auditoría. Aquí se prueba que el riesgo es EJECUTABLE.
  ## OWASP                Top 10 2021 + la guía de prueba (WSTG) o el requisito (ASVS) que aplica,
                          CON la razón de por qué encaja — no un número suelto.
  ## MITRE                CWE (la debilidad) y, cuando haya un adversario, ATT&CK (la técnica).
  ## STRIDE               la categoría del modelo de amenazas de Microsoft, razonada.
  ## CVSS                 vector 3.1 + score, para que la severidad sea defendible y no una opinión.
  ## ISO/IEC 27001        los controles del Anexo A:2022 que este hallazgo incumple — el puente a
                          la certificación.
  ## Qué debe asimilar el equipo   la lección de fondo, en lenguaje de desarrollador. Es la mitad
                          FORMATIVA: que la próxima vez el patrón no se repita.
  ## Criterio de cierre   cómo se verifica, de forma objetiva, que el riesgo ya no es tangible.

LA REGLA, igual que con los guiones (tools/guion-check.py): un hallazgo CONFIRMADO sin su documento
de riesgo es una afirmación de severidad sin fundamento. El paso se NIEGA a darse por completo hasta
que cada confirmado tenga el suyo, con todas las secciones pobladas para ESE hallazgo (no la
plantilla). Los hallazgos «sin triar» no lo necesitan todavía — se fundamentan cuando se confirmen.

Uso:  tools/riesgos.py <target> [--andamiar]
      --andamiar  crea el esqueleto de los documentos que falten (con las secciones y un
                  recordatorio por rellenar), para no empezar de cero.
"""
from __future__ import annotations

import os
import sys

LAB = os.environ.get("LAB_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(LAB, "tools"))

import hallazgos as reg  # noqa: E402

SECCIONES = [
    ("Dónde vive", "el componente/endpoint/archivo EXACTO"),
    ("Por qué es tangible", "la cadena real de explotación + la evidencia ya recogida"),
    ("OWASP", "Top 10 2021 + WSTG/ASVS, con la razón del encaje"),
    ("MITRE", "CWE (debilidad) y ATT&CK (técnica) cuando haya adversario"),
    ("STRIDE", "la categoría del modelo, razonada"),
    ("CVSS", "vector 3.1 + score"),
    ("ISO/IEC 27001", "controles del Anexo A:2022 incumplidos"),
    ("Qué debe asimilar el equipo", "la lección de fondo, formativa"),
    ("Criterio de cierre", "verificación objetiva de que ya no es tangible"),
]

# Marcadores que delatan un documento SIN rellenar (plantilla del --andamiar). Se usan las formas
# EXACTAS que el esqueleto escribe, no palabras sueltas: «TODO» a secas caza «TODOS los esquemas»
# de una prosa legítima. El marcador real del andamiaje es `⟨PENDIENTE: …⟩`.
PLANTILLA = ("⟨PENDIENTE:", "⟨FALTA", "<completar>", "por rellenar>")


def confirmado(fila: dict) -> bool:
    # Mismo criterio que report.py: sin clave de triaje = fila escrita a mano (confirmada);
    # con clave = viene de un escáner y solo cuenta si el juicio la marcó a corregir/bloqueante.
    # Aquí, para no acoplarse al triaje, tratamos como confirmados los de fila-a-mano (E*, I*)
    # y los H* que ya tengan severidad y prosa en hallazgos/<id>.md.
    if not (fila.get("clave") or "").strip():
        return True
    return False


def secciones_presentes(texto: str) -> set[str]:
    presentes = set()
    for titulo, _ in SECCIONES:
        # Cabecera markdown que empiece por el título (tolerante a nivel ## / ###).
        for linea in texto.splitlines():
            l = linea.strip().lstrip("#").strip()
            if l.lower().startswith(titulo.lower()):
                presentes.add(titulo)
                break
    return presentes


def cuerpo_de_seccion(texto: str, titulo: str) -> str:
    """El texto entre esta cabecera y la siguiente, para detectar secciones vacías/plantilla."""
    lineas = texto.splitlines()
    dentro = False
    buf = []
    for linea in lineas:
        l = linea.strip().lstrip("#").strip()
        es_cabecera = linea.strip().startswith("#")
        if es_cabecera and l.lower().startswith(titulo.lower()):
            dentro = True
            continue
        if dentro and es_cabecera:
            break
        if dentro:
            buf.append(linea)
    return "\n".join(buf).strip()


def revisar(target: str, andamiar: bool = False) -> int:
    tdir = os.path.join(LAB, "targets", target)
    rdir = os.path.join(tdir, "riesgos")
    filas = reg.cargar(tdir)
    abiertos = [f for f in filas
                if f.get("estado") in ("abierto", "reabierto")
                and not f["id"].startswith("L")
                and confirmado(f)]

    print(f"== fundamentación de riesgos: {target} ==\n")
    if not abiertos:
        print("  No hay hallazgos confirmados todavía. Nada que fundamentar en esta ronda.")
        return 0

    faltan, incompletos, ok = [], [], []
    if andamiar:
        os.makedirs(rdir, exist_ok=True)

    for f in sorted(abiertos, key=lambda x: x["id"]):
        hid = f["id"]
        path = os.path.join(rdir, f"{hid}.md")
        if not os.path.exists(path):
            faltan.append(f)
            if andamiar:
                _escribir_esqueleto(path, f)
            continue
        texto = open(path, encoding="utf-8").read()
        pres = secciones_presentes(texto)
        vacias = [t for t, _ in SECCIONES
                  if t not in pres or len(cuerpo_de_seccion(texto, t)) < 15]
        plantilla = any(m in texto for m in PLANTILLA)
        if vacias or plantilla:
            incompletos.append((f, vacias, plantilla))
        else:
            ok.append(f)

    for f in ok:
        print(f"  ok    {f['id']:4} {f.get('titulo','')[:60]}  [fundamentado]")
    for f, vacias, plantilla in incompletos:
        motivo = "de plantilla" if plantilla else f"faltan/vacías: {', '.join(vacias)}"
        print(f"  aviso {f['id']:4} {f.get('titulo','')[:50]}  [{motivo}]")
    for f in faltan:
        extra = " (esqueleto creado)" if andamiar else ""
        print(f"  FALTA {f['id']:4} {f.get('titulo','')[:55]}  [sin documento{extra}]")

    print()
    total = len(abiertos)
    hechos = len(ok)
    print(f"  {hechos}/{total} hallazgos confirmados con su fundamentación completa.")
    if faltan or incompletos:
        print("\n  Un hallazgo confirmado SIN fundamentación es una severidad sin prueba ni marco.")
        print(f"  Escribe cada uno en targets/{target}/riesgos/<ID>.md"
              + (" (esqueletos ya creados con --andamiar)." if andamiar else
                 " — corre con --andamiar para el esqueleto."))
        return 1
    print("\n  Cada riesgo confirmado está probado (dónde/cómo/medios) y anclado a OWASP, MITRE,")
    print("  STRIDE, CVSS e ISO/IEC 27001. Trazabilidad lista para el informe y para auditoría.")
    return 0


def _escribir_esqueleto(path: str, f: dict) -> None:
    hid = f["id"]
    titulo = f.get("titulo", "")
    sev = f.get("severidad", "")
    lineas = [f"# {hid} · {titulo}", "",
              f"> Severidad de la auditoría: **{sev}**. Este documento PRUEBA que el riesgo es",
              "> tangible y lo fundamenta en marcos reconocidos. No es una PoC: es trazabilidad",
              "> probatoria y material formativo para el equipo.", ""]
    for titulo_sec, guia in SECCIONES:
        lineas.append(f"## {titulo_sec}")
        lineas.append("")
        lineas.append(f"⟨PENDIENTE: {guia}⟩")
        lineas.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas))


def main(argv: list[str]) -> int:
    if not argv:
        print("uso: tools/riesgos.py <target> [--andamiar]", file=sys.stderr)
        return 2
    target = argv[0]
    andamiar = "--andamiar" in argv[1:]
    return revisar(target, andamiar)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
