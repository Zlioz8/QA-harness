// MATRIZ DE AUTORIZACIÓN POR LOS SEIS ROLES DE COSTOS WEB.
//
// El motor genérico de lib/specs solo conoce dos roles (A y B), que es lo que basta para
// medir "el privilegio bajo no alcanza lo del alto". Costos Web tiene SEIS roles con alcances
// territoriales distintos, y los hallazgos R7 §3.16 y §3.18 nacieron justo entre roles
// intermedios: la interfaz ofrecía una acción que el API denegaba para ese rol concreto.
//
// La política que se declara aquí es una DECISIÓN, no una observación: sale de leer
// routes/api.php y los abort_unless de los controladores. Cuando negocio decida otra cosa,
// se cambia aquí primero y el código después.
import { test, expect, APIRequestContext } from '@playwright/test';
import { sesionDe, cabecerasEscritura, pausa, BASE as BASE_URL } from './_sesion';

// Sin BASE_URL no hay objetivo. Fallar aquí es más honesto que traer un valor por defecto:
// una dirección incrustada sobrevive al despliegue que la motivó y acaba midiendo el
// servidor equivocado en verde. Se declara en targets/costos_web/target.env.local.
const BASE = process.env.BASE_URL || '';
if (!BASE) throw new Error('BASE_URL no declarado — ver targets/costos_web/target.env.local.example');
const ORIGIN = process.env.ALLOWED_ORIGIN || BASE;

type RolId = 1 | 2 | 3 | 4 | 5 | 6;

const CUENTAS: Record<RolId, { nombre: string; user: string; pass: string }> = {
  1: { nombre: 'ADMINISTRADOR', user: process.env.ROL1_ADMINISTRADOR_USER!, pass: process.env.ROL1_ADMINISTRADOR_PASS! },
  2: { nombre: 'DELEGADO',      user: process.env.ROL2_DELEGADO_USER!,      pass: process.env.ROL2_DELEGADO_PASS! },
  3: { nombre: 'DIRECTOR',      user: process.env.ROL3_DIRECTOR_USER!,      pass: process.env.ROL3_DIRECTOR_PASS! },
  4: { nombre: 'SUBDIRECTOR',   user: process.env.ROL4_SUBDIRECTOR_USER!,   pass: process.env.ROL4_SUBDIRECTOR_PASS! },
  5: { nombre: 'COORDINADOR',   user: process.env.ROL5_COORDINADOR_USER!,   pass: process.env.ROL5_COORDINADOR_PASS! },
  6: { nombre: 'PARTICIPANTE',  user: process.env.ROL6_PARTICIPANTE_USER!,  pass: process.env.ROL6_PARTICIPANTE_PASS! },
};

const TODOS: RolId[] = [1, 2, 3, 4, 5, 6];

// permitidos = roles que DEBEN poder; el resto debe recibir 401/403/404.
type Regla = { titulo: string; path: string; method?: string; permitidos: RolId[]; body?: unknown; nota?: string };

const MATRIZ: Regla[] = [
  { titulo: 'identidad propia',            path: '/api/me',                              permitidos: TODOS },
  { titulo: 'catálogos',                   path: '/api/catalogos',                       permitidos: TODOS },
  { titulo: 'periodo activo',              path: '/api/tiempo/activa',                   permitidos: TODOS },

  { titulo: 'listado de usuarios',         path: '/api/usuarios?per_page=1',             permitidos: [1, 2, 3, 4, 5],
    nota: 'acotado por baseQuery segun el rol; el participante no entra' },
  { titulo: 'integrantes del grupo',       path: '/api/usuarios/integrantes-grupo',      permitidos: [1, 2, 3, 4, 5] },
  { titulo: 'seguimiento de formularios',  path: '/api/seguimiento-formularios?per_page=1', permitidos: [1, 2, 3, 4, 5] },
  { titulo: 'grupos',                      path: '/api/grupos',                          permitidos: [1, 2, 3, 4, 5] },

  { titulo: 'área administrativa',         path: '/api/inicioadmin',                     permitidos: [1, 2] },
  { titulo: 'exportar padrón de usuarios', path: '/api/usuarios/exportar',               permitidos: [1, 2],
    nota: 'exportacion masiva de datos personales' },
  { titulo: 'plantilla de importación',    path: '/api/usuarios/plantilla',              permitidos: [1, 2] },
  { titulo: 'reporte de representantes',   path: '/api/seguimiento-representantes/reporte', permitidos: [1, 2] },

  { titulo: 'confirmar integrante',        path: '/api/seguimiento-representantes/confirmar', method: 'POST',
    permitidos: [1, 2, 3, 4, 5], body: { usuario_id: 0, tiempo_id: 0 },
    nota: 'R7 3.18: el coordinador SI debe poder; el participante no. Con ids invalidos la respuesta es 422 -> autorizado' },
];

function sesion(rol: RolId): Promise<APIRequestContext> {
  const { user, pass } = CUENTAS[rol];
  return sesionDe(user, pass);
}

async function tokenDe(ctx: APIRequestContext): Promise<string> {
  const st = await ctx.storageState();
  return decodeURIComponent(st.cookies.find((c) => c.name === 'XSRF-TOKEN')?.value ?? '');
}

test.describe('matriz de autorización — seis roles', () => {
  test.skip(!process.env.ROL1_ADMINISTRADOR_USER, 'faltan las cuentas por rol en target.env');

  for (const regla of MATRIZ) {
    for (const rol of TODOS) {
      const debe = regla.permitidos.includes(rol);
      const metodo = (regla.method || 'GET').toUpperCase();
      const nombre = `${metodo} ${regla.path} — ${rol} ${CUENTAS[rol].nombre} ${debe ? 'PERMITIDO' : 'DENEGADO'}`
        + (regla.nota ? ` (${regla.nota})` : '');

      test(nombre, async () => {
        await pausa();               // respeta throttle:60,1 del propio proyecto
        const ctx = await sesion(rol);
        const res = await ctx.fetch(`${BASE}${regla.path}`, {
          method: metodo,
          maxRedirects: 0,
          ...(regla.body !== undefined
            ? { data: regla.body, headers: { 'Content-Type': 'application/json', 'X-XSRF-TOKEN': await tokenDe(ctx) } }
            : { headers: { 'X-XSRF-TOKEN': await tokenDe(ctx) } }),
        });
        const s = res.status();

        if (debe) {
          // 422 cuenta como autorizado: pasó el guard de rol y falló la validación de datos.
          expect(
            [200, 201, 204, 422].includes(s),
            `${CUENTAS[rol].nombre} debería alcanzar ${regla.path} y recibió ${s}`,
          ).toBeTruthy();
        } else {
          expect(
            [401, 403, 404].includes(s),
            `${CUENTAS[rol].nombre} NO debería alcanzar ${regla.path} y recibió ${s}`,
          ).toBeTruthy();
        }
      });
    }
  }
});
