"""Persist the human judgement about a finding.

This is the piece that keeps the lab honest about its own limits. A scanner produces signal; only
a person can say whether a given hit is real. In the antiplagio run, thirteen apparent
authorization failures turned out to be zero real bypasses — some blocked by a missing scenario,
some because a 200 carried an error body — and that reasoning existed nowhere but in the head of
whoever did it. The next reader started from scratch.

A verdict plus a sentence, stored next to the artifacts, turns a list of raw findings into a list
of *judged* findings. Both the web UI (which writes them) and the generated report (which shows
them) use this module, so a triage note recorded in the browser appears in the report unchanged.

Keys are content-derived — tool, rule and location — rather than positional: a finding must keep
its verdict when the scan re-runs and the ordering changes. Line numbers move, so they are
deliberately left out of the key; a note may occasionally attach to a shifted line, which is far
better than silently losing every verdict on each run.
"""
from __future__ import annotations

import datetime
import json
import os
import time

# Los criterios de juicio. Un clic, sin listas desplegables: el operador toca uno y el hallazgo
# se archiva bajo ese criterio.
#
# POR QUÉ ESTOS Y NO "confirmado / falso positivo / inconcluso". Los tres anteriores mezclaban dos
# preguntas distintas: «¿es real?» y «¿qué hacemos?». Un CVE real sin parche disponible y una
# inyección SQL explotable eran ambos "Confirmado", y el gate los contaba igual. La decisión que
# de verdad se toma en una auditoría no es si el hallazgo existe, es si **frena el despliegue**.
#
# El campo `gate` dice cómo lo trata tools/gate.sh:
#   fail     hace fallar el veredicto SIEMPRE, sin importar el umbral
#   cuenta   suma contra el presupuesto de su dimensión
#   aparte   no suma al presupuesto, pero se lista en su propia sección del informe
#   descuenta no suma: la herramienta se equivocó
VERDICT_INFO = {
    "bloqueante": {
        "label": "Bloqueante",
        "ayuda": "Real y explotable. NO puede pasar a producción.",
        "gate": "fail",
        "exige": (),
    },
    "corregir": {
        "label": "Hay que corregirlo",
        "ayuda": "Real, hay que arreglarlo, pero no frena este despliegue.",
        "gate": "cuenta",
        "exige": (),
    },
    "falso-positivo": {
        "label": "Falso positivo",
        "ayuda": "La herramienta se equivocó: aquí no hay nada.",
        "gate": "descuenta",
        "exige": ("nota",),
    },
    "deuda": {
        "label": "Deuda técnica",
        "ayuda": "Real pero irrelevante ahora. Se anota y no se persigue.",
        "gate": "aparte",
        "exige": (),
    },
    "aceptado": {
        "label": "Riesgo aceptado",
        "ayuda": "Real, y alguien con autoridad lo asume.",
        "gate": "aparte",
        # Sin QUIÉN y HASTA CUÁNDO, «riesgo aceptado» es «deuda técnica» con mejor nombre: nadie
        # responde por él y no caduca nunca. Exigirlos es lo que separa una decisión de una excusa.
        "exige": ("nota", "dueno", "hasta"),
    },
    "fuera-de-alcance": {
        "label": "Fuera de alcance",
        "ayuda": "No es de este equipo ni de este componente (vendor, fixture de prueba).",
        # Es la vía por la que los CVE de dependencias se ignoran para siempre. Exigir de QUIÉN es
        # convierte «no es mío» en «es de aquel», que sí se puede perseguir.
        "gate": "aparte",
        "exige": ("nota", "dueno"),
    },
}

VERDICTS = tuple(VERDICT_INFO)

LABELS = {k: v["label"] for k, v in VERDICT_INFO.items()}

# Veredictos del esquema anterior, para no perder el trabajo ya hecho. Se traducen al leer.
LEGADO = {
    "confirmed": "corregir",         # "real" sin decir si frena: lo conservador es que no bloquea
    "false-positive": "falso-positivo",
    "inconclusive": "",              # inconcluso NO era un juicio: era no haber decidido todavía
}


def key_for(tool: str, rule: str, loc: str) -> str:
    return f"{tool}|{rule}|{loc}"


def path_for(reports_dir: str) -> str:
    return os.path.join(reports_dir, "triage.json")


def load(reports_dir: str) -> dict:
    try:
        with open(path_for(reports_dir), encoding="utf-8") as fh:
            data = json.load(fh)
            if not isinstance(data, dict):
                return {}
            # Traducir el esquema anterior al vuelo. Reescribir el archivo aquí sería peor: una
            # lectura no debe modificar el registro de juicios de nadie.
            for entrada in data.values():
                if isinstance(entrada, dict) and entrada.get("verdict") in LEGADO:
                    entrada["verdict"] = LEGADO[entrada["verdict"]]
            return data
    except (OSError, ValueError):
        return {}


def save(reports_dir: str, entries: dict) -> None:
    """Merge and write atomically. An empty verdict removes the entry rather than storing a
    blank one, so clearing a mistaken judgement is possible from the same form that made it."""
    current = load(reports_dir)
    for key, entry in entries.items():
        verdict = (entry.get("verdict") or "").strip()
        note = (entry.get("note") or "").strip()
        if verdict not in VERDICTS and not note:
            current.pop(key, None)
            continue
        current[key] = {"verdict": verdict, "note": note, "at": time.time(),
                        # Quién lo asume y hasta cuándo. Solo los exige `aceptado` y
                        # `fuera-de-alcance`, pero se guardan siempre que vengan.
                        "dueno": (entry.get("dueno") or "").strip(),
                        "hasta": (entry.get("hasta") or "").strip()}

    os.makedirs(reports_dir, exist_ok=True)
    tmp = path_for(reports_dir) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(current, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path_for(reports_dir))


def falta(verdict: str, entry: dict) -> list[str]:
    """Qué le falta a este juicio para estar completo. Un `aceptado` sin dueño ni fecha no es
    un riesgo aceptado: es un hallazgo escondido bajo una etiqueta que suena a decisión."""
    req = VERDICT_INFO.get(verdict, {}).get("exige", ())
    nombres = {"nota": "una razón", "dueno": "quién lo asume", "hasta": "hasta cuándo"}
    return [nombres[c] for c in req if not (entry.get({"nota": "note"}.get(c, c)) or "").strip()]


def vencido(entry: dict) -> bool:
    """¿Caducó este riesgo aceptado?

    Un «riesgo aceptado» sin caducidad es una amnistía perpetua: se marca una vez y el hallazgo
    desaparece del veredicto para siempre. La fecha existe justamente para impedir eso, así que
    tiene que APLICARSE — vencida, el hallazgo vuelve a contar.

    Sin fecha se considera vencido: el criterio la exige, y una entrada sin ella solo puede venir
    de un registro antiguo o de alguien que se la saltó.
    """
    hasta = (entry.get("hasta") or "").strip()
    if not hasta:
        return True
    try:
        y, m, d = (int(x) for x in hasta.split("-")[:3])
        return datetime.date(y, m, d) < datetime.date.today()
    except (ValueError, TypeError):
        return True


def summary(entries: dict) -> dict:
    out = {v: 0 for v in VERDICTS}
    for e in entries.values():
        v = e.get("verdict")
        if v in out:
            out[v] += 1
    return out
