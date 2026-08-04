// Carga minima sobre las DOS puertas de entrada del sistema, sin sesion.
//
// Que mide y que no: sin login no se ejerce el analisis (que es asincrono via Kafka y no
// devuelve latencia de usuario), asi que esto NO es una prueba del pipeline. Mide lo que
// cualquiera puede pedir sin credenciales, que es exactamente la superficie que un atacante
// puede saturar: la pantalla de login de Moodle, /health de la API, y get_lines.php — el
// endpoint del plugin que responde 200 sin sesion y por tanto es carga gratuita para
// cualquiera con la URL.
import http from 'k6/http';
import { check, group } from 'k6';

const BASE = __ENV.BASE_URL;           // http://moodle:8080 dentro de la red del compose
const API = __ENV.API_INTERNAL_URL || 'http://api:8030';

if (!BASE) {
  throw new Error('BASE_URL vacio: sin objetivo, fallar. Un smoke contra "undefined" sale verde.');
}

export const options = {
  scenarios: {
    constante: {
      executor: 'constant-vus',
      vus: 10,
      duration: '30s',
    },
  },
  thresholds: {
    // Los mismos umbrales declarados en target.env (K6_P95_MS / K6_ERR_RATE), escritos aqui
    // para que k6 falle por si mismo y no solo en el gate.
    http_req_duration: ['p(95)<3000'],
    http_req_failed: ['rate<0.02'],
  },
};

export default function () {
  group('moodle login', () => {
    const r = http.get(`${BASE}/login/index.php`);
    check(r, { 'login 200': (res) => res.status === 200 });
  });

  group('api health', () => {
    const r = http.get(`${API}/health`);
    check(r, { 'health 200': (res) => res.status === 200 });
  });

  group('plugin get_lines sin sesion', () => {
    const r = http.get(`${BASE}/local/antiplagiarsena/get_lines.php?activityid=1`);
    check(r, { 'responde': (res) => res.status === 200 || res.status === 303 });
  });
}
