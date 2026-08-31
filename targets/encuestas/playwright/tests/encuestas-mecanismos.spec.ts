// Mecanismos propios de encuestas — lo que la matriz genérica NO puede saber.
//
// lib/specs/authz-matrix.spec.ts recorre la política por rol (authz-matrix.json);
// lib/specs/security-headers.spec.ts cubre cabeceras. Este archivo afirma los MECANISMOS que
// ESTE sistema declara tener, leídos de su código y ya observados a mano por HTTP en esta
// sesión: la puerta pública de la API niega al anónimo con 401 (no 200 ni 302), el cerco del
// aprendiz, el limitador de login, el servido de ficheros a prueba de path-traversal, y —el
// hallazgo— el origen Apache publicado EN CLARO en el puerto 8000.
//
// Casi todo se comprueba SIN cuenta o con una sola: sigue siendo válido aunque el SSO de tres
// saltos no se pueda completar en este entorno (rebote de login a caplms). Cada prueba AFIRMA lo
// que el código dice; cuando una falla, la pregunta es «¿el mecanismo protege lo que su autor
// creía?», no «¿está mal la prueba?».
import { test, expect, request } from '@playwright/test';

const BASE = process.env.BASE_URL || 'https://zajunavideo5.com';
const PLAIN = process.env.API_PLAINTEXT_ORIGIN || 'http://zajunavideo5.com:8000';
const u = (p: string) => `${BASE}${p}`;

// Rutas de /api que exigen sesión (routes/api.php, dentro del grupo auth:sanctum). Sin token
// Sanctum, Sanctum responde 401 cuando la petición pide JSON.
const PROTEGIDAS = [
  '/api/surveys',
  '/api/users',
  '/api/roleandusers',
  '/api/mis-encuestas',
  '/api/current-user',
];

test.describe('API: la superficie protegida niega al anónimo con 401, no con 200 ni 302', () => {
  test('sin sesión, cada ruta autenticada responde 401', async () => {
    const anon = await request.newContext({ ignoreHTTPSErrors: true });
    const vistos: string[] = [];
    for (const path of PROTEGIDAS) {
      const res = await anon.get(u(path), { maxRedirects: 0, headers: { Accept: 'application/json' } });
      vistos.push(`${path} -> ${res.status()}`);
      // 401 es lo correcto. Un 302 sería Laravel redirigiendo al login por falta de `Accept:
      // json`; un 200 sería el catch-all del CMS contestando sin pasar por el middleware.
      expect(res.status(), `${path} debería negar al anónimo con 401`).toBe(401);
    }
    console.log('anónimo ->', vistos.join(' · '));
    await anon.dispose();
  });

  test('/api/contact-info SÍ es público (200, JSON), no el HTML del CMS', async () => {
    const anon = await request.newContext({ ignoreHTTPSErrors: true });
    const res = await anon.get(u('/api/contact-info'));
    expect(res.status()).toBe(200);
    expect(res.headers()['content-type'] || '').toContain('application/json');
    await anon.dispose();
  });
});

test.describe('El servido de ficheros público resiste el path-traversal', () => {
  // /api/storage/images/{filename} y /api/editor-images/{filename} reciben el nombre de la URL.
  // Observado a mano: los intentos de subir de directorio dan 400/404, nunca 200 con un fichero
  // del sistema. Esta prueba lo fija para que no se regresione.
  const ATAQUES = [
    '/api/storage/images/..%2f..%2f..%2f..%2fetc%2fpasswd',
    '/api/editor-images/..%2f..%2f..%2fcomposer.json',
  ];
  for (const path of ATAQUES) {
    test(`traversal rechazado: ${path.slice(0, 40)}...`, async () => {
      const anon = await request.newContext({ ignoreHTTPSErrors: true });
      const res = await anon.get(u(path), { maxRedirects: 0 });
      expect([400, 403, 404], `${path} nunca debe devolver 200`).toContain(res.status());
      await anon.dispose();
    });
  }

  test('la descarga firmada rechaza (403) sin firma válida', async () => {
    const anon = await request.newContext({ ignoreHTTPSErrors: true });
    const res = await anon.get(u('/api/surveys/1/export-responses/1/signed-download'), { maxRedirects: 0 });
    expect(res.status()).toBe(403);
    await anon.dispose();
  });
});

test.describe('El limitador de login está activo (anti fuerza-bruta)', () => {
  // El README-DESPLIEGUE §0 y routes/api.php:108 declaran `throttle:login` = 5/min. Observado:
  // la respuesta trae `X-RateLimit-Limit: 5`. Se comprueba SIN gastar el cupo — solo se lee la
  // cabecera de UNA petición con credenciales inventadas (no de una cuenta real).
  test('la cabecera declara un límite de 5 intentos', async () => {
    const anon = await request.newContext({ ignoreHTTPSErrors: true });
    const res = await anon.post(u('/api/login'), {
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      data: { username: 'no-existe-de-prueba', password: 'credencial-falsa' },
      maxRedirects: 0,
    });
    const limite = res.headers()['x-ratelimit-limit'];
    expect(limite, 'login debe anunciar su límite de intentos').toBe('5');
    // 422 (validación) o 401 (credenciales malas) son sanos; un 200 con estas credenciales sería
    // el hallazgo más grave posible.
    expect([401, 422]).toContain(res.status());
    await anon.dispose();
  });
});

test.describe('HALLAZGO: el origen Apache está publicado en claro (sin TLS)', () => {
  // `https://.../api/` redirige a http://host:8000/api, y ese puerto sirve la API entera sin
  // cifrar. Esta prueba DOCUMENTA el hallazgo como fallo: cuando el equipo lo corrija (cerrar el
  // 8000 al exterior o forzar TLS), la prueba pasará a verde y marcará la corrección.
  test('el puerto 8000 NO debería servir la API en HTTP plano', async () => {
    const anon = await request.newContext({ ignoreHTTPSErrors: true });
    let alcanzable = false;
    try {
      const res = await anon.get(`${PLAIN}/api/contact-info`, { maxRedirects: 0, timeout: 12000 });
      alcanzable = res.status() === 200;
      console.log(`origen en claro ${PLAIN}/api/contact-info -> ${res.status()} (${res.headers()['server']})`);
    } catch {
      alcanzable = false; // conexión rechazada = corregido
    }
    expect(alcanzable, `${PLAIN} sirve la API sin TLS: cualquiera en la red captura las credenciales`).toBe(false);
    await anon.dispose();
  });
});
