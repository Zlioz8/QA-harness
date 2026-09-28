#!/usr/bin/env python3
"""¿Qué toca hacer AHORA con este proyecto? — el punto de entrada de una sesión.

POR QUÉ EXISTE. Auditar un proyecto son diez pasos con dependencias entre ellos, y saltarse uno
no da error: da un informe que parece completo. Ya ocurrió — se dieron por cubiertas las
dimensiones vivas de `adi` con `playwright/tests` vacío, `zap/automation.yaml` inexistente y la
comprobación hecha a mano por fuera de la herramienta. Nada lo dijo, porque no había nada que lo
dijera.

Un documento con el procedimiento no lo habría impedido: hay que acordarse de leerlo, y de leerlo
entero. Esto es lo contrario — mira el estado REAL en disco y dice la siguiente acción concreta,
con su comando. Es lo que hace que el método sobreviva a cambiar de sesión, de proyecto o de
máquina, sin que nadie tenga que recordar nada.

    tools/siguiente.py <target>        el estado y el próximo paso
    tools/siguiente.py <target> --todo el recorrido completo, con lo ya hecho marcado

REGLA DE LECTURA: un paso en ROJO bloquea a los siguientes. Uno en AMARILLO se puede posponer,
pero recorta cobertura y eso acabará escrito en el informe.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

LAB = os.environ.get("LAB_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(LAB, "tools"))

VERDE, AMAR, ROJO, GRIS = "\033[32m", "\033[33m", "\033[31m", "\033[90m"
FIN, NEG = "\033[0m", "\033[1m"


def sh(cmd: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=LAB, capture_output=True, text=True, timeout=120,
                           env={**os.environ, "LAB_DIR": LAB})
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return 1, str(e)


def existe(*partes: str) -> bool:
    p = os.path.join(LAB, *partes)
    return os.path.exists(p) and (os.path.isdir(p) or os.path.getsize(p) > 0)


def pasos(target: str) -> list[dict]:
    t = os.path.join("targets", target)
    rep = os.path.join("reports", target)
    P: list[dict] = []

    def add(id, titulo, hecho, cmd, porque, bloquea=True):
        P.append({"id": id, "titulo": titulo, "hecho": hecho, "cmd": cmd,
                  "porque": porque, "bloquea": bloquea})

    add("perfil", "Dar de alta el perfil del proyecto",
        existe(t, "target.env"), f"make new TARGET={target}",
        "sin perfil no hay contrato entre el laboratorio y el proyecto")

    add("fuente", "Tener el código en esta máquina",
        _src_ok(target), f"editar targets/{target}/target.env  (SRC_PATH, o SRC_PATH en target.env.local)",
        "SRC_PATH debe apuntar a un checkout real: es lo único sin lo cual no hay nada que analizar")

    add("deploy", "Traer el DEPLOY.md del equipo y contrastarlo",
        existe(t, "DEPLOY.md"), f"make ingest-deploy TARGET={target}",
        "es la entrega del equipo, y es comprobable: dice si el repositorio se despliega desde sí mismo")

    add("detect", "Leer el stack y proponer valores del perfil",
        _perfil_relleno(target), f"make detect TARGET={target}",
        "propone LANGS, adaptador de login y recetas leyendo el código; luego se confirman a mano")

    # `--estricto` a propósito: sin él, guion-check solo falla cuando una dimensión YA dejó
    # artefacto con un guion genérico. Para esta guía eso llega tarde — en un perfil recién
    # creado todos los guiones son la plantilla y el paso no aparecía como pendiente, que es
    # exactamente el paso que se salta. No BLOQUEA (se puede correr el estático antes de
    # afinarlos), pero se ve hasta que esté hecho.
    add("guiones", "Escribir el guion de CADA herramienta para este proyecto",
        sh(["tools/guion-check.py", target, "--estricto"])[0] == 0,
        f"make guiones TARGET={target}   (escribir lo que falte, o declarar GUION_NO_APLICA)",
        "el guion es el TECHO de la cobertura: con el ejemplo genérico se mide otro proyecto",
        bloquea=False)

    # El modelo de amenazas es el único insumo que describe el sistema ENTERO, no una muestra: se
    # escribe leyendo la arquitectura y se evalúa sin la aplicación viva. No bloquea: se puede
    # correr el estático antes de modelar, pero se ve hasta que esté hecho.
    add("amenazas", "Modelar las amenazas del sistema y evaluarlas (STRIDE)",
        existe(rep, "amenazas", "threagile.sarif"),
        f"make amenazas TARGET={target}   (escribir targets/{target}/amenazas/threagile.yaml)",
        "una amenaza modelada sin control medido es un hallazgo, no una laguna; las letras STRIDE "
        "salen de aquí, no de la prosa",
        bloquea=False)

    add("doctor", "Preflight: docker, disco, memoria, puertos, umbrales",
        True, f"make doctor TARGET={target}",
        "atrapa lo que si no aparece a mitad de una corrida como un error ilegible", bloquea=False)

    add("estatico", "Ejecutar lo que no necesita la aplicación viva",
        existe(rep, "semgrep", "semgrep.sarif"), f"make static TARGET={target}",
        "secretos, dependencias, SAST, calidad y SBOM: ya produce hallazgos sin desplegar nada")

    vivo = _live_ok(target)
    add("vivo", "Apuntar a un despliegue vivo (el del equipo, o `make up`)",
        vivo, f"editar BASE_URL/HEALTH_PATH en targets/{target}/target.env.local, o make up TARGET={target}",
        "sin aplicación respondiendo, DAST, autorización y carga no pueden medirse")

    add("cuentas", "Conseguir DOS cuentas de privilegio distinto",
        _dos_cuentas(target),
        f"pedirlas al equipo y ponerlas en targets/{target}/target.env.local",
        "la autorización es la única dimensión que ningún escáner cubre solo: hace falta que "
        "una cuenta de privilegio BAJO intente lo que solo la ALTA debería poder")

    add("dinamico", "Ejecutar las dimensiones vivas",
        existe(rep, "zap", "zap.sarif"), f"make live TARGET={target}",
        "ZAP, matriz de autorización y carga")

    # Los tres pilares AAA miden los controles que el modelo de amenazas da por supuestos: qué
    # responde el login (authn), qué alcanza cada rol (authz) y qué queda registrado (acct).
    add("aaa", "Medir los controles AAA en vivo (autenticación · autorización · auditoría)",
        existe(rep, "aaa", "authn.sarif") or existe(rep, "aaa", "authz.sarif"),
        f"make aaa TARGET={target}   (aaa/authn.json, playwright/authz-matrix.json, aaa/acct.json; "
        f"AAA_DB_URL en target.env.local para la auditoría)",
        "una sonda que falla es un control que no está; un evento sin rastro es repudio: ninguno de "
        "los dos se administra por presupuesto",
        bloquea=False)

    add("triaje", "Juzgar los hallazgos",
        _hay_triaje(rep), "make ui   → pestaña de Triaje",
        "una lista sin juicio no es un informe: la mitad de las señales son ruido en su contexto, "
        "y decidir cuáles es trabajo humano")

    add("riesgos", "Fundamentar cada hallazgo confirmado (OWASP/MITRE/STRIDE/CVSS/ISO 27001)",
        _riesgos_hechos(target), f"make riesgos ANDAMIAR=1 TARGET={target}",
        "por cada riesgo confirmado, un documento que PRUEBA que es tangible (dónde/cómo/medios) y "
        "lo ancla a marcos reconocidos: material formativo para el equipo y trazabilidad para "
        "una futura certificación ISO/IEC 27001")

    add("veredicto", "Veredicto y manifiesto de la corrida",
        existe(rep, "RUN.md"), f"make gate run-manifest TARGET={target}",
        "el veredicto y la cobertura real, para que el informe no pueda contradecirlos")

    add("informe", "Generar el entregable",
        _informe_hecho(target), f"make informe TARGET={target}",
        "INFORME_TECNICO_VERIFICACION_R<n>_<PROYECTO>.md, con los ⟨PENDIENTE⟩ que exigen una persona")

    return P


def _src_ok(target: str) -> bool:
    rc, out = sh(["bash", "-c",
                  f'ENVFILE=targets/{target}/target.env; . tools/lib-env.sh; envget SRC_PATH'])
    p = out.strip()
    return bool(p) and os.path.isdir(p)


def _perfil_relleno(target: str) -> bool:
    rc, out = sh(["bash", "-c",
                  f'ENVFILE=targets/{target}/target.env; . tools/lib-env.sh; envget LANGS'])
    return bool(out.strip())


def _live_ok(target: str) -> bool:
    return sh(["tools/require-live.sh", target])[0] == 0


def _dos_cuentas(target: str) -> bool:
    vals = []
    for k in ("ROLE_A_USER", "ROLE_B_USER"):
        rc, out = sh(["bash", "-c",
                      f'ENVFILE=targets/{target}/target.env; . tools/lib-env.sh; envget {k}'])
        vals.append(out.strip())
    return all(vals) and vals[0] != vals[1]


def _hay_triaje(rep: str) -> bool:
    p = os.path.join(LAB, rep, "triage.json")
    try:
        return len(json.load(open(p, encoding="utf-8"))) > 0
    except Exception:
        return False


def _informe_hecho(target: str) -> bool:
    d = os.path.join(LAB, "reports", target)
    return os.path.isdir(d) and any(x.startswith("INFORME_TECNICO_VERIFICACION_R")
                                    for x in os.listdir(d))


def _riesgos_hechos(target: str) -> bool:
    # Verde cuando tools/riesgos.py sale 0: cada hallazgo confirmado tiene su documento de
    # fundamentación completo. Se delega en la herramienta para no duplicar el criterio.
    try:
        r = subprocess.run([os.path.join(LAB, "tools", "riesgos.py"), target],
                           capture_output=True, env={**os.environ, "LAB_DIR": LAB})
        return r.returncode == 0
    except Exception:
        return False


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2
    target = argv[1]
    todo = "--todo" in argv
    P = pasos(target)

    print(f"\n{NEG}== {target}: dónde estás =={FIN}\n")
    pendiente = None
    for p in P:
        if p["hecho"]:
            if todo:
                print(f"  {VERDE}✓{FIN} {p['titulo']}")
            continue
        color = ROJO if p["bloquea"] else AMAR
        marca = "✗" if p["bloquea"] else "!"
        print(f"  {color}{marca}{FIN} {p['titulo']}")
        if pendiente is None and p["bloquea"]:
            pendiente = p

    if pendiente is None:
        pendiente = next((p for p in P if not p["hecho"]), None)

    print()
    if pendiente is None:
        print(f"{VERDE}Todo el recorrido está cubierto.{FIN} Reaudita con:")
        print(f"    make ingest-deploy static live gate TARGET={target}")
        print(f"    make informe TARGET={target} RONDA_NUEVA=1")
        return 0

    print(f"{NEG}SIGUIENTE PASO{FIN}  {pendiente['titulo']}")
    print(f"    {pendiente['cmd']}")
    print(f"  {GRIS}por qué: {pendiente['porque']}{FIN}")
    restantes = [p for p in P if not p["hecho"]]
    if len(restantes) > 1:
        print(f"\n  quedan {len(restantes)} paso(s). Recorrido completo: "
              f"tools/siguiente.py {target} --todo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
