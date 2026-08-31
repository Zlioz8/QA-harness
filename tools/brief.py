#!/usr/bin/env python3
"""El estado de un proyecto en UNA pantalla, generado — no releído.

POR QUÉ EXISTE. `make siguiente` dice qué toca AHORA; no dice qué se sabe ya. Para eso, quien
retoma un proyecto —o quien lo audita en otra sesión— acaba releyendo el perfil entero
(`target.env` son 17 KB de contrato comentado), el informe de la ronda anterior y la bitácora.
Medido en la sesión del 21/08/2026: reconstruir ese contexto costó más que ejecutar las
dimensiones. Con 18 proyectos por delante, ese coste se paga 18 veces.

Todo lo que se relee está YA en disco en forma estructurada: el perfil lo lee `lib-env.sh`, los
repositorios `lib-repos.sh`, las dimensiones `lib/dimensions.yml`, los hallazgos
`hallazgos.tsv`, el siguiente paso `siguiente.py`. Esto los junta y los imprime.

QUÉ NO HACE, a propósito:
  * No mide nada nuevo. Es un lector; si una cifra no está en disco, aquí sale un hueco.
  * No sustituye al informe. El informe es el juicio; esto es el estado.
  * No inventa frescura: cada artefacto sale con su edad, porque un SARIF de anteayer contra
    otro despliegue no es la misma evidencia que uno de hace diez minutos (es el mismo motivo
    de MAX_ARTIFACT_AGE_H en el perfil).

    tools/brief.py <target>     el estado    (o `make brief TARGET=<target>`)
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

LAB = os.environ.get("LAB_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(LAB, "tools"))

import dimensions  # noqa: E402
import hallazgos as H  # noqa: E402

VERDE, AMAR, ROJO, GRIS, NEG, FIN = (
    "\033[32m", "\033[33m", "\033[31m", "\033[90m", "\033[1m", "\033[0m")

# Las claves del perfil que contestan «¿contra qué se está midiendo?». No son todas: son las que
# cambian la lectura de cualquier cifra posterior.
CLAVES = ["SRC_PATH", "BASE_URL", "APP_INTERNAL_URL", "HEALTH_PATH", "AUTH_ADAPTER",
          "DEPLOY_BRANCHES", "LANGS", "OPENAPI_SPEC", "GUION_NO_APLICA",
          "ROLE_A_USER", "ROLE_B_USER", "COMPOSE_PROJECT_NAME"]


def sh(cmd: list[str], timeout: int = 120) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=LAB, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "LAB_DIR": LAB})
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:  # noqa: BLE001 — un brief nunca debe reventar la sesión
        return 1, str(e)


def perfil(target: str) -> dict[str, str]:
    """Lee el perfil por el ÚNICO lector que existe (lib-env.sh), no por un parser propio.

    Una llamada, no una por clave: `envget` es barato pero arrancar bash doce veces no.
    """
    guion = "; ".join(f'printf "%s=%s\\n" {k} "$(envget {k})"' for k in CLAVES)
    rc, out = sh(["bash", "-c", f'ENVFILE=targets/{target}/target.env; . tools/lib-env.sh; {guion}'])
    d = {}
    for linea in out.splitlines():
        if "=" in linea:
            k, _, v = linea.partition("=")
            d[k.strip()] = v.strip()
    return d


def edad(path: str) -> str:
    try:
        seg = time.time() - os.path.getmtime(path)
    except OSError:
        return ""
    if seg < 90:
        return f"hace {int(seg)} s"
    if seg < 5400:
        return f"hace {int(seg // 60)} min"
    if seg < 172800:
        return f"hace {int(seg // 3600)} h"
    return f"hace {int(seg // 86400)} d"


def cuenta(art: str) -> str:
    """Hallazgos de un SARIF, con el MISMO contador que usa el veredicto (gate-count.py).

    Contar aquí de otra manera sería el defecto que ese archivo documenta: dos lectores del
    mismo formato que acaban discrepando, y una pantalla que contradice al gate.
    """
    rc, out = sh([os.path.join(LAB, "tools", "gate-count.py"), art], timeout=60)
    out = out.strip().splitlines()[-1] if out.strip() else ""
    return out if out.isdigit() else ""


def bloque_perfil(target: str, p: dict[str, str]) -> None:
    src = p.get("SRC_PATH", "")
    ok = os.path.isdir(src) if src else False
    print(f"{NEG}PERFIL{FIN}")
    print(f"  SRC_PATH        {src or '—'}  {VERDE + 'existe' + FIN if ok else ROJO + 'NO EXISTE' + FIN}")
    print(f"  despliegue      {p.get('BASE_URL') or '—'}   salud: {p.get('HEALTH_PATH') or '—'}")
    print(f"  login/ramas     adaptador {p.get('AUTH_ADAPTER') or '—'} · DEPLOY_BRANCHES "
          f"{p.get('DEPLOY_BRANCHES') or '(defecto: dev dev2)'} · LANGS {p.get('LANGS') or '—'}")
    a, b = p.get("ROLE_A_USER", ""), p.get("ROLE_B_USER", "")
    if a and b and a != b:
        cuentas = f"{VERDE}dos cuentas de privilegio distinto{FIN}"
    elif a or b:
        cuentas = f"{AMAR}solo una cuenta — la matriz de autorización NO es medible{FIN}"
    else:
        cuentas = f"{ROJO}sin cuentas — autorización NO DISPONIBLE{FIN}"
    local = os.path.join(LAB, "targets", target, "target.env.local")
    print(f"  cuentas         {cuentas}"
          + (f"  {GRIS}(valores en target.env.local, {edad(local)}){FIN}" if os.path.exists(local) else ""))
    if p.get("GUION_NO_APLICA"):
        print(f"  no aplica       {p['GUION_NO_APLICA']}  {GRIS}(declarado, con razón en el perfil){FIN}")


def bloque_repos(p: dict[str, str]) -> None:
    src = p.get("SRC_PATH", "")
    if not src or not os.path.isdir(src):
        return
    rc, out = sh(["bash", "-c",
                  f'. tools/lib-repos.sh; discover_repos "$1"; echo "---"; non_repo_entries "$1"',
                  "_", src])
    repos: list[str] = []
    fuera: list[str] = []
    cur = repos
    for linea in out.splitlines():
        if linea.strip() == "---":
            cur = fuera
            continue
        if linea.strip():
            cur.append(linea.strip())
    print(f"{NEG}REPOSITORIOS{FIN}  {GRIS}(descubiertos bajo SRC_PATH; el resto se ignora y se declara en RUN.md){FIN}")
    for r in repos or ["(ninguno)"]:
        d = src if r == "." else os.path.join(src, r)
        rc, ref = sh(["git", "-C", d, "log", "-1", "--format=%h %cs"])
        rc2, st = sh(["git", "-C", d, "status", "--porcelain"])
        rc3, br = sh(["git", "-C", d, "rev-parse", "--abbrev-ref", "HEAD"])
        sucio = len([x for x in st.splitlines() if x.strip()])
        plural = "cambio" if sucio == 1 else "cambios"
        marca = f"{AMAR}{sucio} {plural} sin commitear{FIN}" if sucio else f"{GRIS}limpio{FIN}"
        print(f"  {os.path.basename(d)}  @ {br.strip()} {ref.strip()}  {marca}")
    if fuera:
        print(f"  {GRIS}fuera del análisis: {', '.join(fuera[:6])}"
              f"{' …' if len(fuera) > 6 else ''}{FIN}")


def bloque_dimensiones(target: str, p: dict[str, str]) -> None:
    rep = os.path.join(LAB, "reports", target)
    no_aplica = {x.strip() for x in (p.get("GUION_NO_APLICA") or "").split(",") if x.strip()}
    print(f"{NEG}DIMENSIONES{FIN}  {GRIS}(✓ con artefacto · · sin ejecutar · ⊘ declarada no aplicable){FIN}")
    hechas = pend = 0
    for d in dimensions.load():
        if d.id in no_aplica:
            print(f"  ⊘ {d.label[:38]:38s} {GRIS}declarada NO APLICA en el perfil{FIN}")
            continue
        art = os.path.join(rep, d.artifact) if d.artifact else ""
        if art and os.path.exists(art) and os.path.getsize(art) > 0:
            hechas += 1
            n = cuenta(art) if d.kind == "findings" else ""
            det = f"{n} hallazgos" if n else d.kind
            print(f"  {VERDE}✓{FIN} {d.label[:38]:38s} {edad(art):>10s}  {det}")
        else:
            pend += 1
            marca = f"{AMAR}vive{FIN}" if d.live else " "
            print(f"  {GRIS}·{FIN} {d.label[:38]:38s} {GRIS}sin artefacto{FIN}  {marca}")
    print(f"  {GRIS}{hechas} con evidencia · {pend} sin ejecutar{FIN}")


def bloque_hallazgos(target: str) -> None:
    filas = H.cargar(os.path.join(LAB, "targets", target))
    if not filas:
        print(f"{NEG}HALLAZGOS{FIN}  {GRIS}registro vacío: nada triado todavía{FIN}")
        return
    sev: dict[str, int] = {}
    abiertos = 0
    for f in filas:
        if (f.get("estado") or "abierto") != "cerrado":
            abiertos += 1
            sev[f.get("severidad") or "sin severidad"] = sev.get(f.get("severidad") or "sin severidad", 0) + 1
    orden = ["critical", "high", "medium", "low", "info"]
    partes = [f"{sev[s]} {s}" for s in orden if s in sev]
    partes += [f"{v} {k}" for k, v in sev.items() if k not in orden]
    print(f"{NEG}HALLAZGOS{FIN}  ronda R{H.ronda_actual(filas)} · {abiertos} abiertos · "
          + " · ".join(partes))


def bloque_contexto(target: str) -> None:
    p = os.path.join(LAB, "targets", target, "CONTEXTO.md")
    print(f"{NEG}CONTEXTO{FIN}")
    if not os.path.exists(p):
        print(f"  {AMAR}no hay targets/{target}/CONTEXTO.md{FIN} — escríbelo al cerrar la sesión "
              f"(plantilla en targets/_template/CONTEXTO.md)")
        return
    print(f"  targets/{target}/CONTEXTO.md ({edad(p)}) — lo escrito a mano; léelo entero antes de decidir:")
    with open(p, encoding="utf-8") as fh:
        vistas = 0
        for linea in fh:
            linea = linea.rstrip()
            if not linea or linea.startswith("#") or linea.startswith(">"):
                continue
            print(f"    {GRIS}{linea[:100]}{FIN}")
            vistas += 1
            if vistas >= 6:
                print(f"    {GRIS}…{FIN}")
                break


def bloque_siguiente(target: str) -> None:
    rc, out = sh([os.path.join(LAB, "tools", "siguiente.py"), target], timeout=180)
    lineas = [x for x in out.splitlines() if "SIGUIENTE PASO" in x or x.startswith("    ")]
    print(f"{NEG}SIGUIENTE{FIN}  {GRIS}(de tools/siguiente.py — el que manda){FIN}")
    for x in lineas[:3]:
        print("  " + x.strip())


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2
    target = argv[1]
    if not os.path.isdir(os.path.join(LAB, "targets", target)):
        print(f"{ROJO}no existe targets/{target}{FIN} — `make new TARGET={target}`", file=sys.stderr)
        return 2
    p = perfil(target)
    print(f"\n{NEG}== {target} — estado =={FIN}  {GRIS}{time.strftime('%Y-%m-%d %H:%M')}{FIN}\n")
    for bloque in (lambda: bloque_perfil(target, p),
                   lambda: bloque_repos(p),
                   lambda: bloque_dimensiones(target, p),
                   lambda: bloque_hallazgos(target),
                   lambda: bloque_contexto(target),
                   lambda: bloque_siguiente(target)):
        bloque()
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
