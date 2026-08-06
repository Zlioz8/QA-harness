#!/usr/bin/env python3
"""Lector del registro de dimensiones (lib/dimensions.yml).

Es la única puerta a esa lista. Antes vivía copiada en seis sitios y ya había derivado: ui/app.py
leía `zap/zap-report.json` mientras ui/findings.py leía `zap/zap.sarif`, y en el perfil
anuncios_de_plataforma el primero es formato ZAP crudo — así que la pantalla de triaje se comía la
dimensión ZAP entera sin decir nada. Un solo lector es lo que impide que eso vuelva a pasar.

POR QUÉ UN PARSER PROPIO Y NO PyYAML: PyYAML no es dependencia de este laboratorio y no va a
serlo por dieciocho entradas de claves planas. Todo lo que corre en tools/ usa solo la biblioteca
estándar, a propósito — es lo que hace que el lab funcione en una máquina recién instalada.

El subconjunto soportado es deliberadamente pobre, y lib/dimensions.yml está escrito para caber
en él: una lista de mapas, claves planas de un nivel, sin anclas, sin bloques multilínea y SIN
COMENTARIOS EN LÍNEA. Lo último no es pereza: tools/doctor.sh:149-158 documenta que los
comentarios en línea de target.env ya causan un fallo real (compose se los traga como parte del
valor), y no vale la pena repetir esa ambigüedad en un archivo nuevo.

Uso desde Python:   import dimensions; dimensions.load()
Uso desde bash:     tools/dimensions.py --list id,label,artifact,kind      (TSV, una por línea)
                    tools/dimensions.py --list id,artifact --where kind=findings
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, fields as dataclass_fields

LAB = os.environ.get("LAB_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(LAB, "lib", "dimensions.yml")

# Los seis tipos de resultado. Nacen todos aunque hoy solo se consuman `findings` y `manual`:
# ampliar el esquema después obligaría a tocar otra vez a los seis consumidores.
KINDS = ("findings", "verdict", "metrics", "junit", "sbom", "manual")
CLASSES = ("light", "server", "browser", "load")
NEEDS = ("source", "target-network", "nothing", "device")


@dataclass
class Dimension:
    id: str
    label: str
    goal: str
    kind: str
    artifact: str
    inputs: str = ""      # claves de target.env que pide; "," = todas, "|" = una u otra
    script: str = ""      # EL GUION que interpreta la herramienta, bajo targets/<t>/. Puede
                          # llevar ${VAR}. Vacío = esta herramienta no lleva guion.
    script_kind: str = "" # plan | script | specs | reglas | config
    object: str = ""      # la clave que apunta a LO AUDITADO cuando no es el código (APK, imagen,
                          # documento OpenAPI). Es el sujeto, no un ajuste.
    tool: str = ""        # nombre de la HERRAMIENTA; `label` describe la DIMENSIÓN
    service: str = ""     # servicio de docker-compose.yml (a veces != id: `sbom` corre `syft`)
    profile: str = ""     # perfil de compose. Vacío = no es un servicio directo, la conduce un
                          # script de tools/ (secrets.sh orquesta gitleaks+trufflehog sobre varios
                          # repos; device-e2e.sh necesita un TTY y un teléfono enchufado)
    human: str = ""       # artefacto legible por personas, cuando no es el que consume el gate
                          # (ZAP deja un HTML además del SARIF; el informe enlaza el HTML)
    gate: str = ""          # clave de target.env; vacío = esta dimensión no juzga
    default: int | None = None
    live: bool = False
    triage: bool = False
    class_: str = "light"   # `class` es palabra reservada; el YAML sí dice `class`
    mem: str = "1g"
    measured: bool = False
    needs: str = "source"
    runner: str = "local"

    def path(self, reports_dir: str) -> str:
        return os.path.join(reports_dir, self.artifact)

    def needed_keys(self) -> list[list[str]]:
        """`inputs` como grupos de alternativas: "A,B|C" -> [["A"], ["B","C"]].

        Un grupo se cumple si CUALQUIERA de sus claves tiene valor. Es lo que distingue
        "api-lint necesita el spec" de "api-lint necesita el spec Y la URL": basta una.
        """
        return [g.split("|") for g in self.inputs.split(",") if g.strip()]

    @property
    def link(self) -> str:
        """Lo que se enlaza en el informe: el HTML si lo hay, si no el propio artefacto."""
        return self.human or self.artifact

    @property
    def exclusive(self) -> bool:
        """Una corrida de carga tiene que estar sola en la máquina.

        No es una optimización: el generador corre sin límite a propósito para no competir con el
        sistema bajo prueba, así que cualquier otra cosa masticando CPU al mismo tiempo convierte
        el p95 en una medida de la contención de esta laptop, no de la aplicación.
        """
        return self.class_ == "load"


_FIELD_NAMES = {f.name for f in dataclass_fields(Dimension)}
_BOOL = {"true": True, "false": False}


def _coerce(key: str, raw: str):
    if raw == "":
        # `gate:` sin valor significa "esta dimensión no juzga", no la cadena vacía por descuido.
        return None if key == "default" else ""
    low = raw.lower()
    if low in _BOOL:
        return _BOOL[low]
    if key == "default" and raw.lstrip("-").isdigit():
        return int(raw)
    return raw


def _parse(text: str) -> list[Dimension]:
    records: list[dict] = []
    current: dict | None = None

    for lineno, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- "):
            current = {}
            records.append(current)
            stripped = stripped[2:].strip()
        elif current is None:
            raise ValueError(f"{REGISTRY}:{lineno}: una clave antes de la primera entrada '- id:'")

        key, sep, value = stripped.partition(":")
        if not sep:
            raise ValueError(f"{REGISTRY}:{lineno}: se esperaba 'clave: valor', hay {stripped!r}")
        key = key.strip()
        # `class` es palabra reservada de Python; en el YAML se escribe tal cual porque es lo que
        # significa, y aquí se renombra al vuelo en vez de afear el archivo que leen las personas.
        field = "class_" if key == "class" else key
        if field not in _FIELD_NAMES:
            raise ValueError(f"{REGISTRY}:{lineno}: clave desconocida {key!r}")
        current[field] = _coerce(field, value.strip())

    out: list[Dimension] = []
    for rec in records:
        missing = {"id", "label", "goal", "kind", "artifact"} - rec.keys()
        if missing:
            raise ValueError(f"{REGISTRY}: la entrada {rec.get('id', '?')!r} "
                             f"no declara {', '.join(sorted(missing))}")
        dim = Dimension(**rec)
        # Validar aquí y no en el consumidor: un `kind` mal escrito debe morir al cargar el
        # registro, no tres pantallas más tarde como una dimensión que sencillamente no aparece.
        if dim.kind not in KINDS:
            raise ValueError(f"{REGISTRY}: {dim.id}: kind={dim.kind!r} no es uno de {KINDS}")
        if dim.class_ not in CLASSES:
            raise ValueError(f"{REGISTRY}: {dim.id}: class={dim.class_!r} no es uno de {CLASSES}")
        if dim.needs not in NEEDS:
            raise ValueError(f"{REGISTRY}: {dim.id}: needs={dim.needs!r} no es uno de {NEEDS}")
        out.append(dim)

    ids = [d.id for d in out]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        # Un id repetido partiría los veredictos de triaje en dos: triage.key_for() los mezcla.
        raise ValueError(f"{REGISTRY}: id repetido: {', '.join(sorted(dupes))}")

    arts = [d.artifact for d in out]
    dupe_arts = {a for a in arts if arts.count(a) > 1}
    if dupe_arts:
        # Dos dimensiones sobre el mismo archivo es justo el bug de ZAP con otra cara.
        raise ValueError(f"{REGISTRY}: artefacto compartido por dos dimensiones: "
                         f"{', '.join(sorted(dupe_arts))}")
    return out


_cache: list[Dimension] | None = None


def load(path: str = REGISTRY) -> list[Dimension]:
    """El registro, en el orden en que está escrito — que es el orden de lectura en pantalla."""
    global _cache
    if _cache is None or path != REGISTRY:
        with open(path, encoding="utf-8") as fh:
            parsed = _parse(fh.read())
        if path != REGISTRY:
            return parsed
        _cache = parsed
    return _cache


def by_id(dim_id: str) -> Dimension | None:
    return next((d for d in load() if d.id == dim_id), None)


def by_kind(kind: str) -> list[Dimension]:
    return [d for d in load() if d.kind == kind]


DOC_BEGIN = "<!-- dimensiones:inicio -->"
DOC_END = "<!-- dimensiones:fin -->"


def markdown_table() -> str:
    """La tabla de dimensiones para README.md y MANUAL_USO_QA.md.

    La documentación era la SÉPTIMA copia de esta lista, y estaba desactualizada como las otras:
    anunciaba `trufflehog.txt` como artefacto de la dimensión de secretos cuando el gate y el
    informe leen `trufflehog.sarif`, y no mencionaba que ZAP deja dos archivos distintos. Una
    tabla escrita a mano en un documento envejece más rápido que el código, porque nada falla
    cuando miente.

    `make doc-check` compara lo generado con lo que hay en los documentos y sale != 0 si difieren.
    """
    rows = ["| Dimensión | Herramienta | Comando | Artefacto | Runtime |",
            "|---|---|---|---|---|"]
    for d in load():
        art = f"`{d.artifact}`"
        if d.human:
            art += f" · `{d.human}`"
        rows.append(f"| {d.label} | {d.tool or d.id} | `make {d.goal}` | {art} | "
                    f"{'**sí**' if d.live else 'no'} |")
    return "\n".join(rows)


def _main(argv: list[str]) -> int:
    """Salida TSV para los consumidores en bash (gate.sh, run-manifest.sh)."""
    if argv and argv[0] == "--markdown":
        print(markdown_table())
        return 0

    cols, where = [], {}
    i = 0
    while i < len(argv):
        if argv[i] == "--list" and i + 1 < len(argv):
            cols = argv[i + 1].split(",")
            i += 2
        elif argv[i] == "--where" and i + 1 < len(argv):
            k, _, v = argv[i + 1].partition("=")
            where[k] = v
            i += 2
        else:
            print(f"uso: dimensions.py --list campo[,campo...] [--where campo=valor]",
                  file=sys.stderr)
            return 2
    if not cols:
        cols = ["id"]

    for dim in load():
        field = lambda c: getattr(dim, "class_" if c == "class" else c)  # noqa: E731
        if any(str(field(k)) != v for k, v in where.items()):
            continue
        print("\t".join("" if field(c) is None else str(field(c)) for c in cols))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(_main(sys.argv[1:]))
    except (OSError, ValueError) as exc:
        print(f"dimensions: {exc}", file=sys.stderr)
        sys.exit(1)
