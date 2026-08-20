#!/usr/bin/env python3
"""¿Está cada herramienta aplicada A ESTE proyecto, o corriendo con el ejemplo genérico?

EL FALLO QUE ESTO IMPIDE, y que ya ocurrió. Auditando `adi` se dio por cubierta la dimensión de
autorización habiendo escrito `playwright/authz-matrix.json` pero NINGÚN test: `playwright/tests`
estaba vacío, `zap/automation.yaml` no existía y `k6/smoke.js` tampoco. La comprobación se hizo a
mano, con curl y un navegador, en paralelo a una herramienta que no podía ejecutarse. Nada en el
laboratorio lo dijo: `make doctor` pasaba, el perfil parecía completo, y solo apareció al mirar
`tools/guion.py` por otro motivo.

La lección no es «acuérdate de escribir los guiones». Es que **el laboratorio tiene que negarse**,
igual que ya se niega a medir contra una aplicación caída (require-live) o con una sola cuenta
(require-auth). Un guion es el TECHO de la cobertura: una dimensión no puede encontrar nada fuera
de lo que su guion ejercita, así que correr con el ejemplo genérico no es media medición — es una
medición de otro proyecto con el nombre de este.

TRES ESTADOS Y TRES CONSECUENCIAS DISTINTAS:

  ausente / vacío   la herramienta no tiene qué interpretar. Si además hay artefacto en disco,
                    es el caso más grave: algo se ejecutó y dejó un resultado que parece
                    cobertura. ERROR.
  de plantilla      corre, pero mide el ejemplo. ERROR si hay artefacto; AVISO si no se ha
                    ejecutado todavía (aún estás a tiempo).
  propio            alguien lo escribió para este sistema. OK.

NO APLICA es un cuarto estado legítimo y hay que poder declararlo: un proyecto sin OpenAPI no
necesita un spectral.yaml propio. Se declara en el perfil con `GUION_NO_APLICA=api-lint,jmeter`
y entonces la dimensión se reporta NO DISPONIBLE con su razón, que es una afirmación honesta —
distinta de un silencio.

Uso:  tools/guion-check.py <target> [--estricto]
      --estricto  también falla por los AVISOS (guiones genéricos aún sin ejecutar)
"""
from __future__ import annotations

import os
import sys

LAB = os.environ.get("LAB_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(LAB, "tools"))

import dimensions  # noqa: E402
import guion       # noqa: E402


def leer_perfil(target: str) -> dict:
    """target.env + target.env.local, con el mismo contrato que tools/lib-env.sh."""
    vals: dict[str, str] = {}
    base = os.path.join(LAB, "targets", target, "target.env")
    for path in (base, base + ".local"):
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                v = v.split(" #")[0].strip().strip('"')
                if v or k not in vals:
                    vals[k.strip()] = v
    return vals


def revisar(target: str) -> tuple[list[dict], list[dict], list[dict]]:
    tdir = os.path.join(LAB, "targets", target)
    tpl = os.path.join(LAB, "targets", "_template")
    rep = os.path.join(LAB, "reports", target)
    vals = leer_perfil(target)
    no_aplica = {x.strip() for x in (vals.get("GUION_NO_APLICA") or "").split(",") if x.strip()}

    errores, avisos, ok = [], [], []
    for d in dimensions.load():
        g = guion.analizar(d, vals, tdir, tpl)
        if g is None:
            continue  # esta herramienta no lleva guion (trivy, syft: apuntan al árbol y ya)
        art = getattr(d, "artifact", "") or ""
        hay_artefacto = bool(art) and os.path.exists(os.path.join(rep, art)) \
            and os.path.getsize(os.path.join(rep, art)) > 0
        fila = {"id": d.id, "label": getattr(d, "label", d.id), "guion": g["rel"],
                "estado": g["estado"], "nota": g.get("nota", ""), "artefacto": hay_artefacto}

        if d.id in no_aplica:
            fila["estado"] = "no aplica (declarado)"
            ok.append(fila)
        elif g["estado"] == "propio":
            ok.append(fila)
        elif hay_artefacto:
            # Lo peligroso: se ejecutó y dejó un resultado que parece cobertura.
            errores.append(fila)
        else:
            avisos.append(fila)
    return errores, avisos, ok


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2
    target = argv[1]
    estricto = "--estricto" in argv
    errores, avisos, ok = revisar(target)

    print(f"== guiones: {target} ==\n")
    for f in ok:
        print(f"  ok    {f['id']:<16} {f['guion']}  [{f['estado']}]")
    for f in avisos:
        print(f"  aviso {f['id']:<16} {f['guion']}  [{f['estado']}]")
        print(f"        {f['nota']}")
    for f in errores:
        print(f"  ERROR {f['id']:<16} {f['guion']}  [{f['estado']}] — Y HAY ARTEFACTO EN DISCO")
        print(f"        {f['nota']}")
        print(f"        El resultado de esta dimensión describe el ejemplo genérico, no "
              f"{target}. Se está reportando como cobertura.")

    print()
    if errores:
        print(f"FALLO: {len(errores)} dimensión(es) dejaron resultado corriendo con un guion que")
        print("       no es de este proyecto. Escríbelos, o declara la dimensión no aplicable:")
        print(f"       GUION_NO_APLICA={','.join(f['id'] for f in errores)}   en targets/{target}/target.env")
        return 1
    if avisos and estricto:
        print(f"FALLO (--estricto): {len(avisos)} guion(es) genéricos sin escribir todavía.")
        return 1
    if avisos:
        print(f"{len(avisos)} guion(es) aún genéricos. No han producido resultado, así que no")
        print("hay nada falseado — pero esas dimensiones no medirán este sistema hasta escribirlos.")
    else:
        print("Todas las dimensiones con guion lo tienen escrito para este proyecto (o declarado no aplicable).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
