// k6 side of the auth contract. Same roles (A = high privilege, B = low), same
// AUTH_ADAPTER switch as lib/auth/index.ts, so a load script written for one project
// reads identically in the next.
//
// k6 resets the per-VU cookie jar on EVERY iteration. Logging in once and relying on
// implicit cookies makes later iterations travel unauthenticated, and the backend answers
// with an auth error — that measures the login wall, not the endpoint. Hence an explicit
// module-scope jar per VU, passed on every request.
import http from 'k6/http';
import { check } from 'k6';

export const BASE = __ENV.BASE_URL || 'http://app:8000';
export const ORIGIN = __ENV.ALLOWED_ORIGIN || '';
const ADAPTER = __ENV.AUTH_ADAPTER || 'none';

export const CREDS = {
  A: { user: __ENV.ROLE_A_USER || '', pass: __ENV.ROLE_A_PASS || '' },
  B: { user: __ENV.ROLE_B_USER || '', pass: __ENV.ROLE_B_PASS || '' },
};

export const jar = new http.CookieJar();
const hdr = () => (ORIGIN ? { Origin: ORIGIN } : {});

function cookie(name) {
  const c = jar.cookiesForURL(`${BASE}/`);
  return c[name] ? decodeURIComponent(c[name][0]) : '';
}

let bearer = '';

export function login(role = 'A') {
  const { user, pass } = CREDS[role];
  switch (ADAPTER) {
    case 'sanctum': {
      http.get(`${BASE}/sanctum/csrf-cookie`, { jar, headers: hdr() });
      const r = http.post(`${BASE}/api/login`, JSON.stringify({ email: user, password: pass }), {
        jar,
        headers: { 'Content-Type': 'application/json', 'X-XSRF-TOKEN': cookie('XSRF-TOKEN'), ...hdr() },
        tags: { endpoint: 'login' },
      });
      return check(r, { 'login 200': (x) => x.status === 200 });
    }
    case 'moodle-session': {
      const page = http.get(`${BASE}/login/index.php`, { jar, headers: hdr() });
      const m = /name="logintoken"\s+value="([^"]+)"/.exec(page.body || '');
      const r = http.post(
        `${BASE}/login/index.php`,
        { username: user, password: pass, logintoken: m ? m[1] : '' },
        { jar, headers: hdr(), tags: { endpoint: 'login' } },
      );
      return check(r, { 'login ok': (x) => x.status === 200 && !/loginerrors/.test(x.body || '') });
    }
    case 'jwt-bearer': {
      const r = http.post(`${BASE}${__ENV.LOGIN_PATH || '/api/login'}`,
        JSON.stringify({ username: user, password: pass }),
        { headers: { 'Content-Type': 'application/json' }, tags: { endpoint: 'login' } });
      if (r.status === 200) {
        const b = r.json();
        bearer = b.access_token || b.token || b.jwt || '';
      }
      return check(r, { 'login 200': (x) => x.status === 200 });
    }
    default:
      return true; // unauthenticated surface
  }
}

export function authedGet(path, tag) {
  return http.get(`${BASE}${path}`, {
    jar,
    headers: { ...hdr(), ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}) },
    tags: { endpoint: tag },
  });
}
