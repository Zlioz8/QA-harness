#!/usr/bin/env python3
"""risks.json de Threagile -> SARIF que el gate cuenta, con la letra STRIDE de cada riesgo.

POR QUÉ UN CONVERSOR. Threagile escribe su propio formato: un array plano de riesgos con
`category`, `severity` (low|medium|elevated|high|critical), `risk_status`, `synthetic_id` y los
activos/enlaces implicados. El gate, el informe, la UI y el triaje solo saben leer SARIF
(tools/sarif.py es el único lector). Mismo patrón que zap-sarif.py o sonar-sarif.py.

DOS DECISIONES QUE IMPORTAN.
  1. `ruleId = <categoría>/<severidad>`. tools/sarif.py:severity_of resuelve la severidad POR
     REGLA (tags de la regla antes que el `level` del resultado), y Threagile grada por
     INSTANCIA: la misma categoría sale `medium` en un enlace y `critical` en otro. Codificar
     la severidad en el id conserva la gradación real sin tocar el único lector del laboratorio.
     Coste asumido: si el modelo re-grada un riesgo, cambia su clave de triaje y hay que volver
     a juzgarlo — que es lo correcto para un riesgo re-evaluado.
  2. La letra STRIDE NO viaja en el riesgo: está en la definición de cada regla. El mapa de
     abajo se leyó de las 42 reglas builtin de Threagile 0.9.1 y se completa con las categorías
     propias del modelo (`individual_risk_categories`, campo `stride`). Ninguna regla builtin es
     Repudiation: la R solo puede salir del modelo, y se MIDE con las sondas de auditoría (aaa).

Esto es STRIDE y solo STRIDE. El pilar AAA no se etiqueta aquí: son dos preguntas distintas
(qué puede pasar / qué hace el sistema con la identidad) y mezclarlas en el artefacto es
exactamente lo que el informe separa en dos secciones.

Uso:  tools/threagile-sarif.py reports/<t>/amenazas targets/<t>/amenazas/threagile.yaml
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime

# categoría builtin -> letra STRIDE (Threagile 0.9.1, risks/built-in/*)
STRIDE_BUILTIN = {
    # Spoofing
    "cross-site-request-forgery": "S", "missing-file-validation": "S",
    "missing-identity-store": "S", "service-registry-poisoning": "S",
    # Tampering
    "code-backdooring": "T", "container-baseimage-backdooring": "T", "cross-site-scripting": "T",
    "ldap-injection": "T", "missing-build-infrastructure": "T", "missing-cloud-hardening": "T",
    "missing-hardening": "T", "missing-waf": "T", "push-instead-of-pull-deployment": "T",
    "search-query-injection": "T", "sql-nosql-injection": "T", "unchecked-deployment": "T",
    "untrusted-deserialization": "T",
    # Information disclosure
    "accidental-secret-leak": "I", "incomplete-model": "I", "missing-vault": "I",
    "path-traversal": "I", "server-side-request-forgery": "I", "unencrypted-asset": "I",
    "unencrypted-communication": "I", "wrong-communication-link-content": "I",
    "xml-external-entity": "I",
    # Denial of service
    "dos-risky-access-across-trust-boundary": "D",
    # Elevation of privilege
    "container-platform-escape": "E", "missing-authentication": "E",
    "missing-authentication-second-factor": "E", "missing-identity-propagation": "E",
    "missing-identity-provider-isolation": "E", "missing-network-segmentation": "E",
    "missing-vault-isolation": "E", "mixed-targets-on-shared-runtime": "E",
    "unguarded-access-from-internet": "E", "unguarded-direct-datastore-access": "E",
    "unnecessary-communication-link": "E", "unnecessary-data-asset": "E",
    "unnecessary-data-transfer": "E", "unnecessary-technical-asset": "E",
    "wrong-trust-boundary-content": "E",
}
LETRA = {"spoofing": "S", "tampering": "T", "repudiation": "R", "information-disclosure": "I",
         "denial-of-service": "D", "elevation-of-privilege": "E"}
NOMBRE = {"S": "Spoofing", "T": "Tampering", "R": "Repudiation", "I": "Information disclosure",
          "D": "Denial of service", "E": "Elevation of privilege", "?": "sin letra"}
SEV_ORDEN = ["critical", "high", "elevated", "medium", "low"]
SEV_TAG = {"critical": "critical", "high": "high", "elevated": "high", "medium": "medium", "low": "low"}
SEV_SCORE = {"critical": "9.5", "high": "8.0", "elevated": "6.5", "medium": "5.0", "low": "2.5"}
SEV_LEVEL = {"critical": "error", "high": "error", "elevated": "error", "medium": "warning", "low": "note"}

# Qué significa cada categoría y qué hacer con ella, en el idioma del informe. Es lo que ve el
# QA en la pantalla de triaje y en el dashboard (message del resultado) y lo que lee el equipo en
# amenazas.md: sin esto, «Missing Hardening risk at nginx» es una frase en inglés que nadie
# convierte en una acción. (qué es, qué hacer)
CATALOGO = {
    "accidental-secret-leak": ("un repositorio o registro de artefactos puede llevar secretos commiteados por accidente",
                               "escaneo de secretos en el historial (el laboratorio ya lo hace con gitleaks/TruffleHog) y ningún .env versionado"),
    "code-backdooring": ("el código llega a producción sin control de quién lo cambió: se le puede colar una puerta trasera",
                         "revisión obligatoria por MR, ramas protegidas, build reproducible desde el repositorio"),
    "container-baseimage-backdooring": ("el activo corre en un contenedor cuya imagen base puede venir troyanizada o con CVE",
                                        "fijar la imagen por digest, escanearla (make image-scan) y traerla de un registro de confianza"),
    "container-platform-escape": ("varios activos comparten la plataforma de contenedores: un escape compromete al host y a los vecinos",
                                  "contenedores sin privilegios, sin el socket de docker montado, runtime actualizado"),
    "cross-site-request-forgery": ("una aplicación con sesión de navegador acepta escrituras que otro sitio puede provocar (CSRF)",
                                   "token anti-CSRF, cookies SameSite, verificar Origin en las escrituras"),
    "cross-site-scripting": ("una aplicación web muestra datos que pueden llevar script (XSS)",
                             "escapar la salida, Content-Security-Policy, no confiar en HTML de terceros"),
    "dos-risky-access-across-trust-boundary": ("un enlace cruza una frontera de confianza hacia un activo crítico sin nada que limite el volumen: se puede tumbar desde fuera",
                                               "limitador de peticiones, timeouts, colas o redundancia en el lado que recibe"),
    "incomplete-model": ("el modelo tiene activos con tecnología desconocida o enlaces con protocolo desconocido",
                         "completar el modelo: no es un riesgo del sistema, es un hueco del guion"),
    "ldap-injection": ("una consulta LDAP se construye con datos de la persona",
                       "sanear y parametrizar la consulta"),
    "missing-authentication": ("un activo recibe datos sensibles por un enlace que no autentica a quien llama",
                               "exigir autenticación en ese enlace (token, credenciales, certificado)"),
    "missing-authentication-second-factor": ("desde internet se entra con solo usuario y contraseña a datos muy sensibles",
                                             "segundo factor; si la política institucional no lo prevé, aceptarlo en el triaje con esa razón escrita"),
    "missing-build-infrastructure": ("hay código a medida pero el modelo no declara cómo se construye ni desde qué repositorio",
                                     "modelar el pipeline y el repositorio, o crearlos: build reproducible con pruebas"),
    "missing-cloud-hardening": ("un activo en nube sin las guías de endurecimiento del proveedor",
                                "aplicar el benchmark del proveedor (CIS) y revisar permisos IAM"),
    "missing-file-validation": ("un activo acepta archivos subidos sin validarlos",
                                "validar tipo y tamaño, renombrar, guardar fuera del árbol servido, antivirus"),
    "missing-hardening": ("un activo muy expuesto o muy crítico sin endurecimiento explícito",
                          "endurecer sistema y servicio (CIS), cerrar lo que no se usa, actualizar; en nginx, cabeceras y server_tokens off"),
    "missing-identity-propagation": ("un servicio llama a otro con un usuario técnico en lugar de la persona: el destino no puede autorizar ni auditar por persona",
                                     "propagar la identidad (token de la persona), o autorizar con rigor en el llamador y auditar por persona"),
    "missing-identity-provider-isolation": ("el proveedor de identidad comparte red o runtime con otros activos",
                                            "aislar el IdP en su propia frontera"),
    "missing-identity-store": ("hay autenticación pero el modelo no dice dónde viven las identidades",
                               "modelar el almacén de identidades (Moodle, LDAP, IdP); si de verdad no existe, crearlo"),
    "missing-network-segmentation": ("activos de distinta criticidad en la misma red",
                                     "segmentar redes o fronteras de confianza"),
    "missing-vault": ("los secretos (credenciales de base, tokens de sistema) no viven en un gestor de secretos",
                      "gestor de secretos, o justificar el mecanismo actual (.env con permisos, cifrado) y aceptarlo con razón"),
    "missing-vault-isolation": ("el gestor de secretos comparte red o runtime con otros activos",
                                "aislarlo"),
    "missing-waf": ("un activo web expuesto a internet sin cortafuegos de aplicación delante",
                    "WAF, o compensar con limitador y validación estricta y aceptarlo con razón"),
    "mixed-targets-on-shared-runtime": ("activos de distinta criticidad (borde y base de datos) corren en el mismo runtime: comprometer uno da acceso al otro",
                                        "separar hosts o aislar; en un despliegue LOCAL suele aceptarse con esa razón"),
    "path-traversal": ("un activo sirve archivos según un parámetro de la persona",
                       "normalizar rutas y servir desde una lista cerrada"),
    "push-instead-of-pull-deployment": ("el pipeline empuja artefactos hacia producción, que así confía en la máquina de build",
                                        "despliegue por pull desde producción, o credenciales mínimas y rotadas"),
    "search-query-injection": ("una consulta a un motor de búsqueda se construye con datos de la persona",
                               "sanear y parametrizar"),
    "server-side-request-forgery": ("un servicio hace peticiones salientes cuyo destino puede influir la persona (SSRF)",
                                    "destinos por configuración y lista cerrada; nunca una URL que llegue del cliente"),
    "service-registry-poisoning": ("el registro de servicios puede envenenarse para desviar tráfico",
                                   "autenticar y aislar el registro"),
    "sql-nosql-injection": ("un activo consulta la base con datos de la persona",
                            "consultas parametrizadas en todo el código (asyncpg/ORM), revisar SQL dinámico"),
    "unchecked-deployment": ("el pipeline despliega sin análisis de seguridad",
                             "SAST, dependencias y secretos en el pipeline (o este laboratorio antes de cada entrega)"),
    "unencrypted-asset": ("un activo guarda o procesa datos confidenciales sin cifrado en reposo",
                          "cifrar disco/volumen o columnas sensibles; si el dato ya va cifrado en la aplicación, declararlo en el modelo"),
    "unencrypted-communication": ("un enlace en claro (http, sql sin TLS) transporta datos confidenciales",
                                  "TLS en el enlace; si es una red interna aislada (docker), aceptarlo con esa razón escrita"),
    "unguarded-access-from-internet": ("un activo se alcanza desde internet sin un borde (proxy, balanceador, WAF) delante",
                                       "poner un borde o, si el activo ES el borde, aceptarlo y endurecerlo"),
    "unguarded-direct-datastore-access": ("una base de datos se accede directamente desde fuera de su frontera",
                                          "solo el servicio dueño accede; el resto por su API"),
    "unnecessary-communication-link": ("un enlace del modelo no transporta ningún dato: superficie sin función",
                                       "quitarlo del sistema o modelar qué datos lleva"),
    "unnecessary-data-asset": ("un dato del modelo que ningún activo procesa ni guarda",
                               "quitarlo del modelo o asignarlo a quien lo use"),
    "unnecessary-data-transfer": ("un enlace transporta datos que el destino no procesa",
                                  "no enviar lo que no se usa, o corregir el modelo"),
    "unnecessary-technical-asset": ("un activo sin enlaces ni datos: superficie sin función",
                                    "retirarlo o modelar su papel"),
    "untrusted-deserialization": ("un activo deserializa objetos que llegan de fuera",
                                  "formatos de datos (json) en vez de serialización nativa; lista blanca de clases"),
    "wrong-communication-link-content": ("un enlace declara datos que el destino no procesa, o es de solo lectura y envía datos",
                                         "corregir el modelo, o el sistema si el modelo tiene razón"),
    "wrong-trust-boundary-content": ("una frontera de red contiene un activo que no es de red",
                                     "corregir el tipo de frontera o del activo"),
    "xml-external-entity": ("un activo acepta XML y puede resolver entidades externas (XXE)",
                            "desactivar entidades externas y DTD en el parser"),
}


def categorias_propias(modelo: str) -> dict[str, str]:
    """id -> letra de las `individual_risk_categories` del modelo. Parser por líneas, sin PyYAML.
    De paso llena CATALOGO con la `description` y la `mitigation` de cada categoría propia."""
    out: dict[str, str] = {}
    if not modelo or not os.path.exists(modelo):
        return out
    bloque, cid, letra = None, None, None
    desc, mit = "", ""
    for linea in open(modelo, encoding="utf-8", errors="replace"):
        if re.match(r"^[a-z_]+:", linea):
            bloque = linea.split(":", 1)[0]
            continue
        if bloque != "individual_risk_categories":
            continue
        if re.match(r"^  \S", linea):            # nueva categoría (2 espacios)
            if cid:
                out[cid] = letra or "?"
                CATALOGO.setdefault(cid, (desc or "categoría propia del modelo", mit or "ver el modelo"))
            cid, letra, desc, mit = None, None, "", ""
            continue
        m = re.match(r"^    id:\s*(\S+)", linea)
        if m:
            cid = m.group(1)
        m = re.match(r"^    stride:\s*([a-z-]+)", linea)
        if m:
            letra = LETRA.get(m.group(1), "?")
        m = re.match(r"^    description:\s*(.+)$", linea)
        if m:
            desc = m.group(1).strip()
        m = re.match(r"^    mitigation:\s*(.+)$", linea)
        if m:
            mit = m.group(1).strip()
    if cid:
        out[cid] = letra or "?"
        CATALOGO.setdefault(cid, (desc or "categoría propia del modelo", mit or "ver el modelo"))
    return out


def limpiar(html: str) -> str:
    """Título sin HTML y sin la coletilla «in the threat model (referencing asset X as an example)»:
    la UI corta el mensaje a 400 caracteres y lo que importa (qué es / qué hacer) va después."""
    t = re.sub(r"<[^>]+>", "", html or "").strip()
    t = re.sub(r"\s*in the threat model\s*\(referencing asset .*? as an example\)", "", t)
    return t if len(t) <= 130 else t[:127] + "…"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    outdir = argv[1]
    modelo = argv[2] if len(argv) > 2 else ""
    src = os.path.join(outdir, "risks.json")
    if not os.path.exists(src):
        print(f"amenazas: no hay {src} — NO EJECUTADO, no se escribe SARIF")
        return 0
    riesgos = json.load(open(src, encoding="utf-8"))
    if not isinstance(riesgos, list):
        print(f"amenazas: {src} no es una lista de riesgos — no se escribe SARIF")
        return 1

    propias = categorias_propias(modelo)
    stride_de = {**STRIDE_BUILTIN, **propias}
    rules: dict[str, dict] = {}
    results = []
    desconocidas: set[str] = set()
    por_letra = {k: 0 for k in "STRIDE"}
    por_letra["?"] = 0
    por_sev = {s: 0 for s in SEV_ORDEN}
    filas = []

    for r in riesgos:
        cat = str(r.get("category") or "?")
        sev = str(r.get("severity") or "").lower()
        if sev not in SEV_TAG:
            print(f"amenazas: severidad desconocida {sev!r} en {cat}; se cuenta como low", file=sys.stderr)
            sev = "low"
        letra = stride_de.get(cat)
        if letra is None:
            desconocidas.add(cat)
            letra = "?"
        sid = str(r.get("synthetic_id") or f"{cat}@?")
        titulo = limpiar(r.get("title", ""))
        estado = str(r.get("risk_status") or "unchecked")
        rule_id = f"{cat}/{sev}"
        que_es, hacer = CATALOGO.get(cat, ("categoría sin descripción en el catálogo", "leer la regla en Threagile"))
        if rule_id not in rules:
            rules[rule_id] = {
                "id": rule_id,
                "name": cat,
                "shortDescription": {"text": f"{cat} ({sev}) · STRIDE {NOMBRE[letra]}"},
                "fullDescription": {"text": f"{que_es}. Qué hacer: {hacer}."},
                "properties": {
                    # La severidad en tags: es lo PRIMERO que mira tools/sarif.py:severity_of().
                    "tags": [SEV_TAG[sev], f"stride:{letra}", "threagile"],
                    "security-severity": SEV_SCORE[sev],
                },
                "defaultConfiguration": {"level": SEV_LEVEL[sev]},
            }
        partes = [f"[{estado}] {titulo}",
                  f"qué es: {que_es}",
                  f"qué hacer: {hacer}",
                  f"probabilidad {r.get('exploitation_likelihood', '?')}",
                  f"impacto {r.get('exploitation_impact', '?')}",
                  f"fuga de datos {r.get('data_breach_probability', '?')}"]
        if r.get("most_relevant_technical_asset"):
            partes.append(f"activo: {r['most_relevant_technical_asset']}")
        if r.get("most_relevant_communication_link"):
            partes.append(f"enlace: {r['most_relevant_communication_link']}")
        results.append({
            "ruleId": rule_id,
            "level": SEV_LEVEL[sev],
            "message": {"text": " · ".join(partes)},
            "locations": [{"physicalLocation": {
                # El synthetic_id es único y estable mientras no cambien los ids del modelo:
                # con él la clave de triaje (amenazas|cat/sev|synthetic_id) sobrevive a las rondas.
                "artifactLocation": {"uri": sid},
                "region": {"startLine": 1},
            }}],
        })
        por_letra[letra] += 1
        por_sev[sev] += 1
        filas.append((SEV_ORDEN.index(sev), titulo, sev, letra,
                      r.get("most_relevant_technical_asset") or "", r.get("most_relevant_communication_link") or "",
                      estado, sid))

    for cat in sorted(desconocidas):
        print(f"amenazas: categoría {cat!r} sin letra STRIDE conocida (¿regla nueva de Threagile o "
              f"categoría propia sin `stride:`?) — etiquetada stride:?", file=sys.stderr)

    sarif = {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{"tool": {"driver": {"name": "threagile", "version": "0.9.1",
                                       "rules": list(rules.values())}},
                  "results": results}],
    }
    out = os.path.join(outdir, "threagile.sarif")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(sarif, fh, indent=1, ensure_ascii=False)

    # El artefacto para personas: la misma información ordenada por severidad, con la letra.
    filas.sort()
    md = [f"# Modelo de amenazas — {os.path.basename(os.path.dirname(os.path.abspath(outdir)))} "
          f"(Threagile 0.9.1 · {datetime.now().strftime('%Y-%m-%d %H:%M')})", "",
          f"Riesgos: **{len(riesgos)}** · por severidad: " +
          " · ".join(f"{s} {por_sev[s]}" for s in SEV_ORDEN if por_sev[s]), "",
          "Por letra STRIDE: " + " · ".join(f"**{k}** {por_letra[k]}" for k in "STRIDE") +
          (f" · sin letra {por_letra['?']}" if por_letra["?"] else ""), "",
          "| Riesgo | Severidad | STRIDE | Activo / enlace | Estado (modelo) | synthetic_id |",
          "|---|---|---|---|---|---|"]
    for _, titulo, sev, letra, activo, enlace, estado, sid in filas:
        donde = " / ".join(x for x in (activo, enlace) if x)
        md.append(f"| {titulo} | {sev} | {letra} | {donde} | {estado} | `{sid}` |")
    presentes = sorted({f[0] for f in [(r.get("category"),) for r in riesgos]} - {None})
    md += ["", "## Cómo leer cada categoría presente", "",
           "| Categoría | STRIDE | Qué significa | Qué hacer |", "|---|---|---|---|"]
    for cat in presentes:
        que_es, hacer = CATALOGO.get(cat, ("—", "—"))
        md.append(f"| `{cat}` | {stride_de.get(cat, '?')} | {que_es} | {hacer} |")
    md += ["", "## Cómo se cierra un riesgo", "",
           "Cada riesgo es un hallazgo más en la pestaña de triaje (`make ui`, «Ver y juzgar» de la dimensión) y en el "
           "dashboard. Se cierra de tres formas, y solo de tres: **corrigiendo el sistema** (y volviendo a evaluar el "
           "modelo, o midiéndolo con una sonda AAA que pase), **aceptándolo** con dueño, razón y fecha, o marcándolo "
           "**falso positivo** cuando el modelo estaba mal (entonces se corrige el modelo, no se borra el riesgo). "
           "Quitar el activo o el enlace del modelo para que el riesgo desaparezca es mentirse: el sistema sigue igual.", ""]
    md += ["",
           "La letra la aporta la REGLA de Threagile, no el riesgo; ninguna regla builtin es "
           "Repudiation: la **R** solo sale de `individual_risk_categories` del modelo y se mide con "
           "las sondas de auditoría (`aaa-acct`). El estado del modelo (`risk_tracking`) se muestra, "
           "no filtra: el juicio del laboratorio es el triaje.", ""]
    with open(os.path.join(outdir, "amenazas.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))

    letras = "/".join(f"{k}={por_letra[k]}" for k in "STRIDE")
    print(f"amenazas: {len(results)} riesgos ({letras}"
          f"{f', ?={por_letra['?']}' if por_letra['?'] else ''}) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
