// Mecanismos propios de analitica_notificaciones — lo que la matriz genérica NO puede saber.
//
// lib/specs/authz-matrix.spec.ts recorre la política (qué rol alcanza qué) y necesita DOS cuentas
// que autentiquen. lib/specs/security-headers.spec.ts cubre las cabeceras. Este archivo cubre los
// MECANISMOS que este sistema declara tener y que se leen en su código, casi todos comprobables
// con UNA sola cuenta (rol A) o sin ninguna — importante aquí, porque el rol B (comunidades1) no
// obtiene token del web service de Moodle y la matriz de dos privilegios queda NO DISPONIBLE
// hasta que llegue una cuenta de bajo privilegio que sí acceda a reportes.
//
// Cada prueba afirma lo que el CÓDIGO dice. Cuando una falla, la pregunta es «¿el mecanismo
// protege lo que su autor creía?», no «¿está mal la prueba?».
import { test, expect } from '@playwright/test';
import { request } from '@playwright/test';
import { loginAs, hasRole } from './_auth';

const BASE = process.env.BASE_URL || 'http://localhost:8089';
const u = (p: string) => `${BASE}${p}`;

// Endpoints que exigen sesión (Depends CurrentUser), leídos de los routers.
const PROTEGIDOS = [
  '/api/reportes',
  '/api/solicitudes',
  '/api/programados',
  '/api/reportes/fichas_programas/filtros',
];

test.describe('Autenticación: la superficie protegida niega al anónimo con 401, no con 302 ni 200', () => {
  test('sin token, cada endpoint protegido responde 401', async () => {
    const anon = await request.newContext({ ignoreHTTPSErrors: true });
    const vistos: string[] = [];
    for (const path of PROTEGIDOS) {
      const res = await anon.get(u(path), { maxRedirects: 0 });
      vistos.push(`${path} -> ${res.status()}`);
      // 401 es lo correcto (api/auth.py:get_current_user). Un 302 al login sería un framework
      // redirigiendo (no es el caso en FastAPI); un 200 sería el catch-all tragándose la ruta,
      // que es justo el defecto de la prueba siguiente.
      expect(res.status(), `${path} debería negar al anónimo con 401`).toBe(401);
    }
    console.log('anónimo ->', vistos.join(' · '));
    await anon.dispose();
  });

  test('/api/health SÍ es público (200 sin sesión)', async () => {
    const anon = await request.newContext({ ignoreHTTPSErrors: true });
    const res = await anon.get(u('/api/health'));
    expect(res.status()).toBe(200);
    await anon.dispose();
  });
});

test.describe('Catch-all: el SPA responde 200 a cualquier ruta y rompe la detección de 404', () => {
  // api/main.py:130  @app.get('/{path:path}')  devuelve index.html para CUALQUIER path.
  // Consecuencia de seguridad: no hay 404. Un escáner —y un humano— no puede distinguir "no
  // existe" de "existe pero no lo ves". Se AFIRMA el comportamiento actual para que se note si
  // algún día se corrige (por ejemplo, devolviendo 404 para prefijos /api/ desconocidos).
  test('una ruta inventada devuelve 200 con el HTML del SPA', async () => {
    const anon = await request.newContext({ ignoreHTTPSErrors: true });
    const res = await anon.get(u('/ruta-que-no-existe-' + Date.now()));
    expect(res.status(), 'el catch-all devuelve 200 para todo — hallazgo, no error de la prueba').toBe(200);
    const body = await res.text();
    expect(body).toContain('<html');
    await anon.dispose();
  });

  test('un /api/ inexistente NO responde 404 (queda tapado por el catch-all)', async () => {
    const anon = await request.newContext({ ignoreHTTPSErrors: true });
    const res = await anon.get(u('/api/no-existe-' + Date.now()));
    // Documenta el defecto: lo deseable sería 404; hoy es 200 (SPA) o 401. Nunca 404.
    expect(res.status(), 'un /api/ desconocido no debería resolver como 404 hoy').not.toBe(404);
    console.log('/api/ inexistente ->', res.status());
    await anon.dispose();
  });
});

test.describe('C5 — el router admin no está montado: /api/admin/* cae en el catch-all', () => {
  // api/routers/admin.py define 4 rutas /api/admin/users con guarda CurrentAdmin, y
  // api/routers/__init__.py las exporta, pero api/main.py NUNCA hace include_router(admin).
  // Efecto: GET /api/admin/users no da 401 (no hay guarda que se ejecute) ni datos de admin;
  // da el SPA con 200, como cualquier ruta inventada. Superficie administrativa muerta.
  test('GET /api/admin/users devuelve el SPA (200), no 401 ni JSON de admin', async () => {
    const anon = await request.newContext({ ignoreHTTPSErrors: true });
    const res = await anon.get(u('/api/admin/users'), { maxRedirects: 0 });
    const body = await res.text();
    const esSpa = res.status() === 200 && body.includes('<html');
    console.log(`/api/admin/users -> ${res.status()} ${esSpa ? '(SPA, router NO montado)' : ''}`);
    // Si algún día se monta el router, esto pasará a 401 para el anónimo y la prueba fallará:
    // eso será la señal de que C5 se corrigió.
    expect(esSpa, 'admin router sin montar: la ruta cae en el catch-all').toBe(true);
    await anon.dispose();
  });
});

test.describe('SSO — el wstoken de Moodle viaja en la URL', () => {
  // api/routers/auth.py:80  GET /api/auth/moodle-autologin?token=<wstoken>. Un token de sesión
  // en la query string queda en los logs de nginx, en el historial del navegador y en el
  // Referer. Aquí solo se AFIRMA que el endpoint acepta el token por query (no por header ni
  // cuerpo), que es la forma del hallazgo; no se prueba con un token real.
  test('moodle-autologin toma el token por query string', async () => {
    const anon = await request.newContext({ ignoreHTTPSErrors: true });
    // Sin token válido responde 401/503 (get_moodle_user_info_by_token lanza), no 422 por
    // parámetro faltante distinto: la firma del endpoint es ?token=, que es el punto.
    const res = await anon.get(u('/api/auth/moodle-autologin?token=token-invalido-de-prueba'), { maxRedirects: 0 });
    console.log('moodle-autologin?token=... ->', res.status());
    expect([401, 403, 503], 'el endpoint procesa el token de la query (lo rechaza por inválido, no por ausente)').toContain(res.status());
    await anon.dispose();
  });
});

test.describe('Propiedad de las solicitudes (rol A consigo mismo)', () => {
  // La prueba FUERTE —el rol B intenta leer la solicitud de A y recibe 403 (solicitudes.py:64,
  // s.usuario_email != current_user)— necesita que B autentique, y hoy no puede. Se deja
  // registrada como NO DISPONIBLE. Lo que SÍ se puede con solo el rol A: que pedir una solicitud
  // con un id que no existe/ajeno dé 404/403, nunca los datos.
  test('rol A: una solicitud inexistente da 404, no una fuga', async () => {
    test.skip(!hasRole('A'), 'necesita ROLE_A');
    const ctx = await loginAs('A');
    const res = await ctx.get(u('/api/solicitudes/999999999'), { maxRedirects: 0 });
    expect([404, 403], 'un id inexistente no debe devolver datos').toContain(res.status());
  });
});
