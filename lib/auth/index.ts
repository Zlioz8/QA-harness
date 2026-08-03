// Auth adapters — the one piece of a target profile that is genuinely project-specific,
// isolated behind a fixed signature so that every generic spec in lib/specs/ stays portable.
//
// A target picks one with AUTH_ADAPTER in target.env. Adding a stack means adding ONE
// adapter here, which then serves every future project on that stack.
//
// Contract:  loginAs(role) -> APIRequestContext whose cookie jar / headers are authenticated.
//            roles are "A" (high privilege) and "B" (low privilege), never a raw account name,
//            so the authorization specs read the same in every project.

import { APIRequestContext, request as pwRequest } from '@playwright/test';

export type Role = 'A' | 'B';

export const BASE = process.env.BASE_URL || 'http://localhost:8099';
export const ORIGIN = process.env.ALLOWED_ORIGIN || '';

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
const sesiones = new Map<string, Promise<APIRequestContext>>();

export interface AuthAdapter {
  name: string;
  loginAs(role: Role): Promise<APIRequestContext>;
  /** Header a state-changing request needs (CSRF token, sesskey, bearer). */
  writeHeaders(ctx: APIRequestContext): Promise<Record<string, string>>;
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

async function cookie(ctx: APIRequestContext, name: string): Promise<string> {
  const state = await ctx.storageState();
  return decodeURIComponent(state.cookies.find((c) => c.name === name)?.value ?? '');
}

// ---- Laravel Sanctum SPA (cookie session + XSRF header) --------------------
const sanctum: AuthAdapter = {
  name: 'sanctum',
  async loginAs(role) {
    const ctx = await newCtx();
    await ctx.get(u('/sanctum/csrf-cookie'));
    const res = await ctx.post(u('/api/login'), {
      headers: { 'X-XSRF-TOKEN': await cookie(ctx, 'XSRF-TOKEN'), 'Content-Type': 'application/json' },
      data: { email: CREDS[role].user, password: CREDS[role].pass },
    });
    if (res.status() !== 200) throw new Error(`sanctum login failed for role ${role}: ${res.status()}`);
    return ctx;
  },
  async writeHeaders(ctx) {
    return { 'X-XSRF-TOKEN': await cookie(ctx, 'XSRF-TOKEN') };
  },
};

// ---- Moodle form session (MoodleSession cookie + logintoken + sesskey) -----
// Moodle guards the login form itself with a one-shot `logintoken`, and every
// state-changing request afterwards with `sesskey`. Both are scraped from HTML —
// there is no JSON login endpoint to call.
const moodleSession: AuthAdapter = {
  name: 'moodle-session',
  async loginAs(role) {
    const ctx = await newCtx();
    const page = await (await ctx.get(u('/login/index.php'))).text();
    const token = /name="logintoken"\s+value="([^"]+)"/.exec(page)?.[1] ?? '';
    const res = await ctx.post(u('/login/index.php'), {
      form: { username: CREDS[role].user, password: CREDS[role].pass, logintoken: token },
      maxRedirects: 5,
    });
    const body = await res.text();
    if (body.includes('loginerrors') || body.includes('name="logintoken"'))
      throw new Error(`moodle login failed for role ${role}`);
    return ctx;
  },
  async writeHeaders(ctx) {
    // sesskey travels as a parameter, not a header; specs read it via sesskeyOf().
    return {};
  },
};

/** Moodle's per-session CSRF value, needed as a query/form parameter. */
export async function sesskeyOf(ctx: APIRequestContext): Promise<string> {
  const html = await (await ctx.get(u('/my/'))).text();
  return /"sesskey":"([^"]+)"/.exec(html)?.[1] ?? /sesskey=([A-Za-z0-9]+)/.exec(html)?.[1] ?? '';
}

// ---- JSON API returning a bearer token ------------------------------------
const jwtBearer: AuthAdapter = {
  name: 'jwt-bearer',
  async loginAs(role) {
    const path = process.env.LOGIN_PATH || '/api/login';
    const tmp = await newCtx();
    const res = await tmp.post(u(path), {
      data: { username: CREDS[role].user, password: CREDS[role].pass },
    });
    if (res.status() !== 200) throw new Error(`jwt login failed for role ${role}: ${res.status()}`);
    const body = await res.json();
    const token = body.access_token || body.token || body.jwt;
    if (!token) throw new Error('jwt login: no token field in response');
    return pwRequest.newContext({
      baseURL: BASE,
      extraHTTPHeaders: { Authorization: `Bearer ${token}`, ...(ORIGIN ? { Origin: ORIGIN } : {}) },
      ignoreHTTPSErrors: true,
    });
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
const zajuna: AuthAdapter = {
  name: 'zajuna',
  async loginAs(role) {
    const path = process.env.LOGIN_PATH || '/auth/login';
    const tmp = await newCtx();
    // Absolute url (BASE may carry a path prefix like /mobile/api that a leading-slash path
    // would drop when Playwright resolves it against the origin).
    const res = await tmp.post(u(path), {
      data: {
        type_document: process.env.DOC_TYPE || 'CC',
        document: CREDS[role].user,
        password: CREDS[role].pass,
      },
    });
    if (res.status() !== 200) throw new Error(`zajuna login failed for role ${role}: ${res.status()}`);
    const token = (await res.json()).access_token;
    if (!token) throw new Error('zajuna login: no access_token in response');
    return pwRequest.newContext({
      baseURL: BASE,
      extraHTTPHeaders: { Authorization: `Bearer ${token}`, ...(ORIGIN ? { Origin: ORIGIN } : {}) },
      ignoreHTTPSErrors: true,
    });
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

const ADAPTERS: Record<string, AuthAdapter> = {
  sanctum,
  'moodle-session': moodleSession,
  'jwt-bearer': jwtBearer,
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
