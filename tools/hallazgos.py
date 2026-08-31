#!/usr/bin/env python3
"""El registro de hallazgos de un proyecto: identidad humana estable entre rondas.

EL PROBLEMA. Las herramientas identifican un hallazgo por `herramienta|regla|ubicación`
(tools/triage.py), que es la clave correcta para que un veredicto sobreviva a un reescaneo —
deliberadamente SIN número de línea, porque el código se mueve. Pero esa clave no sirve para
hablar con nadie: no se puede escribir «seguimos esperando
`semgrep|tainted-sql-string|/src/dashboard/server/batch_schedule.php`» en un correo.

Los informes de esta fábrica usan otra cosa, y llevan diez rondas usándola: `H1`, `§3.20`,
`I.3`, `L.11`. Un hallazgo conserva su identidad de R3 a R10, y eso es lo que permite decir
«abierto desde R3» — que convierte un problema técnico en un problema de proceso, que es otra
conversación y normalmente la más importante.

Este archivo es el puente. Una fila por hallazgo:

    id  clave  titulo  severidad  dimension  responsable  abierto_en  cerrado_en  estado

  id           H<n> hallazgo de código/seguridad · I<n> infraestructura · L<n> defecto del
               PROPIO laboratorio. La taxonomía es la de los informes existentes.
  clave        la clave de triaje. Es el único vínculo con lo que las herramientas producen.
  abierto_en   número de ronda en que apareció. NUNCA se reescribe.
  cerrado_en   ronda en que dejó de aparecer. Se reabre si vuelve.
  estado       abierto | cerrado | reabierto

REGLA QUE NO SE PUEDE ROMPER: un `id` ya emitido no se reasigna jamás. Reutilizarlo haría que
un informe viejo y uno nuevo llamaran igual a cosas distintas, y el historial dejaría de valer.

TSV y no JSON a propósito: esto lo lee y lo edita una persona —el responsable y el esfuerzo se
asignan a mano— y un TSV se revisa en un diff sin ruido de formato.
"""
from __future__ import annotations

import os
import sys

# `sub` es el número §3.n con el que el hallazgo aparece en el informe y en las conversaciones
# («seguimos con §3.20»). Es la taxonomía que la serie R3–R10 de Costos Web ya usa, y el motivo
# de que exista un id humano: nadie cita `semgrep|tainted-sql|/src/x.php` en un correo.
# `esfuerzo` lo estima una persona; sin él la tabla del resumen no se puede priorizar.
CAMPOS = ["id", "sub", "clave", "titulo", "severidad", "dimension",
          "responsable", "esfuerzo", "abierto_en", "cerrado_en", "estado"]

PREFIJOS = {"codigo": "H", "infra": "I", "lab": "L"}


def ruta(target_dir: str) -> str:
    return os.path.join(target_dir, "hallazgos.tsv")


def cargar(target_dir: str) -> list[dict]:
    p = ruta(target_dir)
    if not os.path.exists(p):
        return []
    filas = []
    with open(p, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.rstrip("\n")
            if not linea.strip() or linea.startswith("#") or linea.startswith("id\t"):
                continue
            partes = linea.split("\t")
            partes += [""] * (len(CAMPOS) - len(partes))
            filas.append(dict(zip(CAMPOS, partes[: len(CAMPOS)])))
    return filas


def guardar(target_dir: str, filas: list[dict]) -> None:
    p = ruta(target_dir)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("# Registro de hallazgos — identidad estable entre rondas.\n")
        fh.write("# Lo mantiene tools/report.py; responsable y severidad se ajustan A MANO.\n")
        fh.write("# Un id emitido NO se reasigna nunca.\n")
        fh.write("\t".join(CAMPOS) + "\n")
        for f in filas:
            fh.write("\t".join((f.get(c) or "") for c in CAMPOS) + "\n")
    os.replace(tmp, p)


def _siguiente(filas: list[dict], prefijo: str) -> int:
    n = 0
    for f in filas:
        i = f.get("id", "")
        if i.startswith(prefijo) and i[len(prefijo):].isdigit():
            n = max(n, int(i[len(prefijo):]))
    return n + 1


def ronda_actual(filas: list[dict]) -> int:
    """La ronda que se está escribiendo: una más que la última registrada.

    Sale del registro y no de que alguien la recuerde, que es como una serie de informes
    acaba teniendo dos R7 y ningún R6.
    """
    n = 0
    for f in filas:
        for c in ("abierto_en", "cerrado_en"):
            v = (f.get(c) or "").strip()
            if v.isdigit():
                n = max(n, int(v))
    return n or 1


def sincronizar(target_dir: str, presentes: dict[str, dict], ronda: int,
                clase: str = "codigo") -> tuple[list[dict], dict]:
    """Cruza el registro con lo que la corrida encontró.

    `presentes` es {clave_triaje: hallazgo}. Devuelve (filas, resumen) donde resumen trae
    nuevos / persistentes / cerrados / reabiertos, que es lo que el informe necesita para
    responder «¿arreglaron lo que se reportó?» en vez de solo «¿cuántos hay?».
    """
    filas = cargar(target_dir)
    por_clave = {f["clave"]: f for f in filas if f.get("clave")}
    nuevos, persistentes, cerrados, reabiertos = [], [], [], []

    for clave, h in presentes.items():
        f = por_clave.get(clave)
        if f is None:
            pref = PREFIJOS.get(clase, "H")
            f = {
                "id": f"{pref}{_siguiente(filas, pref)}",
                "sub": "",
                "clave": clave,
                "titulo": (h.get("rule") or "")[:120],
                "severidad": h.get("sev", "unranked"),
                "dimension": h.get("tool", ""),
                "responsable": "",          # lo asigna una persona
                "esfuerzo": "",             # ídem
                "abierto_en": str(ronda),
                "cerrado_en": "",
                "estado": "abierto",
            }
            filas.append(f)
            por_clave[clave] = f
            nuevos.append(f)
        elif f.get("estado") == "cerrado":
            f["estado"] = "reabierto"
            f["cerrado_en"] = ""
            reabiertos.append(f)
        else:
            persistentes.append(f)

    # Hallazgos de JUICIO HUMANO: los que produce leer el código, no una herramienta. Un
    # "router admin nunca montado" o un "wstoken en la URL" no los emite ningún escáner, así que
    # su clave nunca está en `presentes` — y sin esta guarda el reconciliador los cerraba en cada
    # corrida, borrando exactamente el aporte que la metodología reserva a la persona. Su estado
    # es autoritativo a mano: se reconocen por la dimensión (`codigo`/`manual`) o por el prefijo
    # de clave, y el cruce con los escaneos no los toca. Se cierran editando el registro, como se
    # abrieron.
    def _es_humano(f: dict) -> bool:
        # Sin clave de triaje no puede venir de un escaneo: lo redactó una persona. Y una dimensión
        # conducida (codigo/manual/mcp-journey) tampoco re-emite su hallazgo en un artefacto que el
        # cruce lea. En ambos casos su estado es autoritativo a mano.
        if not (f.get("clave") or "").strip():
            return True
        if (f.get("dimension") or "").strip() in ("codigo", "manual", "mcp-journey"):
            return True
        clv = (f.get("clave") or "")
        return clv.startswith("codigo|") or clv.startswith("manual|")

    for clave, f in por_clave.items():
        if _es_humano(f):
            continue
        if clave not in presentes and f.get("estado") in ("abierto", "reabierto"):
            f["estado"] = "cerrado"
            f["cerrado_en"] = str(ronda)
            cerrados.append(f)

    guardar(target_dir, filas)
    return filas, {"nuevos": nuevos, "persistentes": persistentes,
                   "cerrados": cerrados, "reabiertos": reabiertos}


def antiguedad(fila: dict, ronda: int) -> int:
    """Cuántas rondas lleva abierto. Es el dato que convierte un defecto en un proceso."""
    try:
        return max(0, ronda - int(fila.get("abierto_en") or ronda))
    except ValueError:
        return 0


def _cli(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2
    for f in cargar(argv[1]):
        print("\t".join((f.get(c) or "") for c in CAMPOS))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))
