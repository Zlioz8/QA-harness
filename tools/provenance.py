#!/usr/bin/env python3
"""¿Este artefacto midió el sistema que el perfil describe HOY?

Un artefacto en disco no lo dice. `zap.sarif` es un archivo con alertas; nada en él distingue si
salieron del despliegue del 166 o de un Moodle efímero levantado hace tres días en esta laptop.
Y el veredicto SUMA lo que encuentra, así que un `GATE FAILED` puede estar hecho de evidencia
sobre dos sistemas distintos — medido aquí: cinco dimensiones de hacía minutos contra el 166,
más sonar y playwright de hacía TRES DÍAS contra otro despliegue, las diez marcadas `yes`.

QUÉ SE COMPARA, Y POR QUÉ NO LO MISMO PARA TODAS:
    needs: source          -> el COMMIT. Cambiar de despliegue no invalida un SAST.
    needs: target-network  -> la URL. Cambiar de rama no invalida un DAST.
Comparar ambas cosas en todas excluiría dimensiones que siguen siendo válidas, y un aviso que
salta cuando no toca se aprende a ignorar.

QUÉ SE HACE CON UNA DISCREPANCIA: se AVISA y se EXCLUYE del veredicto. No se falla. Un artefacto
sobre otro sistema no es un fallo de este sistema — es que no hay evidencia sobre este. Es
`NO EJECUTADO` con otra causa, y merece el mismo trato: no contar, y decirlo.

Salida (una línea por dimensión, para gate.sh):
    <dim> <estado> <detalle>
donde estado = ok | excluida | sin-sello
"""
import json
import os
import sys

LAB = os.environ.get("LAB_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(LAB, "tools"))
import dimensions  # noqa: E402


def _perfil(target):
    """Los valores efectivos del perfil, con el override local encima."""
    sys.path.insert(0, os.path.join(LAB, "ui"))
    import contract  # noqa: PLC0415
    base = os.path.join(LAB, "targets", target, "target.env")
    v = {f.key: f.value for f in contract.load(base).fields if not f.commented}
    if os.path.isfile(base + ".local"):
        for f in contract.load(base + ".local").fields:
            if not f.commented and f.value.strip():
                v[f.key] = f.value
    return v


def estado(target, dim, valores=None):
    """(estado, detalle) de la procedencia de una dimensión."""
    valores = valores if valores is not None else _perfil(target)
    rep = os.path.join(LAB, "reports", target)
    if not os.path.exists(os.path.join(rep, dim.artifact)):
        return "ok", ""                      # sin artefacto no hay nada que atribuir
    sello = os.path.join(rep, ".provenance", f"{dim.id}.json")
    if not os.path.isfile(sello):
        # Todo lo producido antes de que existiera el sello. NO se excluye: hacer desaparecer del
        # veredicto lo que ya estaba convertiría una mejora en un muro. Se dice, y ya.
        return "sin-sello", "producido antes de que se sellara la procedencia"
    try:
        with open(sello, encoding="utf-8") as fh:
            s = json.load(fh)
    except (OSError, ValueError):
        return "sin-sello", "sello ilegible"

    if dim.needs == "target-network":
        antes, ahora = s.get("app_internal_url", ""), valores.get("APP_INTERNAL_URL", "")
        if antes and ahora and antes != ahora:
            return "excluida", f"midió {antes}, el perfil apunta ahora a {ahora}"
    else:
        antes, ahora = s.get("commit", ""), ""
        # El commit de AHORA se relee del checkout, no del sello: es lo que hace la comparación.
        src = valores.get("SRC_PATH", "")
        if src:
            import subprocess  # noqa: PLC0415
            try:
                ahora = subprocess.run(["git", "-C", src, "rev-parse", "--short", "HEAD"],
                                       capture_output=True, text=True, timeout=10).stdout.strip()
            except Exception:  # noqa: BLE001
                ahora = ""
        if antes and ahora and antes.split("+")[0] != ahora:
            return "excluida", f"midió el commit {antes}, el checkout está en {ahora}"
    return "ok", ""


def main(argv):
    if len(argv) != 1:
        print("uso: provenance.py <target>", file=sys.stderr)
        return 2
    target = argv[0]
    valores = _perfil(target)
    for dim in dimensions.load():
        est, det = estado(target, dim, valores)
        print(f"{dim.id}\t{est}\t{det}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
