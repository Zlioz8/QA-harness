// ¿Las credenciales que entregó el operador QA funcionan de verdad contra ESTE despliegue?
//
// POR QUÉ ESTO SUSTITUYÓ A LA SIEMBRA. El laboratorio traía scripts que CREABAN las dos cuentas
// (seed-users.sh, 407 líneas contando el fixture SQL). El propio script lo advertía en su
// cabecera: un fallo de autorización sobre cuentas sembradas significa "la semilla estaba mal",
// no "la aplicación es segura" — y eso se lee como un aprobado.
//
// El problema es más profundo que la fiabilidad de la semilla: si el laboratorio fabrica las
// cuentas, la matriz de autorización mide un accesorio que el propio laboratorio construyó, con
// los roles y las matrículas que él mismo eligió. No mide el control de acceso del sistema real.
// Un permiso mal puesto en producción es invisible para una cuenta recién creada a medida.
//
// Así que ya no se siembra nada. Si el sistema tiene login, las credenciales las ENTREGA el
// operador QA, son cuentas reales de ese despliegue, y esta comprobación falla ruidosamente
// cuando no lo son.
//
// Se ejecuta ANTES que la matriz: sin esto, dos credenciales inválidas producían treinta specs en
// rojo con el mismo `moodle login failed`, que se leen como treinta fallos de autorización
// cuando son UNA precondición incumplida. Medido contra el servidor 166: 30 fallos, una causa.
import { test, expect } from '@playwright/test';
import { adapter, CREDS, type Role } from '../auth/index';

const ADAPTER = (process.env.AUTH_ADAPTER || 'none').trim();

test.describe('credenciales entregadas por el operador QA', () => {
  test.skip(ADAPTER === 'none' || ADAPTER === '',
    'AUTH_ADAPTER=none: este perfil solo cubre la superficie sin autenticar. No es un fallo, ' +
    'es media foto — y el informe debe decirlo así.');

  for (const role of ['A', 'B'] as Role[]) {
    test(`rol ${role} (${CREDS[role].user || '(sin declarar)'}) inicia sesión`, async () => {
      const { user, pass } = CREDS[role];

      // Distinguir "no lo declaraste" de "lo declaraste y no sirve". Son dos arreglos distintos
      // y el mensaje tiene que llevar al correcto.
      expect(user, `ROLE_${role}_USER está vacío. La autorización es la única dimensión que ` +
        `ningún escáner puede comprobar por ti, y necesita DOS cuentas reales de privilegio ` +
        `distinto en este despliegue. El laboratorio ya no las crea.`).toBeTruthy();
      expect(pass, `ROLE_${role}_PASS está vacío. Si la cuenta es real, la contraseña va en ` +
        `targets/<perfil>/target.env.local, que no se versiona.`).toBeTruthy();

      const ctx = await adapter().loginAs(role);

      // El adaptador lanza si el login falla; llegar aquí ya es la prueba. Se comprueba además
      // que la sesión SIRVE para algo: un adaptador puede devolver un contexto con una cookie
      // que el servidor no reconoce, y entonces todo lo posterior da 302 al login sin decir nada.
      const res = await ctx.get('/');
      expect(res.status(), `El rol ${role} inició sesión pero su sesión no vale: GET / devolvió ` +
        `${res.status()}. Suele ser una cuenta suspendida, sin matrícula, o forzada a cambiar ` +
        `la contraseña en el primer acceso.`).toBeLessThan(400);
    });
  }
});
