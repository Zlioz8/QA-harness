// SESIONES COMPARTIDAS Y RITMO — para no medir el limitador de la aplicación en vez de su
// autorización.
//
// Costos Web protege el acceso con `throttle:login` (10 intentos por minuto y por email+IP,
// que es la corrección que pidió R5 §3.1) y las rutas autenticadas con `throttle:60,1`. Una
// suite que inicia sesión en cada prueba dispara ambos: a partir del intento 11 el login
// devuelve 429, y la comprobación se apunta como "acceso denegado" cuando lo único que pasó
// es que el laboratorio se atropelló a sí mismo. Se reportaban 59 fallos de autorización
// inexistentes.
//
// Dos medidas:
//   1. La sesión de cada cuenta se guarda en disco y la comparten TODOS los archivos de prueba
//      (Playwright aísla los módulos por archivo, así que memorizar en memoria no basta).
//   2. `pausa()` espacia las peticiones para no rebasar las 60 por minuto de un mismo usuario.
import { APIRequestContext, request as pwRequest } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

// Sin BASE_URL no hay objetivo. Fallar aquí es más honesto que traer un valor por defecto:
// una dirección incrustada sobrevive al despliegue que la motivó y acaba midiendo el
// servidor equivocado en verde. Se declara en targets/costos_web/target.env.local.
const BASE = process.env.BASE_URL || '';
if (!BASE) throw new Error('BASE_URL no declarado — ver targets/costos_web/target.env.local.example');
const ORIGIN = process.env.ALLOWED_ORIGIN || BASE;
const DIR = '/tmp/seclab-sesiones';

// Cabeceras que envía el SPA real. `Accept: application/json` es indispensable: sin ella
// Laravel responde a una petición no autenticada con un 302 al login en vez de un 401, y la
// matriz no puede distinguir "denegado" de "redirigido a una página que existe".
const CABECERAS = { Origin: ORIGIN, Referer: `${BASE}/`, Accept: 'application/json' };

const enMemoria = new Map<string, Promise<APIRequestContext>>();

function nuevoCtx(storageState?: string) {
  return pwRequest.newContext({
    baseURL: BASE,
    extraHTTPHeaders: CABECERAS,
    ignoreHTTPSErrors: true,
    ...(storageState ? { storageState } : {}),
  });
}

async function tokenDe(ctx: APIRequestContext): Promise<string> {
  const st = await ctx.storageState();
  return decodeURIComponent(st.cookies.find((c) => c.name === 'XSRF-TOKEN')?.value ?? '');
}

async function iniciar(user: string, pass: string): Promise<APIRequestContext> {
  fs.mkdirSync(DIR, { recursive: true });
  const archivo = path.join(DIR, `${Buffer.from(user).toString('hex')}.json`);

  // SESSION_LIFETIME del proyecto son 15 minutos; se reutiliza si es más reciente que 10.
  if (fs.existsSync(archivo) && Date.now() - fs.statSync(archivo).mtimeMs < 10 * 60_000) {
    const ctx = await nuevoCtx(archivo);
    const yo = await ctx.get('/api/me');
    if (yo.status() === 200) return ctx;
  }

  const ctx = await nuevoCtx();
  await ctx.get('/sanctum/csrf-cookie');
  const res = await ctx.post('/api/login', {
    headers: { 'X-XSRF-TOKEN': await tokenDe(ctx), 'Content-Type': 'application/json' },
    data: { email: user, password: pass },
  });
  if (res.status() !== 200) throw new Error(`login ${user} -> ${res.status()}`);
  await ctx.storageState({ path: archivo });
  return ctx;
}

/** Sesión autenticada de una cuenta, compartida entre pruebas y entre archivos. */
export function sesionDe(user: string, pass: string): Promise<APIRequestContext> {
  let s = enMemoria.get(user);
  if (!s) {
    s = iniciar(user, pass);
    enMemoria.set(user, s);
  }
  return s;
}

/** Cabeceras de escritura (CSRF) para la sesión dada. */
export async function cabecerasEscritura(ctx: APIRequestContext): Promise<Record<string, string>> {
  return { 'X-XSRF-TOKEN': await tokenDe(ctx), 'Content-Type': 'application/json' };
}

/** Espaciado entre peticiones para no rebasar `throttle:60,1` del mismo usuario. */
export const pausa = (ms = 1100) => new Promise((r) => setTimeout(r, ms));

export { BASE, ORIGIN };
