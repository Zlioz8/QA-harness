#!/usr/bin/env bash
# Precondición de toda dimensión AUTENTICADA: las credenciales que entregó el operador QA tienen
# que funcionar contra este despliegue. Análogo exacto de tools/require-live.sh, que hace lo mismo
# con la aplicación.
#
# QUÉ SUSTITUYE. El laboratorio traía scripts que CREABAN las dos cuentas antes de auditar
# (seed-users.sh + un fixture SQL, 407 líneas). Se eliminaron. Si el laboratorio fabrica las
# cuentas, la matriz de autorización mide un accesorio que él mismo construyó —con los roles y las
# matrículas que él eligió— y no el control de acceso del sistema real. Un permiso mal puesto en
# producción es invisible para una cuenta creada a medida cinco minutos antes.
#
# Regla nueva: si el sistema tiene login, las credenciales las ENTREGA una persona, son cuentas
# reales de ese despliegue, y esto falla en voz alta cuando no lo son.
#
# POR QUÉ ES UN PRECHEQUEO Y NO SE DEJA QUE FALLE LA MATRIZ. Medido contra el servidor 166: dos
# credenciales que no existían allí produjeron TREINTA specs en rojo, todas con el mismo
# `moodle login failed`. Treinta líneas rojas se leen como treinta fallos de autorización; era UNA
# precondición incumplida. La diferencia importa: lo primero manda a revisar permisos, lo segundo
# a pedir credenciales.
set -uo pipefail

TARGET="${1:?uso: require-auth.sh <target>}"
ENVFILE="targets/$TARGET/target.env"
[ -f "$ENVFILE" ] || { echo "no existe $ENVFILE"; exit 2; }

. "$(dirname "$0")/lib-env.sh"

AUTH_ADAPTER=$(envget AUTH_ADAPTER)
ROLE_A_USER=$(envget ROLE_A_USER); ROLE_A_PASS=$(envget ROLE_A_PASS)
ROLE_B_USER=$(envget ROLE_B_USER); ROLE_B_PASS=$(envget ROLE_B_PASS)

if [ -z "${AUTH_ADAPTER:-}" ] || [ "$AUTH_ADAPTER" = "none" ]; then
  echo "auth check: AUTH_ADAPTER=none — solo se cubre la superficie SIN autenticar."
  echo "            No es un fallo: es media foto, y el informe debe decirlo así."
  exit 0
fi

# Lo que falta se dice por su nombre, y por separado: "no lo declaraste" y "lo declaraste y no
# sirve" tienen arreglos distintos.
missing=""
[ -z "${ROLE_A_USER:-}" ] && missing="$missing ROLE_A_USER"
[ -z "${ROLE_A_PASS:-}" ] && missing="$missing ROLE_A_PASS"
[ -z "${ROLE_B_USER:-}" ] && missing="$missing ROLE_B_USER"
[ -z "${ROLE_B_PASS:-}" ] && missing="$missing ROLE_B_PASS"

if [ -n "${missing// }" ]; then
  cat <<EOF

  ABORTADO: faltan credenciales.$missing

  Este perfil declara AUTH_ADAPTER=$AUTH_ADAPTER, así que el sistema tiene login, y la
  autorización es la ÚNICA dimensión que ningún escáner puede comprobar por ti: hace falta una
  cuenta de privilegio BAJO que intente hacer lo que solo la de privilegio ALTO debería poder.

  El laboratorio YA NO CREA ESAS CUENTAS. Antes las sembraba, y una matriz de autorización sobre
  cuentas fabricadas por el propio laboratorio no mide el control de acceso del sistema: mide el
  accesorio, con los roles y las matrículas que el laboratorio eligió.

  Qué hacer: pídele al equipo dueño del despliegue dos cuentas REALES de privilegio distinto,
  y ponlas en  targets/$TARGET/target.env.local  (no se versiona):

    ROLE_A_USER=<cuenta de privilegio alto>
    ROLE_A_PASS=<su contraseña>
    ROLE_B_USER=<cuenta de privilegio bajo>
    ROLE_B_PASS=<su contraseña>

  Si no se pueden conseguir, la dimensión de autorización es NO DISPONIBLE — que NO es lo mismo
  que "sin hallazgos", y así tiene que constar en el informe.

EOF
  exit 1
fi

if [ "$ROLE_A_USER" = "$ROLE_B_USER" ]; then
  echo
  echo "  ABORTADO: ROLE_A_USER y ROLE_B_USER son la MISMA cuenta ($ROLE_A_USER)."
  echo
  echo "  La matriz compara lo que puede una y no debería poder la otra. Con una sola cuenta"
  echo "  todas las comprobaciones pasan por construcción, y el informe sale verde sin haber"
  echo "  probado nada."
  echo
  exit 1
fi

echo "auth check: adaptador '$AUTH_ADAPTER' · roles '$ROLE_A_USER' / '$ROLE_B_USER'"
echo "            comprobando que las credenciales funcionan contra el despliegue…"

# Se comprueba con el MISMO adaptador que usará la matriz (lib/auth/), no con un curl aparte.
# Una segunda implementación del login acabaría discrepando de la primera, y el desacuerdo sería
# invisible: la comprobación pasaría y la matriz fallaría, o al revés.
DC="docker compose --env-file $ENVFILE"
[ -f "$ENVFILE.local" ] && DC="$DC --env-file $ENVFILE.local"
DC="$DC -f docker-compose.yml"

out=$($DC --profile e2e run --rm playwright sh -c \
  "mkdir -p /run && cp -r /e2e/. /run/ 2>/dev/null; mkdir -p /run/lib && cp -r /seclab-lib/. /run/lib/ && cd /run && \
   npm init -y >/dev/null 2>&1 && npm i -D @playwright/test@1.49.0 >/dev/null 2>&1 && \
   npx playwright test lib/specs/auth-check.spec.ts --reporter=line" 2>&1)
code=$?

echo "$out" | grep -viE "^npm |^added |^\s*$" | tail -12

if [ "$code" -eq 0 ]; then
  echo "auth check: las dos cuentas inician sesión y su sesión sirve."
  exit 0
fi

cat <<EOF

  ABORTADO: las credenciales entregadas NO funcionan contra este despliegue.

  Arriba está el motivo exacto por rol. Las causas habituales, en orden de frecuencia:
    · la cuenta no existe EN ESTE despliegue (existe en otro entorno)
    · contraseña caducada, o el primer acceso obliga a cambiarla
    · cuenta suspendida, o sin matrícula en el curso que la matriz recorre
    · AUTH_ADAPTER equivocado para cómo inicia sesión de verdad esta aplicación

  No se ejecuta la matriz de autorización: treinta specs en rojo por una credencial mala se leen
  como treinta fallos de autorización, y son UNA precondición incumplida.

EOF
exit 1
