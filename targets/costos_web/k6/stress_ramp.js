// STRESS — rampa escalonada hasta degradar. Busca el PUNTO DE QUIEBRE.
//
// No lleva thresholds que aborten: el objetivo es precisamente pasar del punto de
// fallo y registrar la curva. Cada escalón queda etiquetado para poder decir
// "a N VUs la tasa de error cruzó 1% / 5% y p95 se disparó".
import { check } from 'k6';
import { Trend, Rate } from 'k6/metrics';
import { login, authedGet } from './lib/session.js';

const tListado = new Trend('t_listado', true);
const errores = new Rate('errores');

export const options = {
  scenarios: {
    rampa: {
      executor: 'ramping-vus',
      startVUs: 10,
      stages: [
        { duration: '30s', target: 50 },
        { duration: '1m',  target: 50 },
        { duration: '30s', target: 100 },
        { duration: '1m',  target: 100 },
        { duration: '30s', target: 200 },
        { duration: '1m',  target: 200 },
        { duration: '30s', target: 400 },
        { duration: '1m',  target: 400 },
        { duration: '30s', target: 800 },
        { duration: '1m',  target: 800 },
        { duration: '30s', target: 0 },
      ],
      gracefulRampDown: '20s',
    },
  },
  // Sin gates: queremos observar la rotura, no abortar en ella.
  thresholds: {},
};

let authed = false;

export default function () {
  if (!authed) authed = login('admin');
  const res = authedGet('/api/usuarios?per_page=10', 'usuarios_pag');
  tListado.add(res.timings.duration);
  errores.add(res.status !== 200);
  check(res, { 'listado 200': (r) => r.status === 200 });
}
