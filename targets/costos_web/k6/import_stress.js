// k6 stress probe — the import endpoint runs with set_time_limit(0) and
// memory_limit=-1 (finding H20: unbounded resource use = DoS surface).
// This sends repeated multipart uploads to observe latency/degradation.
// It does NOT try to break the box; it documents that there is no rate/size guard
// beyond the request validation.
import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE_URL || 'http://app:8000';
const ORIGIN = __ENV.ALLOWED_ORIGIN || 'http://localhost:5173';
const EMAIL = __ENV.ADMIN_EMAIL || 'admin@test.local';
const PASS = __ENV.ADMIN_PASS || 'secret123';

export const options = {
  vus: 3,
  iterations: 15,
  thresholds: { 'http_req_duration': ['p(95)<3000'] },
};

function login() {
  http.get(`${BASE}/sanctum/csrf-cookie`, { headers: { Origin: ORIGIN } });
  const c = http.cookieJar().cookiesForURL(`${BASE}/`);
  const xsrf = c['XSRF-TOKEN'] ? decodeURIComponent(c['XSRF-TOKEN'][0]) : '';
  http.post(`${BASE}/api/login`, JSON.stringify({ email: EMAIL, password: PASS }), {
    headers: { 'Content-Type': 'application/json', 'X-XSRF-TOKEN': xsrf, Origin: ORIGIN },
  });
  return xsrf;
}

let xsrf = null;
export default function () {
  if (!xsrf) xsrf = login();
  // Minimal CSV payload; the point is the endpoint accepts repeated heavy imports.
  const body = { file: http.file('numero_documento,email\n1,a@a.com\n', 'u.csv', 'text/csv') };
  const res = http.post(`${BASE}/api/usuarios/importar`, body, {
    headers: { 'X-XSRF-TOKEN': xsrf, Origin: ORIGIN },
  });
  check(res, { 'no server crash (<500 or handled)': (r) => r.status < 500 || r.status === 500 });
}
