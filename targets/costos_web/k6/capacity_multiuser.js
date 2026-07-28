// CAPACIDAD REAL — cada VU usa una cuenta distinta (load1..load200), así el
// throttle por-usuario (60/min) NO enmascara el techo del servidor. Jornada
// realista: listado + un catálogo, con think-time de 1 s. Mide la capacidad
// agregada de 200 usuarios DIFERENTES, que es el escenario de producción.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

const BASE = __ENV.BASE_URL || 'http://nginx-prod';
const ORIGIN = __ENV.ALLOWED_ORIGIN || 'http://localhost:5173';
const TARGET = parseInt(__ENV.TARGET_VUS || '200', 10);
const N_USERS = parseInt(__ENV.N_USERS || '200', 10);

const tListado = new Trend('t_listado', true);

export const options = {
  scenarios: {
    capacidad: {
      executor: 'ramping-vus', startVUs: 1,
      stages: [
        { duration: '1m', target: TARGET },
        { duration: '5m', target: TARGET },
        { duration: '30s', target: 0 },
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    'http_req_failed': ['rate<0.01'],
    'http_req_duration': ['p(95)<1500'],
    'http_reqs': ['rate>50'],
  },
};

// jar por-VU; cada VU toma una cuenta según su número (1..N_USERS, ciclando).
const jar = new http.CookieJar();
let authed = false;

function login() {
  const uid = ((__VU - 1) % N_USERS) + 1;
  const email = `load${uid}@test.local`;
  http.get(`${BASE}/sanctum/csrf-cookie`, { jar, headers: { Origin: ORIGIN } });
  const c = jar.cookiesForURL(`${BASE}/`);
  const xsrf = c['XSRF-TOKEN'] ? decodeURIComponent(c['XSRF-TOKEN'][0]) : '';
  const res = http.post(`${BASE}/api/login`, JSON.stringify({ email, password: 'secret123' }), {
    jar, headers: { 'Content-Type': 'application/json', 'X-XSRF-TOKEN': xsrf, Origin: ORIGIN },
    tags: { endpoint: 'login' },
  });
  return check(res, { 'login 200': (r) => r.status === 200 });
}

export default function () {
  if (!authed) authed = login();
  // 1 petición/iteración + think-time 1,5 s ⇒ ~40 req/min por usuario (bajo el
  // throttle de 60/min): así el 429 no enmascara el techo real del servidor.
  const r1 = http.get(`${BASE}/api/usuarios?per_page=10`, { jar, headers: { Origin: ORIGIN }, tags: { endpoint: 'usuarios' } });
  tListado.add(r1.timings.duration);
  check(r1, { 'listado 200': (r) => r.status === 200, 'no 429': (r) => r.status !== 429 });
  sleep(parseFloat(__ENV.THINK || '1.5'));
}
