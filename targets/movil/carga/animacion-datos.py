#!/usr/bin/env python3
"""Series por segundo de una corrida, para la animación. Solo biblioteca estándar.

Cada número sale de un registro real de la corrida:
  - llegadas y salidas por segundo, y peticiones EN VUELO: del log de nginx (rid=k6-…, rt=)
  - llamadas a Moodle en vuelo y su duración: del log del backend ([ws] rid=… ms=)
  - CPU de la API y procesos de php-fpm: de la telemetría (contenedores.csv, procesos.csv)
  - p95 de cada segundo: de los rt de nginx
  - respuestas 429 por segundo: del estado en el log de nginx
  - líneas de log del backend por segundo: de la marca de tiempo de cada línea del log
  - filas escritas en la base de la API por petición: de `escrituras.json` (hook-despues)
El log de nginx tiene resolución de un segundo: dentro de cada segundo las llegadas se reparten
uniformemente. Eso es lo único interpolado, y se dice.

  animacion-datos.py <dir-del-paso> <etiqueta> [--telefono <dir-telefono>] [--procesos N] >> datos.json

Una etiqueta «Nombre del escenario|antes» o «…|despues» marca la corrida como mitad de una
pareja: la animación empareja las dos mitades del mismo nombre y las dibuja a la vez.
"""
import argparse, csv, datetime as dt, json, os, re, sys, statistics

#: Tablas de rendimiento de la API: lo que la fase 0 dejó de escribir en cada petición.
TABLAS_RENDIMIENTO = ("endpoint_test_results", "performance_logs", "timeout_config_logs")

def leer_nginx(ruta):
    out = []
    for l in open(ruta, errors="replace"):
        m = re.search(r'\[(\d\d/\w+/\d{4}:\d\d:\d\d:\d\d) [^\]]*\] "(\w+) (\S+)[^"]*" (\d+) (\d+)B rt=([\d.]+)s rid=(\S+)(?: ua="([^"]*)")?', l)
        if not m: continue
        # Del generador: lleva su rid (k6-…) o, si la petición no lo manda (el login), su User-Agent.
        if not (m.group(7).startswith("k6-") or (m.group(8) or "").startswith("k6-")): continue
        t = dt.datetime.strptime(m.group(1), "%d/%b/%Y:%H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp()
        out.append((t, m.group(2), re.sub(r"/\d+", "/{id}", m.group(3).split("?")[0].replace("/mobile/api", "")), int(m.group(4)), float(m.group(6)) * 1000, m.group(7)))
    return out

def leer_ws(ruta):
    out = []
    for l in open(ruta, errors="replace"):
        m = re.search(r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)Z .*\[ws\] rid=(k6-\S+) fn=(\S+) status=\d+ ms=(\d+)', l)
        if not m: continue
        t = dt.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp()
        out.append((t, m.group(2), m.group(3), int(m.group(4))))
    return out

def lineas_por_segundo(ruta, desde, hasta):
    """Cuántas líneas escribió el backend en cada segundo de la ventana."""
    d = {}
    for l in open(ruta, errors="replace"):
        m = re.match(r'(?:\S+\s+\|\s+)?(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)Z ', l)
        if not m: continue
        t = int(dt.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp())
        if desde <= t <= hasta: d[t] = d.get(t, 0) + 1
    return d

def serie_tel(ruta, col, nombre, clave):
    d = {}
    for r in csv.DictReader(open(ruta)):
        if r.get(clave) != nombre: continue
        d[int(float(r["t"]))] = float(r[col])
    return d

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir"); ap.add_argument("etiqueta")
    ap.add_argument("--telefono"); ap.add_argument("--procesos", type=int)
    args = ap.parse_args()
    d, tel = args.dir, args.telefono
    etiqueta, _, lado = args.etiqueta.partition("|")
    det = json.load(open(os.path.join(d, "detalle.json")))
    ini = det.get("inicio_s"); rampa = det.get("rampa_s") or 0; meseta = det.get("meseta_s") or 0
    ng = leer_nginx(os.path.join(d, "logs", "movil_api-nginx-1.log"))
    ws = leer_ws(os.path.join(d, "logs", "movil_api-web-1.log"))
    if ini:
        # Solo la ventana de ESTE paso: el volcado del log de nginx puede traer pasos anteriores
        # (un json-log roto hace que `docker logs --since` devuelva de más; L-R9-02).
        desde, hasta = ini - 90, ini + (det.get("duracion_ms") or 0) / 1000 + 5
        ng = [x for x in ng if desde <= x[0] <= hasta]
        ws = [x for x in ws if desde <= x[0] <= hasta]
    if not ng: sys.exit("sin peticiones k6 en el log de nginx")
    t0 = int(min(t for t, *_ in ng)); t1 = int(max(t + rt / 1000 for t, _, _, _, rt, _ in ng)) + 1
    cpu = serie_tel(os.path.join(d, "telemetria", "contenedores.csv"), "cpu_pct", "movil_api-web-1", "contenedor")
    fpm = serie_tel(os.path.join(d, "telemetria", "procesos.csv"), "procesos", "phpfpm", "grupo")
    fpmcpu = serie_tel(os.path.join(d, "telemetria", "procesos.csv"), "cpu_pct", "phpfpm", "grupo")
    n = t1 - t0
    llegadas = [0] * n; salidas = [0] * n; vuelo = [0] * n; rts = [[] for _ in range(n)]; errores = [0] * n; rechazos = [0] * n
    mvuelo = [0] * n; mllam = [0] * n; mms = [[] for _ in range(n)]
    # El log de nginx trunca la llegada al segundo: dentro de cada segundo, las llegadas se
    # reparten uniformemente (la k-ésima de m, en s + (k+0,5)/m). Es lo único interpolado.
    por_seg = {}
    for t, met, ruta, est, rt, rid in ng:
        por_seg.setdefault(int(t), []).append((rt, est))
    conc = [0.0] * n
    for seg, lista in por_seg.items():
        a = seg - t0; m = len(lista)
        llegadas[a] += m
        for k, (rt, est) in enumerate(lista):
            p_ini = seg + (k + 0.5) / m; p_fin = p_ini + rt / 1000
            b = int(p_fin) - t0
            if 0 <= b < n: salidas[b] += 1
            for s in range(a, min(b, n - 1) + 1):
                vuelo[s] += 1
                # concurrencia media en el segundo s = solapamiento de [p_ini, p_fin] con [s, s+1]
                lo, hi = max(p_ini, t0 + s), min(p_fin, t0 + s + 1)
                if hi > lo: conc[s] += hi - lo
            rts[a].append(rt)
            if est >= 500 or est == 499: errores[a] += 1
            if est == 429: rechazos[a] += 1
    conc = [round(x, 2) for x in conc]
    mconc = [0.0] * n
    por_seg_ws = {}
    for t, rid, fn, ms in ws:
        por_seg_ws.setdefault(int(t), []).append(ms)
    for seg, lista in por_seg_ws.items():
        m = len(lista)
        for k, ms in enumerate(lista):
            # el log se escribe al TERMINAR la llamada, con el segundo truncado: se reparte igual
            l_fin = seg + (k + 0.5) / m; l_ini = l_fin - ms / 1000
            a = int(l_ini) - t0; b = int(l_fin) - t0
            if not (0 <= b < n): continue
            mllam[max(a, 0)] += 1
            for s in range(max(a, 0), b + 1):
                mvuelo[s] += 1
                lo, hi = max(l_ini, t0 + s), min(l_fin, t0 + s + 1)
                if hi > lo: mconc[s] += hi - lo
            mms[b].append(ms)
    mconc = [round(x, 2) for x in mconc]
    def q(xs, p):
        if not xs: return None
        xs = sorted(xs); return round(xs[min(len(xs) - 1, int(p * (len(xs) - 1)))])
    def cerca(serie, t):
        for dt_ in (0, -1, 1, -2, 2): 
            if t + dt_ in serie: return serie[t + dt_]
        return None
    lineas = lineas_por_segundo(os.path.join(d, "logs", "movil_api-web-1.log"), t0, t1)
    log_lineas = [lineas.get(t0 + s, 0) for s in range(n)]
    filas = None
    try:
        tablas = json.load(open(os.path.join(d, "escrituras.json")))["tablas"]
        filas = round(sum(tablas[k]["filas_por_peticion"] for k in TABLAS_RENDIMIENTO if k in tablas), 3)
    except (OSError, KeyError, ValueError):
        pass
    m_proc = re.match(r"(\d+) proceso", etiqueta)
    procesos = args.procesos or (int(m_proc.group(1)) if m_proc else 1)
    salida = {
        "etiqueta": etiqueta, "lado": lado or None, "t0": t0, "segundos": n, "vus": det.get("vus"),
        "fase": {"rampa": [ini - t0 if ini else 0, (ini - t0 + rampa) if ini else rampa], "meseta": [(ini - t0 + rampa) if ini else rampa, (ini - t0 + rampa + meseta) if ini else rampa + meseta]},
        "series": {
            "llegadas": llegadas, "salidas": salidas, "en_vuelo": vuelo, "concurrencia": conc, "errores": errores,
            "rechazos": rechazos, "log_lineas": log_lineas,
            "moodle_concurrencia": mconc,
            "p50": [q(x, .5) for x in rts], "p95": [q(x, .95) for x in rts],
            "moodle_llamadas": mllam, "moodle_en_vuelo": mvuelo, "moodle_ms_p50": [q(x, .5) for x in mms],
            "api_cpu": [cerca(cpu, t0 + s) for s in range(n)], "fpm_procesos": [cerca(fpm, t0 + s) for s in range(n)], "fpm_cpu": [cerca(fpmcpu, t0 + s) for s in range(n)],
        },
        "resumen": {"peticiones": len(ng), "moodle": len(ws), "p95_meseta": (det.get("meseta") or det["global"])["ms"]["p(95)"], "rps_meseta": (det.get("meseta") or det["global"])["por_segundo"],
                    "procesos": procesos, "rechazos": sum(rechazos), "filas_por_peticion": filas,
                    "lineas_log_por_peticion": round(sum(log_lineas) / len(ng), 1)},
    }
    if tel:
        # Una persona real: cada petición con inicio y fin en ms (reloj del teléfono).
        pets = []
        for r in csv.DictReader(open(os.path.join(tel, "peticiones.csv"))):
            if not r["fin"]: continue
            pets.append({"rec": r["recorrido"], "repe": int(r["repe"]), "ruta": re.sub(r"/\d+", "/{id}", r["url"]).replace("/mobile/api", ""), "ini": float(r["inicio"]), "fin": float(r["fin"]), "ms": float(r["ms_telefono"]), "srv": float(r["ms_servidor"]) if r["ms_servidor"] else None})
        if pets:
            base = min(p["ini"] for p in pets)
            for p in pets: p["ini"] -= base; p["fin"] -= base
        salida["telefono"] = pets
    print(json.dumps(salida, separators=(",", ":")))

if __name__ == "__main__":
    main()
