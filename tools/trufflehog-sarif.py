#!/usr/bin/env python3
"""Convierte la salida de TruffleHog a SARIF.

EL ADAPTADOR QUE FALTABA. tools/secrets.sh:87-97 lleva ejecutando TruffleHog desde siempre y
volcando su JSON en reports/<t>/trufflehog.txt — un archivo que NO LEE NADIE: ni tools/gate.sh,
ni la tabla de cobertura de tools/run-manifest.sh, ni el informe, ni las pantallas de triaje.
Exactamente el modo de fallo que este laboratorio existe para no cometer: una dimensión que se
ejecuta, deja artefacto, y aun así no llega al veredicto.

Y es la que más importa de las dos de secretos. gitleaks encuentra cosas que PARECEN credenciales;
TruffleHog llama a la API del proveedor y comprueba si la credencial SIGUE VIVA. Esa distinción
—`Verified: true`— es la diferencia entre "hay que rotar esto hoy" y "un patrón que quizá nunca
fue nada". Producirla y tirarla es peor que no producirla, porque cuesta lo mismo.

Por eso el mapeo de severidad no es negociable:
    Verified: true   -> critical   (credencial viva; su presupuesto en el gate es 0)
    Verified: false  -> medium     (candidata sin confirmar: es señal, no es alarma)

Uso: trufflehog-sarif.py <reports_dir>        (normalmente lo llama tools/secrets.sh)
"""
import json
import os
import sys


def location_of(record):
    """TruffleHog anida el origen distinto según lo que escaneó.

    tools/secrets.sh usa `git file:///repo/<rel>` cuando hay repositorio y `filesystem /repo`
    cuando no lo hay (un checkout sin .git todavía debe escanearse, o un árbol limpio se leería
    como "sin fugas" siendo en realidad "no se miró"). Las dos formas tienen que salir aquí, o la
    conversión perdería justo el caso que aquel arreglo cubría.
    """
    data = ((record.get("SourceMetadata") or {}).get("Data") or {})
    for key in ("Git", "Filesystem", "Github", "Gitlab"):
        node = data.get(key)
        if isinstance(node, dict):
            path = node.get("file") or node.get("link") or ""
            line = node.get("line") or 0
            commit = node.get("commit") or ""
            return path, int(line or 0), commit
    return "", 0, ""


def main(argv):
    if len(argv) != 1:
        print("uso: trufflehog-sarif.py <reports_dir>", file=sys.stderr)
        return 2
    reports = argv[0]
    src = os.path.join(reports, "trufflehog.txt")
    out = os.path.join(reports, "trufflehog.sarif")

    if not os.path.exists(src):
        # Sin entrada no se escribe un SARIF vacío: un archivo con cero resultados se lee como
        # "corrió y no encontró nada", y esto sería "no corrió". Son cosas distintas y el
        # laboratorio entero se apoya en no confundirlas.
        print("trufflehog: no hay trufflehog.txt — NO EJECUTADO, no se escribe SARIF")
        return 0

    results, rules, seen_rules = [], [], set()
    verified = 0
    malformed = 0

    with open(src, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw or not raw.startswith("{"):
                continue
            try:
                rec = json.loads(raw)
            except ValueError:
                # Un `timeout` que corta a TruffleHog a mitad deja una última línea partida.
                # Se cuenta y se informa: descartarla en silencio ocultaría una corrida truncada.
                malformed += 1
                continue

            detector = rec.get("DetectorName") or "unknown"
            is_verified = bool(rec.get("Verified"))
            verified += is_verified
            rule_id = f"trufflehog.{detector}.{'verified' if is_verified else 'unverified'}"

            if rule_id not in seen_rules:
                seen_rules.add(rule_id)
                rules.append({
                    "id": rule_id,
                    "name": f"{detector} ({'verificado' if is_verified else 'sin verificar'})",
                    "shortDescription": {
                        "text": f"Credencial de tipo {detector}"
                                + (" CONFIRMADA VIVA por el proveedor" if is_verified
                                   else " detectada, sin confirmar")},
                    "fullDescription": {"text": rec.get("DetectorDescription") or ""},
                    "properties": {
                        # La severidad va en `tags`, que es lo PRIMERO que mira
                        # tools/sarif.py:severity_of() — por delante del score y del level.
                        "tags": ["critical" if is_verified else "medium", "secret"],
                        "security-severity": "9.5" if is_verified else "5.0",
                    },
                    "defaultConfiguration": {"level": "error" if is_verified else "warning"},
                })

            path, line, commit = location_of(rec)
            # `Redacted` y NUNCA `Raw`: el secreto no puede acabar en un artefacto que se adjunta
            # a un informe. Mismo criterio que el --redact de gitleaks en tools/secrets.sh:24.
            msg = rec.get("Redacted") or "(sin valor redactado)"
            if commit:
                msg = f"{msg} · commit {commit[:8]}"
            if is_verified:
                msg = f"VERIFICADA VIVA — {msg}"

            results.append({
                "ruleId": rule_id,
                "level": "error" if is_verified else "warning",
                "message": {"text": msg},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": path.lstrip("/") or "(sin ruta)"},
                    "region": {"startLine": line or 1},
                }}],
            })

    sarif = {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{"tool": {"driver": {"name": "trufflehog", "rules": rules}},
                  "results": results}],
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(sarif, fh, indent=1, ensure_ascii=False)

    note = f" ({malformed} líneas ilegibles: la corrida pudo quedar truncada)" if malformed else ""
    print(f"trufflehog: {len(results)} hallazgos, {verified} VERIFICADOS VIVOS -> {out}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
