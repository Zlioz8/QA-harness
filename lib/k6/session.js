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
    case 'zajuna': {
      const r = http.post(`${BASE}${__ENV.LOGIN_PATH || '/auth/login'}`,
        JSON.stringify({ type_document: __ENV.DOC_TYPE || 'CC', document: user, password: pass }),
        { headers: { 'Content-Type': 'application/json' }, tags: { endpoint: 'login' } });
      if (r.status === 200) bearer = r.json().access_token || '';
      return check(r, { 'login 200': (x) => x.status === 200 });
    }
    // Login por formulario en PHP plano. Mismo contrato que el adaptador `php-form` de
    // lib/auth/index.ts, y tiene que existir en LOS DOS sitios: sin este caso, k6 caía al
    // `default` de abajo y medía la pantalla de login sin darse cuenta — un p95 excelente
    // sobre el formulario, no sobre la aplicación.
    //
    // Un login por formulario responde 200 tanto si funcionó como si no, así que el marcador
    // es lo único que decide. Sin LOGIN_OK_MARKER esto no puede afirmar que la sesión existe,
    // y lo dice fallando el check en vez de suponer que sí.
    case 'php-form': {
      const r = http.post(
        `${BASE}${__ENV.LOGIN_PATH || '/login'}`,
        {
          [__ENV.LOGIN_USER_FIELD || 'username']: user,
          [__ENV.LOGIN_PASS_FIELD || 'password']: pass,
        },
        { jar, headers: hdr(), tags: { endpoint: 'login' } },
      );
      const ok = __ENV.LOGIN_OK_MARKER;
      return check(r, {
        'login ok': (x) => x.status === 200 && (ok ? (x.body || '').includes(ok) : true),
      });
    }
    default:
      return true; // unauthenticated surface
  }
}

// Bearer-authenticated POST with a JSON body — Zajuna's endpoints are POST, not GET.
export function authedPost(path, body, tag) {
  return http.post(`${BASE}${path}`, JSON.stringify(body || {}), {
    jar,
    headers: { 'Content-Type': 'application/json', ...hdr(), ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}) },
    tags: { endpoint: tag },
  });
}

export function authedGet(path, tag) {
  return http.get(`${BASE}${path}`, {
    jar,
    headers: { ...hdr(), ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}) },
    tags: { endpoint: tag },
  });
}
