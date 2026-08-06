"""Read and write a target profile without knowing anything about any project.

`targets/<name>/target.env` is the whole contract between the lab and one audited project, and
it is already self-describing:

    # ---- source -----------------------------------------------------        -> a fieldset
    # Absolute path to a checkout you already have. Preferred: no SSH keys      -> help text
    # enter a container (lab finding L2).
    SRC_PATH=/absolute/path/to/repo                                            -> a field
    QODANA_IMAGE=            # empty = skip                                    -> field + hint

So the web form is *generated from the contract*. Adding a project does not touch the UI, and
neither does adding a key: it shows up on its own, with its help text. Any form built from a
hardcoded list of fields would be a second copy of the contract, and copies drift.

Writing back edits ONLY the value portion of the line that changed. The comments in target.env
are the documentation of the contract — a UI that flattened them on first save would destroy the
thing that makes the lab usable, and the operator would not notice until much later.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Iterator

# Keys whose value must never be echoed back to the browser or into a log stream.
SECRET_RE = re.compile(r"(PASS|PASSWORD|SECRET|TOKEN|APIKEY|API_KEY)$", re.I)

# Fields the contract requires for each dimension, with what is lost when they are missing.
# This is the one piece of judgement the UI carries, and it is about the CONTRACT, not about any
# project — it is the information that today lives only in the migration report.
REQUIREMENTS = {
    "SRC_PATH": "Sin esto no hay nada que analizar: es el único campo imprescindible.",
    "BASE_URL": "Sin esto no hay DAST, ni pruebas de autorización, ni carga.",
    "HEALTH_PATH": "Sin esto no se distingue «no hay hallazgos» de «no había nada corriendo».",
    "AUTH_ADAPTER": "Con «none» solo se cubre la superficie sin autenticar.",
    "ROLE_A_USER": "Cuenta REAL de privilegio alto, entregada por el operador QA. El laboratorio ya no siembra cuentas.",
    "ROLE_B_USER": "Y una REAL de privilegio bajo: sin ella no hay nada que intentar indebidamente.",
}

KEY_RE = re.compile(r"^([A-Za-z_]\w*)=(.*)$")


def _section_name(line: str) -> str | None:
    """`# ---- source ------` -> "source".

    Exige guiones a AMBOS lados. Antes bastaba con que el comentario empezara por `--`, y eso
    convertía en cabecera de sección cualquier línea de ayuda que citara una opción de línea de
    comandos. Encontrado en cuanto la plantilla documentó el filtro de fuzzing:

        #   --exclude-method PUT --exclude-method DELETE --exclude-path-regex create

    pasó a ser una «sección» con ese nombre completo, y se tragó los TRECE campos siguientes:
    en el formulario de la interfaz aparecían bajo un título absurdo, lejos de donde les toca.
    Un archivo de configuración tiene que poder documentar banderas sin que el formulario se
    reorganice solo. Se sigue sin usar regex: dos rachas de guiones codiciosas alrededor de un
    grupo perezoso hacen backtracking pésimo en las líneas separadoras largas.
    """
    body = line.lstrip("#").strip()
    if not (body.startswith("--") and body.endswith("--")):
        return None
    name = body.strip("-").strip()
    return name or None


@dataclass
class Field:
    key: str
    value: str
    help: str = ""
    hint: str = ""          # trailing comment on the same line
    section: str = "general"
    line_no: int = 0
    commented: bool = False  # `#KEY=value` — an option the profile shows but does not use

    @property
    def secret(self) -> bool:
        return bool(SECRET_RE.search(self.key))

    @property
    def required(self) -> bool:
        """Si el formulario debe marcarlo con un asterisco."""
        return self.key in REQUIREMENTS

    @property
    def why_required(self) -> str:
        """Qué se pierde sin este campo. Siempre disponible — es el texto del tooltip del
        asterisco, que debe estar aunque la ayuda del perfil ya lo cuente en el cuerpo."""
        return REQUIREMENTS.get(self.key, "")

    @property
    def requirement(self) -> str:
        """Qué se pierde si este campo queda vacío — SOLO si el perfil no lo dice ya.

        REQUIREMENTS nació cuando target.env no explicaba nada: era el único sitio donde constaba
        qué dimensión se caía por dejar un campo en blanco. Desde que la plantilla lo dice en su
        propia ayuda ([OBLIGATORIO] / [DESBLOQUEA ...]), repetirlo aquí imprime la misma frase dos
        veces seguidas bajo cada campo — visible en la pantalla de configuración.
        Y peor que feo: son dos copias del mismo conocimiento, y la de aquí no la lee nadie al
        editar el .env, así que es la que se queda atrás.

        El contrato es el archivo. Este texto solo cubre el hueco de un perfil antiguo cuya
        plantilla todavía no lo explicaba.
        """
        if self.help.strip():
            return ""
        return REQUIREMENTS.get(self.key, "")


@dataclass
class Profile:
    path: str
    lines: list[str] = field(default_factory=list)
    fields: list[Field] = field(default_factory=list)

    def get(self, key: str, default: str = "") -> str:
        for f in self.fields:
            if f.key == key and not f.commented:
                return f.value
        return default

    def sections(self) -> Iterator[tuple[str, list[Field]]]:
        seen: list[str] = []
        for f in self.fields:
            if f.section not in seen:
                seen.append(f.section)
        for name in seen:
            yield name, [f for f in self.fields if f.section == name]

    def secret_values(self) -> list[str]:
        """Non-empty secret values, for redaction before anything reaches the browser."""
        return [f.value for f in self.fields if f.secret and f.value.strip()]


def load(path: str) -> Profile:
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    prof = Profile(path=path, lines=lines)
    section = "general"
    pending: list[str] = []   # comment lines seen since the last field: the help text

    for i, raw in enumerate(lines):
        line = raw.rstrip("\n")

        if line.lstrip().startswith("#"):
            name = _section_name(line)
            if name:
                section = name
                pending = []
                continue

        stripped = line.strip()

        # A commented-out assignment is an option, not prose — keep it as a disabled field so
        # the operator can see it exists (REPO_URL, DEPLOY_KEY...) instead of it being invisible.
        if stripped.startswith("#"):
            body = stripped.lstrip("#").strip()
            km = KEY_RE.match(body)
            if km and not body.startswith(" "):
                prof.fields.append(Field(key=km.group(1), value=km.group(2).strip(),
                                         help="\n".join(pending), section=section,
                                         line_no=i, commented=True))
                pending = []
            elif body and not re.fullmatch(r"[=\-_*#]{4,}", body):
                # Skip decorative banners (`# =========`): they are visual separators, not help.
                pending.append(body)
            continue

        km = KEY_RE.match(line)
        if km:
            value = km.group(2)
            hint = ""
            # Trailing comment: `QODANA_IMAGE=   # empty = skip`
            if "#" in value:
                value, hint = value.split("#", 1)
                hint = hint.strip()
            prof.fields.append(Field(key=km.group(1), value=value.strip(), hint=hint,
                                     help="\n".join(pending), section=section, line_no=i))
            pending = []
        elif not stripped:
            pending = []

    return prof


def save(prof: Profile, updates: dict[str, str]) -> list[str]:
    """Apply `updates` in place, touching only the value part of each changed line.

    Returns the keys actually modified. Unknown keys are ignored rather than appended: a typo in
    a form post must not silently grow the contract with a key nothing reads.
    """
    by_key = {f.key: f for f in prof.fields if not f.commented}
    changed: list[str] = []

    for key, new_value in updates.items():
        f = by_key.get(key)
        if f is None or new_value == f.value:
            continue
        original = prof.lines[f.line_no]
        # Rebuild the line preserving any trailing comment exactly as it was.
        rebuilt = f"{key}={new_value}"
        if f.hint:
            rebuilt = f"{rebuilt}   # {f.hint}"
        prof.lines[f.line_no] = rebuilt
        f.value = new_value
        changed.append(key)
        del original

    if changed:
        tmp = prof.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(prof.lines) + "\n")
        os.replace(tmp, prof.path)   # atomic: never leave a half-written contract behind
    return changed


def redact(text: str, secrets: list[str]) -> str:
    """Replace known secret values with a marker.

    The lab passes credentials to the tools it runs, and tools echo their configuration more
    often than one expects. Cheap insurance so a password never lands in a browser log pane.
    """
    for s in secrets:
        if s and len(s) >= 4:
            text = text.replace(s, "«redactado»")
    return text
