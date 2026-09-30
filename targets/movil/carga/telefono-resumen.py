#!/usr/bin/env python3
"""Junta varias corridas del teléfono (carga/telefono.sh) en una tabla: qué sintió la persona
con el servidor libre y bajo cada carga.

  telefono-resumen.py <dir-de-corridas> [nombre-de-corrida ...]   (por omisión, todas, en orden)
"""
import csv, json, os, sys

def cargar(d):
    rec = {}
    for l in open(os.path.join(d, "eventos.jsonl")):
        e = json.loads(l)
        if e.get("tipo") == "recorrido" and e.get("ms_hasta_ultima_respuesta") is not None:
            rec.setdefault(e["recorrido"], []).append(e["ms_hasta_ultima_respuesta"])
    xs = [float(r["ms_telefono"]) for r in csv.DictReader(open(os.path.join(d, "peticiones.csv"))) if r["ms_telefono"]]
    srv = [(float(r["ms_telefono"]), float(r["ms_servidor"])) for r in csv.DictReader(open(os.path.join(d, "peticiones.csv"))) if r["ms_telefono"] and r["ms_servidor"]]
    xs.sort()
    q = lambda v, p: v[min(len(v) - 1, int(p * (len(v) - 1)))] if v else None
    red = sorted(a - b for a, b in srv)
    return rec, {"n": len(xs), "p50": q(xs, .5), "p95": q(xs, .95), "max": xs[-1] if xs else None, "lentas": sum(1 for x in xs if x > 1500), "red_p50": q(red, .5)}

base = sys.argv[1]
nombres = sys.argv[2:] or sorted(x for x in os.listdir(base) if os.path.isdir(os.path.join(base, x)))
datos = {n: cargar(os.path.join(base, n)) for n in nombres}
gestos = []
for n in nombres:
    for g in datos[n][0]:
        if g not in gestos: gestos.append(g)
L = ["# El teléfono bajo carga", "", "Cada celda: milisegundos desde la primera petición del gesto hasta su última respuesta, vistos en el teléfono (mediana de las repeticiones).", "",
     "| Gesto | " + " | ".join(nombres) + " |", "|---|" + "---:|" * len(nombres)]
for g in gestos:
    fila = []
    for n in nombres:
        v = sorted(datos[n][0].get(g, []))
        fila.append(f"{v[len(v) // 2]:.0f}" if v else "—")
    L.append(f"| {g} | " + " | ".join(fila) + " |")
L += ["", "Por petición (todas las rutas):", "", "| Corrida | n | p50 | p95 | máx | > 1,5 s | red ida y vuelta p50 |", "|---|---:|---:|---:|---:|---:|---:|"]
for n in nombres:
    r = datos[n][1]
    L.append(f"| {n} | {r['n']} | {r['p50']:.0f} ms | {r['p95']:.0f} ms | {r['max']:.0f} ms | {r['lentas']} | {r['red_p50']:.0f} ms |")
print("\n".join(L))
