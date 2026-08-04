// k6 load — GET /api/usuarios bajo concurrencia, sobre un despliegue REAL (peldaño 2).
//
// Dos hechos del host de validación obligan esta forma:
//   1. Rate limit 60 req/min/usuario: un solo usuario satura el LIMITADOR (429), no el endpoint.
//      Así que los VUs se reparten entre las cuentas que la política deja listar (roles 1-5; el
//      rol 6 participante recibe 403 por diseño) y cada VU se autolimita bajo el techo.
//   2. Solo existen las cuentas reales (no hay load1..N sintéticas). Vienen de target.env.local,
//      que el servicio k6 carga vía env_file — el script las lee de __ENV directamente.
//
// Mide LATENCIA del listado bajo carga sostenida permitida. El colapso por dataset completo
// (H19/H20) se prueba aparte con un per_page grande: el endpoint hoy capa la paginación.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const BASE = __ENV.BASE_URL || 'http://app:8000';
const ORIGIN = __ENV.ALLOWED_ORIGIN || 'http://localhost:5173';
const PER_PAGE = __ENV.PER_PAGE || '10';
const THINK = parseFloat(__ENV.THINK || '2.2'); // ~27 req/min/usuario, bajo el límite de 60/min

// Cuentas que la política permite para listar usuarios (rol 6 queda fuera: 403 por diseño).
const ACCOUNTS = [
  [__ENV.ROL1_ADMINISTRADOR_USER, __ENV.ROL1_ADMINISTRADOR_PASS],
  [__ENV.ROL2_DELEGADO_USER, __ENV.ROL2_DELEGADO_PASS],
  [__ENV.ROL3_DIRECTOR_USER, __ENV.ROL3_DIRECTOR_PASS],
  [__ENV.ROL4_SUBDIRECTOR_USER, __ENV.ROL4_SUBDIRECTOR_PASS],
  [__ENV.ROL5_COORDINADOR_USER, __ENV.ROL5_COORDINADOR_PASS],
].filter(([u, p]) => u && p);
// Fallback portable: si el target no declara los seis roles, usa ROLE_A / ADMIN_*.
if (ACCOUNTS.length === 0) {
  const u = __ENV.ROLE_A_USER || __ENV.ADMIN_EMAIL;
  const p = __ENV.ROLE_A_PASS || __ENV.ADMIN_PASS;
  if (u && p) ACCOUNTS.push([u, p]);
}

const usuariosLatency = new Trend('usuarios_latency', true);
const throttled = new Rate('throttled_429');

// Un VU por cuenta: reparte la carga sin que ningún usuario cruce su límite. Ajustable con LOAD_VUS.
const VUS = parseInt(__ENV.LOAD_VUS || String(Math.max(ACCOUNTS.length, 1)), 10);

export const options = {
  scenarios: {
    listado: { executor: 'constant-vus', vus: VUS, duration: __ENV.LOAD_DURATION || '60s' },
  },
  thresholds: {
    usuarios_latency: ['p(95)<1500'],
    'http_req_failed{endpoint:usuarios}': ['rate<0.05'],
  },
};

// Jar por-VU en ámbito de módulo: sobrevive a las iteraciones (k6 reinicia el jar por iteración).
const jar = new http.CookieJar();
let authed = false;

function login() {
  const [email, pass] = ACCOUNTS[(__VU - 1) % ACCOUNTS.length];
  http.get(`${BASE}/sanctum/csrf-cookie`, { jar, headers: { Origin: ORIGIN } });
  const c = jar.cookiesForURL(`${BASE}/`);
  const xsrf = c['XSRF-TOKEN'] ? decodeURIComponent(c['XSRF-TOKEN'][0]) : '';
  const res = http.post(`${BASE}/api/login`, JSON.stringify({ email, password: pass }), {
    jar,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-XSRF-TOKEN': xsrf, Origin: ORIGIN },
    tags: { endpoint: 'login' },
  });
  return check(res, { 'login 200': (r) => r.status === 200 });
}

export default function () {
  if (!authed) authed = login();
  const res = http.get(`${BASE}/api/usuarios?per_page=${PER_PAGE}`, {
    jar,
    headers: { Origin: ORIGIN },
    tags: { endpoint: 'usuarios' },
  });
  usuariosLatency.add(res.timings.duration);
  throttled.add(res.status === 429);
  check(res, { 'usuarios 200': (r) => r.status === 200 });
  sleep(THINK);
}
