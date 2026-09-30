#!/usr/bin/env python3
"""De una escalera de carga a una afirmación de capacidad. Solo biblioteca estándar.

  perf-capacidad.py paso <dir-del-paso> [--p95 MS] [--p99 MS] [--err X] [--checks X]
      Juzga UN paso contra el SLO. Sale 0 si cumple, 1 si no, 2 si no hay nada que leer.
  perf-capacidad.py informe <target> [--corrida DIR]
      Escribe CAPACIDAD.md y capacidad.json: rodilla, punto de quiebre, recurso que se saturó,
      costo unitario y recursos por escenario de demanda.
  perf-capacidad.py comparar <corrida-A> <corrida-B> [--nombres A,B]
      A/B entre dos escaleras (antes y después de un cambio), paso a paso.
  perf-capacidad.py curva <valor:paralelismo> [<valor:paralelismo> ...]
      Ajusta la ley universal de escalabilidad a tres o más sobres medidos.

REGLA DE ESTE ARCHIVO: cada cifra que escribe lleva una de tres marcas —medido, extrapolado,
supuesto— y nunca se promueve una a la de arriba. Lo que no se pudo medir se escribe «no medido»,
no se rellena. Un informe de capacidad que mezcla las tres sin decirlo es peor que no tenerlo:
alguien comprará servidores con él.
"""
import argparse
import csv
import json
import math
import os
import re
import statistics
import sys


# ------------------------------------------------------------------ lectura
def leer_json(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def leer_env(ruta):
    """target.env como DATOS (nunca se hace source). El .local gana si trae valor."""
    d = {}
    for r in (ruta, ruta + ".local"):
        try:
            with open(r, encoding="utf-8") as f:
                for linea in f:
                    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", linea.rstrip("\n"))
                    if not m:
                        continue
                    v = re.sub(r"\s+#.*$", "", m.group(2)).strip().strip('"')
                    if v or m.group(1) not in d:
                        d[m.group(1)] = v
        except OSError:
            pass
    return d


def leer_csv(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def num(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


# ------------------------------------------------------------------ un paso
def cifras_del_paso(d):
    """Las cifras de un paso. Prefiere la MESETA (detalle.json); si no hay, el global."""
    det = leer_json(os.path.join(d, "detalle.json"))
    if det:
        m = det.get("meseta")
        g = det.get("global") or {}
        base = "meseta" if m else "toda la corrida"
        x = m or g
        ms = x.get("ms") or {}
        return {
            "base": base, "vus": det.get("vus"), "peticiones": x.get("peticiones"),
            "rps": x.get("por_segundo"), "p50": ms.get("med"), "p95": ms.get("p(95)"), "p99": ms.get("p(99)"),
            "error": x.get("error"), "checks": x.get("checks"),
            "bytes_rx": g.get("bytes_recibidos"), "bytes_tx": g.get("bytes_enviados"),
            "peticiones_total": g.get("peticiones"), "inicio_s": det.get("inicio_s"),
            "rampa_s": det.get("rampa_s") or 0, "meseta_s": det.get("meseta_s") or 0, "detalle": det,
        }
    s = leer_json(os.path.join(d, "summary.json"))
    if not s:
        return None
    M = s.get("metrics", {})
    dur, f, r, c = M.get("http_req_duration", {}), M.get("http_req_failed", {}), M.get("http_reqs", {}), M.get("checks", {})
    return {
        "base": "toda la corrida (sin detalle.json)", "vus": None, "peticiones": r.get("count"), "rps": r.get("rate"),
        "p50": dur.get("med"), "p95": dur.get("p(95)"), "p99": dur.get("p(99)"),
        "error": f.get("value", f.get("rate")), "checks": c.get("value", c.get("rate")),
        "bytes_rx": (M.get("data_received") or {}).get("count"), "bytes_tx": (M.get("data_sent") or {}).get("count"),
        "peticiones_total": r.get("count"), "inicio_s": None, "rampa_s": 0, "meseta_s": 0, "detalle": None,
    }


def juzgar(c, slo):
    motivos = []
    if c["p95"] is None or c["error"] is None:
        return "NO-MEDIDO", ["el resumen no trae p95 o tasa de error"]
    if slo.get("p95") is not None and c["p95"] > slo["p95"]:
        motivos.append(f"p95 {c['p95']:.0f} ms > {slo['p95']:.0f}")
    if slo.get("p99") is not None and c["p99"] is not None and c["p99"] > slo["p99"]:
        motivos.append(f"p99 {c['p99']:.0f} ms > {slo['p99']:.0f}")
    if slo.get("err") is not None and c["error"] > slo["err"]:
        motivos.append(f"error {100 * c['error']:.2f} % > {100 * slo['err']:.2f} %")
    if slo.get("checks") is not None and c["checks"] is not None and c["checks"] < slo["checks"]:
        motivos.append(f"checks {100 * c['checks']:.2f} % < {100 * slo['checks']:.2f} %")
    # Un paso sin peticiones no «cumple»: no midió. Es el PASS falso más barato que existe.
    if not c.get("peticiones"):
        return "NO-MEDIDO", ["cero peticiones en la ventana juzgada"]
    return ("FAIL", motivos) if motivos else ("PASS", [])


def cmd_paso(a):
    c = cifras_del_paso(a.dir)
    if not c:
        print(f"  paso: no hay summary.json ni detalle.json en {a.dir} — NO MEDIDO")
        return 2
    slo = {"p95": a.p95, "p99": a.p99, "err": a.err, "checks": a.checks}
    ver, motivos = juzgar(c, slo)
    fila = {k: c[k] for k in ("base", "vus", "peticiones", "rps", "p50", "p95", "p99", "error", "checks")}
    fila.update({"veredicto": ver, "motivos": motivos, "slo": slo})
    if a.vus is not None:
        fila["vus"] = a.vus
    with open(os.path.join(a.dir, "paso.json"), "w", encoding="utf-8") as f:
        json.dump(fila, f, indent=1, ensure_ascii=False)
    f2 = lambda v, s="{:.0f}": "—" if v is None else s.format(v)
    print(f"  {fila['vus'] or '?':>5} usuarios · {f2(c['rps'], '{:.1f}')} pet/s · p50 {f2(c['p50'])} · p95 {f2(c['p95'])} · "
          f"p99 {f2(c['p99'])} ms · error {f2(None if c['error'] is None else 100 * c['error'], '{:.2f}')} % · "
          f"{ver}{' — ' + '; '.join(motivos) if motivos else ''}  [{c['base']}]")
    return {"PASS": 0, "FAIL": 1}.get(ver, 2)


# ------------------------------------------------------------------ telemetría de un paso
def ventana(c):
    if c.get("inicio_s") and c.get("meseta_s"):
        t0 = c["inicio_s"] + c["rampa_s"]
        return t0, t0 + c["meseta_s"]
    return None


def agregados(filas, clave, campos, v):
    """{nombre: {campo: {media, max}}} sobre la ventana v (o todo si v es None)."""
    out = {}
    for f in filas:
        t = num(f.get("t"))
        if v and (t is None or t < v[0] or t > v[1]):
            continue
        d = out.setdefault(f.get(clave, "host"), {k: [] for k in campos})
        for k in campos:
            x = num(f.get(k))
            if x is not None:
                d[k].append(x)
    def p90(xs):
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(round(0.9 * (len(xs) - 1))))]
    return {n: {k: {"media": statistics.fmean(xs), "p90": p90(xs), "max": max(xs), "n": len(xs)} for k, xs in d.items() if xs}
            for n, d in out.items()}


BASES_PG = None  # None = todas; la fija cmd_informe con PERF_WATCH_PG o con los techos


def telemetria(d, c):
    tel = os.path.join(d, "telemetria")
    if not os.path.isdir(tel):
        return None
    v = ventana(c)
    return {
        "ventana": "meseta" if v else "toda la corrida",
        "host": agregados(leer_csv(os.path.join(tel, "host.csv")), "_", ["cpu_pct", "iowait_pct", "mem_usada_mb", "rx_bps", "tx_bps"], v).get("host", {}),
        "contenedores": agregados(leer_csv(os.path.join(tel, "contenedores.csv")), "contenedor", ["cpu_pct", "estrangulado_pct", "mem_mb", "pids"], v),
        "procesos": agregados(leer_csv(os.path.join(tel, "procesos.csv")), "grupo", ["procesos", "activos", "cpu_pct", "rss_mb"], v),
        "pg": {k: x for k, x in agregados(leer_csv(os.path.join(tel, "pg.csv")), "base", ["conexiones", "activas", "idle_en_tx", "esperando"], v).items()
               if BASES_PG is None or k in BASES_PG},
        "no_medido": (open(os.path.join(tel, "NO-MEDIDO.txt")).read().strip() if os.path.exists(os.path.join(tel, "NO-MEDIDO.txt")) else ""),
    }


METRICA_A_CAMPO = {"cpu": "cpu_pct", "mem": "mem_mb", "procesos": "procesos", "activos": "activos",
                   "conexiones": "conexiones", "activas": "activas", "rss": "rss_mb"}


def techos(env, manifiesto):
    """Los techos de cada pieza. Los declara el perfil (PERF_TECHOS), porque dependen de cómo está
    configurado lo que se mide: un proceso de un solo hilo tiene techo en 100 % de un núcleo aunque
    el contenedor no tenga límite. Un límite de CPU del contenedor se añade solo.
        PERF_TECHOS=web:cpu=100;phpfpm:procesos=40;moodle:conexiones=100
    """
    t = []
    declarados = (manifiesto or {}).get("techos") or env.get("PERF_TECHOS") or ""
    for par in [p for p in declarados.split(";") if p.strip()]:
        m = re.match(r"^\s*([^:]+):(\w+)=([\d.]+)\s*$", par)
        if m and m.group(2) in METRICA_A_CAMPO:
            t.append({"nombre": m.group(1).strip(), "metrica": m.group(2), "techo": float(m.group(3)), "origen": "declarado en PERF_TECHOS"})
    for nombre, info in ((manifiesto or {}).get("contenedores") or {}).items():
        if info.get("cpus") and not any(x["nombre"] == nombre and x["metrica"] == "cpu" for x in t):
            t.append({"nombre": nombre, "metrica": "cpu", "techo": 100.0 * info["cpus"], "origen": "límite del contenedor"})
    return t


def uso_de(tel, techo):
    campo = METRICA_A_CAMPO[techo["metrica"]]
    for familia in ("contenedores", "procesos", "pg"):
        d = (tel.get(familia) or {}).get(techo["nombre"])
        if d and campo in d:
            return d[campo]
    return None


# ------------------------------------------------------------------ informe
def ultima_corrida(target):
    base = os.path.join("reports", target, "k6", "runs")
    try:
        c = sorted(x for x in os.listdir(base) if os.path.exists(os.path.join(base, x, "escalera.csv")))
    except OSError:
        return None
    return os.path.join(base, c[-1]) if c else None


def cargar_corrida(corrida, env=None):
    man = leer_json(os.path.join(corrida, "RUN.json")) or {}
    pasos = []
    for fila in leer_csv(os.path.join(corrida, "escalera.csv")):
        d = os.path.join(corrida, fila["paso"])
        c = cifras_del_paso(d)
        if not c:
            continue
        c["vus"] = int(num(fila.get("vus"), c.get("vus") or 0))
        c["paso"] = fila["paso"]
        c["veredicto"] = fila.get("veredicto", "?")
        c["motivos"] = fila.get("motivos", "")
        c["tel"] = telemetria(d, c)
        pasos.append(c)
    pasos.sort(key=lambda x: x["vus"])
    return man, pasos


def analizar(man, pasos, env):
    out = {"pasos": [], "techos": techos(env, man)}
    # Lo que se vigila pero NO forma parte de lo que hay que comprar: el generador de carga, un
    # monitor. Se sigue mirando (para saber que no fue él el cuello) y se deja fuera del costo.
    fuera = {x.strip() for x in (env.get("PERF_FUERA_DEL_PRESUPUESTO") or "").split(",") if x.strip()}
    cumplen = [p for p in pasos if p["veredicto"] == "PASS"]
    fallan = [p for p in pasos if p["veredicto"] == "FAIL"]
    ultimo_ok = cumplen[-1] if cumplen else None
    primer_fallo = fallan[0] if fallan else None

    # Rodilla: el primer paso donde el caudal por usuario cae bajo el 85 % del mejor anterior, o
    # donde el p95 dobla al del primer paso. Antes de ahí el sistema escala; después, encola.
    rodilla = None
    mejor = None
    p95_0 = pasos[0]["p95"] if pasos else None
    for i, p in enumerate(pasos):
        por_vu = (p["rps"] or 0) / p["vus"] if p["vus"] else 0
        if mejor is not None and i > 0:
            if por_vu < 0.85 * mejor or (p95_0 and p["p95"] and p["p95"] > 2 * p95_0 and p["p95"] > 200):
                rodilla = (pasos[i - 1], p)
                break
        mejor = por_vu if mejor is None else max(mejor, por_vu)

    def saturacion(p):
        filas = []
        if not p.get("tel"):
            return filas
        for t in out["techos"]:
            u = uso_de(p["tel"], t)
            if not u:
                continue
            filas.append({"nombre": t["nombre"], "metrica": t["metrica"], "techo": t["techo"], "origen": t["origen"],
                          "media": u["media"], "p90": u.get("p90", u["max"]), "max": u["max"], "pct_media": 100 * u["media"] / t["techo"],
                          "pct_p90": 100 * u.get("p90", u["max"]) / t["techo"], "pct_max": 100 * u["max"] / t["techo"]})
        return sorted(filas, key=lambda x: -x["pct_p90"])

    for p in pasos:
        p["saturacion"] = saturacion(p)
        host = ((p.get("tel") or {}).get("host") or {}).get("cpu_pct")
        p["host_cpu"] = host["media"] if host else None

    # El recurso limitante se lee en el paso donde aparece el problema (rodilla o primer fallo).
    foco = (rodilla[1] if rodilla else None) or primer_fallo
    # La MEDIA engaña con un proceso de un solo hilo: a 200 usuarios el de Zajuna Móvil marcaba 44 %
    # de media y 96 % en los picos, y el p95 ya estaba en diez segundos. Una cola se forma en los
    # picos, no en la media: por eso el juicio mira el p90 de la utilización (el 10 % del tiempo por
    # encima) y el máximo, y solo después la media.
    limitante = None
    if foco and foco["saturacion"]:
        candidatos = [x for x in foco["saturacion"] if x["pct_p90"] >= 85 or x["pct_max"] >= 95 or x["pct_media"] >= 80]
        if candidatos:
            limitante = max(candidatos, key=lambda x: (x["pct_p90"], x["pct_media"]))
    out.update({"ultimo_ok": ultimo_ok, "primer_fallo": primer_fallo, "rodilla": rodilla, "foco": foco, "limitante": limitante})

    # Validez: si el HOST entero estaba saturado, el generador y el sistema compitieron y el número
    # describe la máquina, no la aplicación. Se avisa arriba del todo, no en una nota al pie.
    out["host_saturado"] = [p["vus"] for p in pasos if p["host_cpu"] is not None and p["host_cpu"] >= 85]

    # Costo unitario, en el último paso que cumple: es lo último que se sabe con certeza.
    if ultimo_ok and ultimo_ok["rps"]:
        r = ultimo_ok["rps"]
        u = {"rps": r, "vus": ultimo_ok["vus"], "peticiones_por_usuario_minuto": 60 * r / ultimo_ok["vus"], "recursos": []}
        if ultimo_ok.get("bytes_rx") and ultimo_ok.get("peticiones_total"):
            u["bytes_por_peticion"] = ultimo_ok["bytes_rx"] / ultimo_ok["peticiones_total"]
        tel = ultimo_ok.get("tel") or {}
        # Solo lo que crece con el caudal: núcleos y consultas a la vez. «Procesos con trabajo en
        # el intervalo» NO entra: a poco caudal casi todos los procesos de un pool tocan algo en
        # dos segundos y el número parece concurrencia sin serlo. La
        # memoria NO se divide por peticiones: es una huella por proceso, y va en su propia tabla.
        for familia, campos in (("contenedores", ("cpu_pct",)), ("procesos", ("cpu_pct",)), ("pg", ("activas",))):
            for nombre, d in (tel.get(familia) or {}).items():
                if nombre in fuera:
                    continue
                for campo in campos:
                    if campo in d:
                        u["recursos"].append({"nombre": nombre, "campo": campo, "media": d[campo]["media"], "max": d[campo]["max"],
                                              "por_100_rps": 100 * d[campo]["media"] / r})
        u["memoria"] = []
        for nombre, d in (tel.get("contenedores") or {}).items():
            if "mem_mb" in d:
                u["memoria"].append({"nombre": nombre, "mb": d["mem_mb"]["max"], "procesos": None, "mb_por_proceso": None})
        for nombre, d in (tel.get("procesos") or {}).items():
            if nombre in fuera:
                continue
            if "rss_mb" in d and d.get("procesos", {}).get("max"):
                u["memoria"].append({"nombre": nombre, "mb": d["rss_mb"]["max"], "procesos": d["procesos"]["max"],
                                     "mb_por_proceso": d["rss_mb"]["max"] / d["procesos"]["max"]})
        out["unitario"] = u
    return out


def concurrencia(e):
    if e.get("usuarios_concurrentes") is not None:
        return float(e["usuarios_concurrentes"]), "dado"
    try:
        return float(e["poblacion"]) * float(e["adopcion"]) * float(e["activos_diarios"]) * float(e["concurrencia_pico"]), \
            "población × adopción × activos diarios × concurrencia en la hora pico"
    except (KeyError, TypeError, ValueError):
        return None, "incompleto"


def dimensionar(an, demanda):
    u = an.get("unitario")
    if not u or not demanda:
        return []
    objetivo = float(demanda.get("objetivo_utilizacion", 0.6))
    filas = []
    for e in demanda.get("escenarios", []):
        n, como = concurrencia(e)
        if n is None:
            filas.append({"nombre": e.get("nombre", "?"), "error": "escenario incompleto"})
            continue
        rps = n * u["peticiones_por_usuario_minuto"] / 60.0
        f = {"nombre": e.get("nombre", "?"), "concurrentes": n, "como": como, "rps": rps, "fuente": e.get("fuente", "supuesto"),
             "objetivo": objetivo, "recursos": []}
        for r in u["recursos"]:
            necesario = rps * r["por_100_rps"] / 100.0 / objetivo
            f["recursos"].append({"nombre": r["nombre"], "campo": r["campo"], "necesario": necesario})
        if u.get("bytes_por_peticion"):
            f["mbps"] = rps * u["bytes_por_peticion"] * 8 / 1e6
        filas.append(f)
    return filas


UNIDAD = {"cpu_pct": ("núcleos", 0.01), "mem_mb": ("GB de RAM", 1 / 1024), "activos": ("procesos ocupados", 1),
          "procesos": ("procesos", 1), "rss_mb": ("GB residentes", 1 / 1024), "conexiones": ("conexiones", 1), "activas": ("consultas a la vez", 1)}


def fmt(v, s="{:.0f}"):
    return "—" if v is None else s.format(v)


def escribir_informe(target, corrida, man, pasos, an, demanda, filas_dem):
    L = []
    w = L.append
    w(f"# Capacidad — {target}")
    w("")
    w(f"- corrida: `{corrida}`")
    w(f"- fecha: {man.get('fecha', '?')} · host: {man.get('host', '?')}")
    w(f"- medido contra: `{man.get('base_url', '?')}` · código: {man.get('commit', '?')}")
    w(f"- guion: `{man.get('script', '?')}` (sha256 {str(man.get('script_sha256', '?'))[:12]}) · generador {man.get('k6', '?')}")
    w(f"- forma: {man.get('tipo', '?')}, rampa {man.get('rampa', '?')}, meseta {man.get('meseta', '?')} · "
      f"SLO: p95 ≤ {fmt(num((man.get('slo') or {}).get('p95')))} ms, p99 ≤ {fmt(num((man.get('slo') or {}).get('p99')))} ms, "
      f"error ≤ {fmt(None if num((man.get('slo') or {}).get('err')) is None else 100 * num((man.get('slo') or {}).get('err')), '{:.2f}')} %")
    w("")
    w("## Sobre declarado (lo que se midió, tal como estaba)")
    w("")
    cont = man.get("contenedores") or {}
    if cont:
        w("| Contenedor | Imagen | CPU límite | RAM límite | Procesos | Primer proceso |")
        w("|---|---|---|---|---:|---|")
        for n, i in cont.items():
            w(f"| `{n}` | `{str(i.get('imagen', '?')).split('@')[0]}` | {i.get('cpus') or 'sin límite'} | "
              f"{str(round(i['mem_mb'])) + ' MB' if i.get('mem_mb') else 'sin límite'} | {i.get('procesos', '?')} | `{(i.get('proceso') or '?')[:70]}` |")
    else:
        w("No medido: el perfil no declara `PERF_WATCH_CONTAINERS`.")
    if man.get("nota_sobre"):
        w("")
        w(man["nota_sobre"])
    w("")

    if an["host_saturado"]:
        w("> [!warning] Medición NO concluyente en algunos pasos")
        w(f"> El host entero pasó del 85 % de CPU en los pasos de {', '.join(str(x) for x in an['host_saturado'])} usuarios. "
          "Ahí el generador y el sistema compitieron por la misma máquina: la cifra describe el equipo, no la aplicación.")
        w("")

    w("## Escalera")
    w("")
    w("| Usuarios | pet/s | p50 ms | p95 ms | p99 ms | Error % | CPU host % | Veredicto |")
    w("|---:|---:|---:|---:|---:|---:|---:|---|")
    for p in pasos:
        w(f"| {p['vus']} | {fmt(p['rps'], '{:.1f}')} | {fmt(p['p50'])} | {fmt(p['p95'])} | {fmt(p['p99'])} | "
          f"{fmt(None if p['error'] is None else 100 * p['error'], '{:.2f}')} | {fmt(p['host_cpu'], '{:.0f}')} | "
          f"{p['veredicto']}{' — ' + p['motivos'] if p['motivos'] else ''} |")
    w("")
    base = pasos[0]["base"] if pasos else "?"
    w(f"Cifras de k6 sobre: **{base}**. Marca: medido.")
    w("")

    w("## Lectura")
    w("")
    ok, fallo, rod = an["ultimo_ok"], an["primer_fallo"], an["rodilla"]
    if ok:
        w(f"- **Último paso que cumple el SLO:** {ok['vus']} usuarios, {fmt(ok['rps'], '{:.1f}')} pet/s, p95 {fmt(ok['p95'])} ms. (medido)")
    else:
        w("- **Ningún paso cumple el SLO.** (medido)")
    if fallo:
        w(f"- **Punto de quiebre:** entre {ok['vus'] if ok else 0} y {fallo['vus']} usuarios ({fallo['motivos']}). (medido)")
    else:
        w("- **Punto de quiebre: no alcanzado.** La escalera terminó sin incumplir; el techo está por encima del último paso. (medido)")
    if rod:
        w(f"- **Rodilla:** entre {rod[0]['vus']} y {rod[1]['vus']} usuarios: el caudal por usuario deja de crecer en proporción o el p95 se dobla. (medido)")
    else:
        w("- **Rodilla: no observada** en el rango medido.")
    lim = an["limitante"]
    if lim:
        w(f"- **Recurso que se saturó primero:** `{lim['nombre']}` · {lim['metrica']}: {lim['pct_media']:.0f} % de su techo en media, "
          f"{lim['pct_p90']:.0f} % el 10 % del tiempo y {lim['pct_max']:.0f} % en el máximo (techo {lim['techo']:.0f}, {lim['origen']}), "
          f"en el paso de {an['foco']['vus']} usuarios. (medido)")
    elif an["foco"]:
        w("- **Recurso limitante: NO atribuido.** Ninguna pieza vigilada llegó al 80 % de su techo declarado en el paso donde aparece el problema. "
          "El cuello está en algo que no se mira (un candado, una cola interna, una dependencia) o falta declarar su techo en `PERF_TECHOS`.")
    else:
        w("- **Recurso limitante: no aplica**, no hubo degradación en el rango medido.")
    w("")

    foco = an["foco"] or ok
    if foco and foco.get("saturacion"):
        w(f"### Uso de cada pieza frente a su techo ({foco['vus']} usuarios)")
        w("")
        w("| Pieza | Métrica | Media | p90 | Máximo | Techo | % del techo (media / p90) | Origen del techo |")
        w("|---|---|---:|---:|---:|---:|---:|---|")
        for s in foco["saturacion"]:
            w(f"| `{s['nombre']}` | {s['metrica']} | {s['media']:.0f} | {s['p90']:.0f} | {s['max']:.0f} | {s['techo']:.0f} | {s['pct_media']:.0f} % / {s['pct_p90']:.0f} % | {s['origen']} |")
        w("")

    w("### Recursos por paso")
    w("")
    nombres = []
    for p in pasos:
        for fam in ("contenedores", "procesos", "pg"):
            for n in ((p.get("tel") or {}).get(fam) or {}):
                if (fam, n) not in nombres:
                    nombres.append((fam, n))
    if nombres:
        campo = {"contenedores": "cpu_pct", "procesos": "cpu_pct", "pg": "activas"}
        rot = {"contenedores": "CPU %", "procesos": "CPU %", "pg": "activas"}
        w("| Usuarios | " + " | ".join(f"`{n}` {rot[f]}" for f, n in nombres) + " |")
        w("|---:|" + "---:|" * len(nombres))
        for p in pasos:
            celdas = []
            for f, n in nombres:
                d = (((p.get("tel") or {}).get(f) or {}).get(n) or {}).get(campo[f])
                celdas.append(f"{d['media']:.0f} (máx {d['max']:.0f})" if d else "—")
            w(f"| {p['vus']} | " + " | ".join(celdas) + " |")
        w("")
        w("CPU: 100 = un núcleo entero. Ventana: " + ((pasos[0].get("tel") or {}).get("ventana") or "?") + ". Marca: medido.")
    else:
        w("No medido: sin telemetría no se puede atribuir el cuello a una pieza.")
    w("")

    u = an.get("unitario")
    w("## Costo unitario")
    w("")
    if u:
        w(f"En el último paso que cumple ({u['vus']} usuarios, {u['rps']:.1f} pet/s). Marca: medido.")
        w("")
        w(f"- Un usuario activo genera **{u['peticiones_por_usuario_minuto']:.1f} peticiones por minuto**.")
        if u.get("bytes_por_peticion"):
            w(f"- Cada petición pesa **{u['bytes_por_peticion'] / 1024:.1f} KB** de respuesta en promedio.")
        w("")
        w("| Pieza | Recurso | Uso medio | Por cada 100 pet/s |")
        w("|---|---|---:|---:|")
        for r in u["recursos"]:
            nombre_u, k = UNIDAD.get(r["campo"], (r["campo"], 1))
            w(f"| `{r['nombre']}` | {nombre_u} | {r['media'] * k:.2f} | {r['por_100_rps'] * k:.2f} |")
        if u.get("memoria"):
            w("")
            w("Huella de memoria en ese paso (máximo observado). Marca: medido.")
            w("")
            w("| Pieza | Memoria | Procesos | Por proceso |")
            w("|---|---:|---:|---:|")
            for m in u["memoria"]:
                w(f"| `{m['nombre']}` | {m['mb']:.0f} MB | {fmt(m['procesos'])} | {fmt(m['mb_por_proceso'], '{:.0f} MB')} |")
            w("")
            w("La memoria por proceso de un grupo del host es residente (RSS) e incluye páginas compartidas "
              "(caché de código, búferes compartidos): es una cota alta, no la memoria privada de cada proceso.")
    else:
        w("No medido: ningún paso cumplió el SLO, no hay punto sano del que sacar un costo.")
    w("")

    w("## Recursos por escenario de demanda")
    w("")
    if filas_dem:
        w("Marca: **extrapolado**. Proyección lineal desde el costo unitario, con utilización objetivo del "
          f"{100 * float(demanda.get('objetivo_utilizacion', 0.6)):.0f} %. Vale mientras el sistema escale en línea recta, "
          "y eso solo lo demuestra repetir la escalera con otro sobre (`perf-capacidad.py curva`).")
        w("")
        for f in filas_dem:
            if f.get("error"):
                w(f"- **{f['nombre']}**: {f['error']}.")
                continue
            w(f"### {f['nombre']} — {f['concurrentes']:.0f} usuarios a la vez ({f['como']}; fuente: {f['fuente']})")
            w("")
            w(f"Caudal necesario: {f['rps']:.0f} pet/s" + (f" · ancho de banda de respuesta: {f['mbps']:.1f} Mbit/s" if f.get("mbps") else "") + ".")
            w("")
            w("| Pieza | Recurso | Necesario |")
            w("|---|---|---:|")
            for r in f["recursos"]:
                nombre_u, k = UNIDAD.get(r["campo"], (r["campo"], 1))
                w(f"| `{r['nombre']}` | {nombre_u} | {r['necesario'] * k:.1f} |")
            w("")
    else:
        w("No calculado: falta `targets/" + target + "/carga/demanda.json` o no hay costo unitario.")
    w("")
    w("## Lo que este informe NO dice")
    w("")
    w("- No mide lo que el perfil no vigila: una pieza que no está en `PERF_WATCH_*` no aparece, y su ausencia no es «sin problema».")
    w("- Una escalera en un solo sobre no demuestra cómo escala al añadir núcleos o réplicas.")
    w("- Las cifras por escenario heredan el error de sus supuestos de demanda, que están en `demanda.json` con su fuente.")
    return "\n".join(L) + "\n"


def limpiar(o):
    """Quita lo que no es serializable o es ruido antes de escribir capacidad.json."""
    if isinstance(o, dict):
        return {k: limpiar(v) for k, v in o.items() if k not in ("detalle",)}
    if isinstance(o, (list, tuple)):
        return [limpiar(x) for x in o]
    return o


def cmd_informe(a):
    corrida = a.corrida or ultima_corrida(a.target)
    if not corrida or not os.path.exists(os.path.join(corrida, "escalera.csv")):
        print(f"perf-capacidad: no hay ninguna escalera en reports/{a.target}/k6/runs/ — corre `make perf-escalera`.", file=sys.stderr)
        return 2
    env = leer_env(os.path.join("targets", a.target, "target.env"))
    # El muestreo ve TODAS las bases de PostgreSQL del host. Al informe van las que el perfil
    # nombra (PERF_WATCH_PG) o, si no, las que tienen techo declarado.
    global BASES_PG
    nombradas = [x.strip() for x in (env.get("PERF_WATCH_PG") or "").split(",") if x.strip()]
    con_techo = [m.group(1).strip() for m in re.finditer(r"([^;:]+):(?:conexiones|activas)=", env.get("PERF_TECHOS") or "")]
    BASES_PG = set(nombradas or con_techo) or None
    man, pasos = cargar_corrida(corrida)
    if not pasos:
        print(f"perf-capacidad: {corrida} no tiene ningún paso legible.", file=sys.stderr)
        return 2
    an = analizar(man, pasos, env)
    demanda = leer_json(os.path.join("targets", a.target, "carga", "demanda.json"))
    filas_dem = dimensionar(an, demanda)
    md = escribir_informe(a.target, corrida, man, pasos, an, demanda or {}, filas_dem)
    for destino in (corrida, os.path.join("reports", a.target, "k6")):
        with open(os.path.join(destino, "CAPACIDAD.md"), "w", encoding="utf-8") as f:
            f.write(md)
        with open(os.path.join(destino, "capacidad.json"), "w", encoding="utf-8") as f:
            json.dump(limpiar({"corrida": corrida, "manifiesto": man, "analisis": an, "demanda": filas_dem}), f, indent=1, ensure_ascii=False, default=str)
    print(md)
    print(f"perf-capacidad: escrito {os.path.join(corrida, 'CAPACIDAD.md')}")
    return 0


# ------------------------------------------------------------------ comparar
def cmd_comparar(a):
    na, nb = (a.nombres.split(",") + ["A", "B"])[:2] if a.nombres else ("A", "B")
    (ma, pa), (mb, pb) = cargar_corrida(a.a), cargar_corrida(a.b)
    ia, ib = {p["vus"]: p for p in pa}, {p["vus"]: p for p in pb}
    L = [f"# Comparación — {na} frente a {nb}", "",
         f"- {na}: `{a.a}` · código {ma.get('commit', '?')} · {ma.get('nota_sobre', '')}",
         f"- {nb}: `{a.b}` · código {mb.get('commit', '?')} · {mb.get('nota_sobre', '')}", "",
         f"| Usuarios | pet/s {na} | pet/s {nb} | Δ | p95 {na} | p95 {nb} | Δ | p99 {na} | p99 {nb} | Error % {na} | Error % {nb} | Veredicto |",
         "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]

    def delta(x, y):
        return "—" if not x or y is None else f"{100 * (y - x) / x:+.0f} %"

    for v in sorted(set(ia) | set(ib)):
        x, y = ia.get(v), ib.get(v)
        g = lambda p, k, s="{:.0f}": fmt(p[k] if p else None, s)
        e = lambda p: fmt(None if not p or p["error"] is None else 100 * p["error"], "{:.2f}")
        L.append(f"| {v} | {g(x, 'rps', '{:.1f}')} | {g(y, 'rps', '{:.1f}')} | {delta(x and x['rps'], y and y['rps'])} | "
                 f"{g(x, 'p95')} | {g(y, 'p95')} | {delta(x and x['p95'], y and y['p95'])} | {g(x, 'p99')} | {g(y, 'p99')} | "
                 f"{e(x)} | {e(y)} | {(x or {}).get('veredicto', '—')} → {(y or {}).get('veredicto', '—')} |")
    oka = [p for p in pa if p["veredicto"] == "PASS"]
    okb = [p for p in pb if p["veredicto"] == "PASS"]
    L += ["", f"- Último paso que cumple: {na} = {oka[-1]['vus'] if oka else 'ninguno'} usuarios; {nb} = {okb[-1]['vus'] if okb else 'ninguno'} usuarios."]
    if oka and okb and oka[-1]["rps"] and okb[-1]["rps"]:
        L.append(f"- Caudal en ese paso: {oka[-1]['rps']:.1f} → {okb[-1]['rps']:.1f} pet/s ({delta(oka[-1]['rps'], okb[-1]['rps'])}).")
    L += ["", "Marca: medido. Solo es una comparación válida si las dos corridas usaron el mismo guion, la misma forma y el mismo sobre salvo el cambio que se evalúa."]
    md = "\n".join(L) + "\n"
    salida = os.path.join(a.b, f"COMPARACION-{re.sub(r'[^A-Za-z0-9_-]', '_', na)}-vs-{re.sub(r'[^A-Za-z0-9_-]', '_', nb)}.md")
    with open(salida, "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    print(f"perf-capacidad: escrito {salida}")
    return 0


# ------------------------------------------------------------------ curva (ley universal de escalabilidad)
def cmd_curva(a):
    pts = []
    for par in a.puntos:
        x, _, n = par.partition(":")
        pts.append((float(n), float(x)))
    pts.sort()
    if len(pts) < 3:
        print("perf-capacidad: la curva necesita al menos tres sobres medidos (valor:paralelismo).", file=sys.stderr)
        return 2
    n1, x1 = pts[0]
    lam = x1 / n1
    mejor = None
    # X(N) = λN / (1 + α(N−1) + βN(N−1)).  α = contención (lo que se hace en serie),
    # β = coherencia (lo que cuesta ponerse de acuerdo). Rejilla: tres puntos no dan para más.
    for ia in range(0, 1001):
        al = ia / 1000.0
        for ib in range(0, 501):
            be = ib / 10000.0
            err = sum((lam * n / (1 + al * (n - 1) + be * n * (n - 1)) - x) ** 2 for n, x in pts)
            if mejor is None or err < mejor[0]:
                mejor = (err, al, be)
    _, al, be = mejor
    print("| Paralelismo | Medido | Modelo |")
    print("|---:|---:|---:|")
    for n, x in pts:
        print(f"| {n:g} | {x:.1f} | {lam * n / (1 + al * (n - 1) + be * n * (n - 1)):.1f} |")
    print()
    print(f"- contención α = {al:.3f} · coherencia β = {be:.4f} (ajustado, {len(pts)} puntos)")
    if be > 0:
        nmax = math.sqrt((1 - al) / be)
        print(f"- el caudal deja de crecer hacia un paralelismo de {nmax:.0f}: añadir más allá lo empeora. (extrapolado)")
    elif al > 0:
        print(f"- techo asintótico: {lam / al:.0f} (en las unidades medidas), por muchas unidades que se añadan. (extrapolado)")
    else:
        print("- escalado lineal en el rango medido. (medido; fuera del rango es un supuesto)")
    for n in a.proyectar or []:
        print(f"- con paralelismo {n:g}: {lam * n / (1 + al * (n - 1) + be * n * (n - 1)):.0f} (extrapolado)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("paso")
    p.add_argument("dir")
    p.add_argument("--vus", type=int)
    p.add_argument("--p95", type=float)
    p.add_argument("--p99", type=float)
    p.add_argument("--err", type=float)
    p.add_argument("--checks", type=float)
    p.set_defaults(f=cmd_paso)
    i = sub.add_parser("informe")
    i.add_argument("target")
    i.add_argument("--corrida")
    i.set_defaults(f=cmd_informe)
    c = sub.add_parser("comparar")
    c.add_argument("a")
    c.add_argument("b")
    c.add_argument("--nombres")
    c.set_defaults(f=cmd_comparar)
    u = sub.add_parser("curva")
    u.add_argument("puntos", nargs="+", help="valor:paralelismo, p. ej. 120:1 210:2 330:4")
    u.add_argument("--proyectar", type=float, nargs="*")
    u.set_defaults(f=cmd_curva)
    a = ap.parse_args()
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
