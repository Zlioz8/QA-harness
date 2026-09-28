#!/usr/bin/env python3
"""AAA -> tres SARIF, uno por pilar, más aaa/AAA.md (personas) y aaa/aaa.json (el informe).

    aaa/authn.sarif   sondas de autenticación fallidas   (lib/specs/authn.spec.ts, aaa/authn.json)
    aaa/authz.sarif   reglas de la matriz fallidas       (lib/specs/authz-matrix.spec.ts)
    aaa/acct.sarif    eventos de auditoría sin rastro    (tools/aaa-oracle.sh, aaa/acct.json)

Se emite SOLO el pilar que tuvo entrada: un SARIF con `results: []` es correcto cuando la suite
corrió y todo pasó; sin entrada no se escribe nada, y la ausencia se lee como NO EJECUTADO
(tools/gate-count.py devuelve -1). La auditoría con el oráculo «no-disponible» tampoco escribe
SARIF: el gate lo dice en su propia línea, porque no medir no es aprobar.

De dónde sale cada cosa:
  - reports/<t>/playwright/results.json: el reporter JSON de Playwright. Los tests de este
    pilar se reconocen por el prefijo del título, `[authn][stride:X]` y `[authz][stride:X]`.
  - reports/<t>/playwright/aaa-acciones.json: lo que la spec de autenticación anotó de cada
    sonda (pasos, status, qué comprobación falló, «no aplica» y por qué). Si falta una sonda ahí
    pero está en results.json (la suite murió a medias), se usa el estado de results.json.
  - reports/<t>/aaa/oracle.json: el resultado de cada evento del oráculo.

Uso:  tools/aaa-sarif.py <target>        (lo llama `make aaa`)
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime

LAB = os.environ.get("LAB_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TITULO = re.compile(r"^\[(authn|authz)\](?:\[stride:([A-Z\-]*)\])?\s+(.*)$")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
SEV_SCORE = {"critical": "9.5", "high": "8.0", "medium": "5.0", "low": "2.5"}
SEV_LEVEL = {"critical": "error", "high": "error", "medium": "warning", "low": "note"}
LETRAS = "STRIDE"


def leer_json(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def specs_de(results: dict):
    """Recorre el árbol de suites del reporter JSON y devuelve (título, archivo, test)."""
    def walk(s):
        for sp in s.get("specs", []):
            t = (sp.get("tests") or [{}])[0]
            yield sp.get("title", ""), sp.get("file", ""), t
        for sub in s.get("suites", []):
            yield from walk(sub)
    for s in results.get("suites", []):
        yield from walk(s)


def estado_pw(t: dict) -> tuple[str, str]:
    """(pass|fail|no-ejecutada, detalle) desde un test del reporter JSON."""
    st = t.get("status", "")
    if st == "expected":
        return "pass", ""
    if st == "skipped":
        ann = [a.get("description", "") for a in t.get("annotations", []) if a.get("type") == "skip"]
        return "no-ejecutada", (ann[0] if ann else "skipped")
    msgs = []
    for r in t.get("results", []):
        err = (r.get("error") or {}).get("message") or ""
        if err:
            msgs.append(ANSI.sub("", err).strip().splitlines()[0][:300])
    return "fail", " | ".join(dict.fromkeys(msgs)) or st


def sev_norm(s: str, defecto: str) -> str:
    s = (s or "").lower()
    return s if s in SEV_SCORE else defecto


def letras_de(s: str) -> list[str]:
    return [c for c in (s or "") if c in LETRAS]


def sarif(driver: str, filas: list[dict], uri: str) -> dict:
    rules, results = {}, []
    for f in filas:
        rid = f["id"]
        if rid not in rules:
            rules[rid] = {
                "id": rid, "name": rid,
                "shortDescription": {"text": f["titulo"] or rid},
                "properties": {"tags": [f["severidad"], f"aaa:{f['pilar']}"] + [f"stride:{c}" for c in f["letras"]],
                               "security-severity": SEV_SCORE[f["severidad"]]},
                "defaultConfiguration": {"level": SEV_LEVEL[f["severidad"]]},
            }
        results.append({
            "ruleId": rid, "level": SEV_LEVEL[f["severidad"]],
            "message": {"text": f["detalle"] or "falló sin detalle"},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": f.get("uri", uri)},
                                                "region": {"startLine": 1}}}],
        })
    return {"version": "2.1.0", "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [{"tool": {"driver": {"name": driver, "rules": list(rules.values())}}, "results": results}]}


def escribir(p, doc):
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)


def por_letra(items):
    out = {c: {"pass": 0, "fail": 0} for c in LETRAS}
    for it in items:
        for c in it["letras"]:
            if it["resultado"] in ("pass", "fail"):
                out[c][it["resultado"]] += 1
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    t = argv[1]
    rep = os.path.join(LAB, "reports", t)
    outdir = os.path.join(rep, "aaa")
    os.makedirs(outdir, exist_ok=True)
    results = leer_json(os.path.join(rep, "playwright", "results.json")) or {}
    acciones = leer_json(os.path.join(rep, "playwright", "aaa-acciones.json")) or {}
    oracle = leer_json(os.path.join(outdir, "oracle.json"))

    # ---- authn ----
    anotadas = {s["id"]: s for s in acciones.get("sondas", []) if isinstance(s, dict)}
    authn, authz = [], []
    for titulo, archivo, test in specs_de(results):
        m = TITULO.match(titulo)
        if not m:
            continue
        pilar, letras, resto = m.group(1), m.group(2) or "", m.group(3)
        estado, detalle = estado_pw(test)
        if pilar == "authn":
            sid = resto.split(" — ")[0].strip()
            a = anotadas.get(sid)
            fila = {"id": sid, "pilar": "authn", "tipo": (a or {}).get("tipo", ""), "titulo": resto,
                    "letras": letras_de(letras), "severidad": sev_norm((a or {}).get("severidad"), "high"),
                    "resultado": (a or {}).get("resultado") or estado, "detalle": (a or {}).get("detalle") or detalle,
                    "pasos": (a or {}).get("pasos", []), "uri": "aaa/authn.json"}
            if fila["resultado"] == "no-ejecutada" and estado == "fail":
                fila["resultado"], fila["detalle"] = "fail", detalle or "la sonda murió sin anotar resultado"
            authn.append(fila)
        else:
            denegado = " denied" in resto
            authz.append({"id": f"authz:{resto}", "pilar": "authz", "titulo": resto,
                          "letras": letras_de(letras), "severidad": "high" if denegado else "medium",
                          "resultado": estado, "detalle": detalle, "uri": "playwright/authz-matrix.json"})

    # ---- acct ----
    acct = []
    db = "sin-oraculo"
    if oracle:
        db = oracle.get("db", "no-disponible")
        for e in oracle.get("eventos", []):
            acct.append({"id": e["id"], "pilar": "acct", "titulo": e.get("titulo") or e["id"],
                         "letras": letras_de(e.get("stride", "R")) or ["R"],
                         "severidad": sev_norm(e.get("severidad"), "medium"),
                         "resultado": e.get("resultado", ""), "detalle": e.get("detalle", ""),
                         "accion": e.get("accion", ""), "n": e.get("n"), "uri": "aaa/acct.json"})

    emitidos = []
    if authn:
        escribir(os.path.join(outdir, "authn.sarif"), sarif("aaa-authn", [f for f in authn if f["resultado"] == "fail"], "aaa/authn.json"))
        emitidos.append("authn")
    if authz:
        escribir(os.path.join(outdir, "authz.sarif"), sarif("aaa-authz", [f for f in authz if f["resultado"] == "fail"], "playwright/authz-matrix.json"))
        emitidos.append("authz")
    medibles = [f for f in acct if f["resultado"] in ("pass", "fail", "error")]
    if medibles:
        # Un oráculo que no pudo ejecutarse también es resultado: no se sabe si hubo rastro.
        for f in acct:
            if f["resultado"] == "error":
                f["detalle"] = "el oráculo no pudo ejecutarse: " + f["detalle"]
        escribir(os.path.join(outdir, "acct.sarif"), sarif("aaa-acct", [f for f in acct if f["resultado"] in ("fail", "error")], "aaa/acct.json"))
        emitidos.append("acct")

    def cuenta(items, *estados):
        return sum(1 for i in items if i["resultado"] in estados)

    resumen = {
        "generado": datetime.now().isoformat(timespec="seconds"),
        "authn": {"guion": bool(authn), "pass": cuenta(authn, "pass"), "fail": cuenta(authn, "fail"),
                  "no_aplica": cuenta(authn, "no-aplica"), "no_ejecutada": cuenta(authn, "no-ejecutada"),
                  "por_letra": por_letra(authn), "sondas": authn},
        "authz": {"guion": bool(authz), "pass": cuenta(authz, "pass"), "fail": cuenta(authz, "fail"),
                  "no_ejecutada": cuenta(authz, "no-ejecutada"), "por_letra": por_letra(authz), "reglas": authz},
        "acct": {"guion": bool(acct), "db": db, "pass": cuenta(acct, "pass"), "fail": cuenta(acct, "fail"),
                 "error": cuenta(acct, "error"), "no_disponible": cuenta(acct, "no-disponible"),
                 "por_letra": por_letra(acct), "eventos": acct},
    }
    escribir(os.path.join(outdir, "aaa.json"), resumen)

    # ---- AAA.md ----
    ico = {"pass": "✅", "fail": "❌", "error": "⚠️", "no-aplica": "➖", "no-ejecutada": "⏸", "no-disponible": "**NO DISPONIBLE**"}
    md = [f"# AAA — {t} ({resumen['generado']})", "",
          "Tres pilares, tres preguntas, tres artefactos. `pass` es un control que se sostiene; `fail`, uno que no está; "
          "`no aplica`, una sonda que este stack no puede ejecutar (consta, no se cuenta); `NO DISPONIBLE`, una medición "
          "que no se hizo — y no medir no es aprobar.", ""]
    md += ["## 1. Autenticación — `aaa/authn.json` · lib/specs/authn.spec.ts", ""]
    if authn:
        md += [f"pass {resumen['authn']['pass']} · fail {resumen['authn']['fail']} · no aplica {resumen['authn']['no_aplica']} · no ejecutada {resumen['authn']['no_ejecutada']}", "",
               "| Sonda | Tipo | STRIDE | Resultado | Evidencia |", "|---|---|---|---|---|"]
        for f in authn:
            ev = " · ".join(f"{p.get('id')}→{p.get('status')} {'✓' if p.get('ok') else '✗'}" for p in f["pasos"]) or f["detalle"]
            md.append(f"| {f['id']} | {f['tipo']} | {''.join(f['letras']) or '-'} | {ico.get(f['resultado'], f['resultado'])} {f['resultado']} | {ev} |")
    else:
        md.append("Sin sondas: la suite no ejecutó `[authn]` (¿falta `aaa/authn.json`?). **NO MEDIDA.**")
    md += ["", "## 2. Autorización — `playwright/authz-matrix.json` · lib/specs/authz-matrix.spec.ts", ""]
    if authz:
        md += [f"pass {resumen['authz']['pass']} · fail {resumen['authz']['fail']} · no ejecutada {resumen['authz']['no_ejecutada']}", "",
               "| Regla | STRIDE | Resultado | Detalle |", "|---|---|---|---|"]
        for f in authz:
            md.append(f"| {f['titulo']} | {''.join(f['letras']) or '-'} | {ico.get(f['resultado'], f['resultado'])} {f['resultado']} | {f['detalle']} |")
    else:
        md.append("Sin reglas: la suite no ejecutó la matriz. **NO MEDIDA.**")
    md += ["", "## 3. Auditoría — `aaa/acct.json` · tools/aaa-oracle.sh", ""]
    if acct:
        md += [f"oráculo: {db} · pass {resumen['acct']['pass']} · fail {resumen['acct']['fail']} · error {resumen['acct']['error']} · no disponible {resumen['acct']['no_disponible']}", "",
               "| Evento | Acción | STRIDE | Resultado | Detalle |", "|---|---|---|---|---|"]
        for f in acct:
            md.append(f"| {f['id']} | {f['accion']} | {''.join(f['letras'])} | {ico.get(f['resultado'], f['resultado'])} {f['resultado'] if f['resultado'] != 'no-disponible' else ''} | {f['detalle']} |")
        if db == "no-disponible":
            md += ["", "**`no-disponible` no es un aprobado**: sin `AAA_DB_URL` en `target.env.local` la auditoría (repudio) no se midió."]
    else:
        md.append("Sin eventos: no hay `aaa/acct.json` (o el oráculo no corrió). **NO MEDIDA.**")
    md.append("")
    with open(os.path.join(outdir, "AAA.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))

    if not emitidos:
        print("aaa: results.json sin tests [authn]/[authz] y sin oráculo medible — NO EJECUTADO, no se escribe SARIF")
    else:
        print(f"aaa: authn {resumen['authn']['pass']}/{resumen['authn']['fail']} · authz {resumen['authz']['pass']}/{resumen['authz']['fail']} "
              f"· acct {resumen['acct']['pass']}/{resumen['acct']['fail']} (db {db}) -> aaa/{{{','.join(emitidos)}}}.sarif")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
