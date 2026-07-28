// k6 load test — GET /api/usuarios under concurrency.
// Mide el listado (H19/H20). Auth: sesión Sanctum SPA (csrf-cookie -> login).
//
// IMPORTANTE: k6 reinicia el cookie jar del VU en CADA iteración. Por eso usamos un
// CookieJar propio en ámbito de VU, que sí persiste entre iteraciones; si no, las
// peticiones viajan sin sesión y el backend responde error de autenticación
// (falsos negativos que no miden el endpoint).
import http from 'k6/http';
import { check } from 'k6';
import { Trend } from 'k6/metrics';

const BASE = __ENV.BASE_URL || 'http://app:8000';
const ORIGIN = __ENV.ALLOWED_ORIGIN || 'http://localhost:5173';
const EMAIL = __ENV.ADMIN_EMAIL || 'admin@test.local';
const PASS = __ENV.ADMIN_PASS || 'secret123';
const PER_PAGE = __ENV.PER_PAGE || '10';

const usuariosLatency = new Trend('usuarios_latency', true);

export const options = {
  scenarios: {
    listado: {
      executor: 'ramping-vus', startVUs: 1,
      stages: [{ duration: '15s', target: 10 }, { duration: '30s', target: 10 }, { duration: '5s', target: 0 }],
    },
  },
  thresholds: {
    'usuarios_latency': ['p(95)<800'],
    'http_req_failed': ['rate<0.05'],
  },
};

// Jar por VU que sobrevive a las iteraciones.
const jar = new http.CookieJar();
let authed = false;

function login() {
  http.get(`${BASE}/sanctum/csrf-cookie`, { jar, headers: { Origin: ORIGIN } });
  const cookies = jar.cookiesForURL(`${BASE}/`);
  const xsrf = cookies['XSRF-TOKEN'] ? decodeURIComponent(cookies['XSRF-TOKEN'][0]) : '';
  const res = http.post(`${BASE}/api/login`, JSON.stringify({ email: EMAIL, password: PASS }), {
    jar,
    headers: { 'Content-Type': 'application/json', 'X-XSRF-TOKEN': xsrf, Origin: ORIGIN },
  });
  check(res, { 'login 200': (r) => r.status === 200 });
  return res.status === 200;
}

export default function () {
  if (!authed) authed = login();
  const res = http.get(`${BASE}/api/usuarios?per_page=${PER_PAGE}`, {
    jar,
    headers: { Origin: ORIGIN },
  });
  usuariosLatency.add(res.timings.duration);
  check(res, { 'usuarios 200': (r) => r.status === 200 });
}
