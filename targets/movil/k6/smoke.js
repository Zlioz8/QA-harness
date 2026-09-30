// Humo de Zajuna Móvil: ¿la API responde y el modelo de carga sigue hablando su idioma?
// UNA persona (la cuenta de aprendiz del perfil), UN login, un recorrido de la app. Es lo que
// corre `make perf`; la carga de verdad es sesion.js con `make perf-escalera`.
//
// Un solo login a propósito: /auth/login admite 10 por minuto e IP.
import { sleep } from 'k6';
import { opciones, resumen } from '/seclab-lib/carga.js';
import * as M from './modelo.js';

export const options = opciones(M.ENDPOINTS);

export function setup() {
  const s = M.entrar({ usuario: __ENV.ROLE_B_USER, clave: __ENV.ROLE_B_PASS });
  if (!s) throw new Error(`login fallido contra ${__ENV.BASE_URL} — revisa BASE_URL y la cuenta ROLE_B del perfil`);
  return { s };
}

export default function (data) {
  if (!M.tieneSesion()) {
    M.usar({ usuario: __ENV.ROLE_B_USER }, { ...data.s });
    M.arranque();
  }
  for (const f of [M.abrirCurso, M.calificaciones, M.calendario, M.notificaciones, M.evidencia, M.inicio]) {
    f();
    sleep(1);
  }
}

export function handleSummary(data) {
  return resumen(data, { guion: 'smoke.js' });
}
