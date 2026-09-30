#!/usr/bin/env python3
"""Del tráfico REAL de la app a su perfil de peticiones. Solo biblioteca estándar.

La fuente es lo que ya quedó registrado cuando alguien usó la app en un teléfono contra el
despliegue local: el log de acceso del proxy (una línea por petición, con su `rid`) y el log del
backend (una línea `[ws] rid=… fn=…` por cada llamada a Moodle). El `rid` las casa.

Esto NO es el código ni un documento: es lo que la app hizo de verdad. De aquí sale el modelo de
carga (k6/modelo.js) y contra esto se comprueba su fidelidad.

  grabacion.py extraer  <dir>                   vuelca los dos logs a <dir>/ (proxy.log, backend.log)
  grabacion.py analizar <dir> [--desde AAAA-MM-DD] [--ua texto]
                                                escribe peticiones.csv, rutas.csv, rafagas.csv, RESUMEN.md

LÍMITE QUE HAY QUE LEER: el tráfico lo generó quien probaba la app, no una población. Las
SECUENCIAS por pantalla son medidas; la MEZCLA de pantallas y el ritmo entre ellas son los de un
probador, y en el modelo de carga van declarados como supuesto.
"""
import argparse
import csv
import datetime as dt
import os
import re
import statistics
import subprocess
import sys

PROXY = os.environ.get("GRAB_PROXY", "movil_api-nginx-1")
BACKEND = os.environ.get("GRAB_BACKEND", "movil_api-web-1")
PREFIJO = os.environ.get("GRAB_PREFIJO", "/mobile/api")

LINEA = re.compile(r'^(\S+) \[([^\]]+)\] "(\S+) (\S+) [^"]*" (\d+) (\d+)B rt=([\d.]+)s rid=(\S+) ua="([^"]*)"')
WS = re.compile(r"\[ws\] rid=(\S+) fn=(\S+) status=(\d+) ms=(\d+)")


def cola(contenedor):
    """docker logs leído DESDE EL FINAL. Un apagón deja bytes nulos en el json-log y la lectura
    hacia delante se detiene ahí sin avisar (medido el 2026-09-30: `docker logs` entero terminaba
    dos días antes que `--tail 8`). Se busca la cola más larga que todavía llega a hoy."""
    def leer(n):
        r = subprocess.run(["docker", "logs", "-t", "--tail", str(n), contenedor], capture_output=True, text=True, errors="replace")
        return (r.stdout + r.stderr).splitlines()
    hoy = leer(1)
    if not hoy:
        return []
    marca = hoy[-1][:10]
    n, mejor = 2000, leer(2000)
    while True:
        sig = leer(n * 2)
        if not sig or sig[-1][:10] != marca and max(l[:10] for l in sig) != max(l[:10] for l in mejor):
            break
        if len(sig) < n * 2:          # ya no hay más líneas: se leyó todo
            return sorted(sig, key=lambda l: l[:30])
        mejor, n = sig, n * 2
        if n > 8_000_000:
            break
    # Entre n y 2n está el punto donde la lectura se rompe: bisección.
    lo, hi = n, n * 2
    while hi - lo > 200:
        mid = (lo + hi) // 2
        x = leer(mid)
        if x and max(l[:10] for l in x) == max(l[:10] for l in mejor):
            lo, mejor = mid, x
        else:
            hi = mid
    return sorted(mejor, key=lambda l: l[:30])


def extraer(a):
    os.makedirs(a.dir, exist_ok=True)
    for nombre, cont in (("proxy.log", PROXY), ("backend.log", BACKEND)):
        # Las dos mitades: lo que se lee hacia delante (hasta el punto roto, si lo hay) y la cola.
        r = subprocess.run(["docker", "logs", "-t", cont], capture_output=True, text=True, errors="replace")
        lineas = sorted(set((r.stdout + r.stderr).splitlines()) | set(cola(cont)), key=lambda l: l[:30])
        with open(os.path.join(a.dir, nombre), "w", encoding="utf-8") as f:
            f.write("\n".join(lineas) + "\n")
        print(f"{nombre}: {len(lineas)} líneas de {cont}" + (f" ({lineas[0][:10]} a {lineas[-1][:10]})" if lineas else ""))
    return 0


def normalizar(ruta):
    ruta = ruta.split("?", 1)[0]
    if ruta.startswith(PREFIJO):
        ruta = ruta[len(PREFIJO):] or "/"
    return re.sub(r"/\d+", "/{id}", ruta)


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def analizar(a):
    ws = {}
    try:
        for l in open(os.path.join(a.dir, "backend.log"), encoding="utf-8", errors="replace"):
            m = WS.search(l)
            if m:
                ws.setdefault(m.group(1), []).append((m.group(2), int(m.group(3)), int(m.group(4))))
    except OSError:
        pass
    # ¿Desde cuándo hay log del backend? Antes de eso «0 llamadas a Moodle» significa «no se sabe».
    primera_ws = None
    for l in open(os.path.join(a.dir, "backend.log"), encoding="utf-8", errors="replace"):
        if "[ws] rid=" in l:
            primera_ws = l[:19]
            break

    filas = []
    for l in open(os.path.join(a.dir, "proxy.log"), encoding="utf-8", errors="replace"):
        l = l.split(" ", 1)[1] if re.match(r"^\d{4}-\d\d-\d\dT", l) else l
        m = LINEA.match(l)
        if not m:
            continue
        ip, cuando, metodo, ruta, estado, tam, rt, rid, ua = m.groups()
        t = dt.datetime.strptime(cuando, "%d/%b/%Y:%H:%M:%S %z")
        if a.desde and t.strftime("%Y-%m-%d") < a.desde:
            continue
        if a.hasta and t.strftime("%Y-%m-%d") > a.hasta:
            continue
        if a.ventana and not (a.ventana[0] <= t.timestamp() <= a.ventana[1]):
            continue
        if a.ua and a.ua not in ua:
            continue
        if not ruta.startswith(PREFIJO):
            continue
        llamadas = ws.get(rid)
        con_ws = primera_ws is not None and t.strftime("%Y-%m-%dT%H:%M:%S") >= primera_ws
        filas.append({
            "t": t, "ip": ip, "metodo": metodo, "ruta": normalizar(ruta), "cruda": ruta, "estado": int(estado), "bytes": int(tam),
            "ms": float(rt) * 1000, "rid": rid, "ua": ua[:60], "fresco": "fresco=1" in ruta,
            "moodle": (len(llamadas) if llamadas else 0) if con_ws else None,
            "moodle_ms": sum(x[2] for x in llamadas) if llamadas else (0 if con_ws else None),
            "funciones": " ".join(x[0] for x in llamadas) if llamadas else "",
        })
    if not filas:
        print("grabacion: ninguna petición en el rango pedido.", file=sys.stderr)
        return 2
    filas.sort(key=lambda f: f["t"])

    with open(os.path.join(a.dir, "peticiones.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t", "cliente", "metodo", "ruta", "estado", "bytes", "ms", "moodle", "moodle_ms", "funciones", "rid"])
        for x in filas:
            w.writerow([x["t"].isoformat(), x["ua"][:30], x["metodo"], x["cruda"], x["estado"], x["bytes"], f"{x['ms']:.0f}",
                        "" if x["moodle"] is None else x["moodle"], "" if x["moodle_ms"] is None else x["moodle_ms"], x["funciones"], x["rid"]])

    # ---- por ruta
    rutas = {}
    for x in filas:
        rutas.setdefault((x["metodo"], x["ruta"]), []).append(x)
    orden = sorted(rutas.items(), key=lambda kv: -len(kv[1]))
    total = len(filas)
    with open(os.path.join(a.dir, "rutas.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metodo", "ruta", "n", "pct", "ok", "ms_p50", "ms_p95", "bytes_p50", "bytes_max", "moodle_p50", "moodle_max", "moodle_medidas", "funciones_mas_vistas"])
        for (metodo, ruta), xs in orden:
            ok = [x for x in xs if 200 <= x["estado"] < 300]
            mm = [x["moodle"] for x in ok if x["moodle"] is not None]
            vistas = {}
            for x in ok:
                for fn in x["funciones"].split():
                    vistas[fn] = vistas.get(fn, 0) + 1
            top = " ".join(k for k, _ in sorted(vistas.items(), key=lambda kv: -kv[1])[:6])
            w.writerow([metodo, ruta, len(xs), f"{100 * len(xs) / total:.1f}", len(ok), f"{pct([x['ms'] for x in ok], 50) or 0:.0f}",
                        f"{pct([x['ms'] for x in ok], 95) or 0:.0f}", pct([x["bytes"] for x in ok], 50) or 0, max([x["bytes"] for x in ok] or [0]),
                        "" if not mm else pct(mm, 50), "" if not mm else max(mm), len(mm), top])

    # ---- ráfagas: peticiones del mismo cliente separadas menos de `hueco` segundos = un gesto
    hueco = a.hueco
    rafagas, actual = [], {}
    for x in filas:
        k = (x["ip"], x["ua"])
        r = actual.get(k)
        if r and (x["t"] - r[-1]["t"]).total_seconds() <= hueco:
            r.append(x)
        else:
            if r:
                rafagas.append(r)
            actual[k] = [x]
    rafagas += [r for r in actual.values() if r]
    firmas = {}
    for r in rafagas:
        firma = " + ".join(sorted(f"{x['metodo']} {x['ruta']}" for x in r if 200 <= x["estado"] < 300))
        if firma:
            firmas.setdefault(firma, []).append(r)
    with open(os.path.join(a.dir, "rafagas.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["veces", "peticiones", "moodle_p50", "firma"])
        for firma, rs in sorted(firmas.items(), key=lambda kv: -len(kv[1])):
            mm = [sum(x["moodle"] or 0 for x in r) for r in rs if all(x["moodle"] is not None for x in r)]
            w.writerow([len(rs), len(rs[0]), "" if not mm else pct(mm, 50), firma])

    # ---- ritmo: huecos entre ráfagas del mismo cliente = tiempo de «pensar»
    pensar = []
    ult = {}
    for r in sorted(rafagas, key=lambda r: r[0]["t"]):
        k = (r[0]["ip"], r[0]["ua"])
        if k in ult:
            g = (r[0]["t"] - ult[k]).total_seconds()
            if hueco < g < 300:
                pensar.append(g)
        ult[k] = r[-1]["t"]

    dias = sorted({x["t"].strftime("%Y-%m-%d") for x in filas})
    clientes = sorted({x["ua"] for x in filas})
    minutos_activos = len({(x["ua"], x["t"].strftime("%Y-%m-%d %H:%M")) for x in filas})
    L = ["# Grabación del tráfico real de la app", "",
         f"- origen: `docker logs {PROXY}` y `docker logs {BACKEND}`, casados por `rid`",
         f"- rango: {dias[0]} a {dias[-1]} · {total} peticiones · {len(rafagas)} ráfagas",
         f"- clientes: {'; '.join(clientes)}",
         f"- log del backend disponible desde: {primera_ws or 'NO HAY'} (antes de eso la columna de Moodle va vacía: no medido)",
         f"- ritmo: {total / max(minutos_activos, 1):.1f} peticiones por minuto de uso (minutos con al menos una petición: {minutos_activos})",
         ""]
    if pensar:
        L.append(f"- tiempo entre gestos (hueco entre ráfagas de {hueco:g} s a 5 min): mediana {statistics.median(pensar):.1f} s, "
                 f"p25 {pct(pensar, 25):.1f} s, p75 {pct(pensar, 75):.1f} s, n={len(pensar)}")
        L.append("")
    L += ["## Por ruta", "", "| Ruta | n | % | ms p50 | ms p95 | bytes p50 | bytes máx | Moodle p50 | Moodle máx | con log |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for (metodo, ruta), xs in orden:
        ok = [x for x in xs if 200 <= x["estado"] < 300]
        mm = [x["moodle"] for x in ok if x["moodle"] is not None]
        L.append(f"| `{metodo} {ruta}` | {len(xs)} | {100 * len(xs) / total:.1f} | {pct([x['ms'] for x in ok], 50) or 0:.0f} | "
                 f"{pct([x['ms'] for x in ok], 95) or 0:.0f} | {pct([x['bytes'] for x in ok], 50) or 0} | {max([x['bytes'] for x in ok] or [0])} | "
                 f"{'—' if not mm else pct(mm, 50)} | {'—' if not mm else max(mm)} | {len(mm)} |")
    estados = {}
    for x in filas:
        estados[x["estado"]] = estados.get(x["estado"], 0) + 1
    L += ["", "## Estados", "", ", ".join(f"{k}: {v}" for k, v in sorted(estados.items())), "",
          "## Ráfagas más frecuentes (un gesto de la persona)", "", "| Veces | Peticiones | Moodle p50 | Qué pidió la app |", "|---:|---:|---:|---|"]
    for firma, rs in sorted(firmas.items(), key=lambda kv: -len(kv[1]))[:40]:
        mm = [sum(x["moodle"] or 0 for x in r) for r in rs if all(x["moodle"] is not None for x in r)]
        L.append(f"| {len(rs)} | {len(rs[0])} | {'—' if not mm else pct(mm, 50)} | {firma} |")
    with open(os.path.join(a.dir, "RESUMEN.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L[:8]))
    print(f"escrito: {a.dir}/RESUMEN.md, rutas.csv, rafagas.csv, peticiones.csv")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extraer")
    e.add_argument("dir")
    e.set_defaults(f=extraer)
    n = sub.add_parser("analizar")
    n.add_argument("dir")
    n.add_argument("--desde")
    n.add_argument("--hasta")
    n.add_argument("--ua", help="solo peticiones cuyo agente de usuario contenga este texto")
    n.add_argument("--hueco", type=float, default=2.0, help="segundos que separan dos gestos")
    n.add_argument("--ventana", type=float, nargs=2, metavar=("DESDE", "HASTA"), help="solo peticiones entre estos dos instantes (epoch, segundos)")
    n.set_defaults(f=analizar)
    a = ap.parse_args()
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
