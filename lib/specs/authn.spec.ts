// AAA · AUTENTICACIÓN — MOTOR GENÉRICO, GUION DEL PROYECTO.
//
// La misma línea de corte que la matriz de autorización: ejecutar una sonda es automatizable;
// saber qué debe responder ESTE sistema no lo es. El perfil escribe targets/<t>/aaa/authn.json
// (montado aquí como /profile/aaa/authn.json) con sondas TIPADAS y sus expectativas; este archivo
// sabe ejecutar cada tipo a través del adaptador del perfil (lib/auth: rawLogin / logout /
// loginAs), nunca con una ruta de login escrita aquí. Un stack nuevo se sirve añadiendo su
// adaptador, no tocando esto.
//
// Tipos de sonda:
//   login-fallido        rawLogin con contraseña mala: debe quedar SIN sesión; `expect` opcional
//                        sobre el status y el cuerpo del login (pistas de enumeración, trazas).
//   refresh-como-access  el refresh del login crudo, usado como Bearer contra `path`: `expect`.
//                        Sin refresh en este stack -> no aplica.
//   logout-revoca        logout del login crudo y después `path` con la credencial vieja:
//                        `expect` (por defecto denegado). Sin logout en este stack -> no aplica.
//   anonimo              `peticiones` sin sesión, cada una con su `expect`.
//   peticion             escape genérico: as none|A|B|fresh:A|fresh:B, use access|refresh,
//                        method/path/body/headers/repeat, `expect`.
//   limitador            N intentos fallidos seguidos; el último debe responder `expect`
//                        (429 por defecto). DESTRUCTIVA: solo con AAA_DESTRUCTIVO=1.
// `expect`: status[], denegado (401/403/404 o redirección a login — el criterio de la matriz),
// body_has[], body_lacks[], header_has{cabecera: regex}. ${VAR} se expande desde el entorno.
//
// PRESUPUESTO DE LOGINS. Un login crudo por rol y archivo, memorizado y COMPARTIDO por
// refresh-como-access, logout-revoca y fresh:X (por eso logout-revoca va al final del guion),
// más uno fallido por sonda login-fallido. Contra un backend con limitador (movil: 10/min/IP)
// eso es lo que cabe junto a auth-check y la matriz. E2E_PACE_MS espacia las sondas.
//
// LO QUE QUEDA EN DISCO. /reports/aaa-acciones.json (= reports/<t>/playwright/): las ACCIONES
// que se hicieron (login, login-fallido, logout, peticiones), con su instante t0 y el User-Agent
// marcador que se envió, para que tools/aaa-oracle.sh pregunte a la tabla de auditoría si
// quedaron registradas; y el resultado de cada sonda con sus pasos (status y qué comprobación
// falló). Nunca cuerpos de respuesta ni credenciales. Se reescribe tras CADA sonda: una suite
// que muera a medias deja lo medido hasta entonces.
import { test, expect, request as pwRequest } from '@playwright/test';
import * as fs from 'fs';
import { adapter, loginAs, BASE, u, CREDS, Role, RawLogin } from '../auth/index';

const GUION = process.env.AAA_AUTHN_JSON || '/profile/aaa/authn.json';
const SALIDA = process.env.AAA_ACCIONES || '/reports/aaa-acciones.json';
const PACE = Number(process.env.E2E_PACE_MS || 0);
const DESTRUCTIVO = process.env.AAA_DESTRUCTIVO === '1';
const PASS_MALA = 'seclab-contrasena-incorrecta';

type Expect = {
  status?: number[]; denegado?: boolean;
  body_has?: string[]; body_lacks?: string[]; header_has?: Record<string, string>;
};
type Peticion = {
  id?: string; method?: string; path: string; body?: unknown; headers?: Record<string, string>;
  use?: 'access' | 'refresh' | 'none'; repeat?: number; expect?: Expect;
};
type Sonda = {
  id: string; tipo: string; rol?: Role; severidad?: string; stride?: string; titulo?: string;
  nota?: string; destructivo?: boolean;
  path?: string; method?: string; body?: unknown; headers?: Record<string, string>;
  use?: 'access' | 'refresh' | 'none'; repeat?: number; as?: string;
  expect?: Expect; peticiones?: Peticion[]; intentos?: number;
};

const doc = fs.existsSync(GUION) ? JSON.parse(fs.readFileSync(GUION, 'utf8')) : null;
const sondas: Sonda[] = Array.isArray(doc?.sondas) ? doc.sondas : [];

const expandVars = (s: string): string =>
  s.replace(/\$\{([A-Z0-9_]+)\}/g, (m, name) => process.env[name] ?? m);
const expandDeep = (v: any): any =>
  typeof v === 'string' ? expandVars(v)
    : Array.isArray(v) ? v.map(expandDeep)
      : v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, expandDeep(x)]))
        : v;

// ---- registro para el oráculo y el conversor --------------------------------------------------
const registro = {
  generado: '', adaptador: '', guion: GUION,
  acciones: [] as { id: string; rol: string; usuario: string; t0: string; marker: string; status: number }[],
  sondas: [] as { id: string; tipo: string; pilar: string; stride: string; severidad: string; titulo: string;
                  resultado: string; detalle: string; pasos: any[] }[],
};
function guardar() {
  registro.generado = new Date().toISOString();
  try { fs.writeFileSync(SALIDA, JSON.stringify(registro, null, 1)); } catch { /* sin /reports: no rompe la suite */ }
}
const marker = (accion: string) => `seclab-aaa-${accion}-${Date.now()}`;
function anotar(id: string, rol: string, usuario: string, t0: string, mk: string, status: number) {
  registro.acciones.push({ id, rol, usuario, t0, marker: mk, status });
}

/** Una sonda que este stack/perfil no puede ejecutar. No es un fallo: consta como tal. */
class NoAplica extends Error {}

// UN login crudo por rol y archivo, memorizado como promesa (mismo criterio que lib/auth).
const crudos = new Map<Role, Promise<RawLogin>>();
function loginCrudo(rol: Role): Promise<RawLogin> {
  let p = crudos.get(rol);
  if (!p) {
    p = (async () => {
      const a = adapter();
      if (!a.rawLogin) throw new NoAplica(`el adaptador ${a.name} no expone rawLogin`);
      if (!CREDS[rol].user) throw new NoAplica(`sin credenciales del rol ${rol} (ROLE_${rol}_USER)`);
      const t0 = new Date().toISOString();
      const mk = marker('login');
      const r = await a.rawLogin(CREDS[rol].user, CREDS[rol].pass, { 'User-Agent': mk });
      anotar('login', rol, CREDS[rol].user, t0, mk, r.status);
      if (!r.ok) throw new Error(`el login crudo del rol ${rol} falló: ${r.status} (¿credenciales, limitador?)`);
      return r;
    })();
    crudos.set(rol, p);
  }
  return p;
}

const anonimo = () => pwRequest.newContext({ baseURL: BASE, ignoreHTTPSErrors: true });

const esDenegacion = (status: number, location: string) =>
  [401, 403, 404].includes(status) ||
  (status >= 300 && status < 400 && /login|denied|forbidden|permission|nopermission|accessdenied/i.test(location));

type Respuesta = { status: number; location: string; text: () => Promise<string>; headers: Record<string, string> };
const deRes = (res: any): Respuesta => ({
  status: res.status(), location: res.headers()['location'] ?? '', headers: res.headers(),
  text: () => res.text().catch(() => ''),
});

/** Evalúa `expect` sobre una respuesta. Devuelve la lista de comprobaciones que fallaron. */
async function comprobar(r: Respuesta, exp: Expect | undefined): Promise<string[]> {
  const fallos: string[] = [];
  if (!exp) return fallos;
  let cuerpo: string | null = null;
  const texto = async () => (cuerpo ??= await r.text());
  if (exp.status && !exp.status.includes(r.status)) fallos.push(`esperaba ${exp.status.join('|')}, respondió ${r.status}`);
  if (exp.denegado === true && !esDenegacion(r.status, r.location))
    fallos.push(`esperaba denegación, respondió ${r.status}${r.location ? ` -> ${r.location}` : ''}`);
  if (exp.denegado === false && esDenegacion(r.status, r.location)) fallos.push(`esperaba acceso, respondió ${r.status}`);
  for (const s of exp.body_has ?? []) if (!(await texto()).includes(s)) fallos.push(`el cuerpo no contiene «${s}»`);
  for (const s of exp.body_lacks ?? []) if ((await texto()).includes(s)) fallos.push(`el cuerpo contiene «${s}»`);
  for (const [h, re] of Object.entries(exp.header_has ?? {})) {
    const real = r.headers[h.toLowerCase()] ?? '';
    if (!new RegExp(re, 'i').test(real)) fallos.push(`cabecera ${h}: esperaba /${re}/, hay «${real}»`);
  }
  return fallos;
}

/** Una petición del guion con un contexto dado; `repeat` envíos seguidos, se evalúa el último. */
async function pedir(ctx: any, p: Peticion, token: string | undefined, extra: Record<string, string>) {
  const method = (p.method || 'GET').toUpperCase();
  const url = u(expandVars(p.path));
  const body = p.body !== undefined ? expandDeep(p.body) : undefined;
  const headers: Record<string, string> = {
    ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...expandDeep(p.headers ?? {}),
    ...extra,
  };
  let res: any;
  for (let i = 0; i < Math.max(1, p.repeat ?? 1); i++) {
    res = await ctx.fetch(url, { method, maxRedirects: 0, headers, ...(body !== undefined ? { data: body } : {}) });
  }
  return { res: deRes(res), method, path: expandVars(p.path) };
}

/** Ejecuta una sonda; devuelve las comprobaciones fallidas y rellena `pasos`. Lanza NoAplica. */
async function ejecutar(s: Sonda, pasos: any[]): Promise<string[]> {
  const a = adapter();
  const fallos: string[] = [];
  const paso = (id: string, status: number, esperado: string, fallo: string[]) => {
    pasos.push({ id, status, esperado, ok: fallo.length === 0, detalle: fallo.join(' | ') });
    fallos.push(...fallo.map((f) => `${id}: ${f}`));
  };

  switch (s.tipo) {
    case 'login-fallido': {
      if (!a.rawLogin) throw new NoAplica(`el adaptador ${a.name} no expone rawLogin`);
      const rol: Role = s.rol || 'B';
      if (!CREDS[rol].user) throw new NoAplica(`sin credenciales del rol ${rol}`);
      const t0 = new Date().toISOString();
      const mk = marker('login-fallido');
      const r = await a.rawLogin(CREDS[rol].user, PASS_MALA, { 'User-Agent': mk });
      anotar('login-fallido', rol, CREDS[rol].user, t0, mk, r.status);
      const f: string[] = [];
      if (r.ok) f.push('la contraseña incorrecta ABRIÓ sesión');
      const resp: Respuesta = { status: r.status, location: '', headers: {}, text: async () => r.text ?? '' };
      f.push(...(await comprobar(resp, s.expect)));
      paso('login', r.status, s.expect?.status ? s.expect.status.join('|') : 'sin sesión', f);
      return fallos;
    }
    case 'refresh-como-access': {
      const r = await loginCrudo(s.rol || 'A');
      if (!r.tokens?.refresh) throw new NoAplica(`el stack (${a.name}) no emite refresh token`);
      const ctx = await anonimo();
      const p: Peticion = { method: s.method, path: s.path || (process.env.AUTH_CHECK_PATH || '/'), body: s.body, headers: s.headers };
      const { res, method, path } = await pedir(ctx, p, r.tokens.refresh, {});
      paso(`${method} ${path} con refresh`, res.status, JSON.stringify(s.expect ?? { status: [401] }),
        await comprobar(res, s.expect ?? { status: [401] }));
      return fallos;
    }
    case 'logout-revoca': {
      const rol: Role = s.rol || 'A';
      const r = await loginCrudo(rol);
      if (!a.logout) throw new NoAplica(`el adaptador ${a.name} no expone logout`);
      const t0 = new Date().toISOString();
      const mk = marker('logout');
      const st = await a.logout(r, { 'User-Agent': mk });
      if (st === -1) throw new NoAplica('sin LOGOUT_PATH en el perfil ni ruta de logout fija en este stack');
      anotar('logout', rol, CREDS[rol].user, t0, mk, st);
      paso('logout', st, '2xx|3xx', st >= 400 ? [`el logout respondió ${st}`] : []);
      const p: Peticion = { method: s.method, path: s.path || (process.env.AUTH_CHECK_PATH || '/'), body: s.body, headers: s.headers };
      const { res, method, path } = await pedir(r.ctx, p, undefined, {});
      paso(`${method} ${path} con la credencial vieja`, res.status, JSON.stringify(s.expect ?? { denegado: true }),
        await comprobar(res, s.expect ?? { denegado: true }));
      return fallos;
    }
    case 'anonimo': {
      const ctx = await anonimo();
      for (const p of s.peticiones ?? []) {
        const { res, method, path } = await pedir(ctx, p, undefined, {});
        paso(p.id || `${method} ${path}`, res.status, JSON.stringify(p.expect ?? {}), await comprobar(res, p.expect));
      }
      return fallos;
    }
    case 'peticion': {
      const como = s.as || 'none';
      let ctx: any; let token: string | undefined;
      const extra: Record<string, string> = {};
      const t0 = new Date().toISOString();
      const mk = marker(s.id);
      if (como === 'none') { ctx = await anonimo(); extra['User-Agent'] = mk; }
      else if (como === 'A' || como === 'B') ctx = await loginAs(como);           // sesión memorizada del adaptador
      else if (/^fresh:[AB]$/.test(como)) {
        const rol = como.slice(-1) as Role;
        const r = await loginCrudo(rol);
        if (s.use === 'refresh') {
          if (!r.tokens?.refresh) throw new NoAplica(`el stack (${a.name}) no emite refresh token`);
          ctx = await anonimo(); token = r.tokens.refresh;
        } else ctx = r.ctx;
        extra['User-Agent'] = mk;
      } else throw new Error(`sonda ${s.id}: as=${como} no es none|A|B|fresh:A|fresh:B`);
      const p: Peticion = { method: s.method, path: s.path || '/', body: s.body, headers: s.headers, repeat: s.repeat };
      const { res, method, path } = await pedir(ctx, p, token, extra);
      anotar(s.id, como, como === 'none' ? '' : CREDS[como.slice(-1) as Role]?.user ?? '', t0, mk, res.status);
      paso(`${method} ${path}`, res.status, JSON.stringify(s.expect ?? {}), await comprobar(res, s.expect));
      return fallos;
    }
    case 'limitador': {
      if (!a.rawLogin) throw new NoAplica(`el adaptador ${a.name} no expone rawLogin`);
      const rol: Role = s.rol || 'B';
      if (!CREDS[rol].user) throw new NoAplica(`sin credenciales del rol ${rol}`);
      const n = Math.max(2, s.intentos ?? 11);
      const t0 = new Date().toISOString();
      const mk = marker('limitador');
      const estados: number[] = [];
      let ultimo: RawLogin | undefined;
      for (let i = 0; i < n; i++) {
        ultimo = await a.rawLogin(CREDS[rol].user, PASS_MALA, { 'User-Agent': mk });
        estados.push(ultimo.status);
        if (ultimo.ok) break;
      }
      anotar('limitador', rol, CREDS[rol].user, t0, mk, ultimo?.status ?? 0);
      const resp: Respuesta = { status: ultimo?.status ?? 0, location: '', headers: {}, text: async () => ultimo?.text ?? '' };
      const f = await comprobar(resp, s.expect ?? { status: [429] });
      if (ultimo?.ok) f.push('un intento abrió sesión con la contraseña incorrecta');
      paso(`${n} intentos: ${estados.join(',')}`, ultimo?.status ?? 0, JSON.stringify(s.expect ?? { status: [429] }), f);
      return fallos;
    }
    default:
      throw new Error(`sonda ${s.id}: tipo desconocido «${s.tipo}»`);
  }
}

test.describe('AAA · autenticación', () => {
  test.skip(!doc, `no hay ${GUION} en este perfil — autenticación NO medida (consta como tal)`);
  test.beforeEach(async () => { if (PACE) await new Promise((r) => setTimeout(r, PACE)); });
  test.beforeAll(() => { registro.adaptador = adapter().name; guardar(); });

  for (const s of sondas) {
    const letras = (s.stride || '').replace(/[^STRIDE]/g, '') || '-';
    test(`[authn][stride:${letras}] ${s.id} — ${s.titulo || s.tipo}`, async () => {
      const destructiva = s.destructivo ?? s.tipo === 'limitador';
      const entrada = {
        id: s.id, tipo: s.tipo, pilar: 'authn', stride: letras,
        severidad: s.severidad || 'high', titulo: s.titulo || '',
        resultado: 'no-ejecutada', detalle: '', pasos: [] as any[],
      };
      registro.sondas.push(entrada);
      if (destructiva && !DESTRUCTIVO) {
        entrada.detalle = 'destructiva: AAA_DESTRUCTIVO=0';
        guardar();
        test.skip(true, 'sonda destructiva: AAA_DESTRUCTIVO=0');
      }
      let noAplica: string | null = null;
      let fallos: string[] = [];
      try {
        fallos = await ejecutar(s, entrada.pasos);
      } catch (e: any) {
        if (e instanceof NoAplica) noAplica = e.message;
        else {
          entrada.resultado = 'fail';
          entrada.detalle = String(e?.message ?? e);
          guardar();
          throw e;
        }
      }
      if (noAplica) {
        entrada.resultado = 'no-aplica';
        entrada.detalle = noAplica;
        guardar();
        test.skip(true, `no aplica: ${noAplica}`);
      }
      entrada.resultado = fallos.length ? 'fail' : 'pass';
      entrada.detalle = fallos.join(' | ');
      guardar();
      expect(fallos, fallos.join(' | ')).toEqual([]);
    });
  }
});
