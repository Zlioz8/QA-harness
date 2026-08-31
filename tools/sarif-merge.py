#!/usr/bin/env python3
"""Funde los SARIF parciales de una dimensión que corrió varias veces en UN artefacto canónico.

    tools/sarif-merge.py <destino.sarif> <parcial1.sarif> [parcial2.sarif ...]

POR QUÉ EXISTE. Desde que las dimensiones que miran código se ejecutan una vez POR REPOSITORIO
(ver tools/lib-repos.sh), cada una deja N archivos y el gate, el triaje y el informe leen UNA
ruta canónica — la que declara `artifact:` en lib/dimensions.yml. Alguien tiene que juntarlos.

Este código ya existía, incrustado en tools/secrets.sh, porque el escaneo de secretos fue la
primera dimensión multi-repo. Sacarlo aquí no es aseo: era la quinta copia en potencia, y una
de las cosas que copia es la regla de abajo, que es la más importante del archivo.

LA REGLA QUE NO SE TOCA — «ningún pase produjo resultados» NO es «cero hallazgos».

  Si ningún parcial se pudo leer, este script NO escribe el destino y sale con 3.

  Escribir aquí un SARIF vacío pero sintácticamente válido es lo más peligroso que podría
  hacer: tools/gate.sh cuenta resultados sobre un archivo que EXISTE, ve cero, y estampa
  «PASS: 0 hallazgos». Un escaneo que nunca ocurrió se convierte en una aprobación.

  Dejar el archivo AUSENTE hace que sarif_count devuelva -1, y el gate ya sabe decir «not run».
  Medido en su día sobre `adi`, un repositorio con un token de SonarQube commiteado: el montaje
  fallaba, gitleaks no llegaba a arrancar, el merge escribía un informe limpio igualmente, y la
  corrida dijo «0 secretos».

  Ojo a la distinción, que es fina y deliberada: un parcial que se LEE y trae cero resultados sí
  cuenta — eso es un escaneo que ocurrió y no encontró nada, y su cero es una medición legítima.
  Lo que no cuenta es que no haya nada legible.
"""
from __future__ import annotations

import json
import os
import sys


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("uso: sarif-merge.py <destino.sarif> <parcial...>", file=sys.stderr)
        return 2

    out = argv[1]
    parts = sorted(argv[2:])

    base = None
    results: list = []
    leidos = 0
    for f in parts:
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            continue
        leidos += 1
        run = (d.get("runs") or [{}])[0]
        # Copiar ANTES de que `base` pueda quedar aliaseado con `d`: si no, al asignar
        # base["runs"][0]["results"] más abajo se estaría escribiendo sobre la lista que
        # se está leyendo.
        results.extend(list(run.get("results") or []))
        if base is None:
            base = d

    if base is None:
        print(f"sarif-merge: ningún pase produjo resultados legibles — NO se escribe {out}.")
        print("             La dimensión queda NO EJECUTADA, que no es «sin hallazgos».")
        for f in parts:
            try:
                os.remove(f)
            except OSError:
                pass
        return 3

    base.setdefault("runs", [{}])
    base["runs"][0]["results"] = results
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(base, fh, ensure_ascii=False, indent=2)

    for f in parts:
        try:
            os.remove(f)
        except OSError:
            pass

    print(f"sarif-merge: {leidos} pase(s) -> {out} ({len(results)} hallazgos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
