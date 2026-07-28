// ABUSO DE PARÁMETROS — `per_page` no tiene tope en UsuariosController::index
// (`$request->input('per_page', 10)`), así que un cliente puede pedir la tabla
// completa y evadir la paginación. Con 20.368 filas y memory_limit real, esto debe
// reproducir el agotamiento de memoria (500) que la paginación supuestamente cerró.
//
// Poca concurrencia a propósito: se trata de demostrar que UNA petición basta.
import http from 'k6/http';
import { check } from 'k6';
import { Trend, Rate } from 'k6/metrics';
import { login, jar, BASE, ORIGIN } from './lib/session.js';

const tAbuso = new Trend('t_abuso', true);
const err5xx = new Rate('errores_5xx');

const PER_PAGE = __ENV.ABUSE_PER_PAGE || '999999';

export const options = {
  vus: parseInt(__ENV.ABUSE_VUS || '5', 10),
  duration: __ENV.ABUSE_DURATION || '1m',
  thresholds: {},
};

let authed = false;

export default function () {
  if (!authed) authed = login('admin');

  const res = http.get(`${BASE}/api/usuarios?per_page=${PER_PAGE}`, {
    jar,
    headers: { Origin: ORIGIN },
    tags: { endpoint: 'usuarios_abuso' },
    timeout: '120s',
  });

  tAbuso.add(res.timings.duration);
  err5xx.add(res.status >= 500);
  check(res, {
    'no 5xx (si falla, la paginación es evadible)': (r) => r.status < 500,
  });
}
