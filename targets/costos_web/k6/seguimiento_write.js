// SEGUIMIENTO — `GET /api/seguimiento-representantes` NO es de solo lectura:
// `index()` llama a `sincronizarSeguimientos()`, que recorre a todos los
// representantes con `firstOrCreate` (escrituras), y luego arma la respuesta con una
// consulta por grupo dentro de `map` (N+1).
//
// Mide el coste de un GET que escribe, bajo concurrencia moderada.
import { check } from 'k6';
import { Trend } from 'k6/metrics';
import { login, authedGet } from './lib/session.js';

const tSeg = new Trend('t_seguimiento', true);

export const options = {
  scenarios: {
    seguimiento: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '30s', target: 20 },
        { duration: '1m',  target: 20 },
        { duration: '15s', target: 0 },
      ],
    },
  },
  thresholds: {},
};

let authed = false;

export default function () {
  if (!authed) authed = login('admin');
  const res = authedGet('/api/seguimiento-representantes', 'seguimiento');
  tSeg.add(res.timings.duration);
  check(res, { 'seguimiento 200': (r) => r.status === 200 });
}
