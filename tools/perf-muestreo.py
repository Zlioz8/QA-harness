#!/usr/bin/env python3
"""Muestrea el SISTEMA BAJO PRUEBA mientras corre la carga. Solo biblioteca estándar.

Una prueba de carga sin esto responde «a partir de N usuarios va lento» y nada más. Para decir
QUÉ se saturó —y por tanto qué comprar o qué arreglar— hay que mirar el sistema a la vez que se
le carga. Este script es esa mirada, y nada más: no decide nada, solo escribe CSV con hora.

  host.csv          CPU total del host, iowait, carga, memoria, red
  contenedores.csv  CPU (100 = un núcleo), memoria y procesos de cada contenedor, leídos del cgroup
  procesos.csv      grupos de procesos del host por expresión regular (php-fpm, nginx…)
  pg.csv            conexiones de PostgreSQL por base y estado, leídas del título del proceso

Todo sale de /proc y /sys: no pide credenciales de base de datos ni instala nada en el sistema
medido. Por eso mismo se puede enviar por ssh a otro host y ejecutar allí tal cual
(tools/perf-telemetria.sh, PERF_WATCH_SSH).

POR QUÉ EL TÍTULO DEL PROCESO Y NO pg_stat_activity: pedir un rol de lectura en cada PostgreSQL
que participa (el de la aplicación, el de la plataforma) es una credencial más que custodiar, y
el título ya dice lo que hace falta: `postgres: usuario base cliente estado`.

Uso:
  perf-muestreo.py --salida DIR [--intervalo 2] [--contenedores a,b] [--procesos 'n=regex;n2=regex']
"""
import argparse
import os
import re
import signal
import subprocess
import sys
import time

TICK = os.sysconf("SC_CLK_TCK")
PAGINA = os.sysconf("SC_PAGE_SIZE")
NUCLEOS = os.cpu_count() or 1
seguir = True


def parar(*_):
    global seguir
    seguir = False


def leer(ruta):
    try:
        with open(ruta, "r", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


# ------------------------------------------------------------------ host
def cpu_host():
    campos = leer("/proc/stat").split("\n", 1)[0].split()[1:]
    v = [int(x) for x in campos[:8]] + [0] * 8
    user, nice, system, idle, iowait, irq, softirq, steal = v[:8]
    total = user + nice + system + idle + iowait + irq + softirq + steal
    return {"total": total, "idle": idle, "iowait": iowait, "user": user + nice, "sys": system + irq + softirq}


def mem_host():
    d = {}
    for linea in leer("/proc/meminfo").splitlines():
        k, _, resto = linea.partition(":")
        d[k] = int(resto.split()[0]) if resto.split() else 0
    total = d.get("MemTotal", 0)
    disp = d.get("MemAvailable", 0)
    return (total - disp) // 1024, disp // 1024


def red_host():
    rx = tx = 0
    for linea in leer("/proc/net/dev").splitlines()[2:]:
        nombre, _, datos = linea.partition(":")
        nombre = nombre.strip()
        if nombre == "lo" or nombre.startswith(("veth", "br-", "docker")):
            continue
        c = datos.split()
        if len(c) >= 9:
            rx += int(c[0])
            tx += int(c[8])
    return rx, tx


# ------------------------------------------------------------------ procesos
def procesos():
    """pid -> (ticks de CPU, páginas residentes, título)."""
    out = {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        st = leer(f"/proc/{pid}/stat")
        if not st:
            continue
        # El nombre va entre paréntesis y puede llevar espacios: cortar por el ÚLTIMO ')'.
        fin = st.rfind(")")
        c = st[fin + 2:].split()
        if len(c) < 22:
            continue
        titulo = leer(f"/proc/{pid}/cmdline").replace("\0", " ").strip() or st[st.find("(") + 1:fin]
        out[int(pid)] = (int(c[11]) + int(c[12]), int(c[21]), titulo)
    return out


PG = re.compile(r"^postgres: (?:[\w./-]+: )?(\S+) (\S+) (\S+) (.*)$")
PG_FONDO = ("checkpointer", "background writer", "walwriter", "autovacuum", "logical replication",
            "stats collector", "archiver", "startup", "walsender", "walreceiver", "io worker")


def pg_por_base(procs):
    """base -> [total, activas, idle_in_tx, esperando]."""
    out = {}
    for _, (_, _, titulo) in procs.items():
        if not titulo.startswith("postgres: "):
            continue
        if any(f in titulo for f in PG_FONDO):
            continue
        m = PG.match(titulo)
        if not m:
            continue
        base, estado = m.group(2), m.group(4).strip()
        f = out.setdefault(base, [0, 0, 0, 0])
        f[0] += 1
        if estado.startswith("idle in transaction"):
            f[2] += 1
        elif not estado.startswith("idle"):
            f[1] += 1
        if estado.endswith("waiting"):
            f[3] += 1
    return out


# ------------------------------------------------------------------ contenedores (cgroup v2)
def cgroup_de(nombre):
    try:
        cid = subprocess.run(["docker", "inspect", "-f", "{{.Id}}", nombre], capture_output=True, text=True,
                             timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not cid:
        return None
    for ruta in (f"/sys/fs/cgroup/system.slice/docker-{cid}.scope", f"/sys/fs/cgroup/docker/{cid}"):
        if os.path.isdir(ruta):
            return ruta
    return None


def cg_lee(ruta):
    uso = 0
    estrangulado = 0
    for linea in leer(f"{ruta}/cpu.stat").splitlines():
        if linea.startswith("usage_usec"):
            uso = int(linea.split()[1])
        elif linea.startswith("throttled_usec"):
            estrangulado = int(linea.split()[1])
    mem = leer(f"{ruta}/memory.current").strip()
    pids = leer(f"{ruta}/pids.current").strip()
    return uso, estrangulado, int(mem or 0), int(pids or 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--intervalo", type=float, default=2.0)
    ap.add_argument("--contenedores", default="")
    ap.add_argument("--procesos", default="")
    a = ap.parse_args()

    os.makedirs(a.salida, exist_ok=True)
    signal.signal(signal.SIGTERM, parar)
    signal.signal(signal.SIGINT, parar)

    grupos = []
    for par in [p for p in a.procesos.split(";") if p.strip()]:
        nombre, _, expr = par.partition("=")
        try:
            grupos.append((nombre.strip(), re.compile(expr.strip())))
        except re.error as e:
            print(f"perf-muestreo: expresión inválida para '{nombre}': {e}", file=sys.stderr)

    cgs = {}
    sin_cgroup = []
    for nombre in [c for c in re.split(r"[,\s]+", a.contenedores) if c]:
        ruta = cgroup_de(nombre)
        if ruta:
            cgs[nombre] = ruta
        else:
            sin_cgroup.append(nombre)
    if sin_cgroup:
        # Se dice y se sigue: un contenedor que no existe no es «0 % de CPU», es «no medido».
        with open(os.path.join(a.salida, "NO-MEDIDO.txt"), "a") as f:
            f.write("contenedores sin cgroup legible (no medidos): " + " ".join(sin_cgroup) + "\n")

    fh = open(os.path.join(a.salida, "host.csv"), "a", buffering=1)
    fp = open(os.path.join(a.salida, "procesos.csv"), "a", buffering=1)
    fc = open(os.path.join(a.salida, "contenedores.csv"), "a", buffering=1)
    fg = open(os.path.join(a.salida, "pg.csv"), "a", buffering=1)
    if fh.tell() == 0:
        fh.write("t,cpu_pct,user_pct,sys_pct,iowait_pct,carga1,mem_usada_mb,mem_disp_mb,rx_bps,tx_bps,nucleos\n")
    if fp.tell() == 0:
        fp.write("t,grupo,procesos,activos,cpu_pct,rss_mb\n")
    if fc.tell() == 0:
        fc.write("t,contenedor,cpu_pct,estrangulado_pct,mem_mb,pids\n")
    if fg.tell() == 0:
        fg.write("t,base,conexiones,activas,idle_en_tx,esperando\n")

    c0, p0, r0, t0 = cpu_host(), procesos(), red_host(), time.time()
    g0 = {n: cg_lee(r) for n, r in cgs.items()}

    while seguir:
        time.sleep(a.intervalo)
        t1 = time.time()
        dt = max(t1 - t0, 1e-6)
        ts = f"{t1:.1f}"

        c1 = cpu_host()
        dtot = max(c1["total"] - c0["total"], 1)
        ocupado = 100.0 * (1 - (c1["idle"] - c0["idle"] + c1["iowait"] - c0["iowait"]) / dtot)
        usada, disp = mem_host()
        r1 = red_host()
        carga1 = leer("/proc/loadavg").split()[0] if leer("/proc/loadavg") else "0"
        fh.write(f"{ts},{ocupado:.1f},{100.0 * (c1['user'] - c0['user']) / dtot:.1f},"
                 f"{100.0 * (c1['sys'] - c0['sys']) / dtot:.1f},{100.0 * (c1['iowait'] - c0['iowait']) / dtot:.1f},"
                 f"{carga1},{usada},{disp},{8 * (r1[0] - r0[0]) / dt:.0f},{8 * (r1[1] - r0[1]) / dt:.0f},{NUCLEOS}\n")

        p1 = procesos()
        for nombre, expr in grupos:
            n = activos = 0
            ticks = rss = 0
            for pid, (tk, pag, titulo) in p1.items():
                if not expr.search(titulo):
                    continue
                n += 1
                rss += pag
                d = tk - p0[pid][0] if pid in p0 else tk
                if d > 0:
                    activos += 1
                    ticks += d
            fp.write(f"{ts},{nombre},{n},{activos},{100.0 * ticks / TICK / dt:.1f},{rss * PAGINA / 1048576:.0f}\n")

        for base, (tot, act, itx, esp) in sorted(pg_por_base(p1).items()):
            fg.write(f"{ts},{base},{tot},{act},{itx},{esp}\n")

        for nombre, ruta in cgs.items():
            g1 = cg_lee(ruta)
            a0 = g0.get(nombre, g1)
            fc.write(f"{ts},{nombre},{100.0 * (g1[0] - a0[0]) / 1e6 / dt:.1f},"
                     f"{100.0 * (g1[1] - a0[1]) / 1e6 / dt:.1f},{g1[2] / 1048576:.0f},{g1[3]}\n")
            g0[nombre] = g1

        c0, p0, r0, t0 = c1, p1, r1, t1


if __name__ == "__main__":
    main()
