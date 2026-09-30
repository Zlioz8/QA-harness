#!/usr/bin/env bash
# Telemetría del sistema bajo prueba, atada a UNA corrida de carga.
#
#   perf-telemetria.sh start <target> <dir-de-la-corrida>
#   perf-telemetria.sh stop  <target> <dir-de-la-corrida>
#
# Qué se mira lo declara el perfil en target.env (nada de esto está escrito para un proyecto):
#   PERF_WATCH_CONTAINERS   contenedores, separados por espacio o coma
#   PERF_WATCH_PROCS        grupos de procesos del host:  nombre=regex;nombre=regex
#   PERF_LOG_CONTAINERS     contenedores cuyo log de la ventana de la corrida se guarda al parar
#   PERF_INTERVALO_S        segundos entre muestras (2)
#   PERF_WATCH_SSH          usuario@host: el muestreo corre ALLÍ (el sistema bajo prueba es remoto)
#
# Sin PERF_WATCH_* no hay telemetría y se dice: una escalera sin telemetría encuentra el punto de
# quiebre pero no puede atribuirlo, y tools/perf-capacidad.py lo escribirá así.
set -uo pipefail

ACCION="${1:?uso: perf-telemetria.sh start|stop <target> <dir>}"
TARGET="${2:?falta el target}"
DIR="${3:?falta el directorio de la corrida}"
ENVFILE="targets/$TARGET/target.env"
. "$(dirname "$0")/lib-env.sh"

TEL="$DIR/telemetria"
CONT="$(envget PERF_WATCH_CONTAINERS)"
PROCS="$(envget PERF_WATCH_PROCS)"
LOGS="$(envget PERF_LOG_CONTAINERS)"
INT="$(envget PERF_INTERVALO_S)"; INT="${INT:-2}"
REMOTO="$(envget PERF_WATCH_SSH)"
MUESTREO="$(dirname "$0")/perf-muestreo.py"

case "$ACCION" in
  start)
    mkdir -p "$TEL"
    date -Is > "$TEL/.inicio"
    if [ -z "$CONT$PROCS" ]; then
      echo "perf-telemetria: PERF_WATCH_CONTAINERS y PERF_WATCH_PROCS vacíos — NO se mide el sistema." >&2
      echo "sin telemetría: el perfil no declara PERF_WATCH_*" > "$TEL/NO-MEDIDO.txt"
      exit 0
    fi
    if [ -n "$REMOTO" ]; then
      # El muestreo viaja por la entrada estándar y se ejecuta allí; no queda nada instalado.
      RDIR="/tmp/seclab-telemetria-$$"
      echo "$RDIR" > "$TEL/.remoto"
      # shellcheck disable=SC2029
      ssh -o BatchMode=yes "$REMOTO" "mkdir -p $RDIR && cat > $RDIR/muestreo.py" < "$MUESTREO" \
        || { echo "perf-telemetria: no se pudo llegar a $REMOTO — NO se mide el sistema." >&2
             echo "sin telemetría: ssh a $REMOTO falló" > "$TEL/NO-MEDIDO.txt"; exit 0; }
      # shellcheck disable=SC2029
      ssh -o BatchMode=yes "$REMOTO" "nohup python3 $RDIR/muestreo.py --salida $RDIR/out --intervalo $INT \
        --contenedores '$CONT' --procesos '$PROCS' >/dev/null 2>&1 & echo \$! > $RDIR/pid"
    else
      nohup python3 "$MUESTREO" --salida "$TEL" --intervalo "$INT" \
        --contenedores "$CONT" --procesos "$PROCS" >"$TEL/.muestreo.log" 2>&1 &
      echo $! > "$TEL/.pid"
    fi
    ;;
  stop)
    [ -d "$TEL" ] || exit 0
    if [ -f "$TEL/.remoto" ] && [ -n "$REMOTO" ]; then
      RDIR="$(cat "$TEL/.remoto")"
      # shellcheck disable=SC2029
      ssh -o BatchMode=yes "$REMOTO" "kill \$(cat $RDIR/pid) 2>/dev/null; sleep 1; tar -C $RDIR/out -cf - ." \
        | tar -C "$TEL" -xf - 2>/dev/null
      # shellcheck disable=SC2029
      ssh -o BatchMode=yes "$REMOTO" "rm -rf $RDIR"
      rm -f "$TEL/.remoto"
    elif [ -f "$TEL/.pid" ]; then
      kill "$(cat "$TEL/.pid")" 2>/dev/null
      # Esperar a que cierre sus archivos: leer un CSV a medio escribir da una última fila rota.
      for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$(cat "$TEL/.pid")" 2>/dev/null || break; sleep 0.3; done
      rm -f "$TEL/.pid"
    fi
    date -Is > "$TEL/.fin"
    if [ -n "$LOGS" ] && [ -f "$TEL/.inicio" ] && [ -z "$REMOTO" ]; then
      mkdir -p "$DIR/logs"
      for c in $(echo "$LOGS" | tr ',' ' '); do
        docker logs --since "$(cat "$TEL/.inicio")" "$c" >"$DIR/logs/$c.log" 2>&1 \
          || echo "perf-telemetria: sin log de '$c' (¿existe el contenedor?)" >&2
      done
    fi
    ;;
  *) echo "uso: perf-telemetria.sh start|stop <target> <dir>" >&2; exit 2 ;;
esac
