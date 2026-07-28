// Shared Sanctum SPA session helper for every load script.
//
// k6 resets the per-VU cookie jar on EVERY iteration. If you log in once and rely on
// implicit cookies, later iterations travel unauthenticated and the backend answers
// with an auth error — that measures nothing. So each VU keeps its own CookieJar in
// module scope (survives iterations) and passes it explicitly via `jar`.
import http from 'k6/http';
import { check } from 'k6';

export const BASE = __ENV.BASE_URL || 'http://nginx-prod';
export const ORIGIN = __ENV.ALLOWED_ORIGIN || 'http://localhost:5173';

export const CREDS = {
  admin: {
    email: __ENV.ADMIN_EMAIL || 'admin@test.local',
    pass: __ENV.ADMIN_PASS || 'secret123',
  },
  rep: {
    email: __ENV.REP_EMAIL || 'rep@test.local',
    pass: __ENV.REP_PASS || 'secret123',
  },
};

// One jar per VU, created at module scope so it persists across iterations.
export const jar = new http.CookieJar();

export function xsrf() {
  const c = jar.cookiesForURL(`${BASE}/`);
  return c['XSRF-TOKEN'] ? decodeURIComponent(c['XSRF-TOKEN'][0]) : '';
}

export function login(who = 'admin') {
  const { email, pass } = CREDS[who];
  http.get(`${BASE}/sanctum/csrf-cookie`, { jar, headers: { Origin: ORIGIN } });
  const res = http.post(`${BASE}/api/login`, JSON.stringify({ email, password: pass }), {
    jar,
    headers: { 'Content-Type': 'application/json', 'X-XSRF-TOKEN': xsrf(), Origin: ORIGIN },
    tags: { endpoint: 'login' },
  });
  check(res, { 'login 200': (r) => r.status === 200 });
  return res.status === 200;
}

export function authedGet(path, tag) {
  return http.get(`${BASE}${path}`, {
    jar,
    headers: { Origin: ORIGIN },
    tags: { endpoint: tag },
  });
}
