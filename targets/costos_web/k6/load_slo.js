// LOAD — validación contra el SLO objetivo (gate pass/fail).
//
// SLO declarado (supuesto explícito, revisable): con el universo de 20.368 usuarios y
// uso concentrado en la ventana de apertura de costos, se exige soportar
//   200 usuarios concurrentes · p95 < 1500 ms · p99 < 3000 ms · error < 1% · >= 50 req/s
// Perfil de uso mixto (una jornada realista, no un solo endpoint).
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';
import { login, authedGet } from './lib/session.js';

const TARGET = parseInt(__ENV.TARGET_VUS || '200', 10);

const tListado = new Trend('t_listado', true);
const tCatalogo = new Trend('t_catalogo', true);

export const options = {
  scenarios: {
    jornada: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '1m', target: TARGET },   // rampa
        { duration: '5m', target: TARGET },   // meseta: aquí se juzga el SLO
        { duration: '30s', target: 0 },
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    'http_req_failed': ['rate<0.01'],                       // < 1% error
    'http_req_duration': ['p(95)<1500', 'p(99)<3000'],      // SLO de latencia
    't_listado': ['p(95)<1500'],
    'http_reqs': ['rate>50'],                               // throughput mínimo
  },
};

let authed = false;

export default function () {
  if (!authed) authed = login('admin');

  // Jornada típica: consultar el listado y algunos catálogos.
  const r1 = authedGet('/api/usuarios?per_page=10', 'usuarios_pag');
  tListado.add(r1.timings.duration);
  check(r1, { 'listado 200': (r) => r.status === 200 });

  const r2 = authedGet('/api/regionales', 'regionales');
  tCatalogo.add(r2.timings.duration);
  check(r2, { 'catalogo 200': (r) => r.status === 200 });

  sleep(1); // think time
}
