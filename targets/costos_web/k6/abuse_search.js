// BÚSQUEDA — el filtro usa `ILIKE '%valor%'` sobre nombre_completo, numero_documento
// y ldap. Un comodín inicial impide usar índice B-tree: PostgreSQL hace recorrido
// secuencial de las 20.368 filas en CADA petición. Mide ese coste bajo carga.
import { check } from 'k6';
import { Trend } from 'k6/metrics';
import { login, authedGet } from './lib/session.js';

const tBuscar = new Trend('t_buscar', true);
const TERM = __ENV.SEARCH_TERM || 'a';

export const options = {
  scenarios: {
    busqueda: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '30s', target: 50 },
        { duration: '1m',  target: 50 },
        { duration: '15s', target: 0 },
      ],
    },
  },
  thresholds: {},
};

let authed = false;

export default function () {
  if (!authed) authed = login('admin');
  const res = authedGet(`/api/usuarios?per_page=10&buscar=${TERM}`, 'usuarios_buscar');
  tBuscar.add(res.timings.duration);
  check(res, { 'buscar 200': (r) => r.status === 200 });
}
