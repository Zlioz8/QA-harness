// Auth adapters — the one piece of a target profile that is genuinely project-specific,
// isolated behind a fixed signature so that every generic spec in lib/specs/ stays portable.
//
// A target picks one with AUTH_ADAPTER in target.env. Adding a stack means adding ONE
// adapter here, which then serves every future project on that stack.
//
// Contract:  loginAs(role) -> APIRequestContext whose cookie jar / headers are authenticated.
//            roles are "A" (high privilege) and "B" (low privilege), never a raw account name,
//            so the authorization specs read the same in every project.
//
//            rawLogin(user, pass, headers?) -> RawLogin   [opcional, por stack]
//            logout(raw, headers?)          -> status     [opcional, por stack]
//            Son las dos primitivas que necesita el pilar de AUTENTICACIÓN de AAA
//            (lib/specs/authn.spec.ts): un login SIN memorizar, con credenciales explícitas
//            (una contraseña mala, o la buena para ver los tokens en crudo), y un cierre de
//            sesión. Viven aquí y no en la spec por la misma razón que loginAs: el motor de
//            sondas es genérico; lo que cambia por stack es cómo se entra y cómo se sale.
//            Un adaptador sin rawLogin/logout no falla las sondas: constan como NO APLICABLES.

import { APIRequestContext, request as pwRequest } from '@playwright/test';

export type Role = 'A' | 'B';

export const BASE = process.env.BASE_URL || 'http://localhost:8099';
export const ORIGIN = process.env.ALLOWED_ORIGIN || '';
// Ruta de cierre de sesión declarada por el perfil (target.env). Vacía = cada adaptador usa su
// ruta por defecto si el stack la tiene fija (Moodle, zajuna, sanctum); si no, logout no aplica.
const LOGOUT_PATH = process.env.LOGOUT_PATH || '';

export const CREDS: Record<Role, { user: string; pass: string }> = {
  A: { user: process.env.ROLE_A_USER || '', pass: process.env.ROLE_A_PASS || '' },
  B: { user: process.env.ROLE_B_USER || '', pass: process.env.ROLE_B_PASS || '' },
};

/** Absolute URL from a path.
 *
 * Playwright resolves a leading-slash path against the ORIGIN, not against a baseURL that
 * carries a path prefix: with BASE=http://host:8083/zajuna, `ctx.get('/login/index.php')` asks
 * for http://host:8083/login/index.php and gets a 404. Nothing errors — the adapter reports a
 * failed login, or worse the suite reads that 404 as "access denied" and every authorization
 * test passes for the wrong reason. Concatenate; it is also correct for path-less bases.
 */
export const u = (path: string): string =>
  /^https?:\/\//.test(path) ? path : `${BASE}${path}`;

// UNA sesión por rol y por worker, memorizada.
//
// Cada spec llamaba a loginAs() en cada prueba. Contra un backend con limitador de intentos
// —Costos Web: 10 por minuto y por email+IP, que es justo lo que R5 pidió añadir— la suite se
// autodenegaba: a partir del intento 11 el login devolvía 429, loginAs lanzaba, y decenas de
// pruebas de autorización se reportaban como FALLO cuando lo único roto era el ritmo del propio
// laboratorio. Un falso positivo masivo sobre la dimensión que este laboratorio existe para medir.
//
// La memoria es por ARCHIVO de specs (cada archivo es un proceso de worker con su propio módulo).
// lib/specs/authn.spec.ts hace además UN login crudo propio por rol —rawLogin, sin memoria
// compartida con esto— porque necesita ver access/refresh en crudo; y lo comparte entre sus
// sondas. Compartir la sesión entre archivos (L3 en la bitácora) sigue abierto.
const sesiones = new Map<string, Promise<APIRequestContext>>();

/** Resultado de un login CRUDO: lo que devolvió el sistema, sin interpretar más que «¿quedó
 *  sesión utilizable?». Nunca se persiste: la spec anota status y comprobaciones, no cuerpos. */
export type RawLogin = {
  /** Contexto con la credencial puesta si ok; el contexto usado para intentarlo si no. */
  ctx: APIRequestContext;
  status: number;
  ok: boolean;
  /** Cuerpo de la respuesta del login (texto) y su JSON si lo era. Para las comprobaciones
   *  body_has / body_lacks de la sonda login-fallido. */
  text?: string;
  body?: any;
  /** Tokens en crudo en los stacks que los emiten (JSON APIs). */
  tokens?: { access?: string; refresh?: string };
  /** Valor de la cookie de sesión en los stacks de cookie. */
  sessionCookie?: string;
};

export interface AuthAdapter {
  name: string;
  loginAs(role: Role): Promise<APIRequestContext>;
  /** Header a state-changing request needs (CSRF token, sesskey, bearer). */
  writeHeaders(ctx: APIRequestContext): Promise<Record<string, string>>;
  /** Login sin memorizar, con credenciales explícitas. `headers` se envían en la(s) petición(es)
   *  del login (la sonda pone ahí su User-Agent marcador para el oráculo de auditoría). */
  rawLogin?(user: string, pass: string, headers?: Record<string, string>): Promise<RawLogin>;
  /** Cierra la sesión de ese login crudo. Devuelve el status HTTP, o -1 si en este perfil no
   *  hay ruta de logout (ni LOGOUT_PATH ni una fija del stack): la sonda consta como no aplicable. */
  logout?(raw: RawLogin, headers?: Record<string, string>): Promise<number>;
}

async function newCtx(): Promise<APIRequestContext> {
  // `Accept: application/json` en los adaptadores de API. Sin ella, un framework como Laravel
  // responde a la peticion no autenticada con un 302 al login en vez de un 401: la matriz de
  // autorizacion ve una redireccion a una pagina que existe y no puede distinguir denegacion de
  // exito. No se envia en los adaptadores que raspan HTML (moodle-session), donde romperia.
  const quiereJson = ['sanctum', 'jwt-bearer', 'basic'].includes(
    (process.env.AUTH_ADAPTER || '').trim(),
  );
  return pwRequest.newContext({
    baseURL: BASE,
    extraHTTPHeaders: {
      ...(ORIGIN ? { Origin: ORIGIN, Referer: `${BASE}/` } : {}),
      ...(quiereJson ? { Accept: 'application/json' } : {}),
    },
    ignoreHTTPSErrors: true,
  });
}

/** Contexto con un Bearer fijo: lo que devuelve loginAs en los stacks de token. */
function bearerCtx(token: string, extra: Record<string, string> = {}): Promise<APIRequestContext> {
  return pwRequest.newContext({
    baseURL: BASE,
    extraHTTPHeaders: {
      Authorization: `Bearer ${token}`,
      ...extra,
      ...(ORIGIN ? { Origin: ORIGIN } : {}),
    },
    ignoreHTTPSErrors: true,
  });
}

async function cookie(ctx: APIRequestContext, name: string): Promise<string> {
  const state = await ctx.storageState();
  return decodeURIComponent(state.cookies.find((c) => c.name === name)?.value ?? '');
}

/** Texto y JSON (si lo es) de una respuesta, sin lanzar. */
async function leer(res: { text(): Promise<string> }): Promise<{ text: string; body: any }> {
  const text = await res.text().catch(() => '');
  let body: any;
  try { body = JSON.parse(text); } catch { body = undefined; }
  return { text, body };
}

// ---- Encuestas: login directo por USERNAME -> token Bearer -----------------
//
// El modo de auditoría LOCAL de encuestas, sin SSO. `POST /api/login` con {username,password}
// (AuthController::login valida `username`, no `email`) devuelve `access_token`, que la API
// acepta como Bearer. Se usa contra el despliegue de validación de esta máquina, con cuentas de
// la APLICACIÓN creadas por el laboratorio (rol en la columna `users.rol`). La matriz que sale
// de aquí es NO AUTORITATIVA —los roles los elegimos nosotros— pero ejecuta la dimensión de
// verdad; la autoritativa exige las cuentas reales por SSO (adaptador `encuestas-sso`).
async function encuestasRaw(user: string, pass: string, headers: Record<string, string> = {}): Promise<RawLogin> {
  const tmp = await newCtx();
  const res = await tmp.post(u('/api/login'), {
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...headers },
    data: { username: user, password: pass },
  });
  const status = res.status();
  const { text, body } = await leer(res);
  const token = body?.access_token;
  if (status !== 200 || !token) return { ctx: tmp, status, ok: false, text, body };
  return {
    ctx: await bearerCtx(token, { Accept: 'application/json' }),
    status, ok: true, text, body,
    tokens: { access: token, refresh: body?.refresh_token },
  };
}
const encuestasLogin: AuthAdapter = {
  name: 'encuestas-login',
  rawLogin: encuestasRaw,
  async loginAs(role) {
    const r = await encuestasRaw(CREDS[role].user, CREDS[role].pass);
    if (r.status !== 200) throw new Error(`encuestas-login: /api/login ${r.status} para el rol ${role}`);
    if (!r.ok) throw new Error(`encuestas-login: respuesta 200 sin access_token para ${role}`);
    return r.ctx;
  },
  async logout(raw, headers = {}) {
    return (await raw.ctx.post(u(LOGOUT_PATH || '/api/logout'), { headers })).status();
  },
  async writeHeaders() {
    return {}; // el Bearer ya viaja en el contexto
  },
};

// ---- Laravel Sanctum SPA (cookie session + XSRF header) --------------------
async function sanctumRaw(user: string, pass: string, headers: Record<string, string> = {}): Promise<RawLogin> {
  const ctx = await newCtx();
  await ctx.get(u('/sanctum/csrf-cookie'), { headers });
  const res = await ctx.post(u('/api/login'), {
    headers: { 'X-XSRF-TOKEN': await cookie(ctx, 'XSRF-TOKEN'), 'Content-Type': 'application/json', ...headers },
    data: { email: user, password: pass },
  });
  const status = res.status();
  const { text, body } = await leer(res);
  return { ctx, status, ok: status === 200, text, body, sessionCookie: await cookie(ctx, 'laravel_session') };
}
const sanctum: AuthAdapter = {
  name: 'sanctum',
  rawLogin: sanctumRaw,
  async loginAs(role) {
    const r = await sanctumRaw(CREDS[role].user, CREDS[role].pass);
    if (!r.ok) throw new Error(`sanctum login failed for role ${role}: ${r.status}`);
    return r.ctx;
  },
  async logout(raw, headers = {}) {
    return (await raw.ctx.post(u(LOGOUT_PATH || '/api/logout'), {
      headers: { 'X-XSRF-TOKEN': await cookie(raw.ctx, 'XSRF-TOKEN'), ...headers },
    })).status();
  },
  async writeHeaders(ctx) {
    return { 'X-XSRF-TOKEN': await cookie(ctx, 'XSRF-TOKEN') };
  },
};

// ---- Moodle form session (MoodleSession cookie + logintoken + sesskey) -----
// Moodle guards the login form itself with a one-shot `logintoken`, and every
// state-changing request afterwards with `sesskey`. Both are scraped from HTML —
// there is no JSON login endpoint to call.
async function moodleRaw(user: string, pass: string, headers: Record<string, string> = {}): Promise<RawLogin> {
  const ctx = await newCtx();
  const page = await (await ctx.get(u('/login/index.php'), { headers })).text();
  const token = /name="logintoken"\s+value="([^"]+)"/.exec(page)?.[1] ?? '';
  const res = await ctx.post(u('/login/index.php'), {
    form: { username: user, password: pass, logintoken: token },
    maxRedirects: 5,
    headers,
  });
  const text = await res.text();
  const ok = !(text.includes('loginerrors') || text.includes('name="logintoken"'));
  return { ctx, status: res.status(), ok, text, sessionCookie: await cookie(ctx, 'MoodleSession') };
}
const moodleSession: AuthAdapter = {
  name: 'moodle-session',
  rawLogin: moodleRaw,
  async loginAs(role) {
    const r = await moodleRaw(CREDS[role].user, CREDS[role].pass);
    if (!r.ok) throw new Error(`moodle login failed for role ${role}`);
    return r.ctx;
  },
  async logout(raw, headers = {}) {
    // Moodle exige el sesskey también para salir: sin él muestra una confirmación (200) y la
    // sesión sigue viva, con lo que la sonda mediría la confirmación y no el cierre.
    const sk = await sesskeyOf(raw.ctx);
    const res = await raw.ctx.get(u(`${LOGOUT_PATH || '/login/logout.php'}?sesskey=${encodeURIComponent(sk)}`), {
      maxRedirects: 0, headers,
    });
    return res.status();
  },
  async writeHeaders(ctx) {
    // sesskey travels as a parameter, not a header; specs read it via sesskeyOf().
    return {};
  },
};

// ---- Moodle + plugin propio que emite JWT en dos saltos --------------------
//
// El caso de ZAJUNA Early Alert (reportes_de_cursos), y el de cualquier plugin de Moodle que
// ponga delante un servicio propio: Moodle NO es el destino, es el emisor de credenciales.
//
//   1. POST <moodle>/blocks/<plugin>/login.php  {username,password} en JSON
//      -> JWT de IDENTIDAD (RS256, ~1 h) + los cursos donde el usuario puede ver reportes.
//      El Content-Type JSON es obligatorio: es el guarda CSRF del propio endpoint (un <form>
//      cross-origin no puede ponerlo). Mandarlo form-encoded da 400, que se lee como
//      «credenciales malas» cuando lo que falla es la forma de pedirlo.
//   2. GET <moodle>/blocks/<plugin>/token.php?courseid=N  con ese Bearer
//      -> JWT DE CURSO (600 s), atado a UN curso. 403 si el usuario no tiene la capability
//      en ese curso: aquí es donde vive el control de acceso, y por eso el paso 2 no se puede
//      saltar ni cachear entre cursos.
//
// Configuración (target.env), nada de esto es código:
//   ZEA_MOODLE_BASE   prefijo de ruta donde vive Moodle en ese origen ('' o '/zajuna')
//   ZEA_PLUGIN_PATH   ruta del plugin (por defecto /blocks/zajuna_early_alert)
//   ZEA_COURSE_A/_B   el curso con el que cada rol pide su token
//
// `loginAs` devuelve un contexto con el JWT DE CURSO, que es el que la API acepta. Un fallo en
// el paso 2 se lanza con su status: un 403 aquí es un dato de la matriz de autorización, no un
// error del laboratorio, y la diferencia tiene que verse en el mensaje.
//
// rawLogin cubre SOLO el paso 1 (el login del IdP, que es lo que una contraseña mala pone a
// prueba); el JWT de identidad es el `access` crudo. No hay logout: el JWT caduca solo.
async function zeaRaw(user: string, pass: string, headers: Record<string, string> = {}): Promise<RawLogin> {
  const mb = process.env.ZEA_MOODLE_BASE || '';
  const plugin = process.env.ZEA_PLUGIN_PATH || '/blocks/zajuna_early_alert';
  const tmp = await newCtx();
  const r1 = await tmp.post(u(`${mb}${plugin}/login.php`), {
    data: { username: user, password: pass },
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...headers },
  });
  const status = r1.status();
  const { text, body } = await leer(r1);
  const ident = body?.token;
  if (status !== 200 || !ident) return { ctx: tmp, status, ok: false, text, body };
  return { ctx: await bearerCtx(ident, { Accept: 'application/json' }), status, ok: true, text, body, tokens: { access: ident } };
}
const zeaStandalone: AuthAdapter = {
  name: 'zea-standalone',
  rawLogin: zeaRaw,
  async loginAs(role) {
    const mb = process.env.ZEA_MOODLE_BASE || '';
    const plugin = process.env.ZEA_PLUGIN_PATH || '/blocks/zajuna_early_alert';
    const curso = (role === 'B' ? process.env.ZEA_COURSE_B : process.env.ZEA_COURSE_A) || '';
    if (!curso) throw new Error(`zea-standalone: falta ZEA_COURSE_${role} en el perfil`);
    const r1 = await zeaRaw(CREDS[role].user, CREDS[role].pass);
    if (r1.status !== 200)
      throw new Error(`zea login.php falló para el rol ${role}: ${r1.status}`);
    const ident = r1.tokens?.access;
    if (!ident) throw new Error('zea login.php: respuesta 200 sin campo token');
    const tmp = await newCtx();
    const r2 = await tmp.get(u(`${mb}${plugin}/token.php?courseid=${encodeURIComponent(curso)}`), {
      headers: { Authorization: `Bearer ${ident}`, Accept: 'application/json' },
    });
    // UN 403 AQUÍ NO ES UN FALLO DEL LABORATORIO: ES EL RESULTADO.
    //
    // `token.php` deniega con 403 a quien no tiene `viewreports` en ese curso — que es
    // exactamente lo que se espera del rol B (un aprendiz: `db/access.php` concede la capability
    // solo a teacher, editingteacher y manager). Si esto lanzara, la matriz de autorización
    // moriría al construir la sesión y la dimensión entera se reportaría como error del lab en
    // vez de como lo que es: la denegación funcionando.
    //
    // Así que un 403 devuelve un contexto SIN Authorization —las credenciales que ese rol tiene
    // de verdad—, y se marca con una cabecera propia para que quien lea la traza no confunda
    // «no pudo obtener token» con «se olvidó de autenticarse». Cualquier otro fallo (login roto,
    // 5xx, red) sí lanza: eso sería un problema del entorno, y callarlo haría pasar por
    // «denegado» lo que en realidad no se midió.
    if (r2.status() === 403) {
      console.warn(
        `[zea-standalone] token.php 403 para el rol ${role} en el curso ${curso}: ` +
          'esa cuenta NO tiene block/zajuna_early_alert:viewreports ahí. ' +
          'Es un dato de la matriz, no un error — sigue sin cabecera Authorization.',
      );
      return pwRequest.newContext({
        baseURL: BASE,
        extraHTTPHeaders: {
          Accept: 'application/json',
          'X-Zea-Token-Denied': '403',
          ...(ORIGIN ? { Origin: ORIGIN } : {}),
        },
        ignoreHTTPSErrors: true,
      });
    }
    if (r2.status() !== 200)
      throw new Error(`zea token.php ${r2.status()} para el rol ${role} en el curso ${curso}`);
    const curso_jwt = (await r2.json()).token;
    if (!curso_jwt) throw new Error('zea token.php: respuesta 200 sin campo token');
    return bearerCtx(curso_jwt, { Accept: 'application/json' });
  },
  async writeHeaders() {
    // La API de reportes es de solo lectura (todo GET); no hay escritura que cabecear.
    return {};
  },
};

/** Moodle's per-session CSRF value, needed as a query/form parameter. */
export async function sesskeyOf(ctx: APIRequestContext): Promise<string> {
  const html = await (await ctx.get(u('/my/'))).text();
  return /"sesskey":"([^"]+)"/.exec(html)?.[1] ?? /sesskey=([A-Za-z0-9]+)/.exec(html)?.[1] ?? '';
}

// ---- JSON API returning a bearer token ------------------------------------
async function jwtRaw(user: string, pass: string, headers: Record<string, string> = {}): Promise<RawLogin> {
  const path = process.env.LOGIN_PATH || '/api/login';
  const tmp = await newCtx();
  const res = await tmp.post(u(path), { data: { username: user, password: pass }, headers });
  const status = res.status();
  const { text, body } = await leer(res);
  const token = body?.access_token || body?.token || body?.jwt;
  if (status !== 200 || !token) return { ctx: tmp, status, ok: false, text, body };
  return {
    ctx: await bearerCtx(token), status, ok: true, text, body,
    tokens: { access: token, refresh: body?.refresh_token || body?.refresh },
  };
}
const jwtBearer: AuthAdapter = {
  name: 'jwt-bearer',
  rawLogin: jwtRaw,
  async loginAs(role) {
    const r = await jwtRaw(CREDS[role].user, CREDS[role].pass);
    if (r.status !== 200) throw new Error(`jwt login failed for role ${role}: ${r.status}`);
    if (!r.ok) throw new Error('jwt login: no token field in response');
    return r.ctx;
  },
  async logout(raw, headers = {}) {
    // Sin ruta declarada no se adivina: cada API llama distinto a su logout, y medir una ruta
    // inventada mediría un 404 del laboratorio, no el cierre de sesión del sistema.
    if (!LOGOUT_PATH) return -1;
    return (await raw.ctx.post(u(LOGOUT_PATH), { headers })).status();
  },
  async writeHeaders() {
    return {};
  },
};

const basic: AuthAdapter = {
  name: 'basic',
  async loginAs(role) {
    return pwRequest.newContext({
      baseURL: BASE,
      httpCredentials: { username: CREDS[role].user, password: CREDS[role].pass },
      ignoreHTTPSErrors: true,
    });
  },
  async writeHeaders() {
    return {};
  },
};

// ---- Zajuna mobile API (JSON login by document, returns a bearer token) ----
// Custom login shape: POST /auth/login {type_document, document, password} -> {access_token}.
// ROLE_*_USER holds the document number; type is CC unless DOC_TYPE overrides. The token then
// travels as Authorization: Bearer on every request, like jwt-bearer with a different login body.
// The login also returns a refresh_token: rawLogin exposes it so the authn probe can check that
// it is NOT accepted as an access token (H2 of the 2026-09-23 sweep).
async function zajunaRaw(user: string, pass: string, headers: Record<string, string> = {}): Promise<RawLogin> {
  const path = process.env.LOGIN_PATH || '/auth/login';
  const tmp = await newCtx();
  // Absolute url (BASE may carry a path prefix like /mobile/api that a leading-slash path
  // would drop when Playwright resolves it against the origin).
  const res = await tmp.post(u(path), {
    data: {
      type_document: process.env.DOC_TYPE || 'CC',
      document: user,
      password: pass,
    },
    headers,
  });
  const status = res.status();
  const { text, body } = await leer(res);
  const token = body?.access_token;
  if (status !== 200 || !token) return { ctx: tmp, status, ok: false, text, body };
  return {
    ctx: await bearerCtx(token), status, ok: true, text, body,
    tokens: { access: token, refresh: body?.refresh_token },
  };
}
const zajuna: AuthAdapter = {
  name: 'zajuna',
  rawLogin: zajunaRaw,
  async loginAs(role) {
    const r = await zajunaRaw(CREDS[role].user, CREDS[role].pass);
    if (r.status !== 200) throw new Error(`zajuna login failed for role ${role}: ${r.status}`);
    if (!r.ok) throw new Error('zajuna login: no access_token in response');
    return r.ctx;
  },
  async logout(raw, headers = {}) {
    return (await raw.ctx.post(u(LOGOUT_PATH || '/auth/logout'), { headers })).status();
  },
  async writeHeaders() {
    return {};
  },
};

// ---- Plain PHP form login (session cookie, optionally a CSRF field) -------
//
// The factory's most repeated stack has no JSON login endpoint and no framework: a form is
// POSTed, PHP calls session_start(), and a cookie comes back. Everything project-specific is
// configuration rather than code, so this one adapter serves every such project.
//
//   LOGIN_PATH          form action (default /login)
//   LOGIN_USER_FIELD    default "username"
//   LOGIN_PASS_FIELD    default "password"
//   LOGIN_CSRF_FIELD    optional hidden field to scrape from the form first
//   LOGIN_FAIL_MARKER   text present in the body ONLY when login failed
//   LOGIN_OK_MARKER     text present ONLY when it succeeded (preferred: see below)
//   LOGOUT_PATH         ruta que cierra la sesión (GET); sin ella logout no aplica
//
// Deciding success is the whole difficulty. A PHP form login answers 200 whether it worked or
// not — the failure page IS a page — so status codes prove nothing. Absent any marker, the
// fallback is "did a session cookie appear", which is weak: some apps set one for anonymous
// visitors too. State LOGIN_OK_MARKER in the profile and this stops being guesswork; without
// it a failed login can be read as a success, and every authorization test then passes for the
// wrong reason, which is the worst outcome this lab can produce.
async function phpRaw(user: string, pass: string, headers: Record<string, string> = {}): Promise<RawLogin> {
  const path = process.env.LOGIN_PATH || '/login';
  const userField = process.env.LOGIN_USER_FIELD || 'username';
  const passField = process.env.LOGIN_PASS_FIELD || 'password';
  const csrfField = process.env.LOGIN_CSRF_FIELD || '';
  const ctx = await newCtx();

  const form: Record<string, string> = { [userField]: user, [passField]: pass };

  if (csrfField) {
    const page = await (await ctx.get(u(path), { headers })).text();
    const re = new RegExp(`name=["']${csrfField}["'][^>]*value=["']([^"']+)["']`);
    const token = re.exec(page)?.[1]
      ?? new RegExp(`value=["']([^"']+)["'][^>]*name=["']${csrfField}["']`).exec(page)?.[1];
    if (!token) throw new Error(`php-form: no se encontró el campo CSRF "${csrfField}" en ${path}`);
    form[csrfField] = token;
  }

  const res = await ctx.post(u(path), { form, maxRedirects: 5, headers });
  const text = await res.text();

  let ok: boolean;
  const fail = process.env.LOGIN_FAIL_MARKER;
  const okMarker = process.env.LOGIN_OK_MARKER;
  const cookies = (await ctx.storageState()).cookies;
  const sesion = cookies.find((c) => /^(PHPSESSID|.*session.*)$/i.test(c.name));
  if (fail && text.includes(fail)) ok = false;
  else if (okMarker) ok = text.includes(okMarker);
  else ok = Boolean(sesion);
  return { ctx, status: res.status(), ok, text, sessionCookie: sesion?.value };
}
const phpForm: AuthAdapter = {
  name: 'php-form',
  rawLogin: phpRaw,
  async loginAs(role) {
    const r = await phpRaw(CREDS[role].user, CREDS[role].pass);
    if (!r.ok) {
      const fail = process.env.LOGIN_FAIL_MARKER;
      const razon = fail && r.text?.includes(fail) ? 'apareció LOGIN_FAIL_MARKER'
        : process.env.LOGIN_OK_MARKER ? 'no apareció LOGIN_OK_MARKER' : 'ninguna cookie de sesión';
      throw new Error(`php-form: login falló para el rol ${role} (${razon})`);
    }
    return r.ctx;
  },
  async logout(raw, headers = {}) {
    if (!LOGOUT_PATH) return -1;
    return (await raw.ctx.get(u(LOGOUT_PATH), { maxRedirects: 0, headers })).status();
  },
  async writeHeaders() {
    return {};
  },
};

// Unauthenticated. Legitimate for a public surface — but the authorization specs will
// skip, and skipping must be visible in RUN.md rather than read as "passed".
const none: AuthAdapter = {
  name: 'none',
  async loginAs() {
    return newCtx();
  },
  async writeHeaders() {
    return {};
  },
};

// ---- Encuestas: Moodle-session -> pase HMAC del plugin -> token Sanctum -----
//
// El SSO de `encuestas`, y el patrón de cualquier app propia que entra por un plugin de Moodle
// que acuña un pase corto. Moodle NO es el destino: es el emisor. Tres saltos, cada uno leído
// del código del proyecto (AuthController::zajunaAutologin, ZajunaSsoService::validarPase,
// plugin-encuestas-zajuna/plugin/redirect.php):
//
//   1. Login por FORMULARIO de Moodle (igual que moodle-session): cookie MoodleSession.
//   2. GET <moodle>/local/encuestas/redirect.php  con esa sesión
//      -> el plugin firma un pase (JWT HS256 con el secreto compartido) y redirige a
//         <api>/api/auth/zajuna?token=<pase>.
//   3. Ese endpoint valida el pase y REDIRIGE a la SPA con ?token=<access_token Sanctum>.
//      Ese access_token es el Bearer que la API acepta.
//
// EL LABORATORIO NO FABRICA EL PASE. Firmarlo nosotros exigiría el secreto compartido (que NO
// está en el repo, y bien) y mediría nuestra capacidad de firmar, no el control de acceso del
// sistema. Por eso el pase se OBTIENE recorriendo el flujo real con una sesión de Moodle de una
// cuenta REAL — es la única forma de que la credencial resultante signifique algo.
//
// CUÁNDO NO PUEDE CORRER, y hay que declararlo en vez de fingir: si el login web de Moodle de ese
// entorno rebota a un IdP externo (zajunavideo5 manda `login/index.php` a caplms por su
// `alternateloginurl`), el paso 1 no completa. Entonces esto LANZA con un mensaje explícito y la
// dimensión de autorización se reporta NO DISPONIBLE por bloqueo de entorno — que no es «sin
// hallazgos». La superficie NO autenticada (401/403 sin sesión) sí se mide aparte y es autoritativa.
//
// Configuración (target.env / .local), nada de esto es código:
//   MOODLE_BASE_URL   dónde vive Moodle (p.ej. https://host/zajuna)
//   ENC_PLUGIN_PATH   ruta del plugin (por defecto /local/encuestas/redirect.php)
//   ENC_API_BASE      base de la API de Encuestas (BASE_URL por defecto)
//
// Sin rawLogin ni logout: el login crudo de un SSO de tres saltos no dice nada del sistema que se
// audita (mediría el formulario de Moodle). Las sondas que lo necesitan constan como no aplicables.
const encuestasSso: AuthAdapter = {
  name: 'encuestas-sso',
  async loginAs(role) {
    const moodle = (process.env.MOODLE_BASE_URL || process.env.MOODLE_TEST_URL || '').replace(/\/$/, '');
    if (!moodle) throw new Error('encuestas-sso: falta MOODLE_BASE_URL en el perfil');
    const redirectPath = process.env.ENC_PLUGIN_PATH || '/local/encuestas/redirect.php';

    // Paso 1 — sesión de Moodle por formulario.
    const ctx = await pwRequest.newContext({ baseURL: moodle, ignoreHTTPSErrors: true });
    const form = await (await ctx.get(`${moodle}/login/index.php`)).text();
    // Si el login rebotó a un IdP externo, no hay formulario que rellenar: fallo de ENTORNO.
    if (!/name="logintoken"/.test(form)) {
      throw new Error(
        `encuestas-sso: el login web de Moodle en ${moodle} no sirve el formulario ` +
          '(rebota a un IdP externo, p.ej. caplms). El SSO no se puede completar en este ' +
          'entorno: la matriz autenticada queda NO DISPONIBLE por bloqueo, no «sin hallazgos».',
      );
    }
    const token = /name="logintoken"\s+value="([^"]+)"/.exec(form)?.[1] ?? '';
    const login = await ctx.post(`${moodle}/login/index.php`, {
      form: { username: CREDS[role].user, password: CREDS[role].pass, logintoken: token },
      maxRedirects: 5,
    });
    const loginBody = await login.text();
    if (loginBody.includes('loginerrors') || loginBody.includes('name="logintoken"'))
      throw new Error(`encuestas-sso: login de Moodle falló para el rol ${role}`);

    // Paso 2 y 3 — el plugin acuña el pase y el endpoint lo canjea. Se sigue la cadena de
    // redirects a mano para leer el access_token del último Location sin ejecutar la SPA.
    let url = `${moodle}${redirectPath}`;
    let access = '';
    for (let salto = 0; salto < 6 && !access; salto++) {
      const r = await ctx.get(url, { maxRedirects: 0 });
      const loc = r.headers()['location'] || '';
      if (!loc) break;
      const m = /[?&]token=([^&]+)/.exec(loc);
      if (m) { access = decodeURIComponent(m[1]); break; }
      const err = /[?&]error=([^&]+)/.exec(loc);
      if (err) throw new Error(`encuestas-sso: el SSO rechazó al rol ${role}: ${decodeURIComponent(err[1])}`);
      url = /^https?:\/\//.test(loc) ? loc : `${moodle}${loc}`;
    }
    if (!access) throw new Error(`encuestas-sso: no se obtuvo access_token para el rol ${role} tras el SSO`);

    // El Bearer Sanctum contra la API de Encuestas.
    return pwRequest.newContext({
      baseURL: process.env.ENC_API_BASE || BASE,
      extraHTTPHeaders: {
        Authorization: `Bearer ${access}`,
        Accept: 'application/json',
        ...(ORIGIN ? { Origin: ORIGIN } : {}),
      },
      ignoreHTTPSErrors: true,
    });
  },
  async writeHeaders() {
    // La matriz de autorización es de solo lectura (GET); no hay escritura que cabecear.
    return {};
  },
};

const ADAPTERS: Record<string, AuthAdapter> = {
  sanctum,
  'moodle-session': moodleSession,
  'encuestas-sso': encuestasSso,
  'encuestas-login': encuestasLogin,
  'jwt-bearer': jwtBearer,
  'php-form': phpForm,
  'zea-standalone': zeaStandalone,
  zajuna,
  basic,
  none,
};

export function adapter(): AuthAdapter {
  const want = process.env.AUTH_ADAPTER || 'none';
  const a = ADAPTERS[want];
  if (!a) throw new Error(`unknown AUTH_ADAPTER "${want}". Available: ${Object.keys(ADAPTERS).join(', ')}`);
  return a;
}

export const loginAs = (role: Role): Promise<APIRequestContext> => {
  const clave = `${adapter().name}:${role}`;
  let s = sesiones.get(clave);
  if (!s) {
    s = adapter().loginAs(role);
    sesiones.set(clave, s);
  }
  return s;
};
export const writeHeaders = (ctx: APIRequestContext) => adapter().writeHeaders(ctx);
export const hasRole = (role: Role) => Boolean(CREDS[role].user && CREDS[role].pass);
