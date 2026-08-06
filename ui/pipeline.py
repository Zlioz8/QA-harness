"""El estado de la tubería de un proyecto, en las cuatro etapas del diagrama conceptual:

    ENTRADA  ->  HERRAMIENTAS  ->  SALIDAS  ->  ANÁLISIS
    .env         cada una con     el artefacto  veredicto + quién
                 lo que pide      que dejó      lo juzga

POR QUÉ ESTE MÓDULO. La pantalla de proyecto era una rejilla de botones de `make` agrupados en
code/live/admin. Eso es un mando a distancia del Makefile: enseña la fontanería, no el proceso.
El operador no podía ver, sin salir de la pantalla, QUÉ le falta rellenar para que una herramienta
concreta pueda correr — y esa es justamente la pregunta que se hace.

Todo sale del registro (lib/dimensions.yml) y del perfil (target.env). Este módulo no sabe nada de
ninguna herramienta en particular: añadir una dimensión la hace aparecer en las cuatro columnas
sin tocar esto ni render.py.

TRES ESTADOS, NUNCA DOS. Es la disciplina del laboratorio entero, aquí aplicada a la pantalla:
  · ejecutada      hay artefacto y se puede leer
  · NO EJECUTADA   se podía correr y no se corrió — es una omisión
  · no aplica      este perfil no puede medirlo (falta una entrada, o el peldaño no da)
La tercera es la que la interfaz anterior no tenía, y sin ella un hueco parece una decisión.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.environ.get("LAB_DIR", os.getcwd()), "tools"))
import dimensions   # noqa: E402
import guion as guionlib  # noqa: E402  — el archivo que interpreta cada herramienta
import provenance  # noqa: E402  — ¿midió el sistema que el perfil describe hoy?
import sarif        # noqa: E402
import triage as triagelib  # noqa: E402

# Estados de una dimensión, en el orden en que importan al leer la pantalla.
RAN, NOT_RUN, NA = "ejecutada", "NO EJECUTADA", "no aplica"


def overlay(profile_path: str):
    """El perfil EFECTIVO: target.env con target.env.local encima.

    Sin esto la columna de entradas miente. `contract.load()` lee solo el archivo versionado, y
    los valores del despliegue real —la URL de salud, el spec OpenAPI, las credenciales— viven a
    propósito en `.local`, que no se versiona. La pantalla marcaría en rojo claves que SÍ están
    puestas, y mandaría al operador a rellenar lo que ya rellenó.

    Misma regla que tools/lib-env.sh: el `.local` gana cuando trae la clave con valor NO vacío.
    Un valor vacío no anula — en el contrato, vacío significa «no aplica, salto documentado», y un
    `.local` incompleto no debe convertir eso en otra cosa.
    """
    import contract  # noqa: PLC0415
    base = contract.load(profile_path)
    valores = {f.key: f.value for f in base.fields if not f.commented}
    if os.path.isfile(profile_path + ".local"):
        for f in contract.load(profile_path + ".local").fields:
            if not f.commented and f.value.strip():
                valores[f.key] = f.value
    return valores


def _value(valores: dict, key: str) -> str:
    return (valores.get(key) or "").strip()


def missing_inputs(dim, valores) -> list[str]:
    """Qué claves le faltan a ESTA dimensión para poder correr.

    Un grupo separado por `|` se cumple con cualquiera de sus claves: api-lint necesita el spec
    como archivo O como URL, no las dos.
    """
    missing = []
    for group in dim.needed_keys():
        if not any(_value(valores, k) for k in group):
            missing.append(" o ".join(group))
    return missing


def state_of(dim, valores, reports_dir: str, tier: int, live_ok: bool):
    """(estado, motivo, datos) de una dimensión.

    `datos` es lo que el artefacto contiene cuando se pudo leer, o None.
    """
    path = dim.path(reports_dir)
    existe = os.path.exists(path)

    # El ARTEFACTO manda sobre la configuracion actual. Una dimension con artefacto SE EJECUTO,
    # aunque hoy le falte una entrada: el perfil pudo cambiar despues, o la herramienta traia un
    # valor por defecto. Marcarla "no aplica" borraria de la pantalla una corrida que si ocurrio,
    # que es la version de pantalla del error que este laboratorio persigue en todas partes.
    if not existe:
        faltan = missing_inputs(dim, valores)
        if faltan:
            return NA, "falta " + ", ".join(faltan), None
        if dim.live and (tier < 2 or not live_ok):
            return NA, "necesita la aplicación respondiendo", None
        return NOT_RUN, "", None

    if dim.kind == "findings":
        data = sarif.load_sarif(path, dim.id)
        if data is None:
            # El archivo existe y no se deja leer: es peor que ausente, porque parece cobertura.
            return NOT_RUN, "el artefacto existe pero no es SARIF legible", None
        return RAN, "", data
    # Los demás tipos todavía no tienen lector propio (fase 2). Presente = ejecutada.
    return RAN, "", None


def build(target: str, profile_path: str, reports_dir: str, tier: int, live_ok: bool,
          target_dir: str = "", template_dir: str = "") -> dict:
    """Las cuatro etapas, listas para pintar."""
    valores = overlay(profile_path)
    verdicts = triagelib.load(reports_dir)
    prov = {}
    rows, total, judged_keys = [], 0, set()

    for dim in dimensions.load():
        estado, motivo, data = state_of(dim, valores, reports_dir, tier, live_ok)
        try:
            prov[dim.id] = provenance.estado(target, dim, valores)
        except Exception:  # noqa: BLE001 — la procedencia informa; nunca tumba la pantalla
            prov[dim.id] = ("ok", "")
        n = data["count"] if data else None
        sev = data["sev"] if data else {}
        if data:
            total += data["count"]
            for f in data["findings"]:
                k = triagelib.key_for(dim.id, f["rule"], f["loc"])
                if verdicts.get(k, {}).get("verdict"):
                    judged_keys.add(k)

        rows.append({
            "id": dim.id, "label": dim.label, "tool": dim.tool or dim.id,
            "goal": dim.goal, "kind": dim.kind,
            "inputs": dim.needed_keys(), "missing": missing_inputs(dim, valores),
            "artifact": dim.artifact, "link": dim.link,
            "estado": estado, "motivo": motivo,
            "count": n, "sev": sev,
            "clase": dim.class_, "mem": dim.mem, "medido": dim.measured,
            "live": dim.live, "triage": dim.triage,
            # `sin graduar` es información, no un detalle: un umbral de conteo sobre hallazgos
            # que no traen severidad es una cifra inventada, y hay que poder verlo.
            "graduado": sarif.is_graded(data) if data else None,
            # El GUION: el archivo que la herramienta interpreta. None cuando esa herramienta no
            # lleva ninguno (trivy, syft, trufflehog: apuntas al árbol y ya).
            "guion": guionlib.analizar(dim, valores, target_dir, template_dir)
                     if target_dir else None,
            # El OBJETO auditado cuando no es el código: el APK, una imagen, el documento OpenAPI.
            "objeto": ([k for k in dim.object.split("|") if _value(valores, k)] or None)
                      if dim.object else None,
            "objeto_pide": dim.object,
            "prov": prov[dim.id][0],
            "prov_detalle": prov[dim.id][1],
        })

    hechas = sum(1 for r in rows if r["estado"] == RAN)
    return {
        "target": target,
        "rows": rows,
        "resumen": {
            "total": len(rows),
            "ejecutadas": hechas,
            "no_ejecutadas": sum(1 for r in rows if r["estado"] == NOT_RUN),
            "no_aplican": sum(1 for r in rows if r["estado"] == NA),
            "hallazgos": total,
            "juzgados": len(judged_keys),
            "sin_juzgar": max(0, total - len(judged_keys)),
        },
    }
