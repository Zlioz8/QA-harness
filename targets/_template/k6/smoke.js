// Humo de carga de __TARGET__: ¿la aplicación responde y el guion sigue hablando su idioma?
// Es lo que corre `make perf`. UN usuario y UN login: si la aplicación limita el login, varios
// usuarios virtuales iniciando sesión miden el limitador, no la aplicación.
//
// Sustituye las rutas por las de TU aplicación. Para saber cuáles pide de verdad, no leas un
// documento: mira el log de acceso de un despliegue que alguien haya usado.
import { check, sleep } from 'k6';
import { login, authedGet } from '/seclab-lib/session.js';
import { opciones, resumen } from '/seclab-lib/carga.js';

const ENDPOINTS = ['salud'];
export const options = opciones(ENDPOINTS);

export function setup() {
  if (!login('A')) throw new Error('login fallido — revisa BASE_URL, AUTH_ADAPTER y las cuentas del perfil');
}

let dentro = false;
export default function () {
  if (!dentro) dentro = login('A');
  const r = authedGet(__ENV.HEALTH_PATH || '/', 'salud');
  check(r, { 'salud 200': (x) => x.status === 200 });
  sleep(1);
}

export function handleSummary(data) {
  return resumen(data, { guion: 'smoke.js' });
}
