// La carga realista de Zajuna Móvil: N personas usando la app a la vez (modelo.js).
// La forma la pone CARGA_TIPO (lib/k6/carga.js); la conduce `make perf-escalera TARGET=movil`.
import { opciones, resumen, VUS } from '/seclab-lib/carga.js';
import { ENDPOINTS, abrirSesiones, unGesto } from './modelo.js';

export const options = opciones(ENDPOINTS);

export function setup() {
  // Una sesión por persona, abierta ANTES de medir: el login es raro en el uso real y aquí
  // contaminaría la rampa. Su propia prueba es pico-login.js.
  return { sesiones: abrirSesiones(VUS), t0: Date.now() };
}

export default function (data) {
  unGesto(data);
}

export function handleSummary(data) {
  return resumen(data, { guion: 'sesion.js', modelo: 'tráfico grabado 2026-09-24..29' });
}
