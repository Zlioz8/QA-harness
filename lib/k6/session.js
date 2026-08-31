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
      // MOODLE_BASE: el prefijo bajo el que vive Moodle cuando NO está en la raíz del host. En
      // Zajuna el core se sirve en `/zajuna`, así que login/index.php es `/zajuna/login/index.php`.
      // Antes esto era `${BASE}/login/index.php` a secas, y contra un Moodle bajo subpath daba 404
      // -> logintoken vacío -> login fallido -> «100% error» en la carga (medido en
      // portafolio_del_aprendiz, 2026-08-25: 353.837 iteraciones fallando al instante). Es el
      // mismo patrón que zea-standalone ya resolvía con ZEA_MOODLE_BASE; se generaliza porque un
      // Moodle bajo subpath es lo normal aquí (antiplagio, portafolio), no la excepción.
      const mb = __ENV.MOODLE_BASE || '';
      const page = http.get(`${BASE}${mb}/login/index.php`, { jar, headers: hdr() });
      const m = /name="logintoken"\s+value="([^"]+)"/.exec(page.body || '');
      const r = http.post(
        `${BASE}${mb}/login/index.php`,
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
    // Moodle + plugin que emite JWT propios, en DOS saltos. Mismo contrato que el adaptador
    // `zea-standalone` de lib/auth/index.ts, y tiene que existir en LOS DOS sitios por la misma
    // razón que `php-form`: sin este caso k6 cae al `default` y mide la superficie SIN
    // autenticar creyendo que está autenticada.
    //
    //   1. POST <moodle>/blocks/<plugin>/login.php  {username,password} en JSON
    //      -> JWT de IDENTIDAD. El Content-Type JSON es OBLIGATORIO: el guarda CSRF de ese
    //         endpoint rechaza form-encoded a propósito, y con `form` k6 recibiría un 400 que
    //         se lee como credenciales malas.
    //   2. GET <moodle>/blocks/<plugin>/token.php?courseid=N con ese Bearer
    //      -> JWT DE CURSO, que es el único que acepta la API. Sin el paso 2, todo responde 401.
    case 'zea-standalone': {
      const mb = __ENV.ZEA_MOODLE_BASE || '';
      const plugin = __ENV.ZEA_PLUGIN_PATH || '/blocks/zajuna_early_alert';
      const curso = role === 'B' ? __ENV.ZEA_COURSE_B : __ENV.ZEA_COURSE_A;
      const r1 = http.post(`${BASE}${mb}${plugin}/login.php`, JSON.stringify({ username: user, password: pass }), {
        jar,
        headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...hdr() },
        tags: { endpoint: 'login' },
      });
      const ident = r1.status === 200 ? r1.json('token') || '' : '';
      if (!ident) return check(r1, { 'login ok': () => false });
      const r2 = http.get(`${BASE}${mb}${plugin}/token.php?courseid=${encodeURIComponent(curso || '')}`, {
        jar,
        headers: { Authorization: `Bearer ${ident}`, Accept: 'application/json', ...hdr() },
        tags: { endpoint: 'token' },
      });
      bearer = r2.status === 200 ? r2.json('token') || '' : '';
      return check(r2, { 'token de curso 200': (x) => x.status === 200 && bearer !== '' });
    }
    default:
      return true; // unauthenticated surface
  }
}

// El bearer, para poder INICIAR SESIÓN UNA VEZ y repartirlo.
//
// k6 ejecuta `setup()` una sola vez y entrega su retorno a cada VU. Eso es lo que hay que usar
// cuando el login está limitado por intentos: si cada VU (o peor, cada iteración) vuelve a
// autenticarse, la prueba de carga se convierte en un ataque de fuerza bruta contra el propio
// login, el limitador entra, y lo que se mide es el muro — no la aplicación. Ya pasó en este
// laboratorio con Costos Web (10 intentos por minuto) y aquí el riesgo es peor: el throttle de
// `login_guard` puede bloquear a un usuario REAL del servidor.
//
//   export function setup()      { login('A'); return { t: tokenActual() }; }
//   export default function (d)  { usarToken(d.t); ... }
export function tokenActual() {
  return bearer;
}
export function usarToken(t) {
  bearer = t || '';
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
