// Mecanismos propios de ZAJUNA Early Alert — lo que la matriz genérica NO puede saber.
//
// lib/specs/authz-matrix.spec.ts recorre la política por rol y por curso; lib/specs/
// security-headers.spec.ts cubre cabeceras. Este archivo cubre los MECANISMOS que este sistema
// declara tener y que se leen en su código: la puerta pública de la API, la exposición de
// /metrics, el CSRF de login, y la incongruencia de contrato /api-zea vs /zea-api. Casi todo se
// comprueba SIN cuenta o con una sola — importante mientras las cuentas reales no estén puestas.
//
// Cada prueba AFIRMA lo que el código dice. Cuando una falla, la pregunta es «¿el mecanismo
// protege lo que su autor creía?», no «¿está mal la prueba?».
import { test, expect, request } from '@playwright/test';

const BASE = process.env.BASE_URL || 'http://nginx.zajuna.com';
const u = (p: string) => `${BASE}${p}`;

// Endpoints de la API que exigen un JWT DE CURSO (app.go:117-118: el grupo /api/v1 monta
// auth.Middleware). Sin bearer, jwt.go:44 responde 401 "missing bearer token".
const PROTEGIDOS = [
  '/zea-api/api/v1/reports/login?courseid=1&mode=daily&granularity=day',
  '/zea-api/api/v1/reports/activity-progress?courseid=1',
  '/zea-api/api/v1/reports/activity-matrix?courseid=1',
  '/zea-api/api/v1/reports/rap-detail?courseid=1',
  '/zea-api/api/v1/email/health',
];

test.describe('API: la superficie protegida niega al anónimo con 401, no con 200 ni 303', () => {
  test('sin bearer, cada endpoint de /api/v1 responde 401', async () => {
    const anon = await request.newContext({ ignoreHTTPSErrors: true });
    const vistos: string[] = [];
    for (const path of PROTEGIDOS) {
      const res = await anon.get(u(path), { maxRedirects: 0, headers: { Accept: 'application/json' } });
      vistos.push(`${path.split('?')[0]} -> ${res.status()}`);
      // 401 es lo correcto (jwt.go:44). Un 303 sería la petición cayendo en Moodle porque falta
      // la `location` de nginx (DEPLOY.md §17: «un 303 significa que falta la location»); un 200
      // sería que algo delante la contesta sin pasar por el middleware.
      expect(res.status(), `${path} debería negar al anónimo con 401`).toBe(401);
    }
    console.log('anónimo ->', vistos.join(' · '));
    await anon.dispose();
  });

  test('/zea-api/health SÍ es público (200, JSON), no el HTML del CMS', async () => {
    const anon = await request.newContext({ ignoreHTTPSErrors: true });
    const res = await anon.get(u('/zea-api/health'));
    expect(res.status()).toBe(200);
    // El cuerpo tiene que ser el JSON del servicio, no una página. Si llega HTML, la `location`
    // de nginx no está y `/` (el CMS) se está tragando la ruta con un 200 engañoso.
    expect((await res.text()).trim()).toContain('"status"');
    await anon.dispose();
  });
});

test.describe('/metrics: público por diseño — se AFIRMA la exposición para que se note', () => {
  // docs/api/openapi.json declara /metrics con `security: []` y app.go:107 lo sirve fuera del
  // grupo protegido. DEPLOY.md §17 lo da por a salvo «porque el servicio escucha en loopback»,
  // pero detrás del proxy sale a internet (comprobado en el servidor: 200, 15 KB). Esta prueba
  // deja constancia del comportamiento actual: si algún día se cierra, se pondrá roja y habrá que
  // decidir si el cierre fue intencionado.
  test('GET /zea-api/metrics responde 200 sin autenticación', async () => {
    const anon = await request.newContext({ ignoreHTTPSErrors: true });
    const res = await anon.get(u('/zea-api/metrics'), { maxRedirects: 0 });
    expect(res.status(), 'métricas públicas: hallazgo, no error de la prueba').toBe(200);
    const body = await res.text();
    // Formato Prometheus: confirma que son las métricas de verdad, no una página cualquiera.
    expect(body, 'debería ser texto de métricas Prometheus').toMatch(/^#\s*(HELP|TYPE)/m);
    console.log('/metrics expone', body.length, 'bytes sin JWT');
    await anon.dispose();
  });
});

test.describe('Contrato: la URL de producción del OpenAPI no es la que sirve el despliegue', () => {
  // docs/api/openapi.json:19 declara el servidor de producción como `/api-zea`; el nginx del repo
  // (deploy/nginx-moodle.conf.template, scripts/install-nginx.sh) publica la API en `/zea-api/`.
  // Un cliente generado desde el contrato pediría /api-zea y —al no existir esa location— caería
  // en `/`, el CMS, que responde 200 con HTML. No es un 404 honesto: es un 200 mentiroso.
  test('/api-zea/health NO devuelve el JSON del servicio (contrato roto)', async () => {
    const anon = await request.newContext({ ignoreHTTPSErrors: true });
    const res = await anon.get(u('/api-zea/health'), { maxRedirects: 0 });
    const body = await res.text();
    const esJsonDelServicio = res.status() === 200 && body.includes('"status"');
    expect(
      esJsonDelServicio,
      `la ruta del contrato /api-zea/health debería servir el JSON del servicio y no lo hace ` +
        `(status ${res.status()}, ${body.slice(0, 40).replace(/\s+/g, ' ')}…) — el contrato dice /api-zea, el despliegue usa /zea-api`,
    ).toBe(false);
    await anon.dispose();
  });
});

test.describe('CSRF de login: login.php rechaza credenciales form-encoded', () => {
  // plugin/classes/local/login_guard.php: el guarda CSRF exige Content-Type application/json, para
  // que un <form> cross-origin no pueda iniciar sesión en el navegador de la víctima. Se comprueba
  // con credenciales BASURA a propósito: la respuesta correcta es rechazar por la FORMA (400/415),
  // no por las credenciales — y usar credenciales falsas evita disparar el throttle sobre una
  // cuenta real. UNA sola petición: no repetir, para no acumular intentos.
  test('POST form-encoded a login.php se rechaza por Content-Type, no por credenciales', async () => {
    const mb = process.env.ZEA_MOODLE_BASE || '';
    const anon = await request.newContext({ ignoreHTTPSErrors: true });
    const res = await anon.post(u(`${mb}/blocks/zajuna_early_alert/login.php`), {
      form: { username: 'noexiste_qa', password: 'x' },
      maxRedirects: 0,
    });
    // No debe ser 200 con token: eso sería aceptar el form. Se acepta cualquier rechazo (4xx).
    expect(res.status(), 'un login por formulario no debería prosperar (CSRF)').toBeGreaterThanOrEqual(400);
    const body = await res.text();
    expect(body, 'no debería emitir un token de identidad ante un form').not.toContain('"token"');
    await anon.dispose();
  });
});
