#!/usr/bin/env python3
"""Cuenta hallazgos de un SARIF para tools/gate.sh.

Sustituye a esto, que era como el gate contaba (tools/gate.sh:37-40):

    grep -o '"ruleId"' "$1" | wc -l

Dos problemas con aquello. El evidente: es un lector de SARIF hecho con grep, y el laboratorio ya
tenía uno bueno en tools/dashboard.py — dos lectores del mismo formato acaban discrepando, y de
hecho discrepaban en lo que importa: el informe pintaba severidades que el veredicto ignoraba.
El de fondo: `grep` cuenta apariciones de una cadena, así que cualquier `"ruleId"` que aparezca en
otro sitio del documento (una corrección sugerida, una localización relacionada) se cuenta como un
hallazgo más. Hoy los ocho SARIF del repositorio dan el mismo número por los dos caminos, pero eso
es suerte, no una garantía del formato.

CONTRATO CON gate.sh, sin cambios respecto a `sarif_count`:
  * imprime UN entero por stdout
  * -1 cuando el archivo NO EXISTE, que gate.sh lee como `skip` (NO EJECUTADO)
  * nunca falla: un SARIF ilegible cuenta 0, no revienta la corrida entera

Los modificadores de abajo NO se activan solos. La fase 1 cambia el mecanismo y conserva la
semántica exacta, para que se pueda comprobar que el veredicto no se movió ni un dígito; la fase 2
es la que enciende el juicio honesto y trae su propia verificación.

Uso: gate-count.py <ruta.sarif> [--dedup] [--min-sev SEV] [--triage <reports_dir> <tool_id>]
     gate-count.py <ruta.sarif> --graded          -> "yes" | "no" | "empty" | "missing"
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sarif   # noqa: E402 — el ÚNICO lector de SARIF del laboratorio


def main(argv):
    if not argv:
        print("uso: gate-count.py <ruta.sarif> [--dedup] [--min-sev SEV] "
              "[--triage <dir> <tool>] [--gate-class fail|cuenta|aparte|descuenta] [--graded]",
              file=sys.stderr)
        return 2

    path = argv[0]
    dedup = "--dedup" in argv
    graded_query = "--graded" in argv
    min_sev = None
    triage_dir = triage_tool = None
    gate_class = None

    i = 1
    while i < len(argv):
        if argv[i] == "--min-sev" and i + 1 < len(argv):
            min_sev = argv[i + 1]
            i += 2
        elif argv[i] == "--triage" and i + 2 < len(argv):
            triage_dir, triage_tool = argv[i + 1], argv[i + 2]
            i += 3
        elif argv[i] == "--gate-class" and i + 1 < len(argv):
            # fail | cuenta | aparte | descuenta | ""(sin juzgar) — para preguntar por una clase
            # concreta: gate.sh necesita saber cuántos BLOQUEANTES hay, sin sumar nada más.
            gate_class = argv[i + 1]
            i += 2
        else:
            i += 1

    data = sarif.load_sarif(path)
    if data is None:
        # NO EJECUTADO. Jamás cero: un análisis que nadie corrió no es un análisis limpio, y esta
        # línea es la que sostiene esa distinción en el veredicto.
        print("missing" if graded_query else -1)
        return 0

    if graded_query:
        if data["count"] == 0:
            print("empty")
        else:
            print("yes" if sarif.is_graded(data) else "no")
        return 0

    findings = data["findings"]

    if min_sev:
        # "al menos esta severidad": el orden de sarif.SEV_ORDER va de critical a unranked.
        try:
            cut = sarif.SEV_ORDER.index(min_sev)
        except ValueError:
            print(f"gate-count: severidad desconocida {min_sev!r}", file=sys.stderr)
            return 2
        findings = [f for f in findings if sarif.SEV_ORDER.index(f["sev"]) <= cut]

    if triage_dir and triage_tool:
        # El juicio humano decide cómo cuenta cada hallazgo. tools/triage.py declara, por criterio,
        # si hace fallar el veredicto, si suma al presupuesto, si va aparte o si se descuenta.
        #
        # Antes gate.sh no abría triage.json siquiera (`grep -c triage tools/gate.sh` daba 0):
        # el operador podía juzgar 900 hallazgos y el veredicto no se movía. Si el triaje no llega
        # al veredicto, no se hace — y de hecho no se hacía.
        import triage as triagelib  # noqa: PLC0415 — solo se necesita en esta rama
        recorded = triagelib.load(triage_dir)

        clases = {"fail": [], "cuenta": [], "aparte": [], "descuenta": [], "": []}
        for f in findings:
            e = recorded.get(triagelib.key_for(triage_tool, f["rule"], f["loc"]), {})
            v = e.get("verdict") or ""
            clase = triagelib.VERDICT_INFO.get(v, {}).get("gate", "") if v else ""
            # Un riesgo aceptado CADUCA. Sin esto, «aceptado» es una amnistía perpetua: se marca
            # una vez y el hallazgo desaparece del veredicto para siempre, que es justo lo que la
            # fecha existe para impedir. Vencido, vuelve a contar como lo que es.
            if v == "aceptado" and triagelib.vencido(e):
                clase = "cuenta"
            clases[clase].append(f)

        if gate_class:
            findings = clases.get(gate_class, [])
        else:
            # El presupuesto lo consumen los confirmados que hay que corregir Y los que nadie ha
            # mirado todavía. Sin juzgar NO es lo mismo que inofensivo.
            findings = clases["cuenta"] + clases[""]

    if dedup:
        # La misma regla disparando quince veces en el mismo archivo es UN problema, no quince.
        # En reports/movil/semgrep son 185 resultados sobre 109 pares (regla, archivo) únicos.
        findings = list({sarif.dedup_key(f): f for f in findings}.values())

    print(len(findings))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:   # noqa: BLE001 — el gate nunca debe morir por un artefacto raro
        print(f"gate-count: {exc}", file=sys.stderr)
        print(0)
        sys.exit(0)
