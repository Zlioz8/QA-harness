// Perfil de carga de ADI — AUTENTICADO, que es el punto.
//
// Sin iniciar sesión, cada ruta de ADI responde con una redirección al login: un p95 medido
// así describe la pantalla de acceso, no la aplicación. Se autentica con el rol A a través de
// lib/k6/session.js (adaptador `php-form`, el mismo que usa Playwright).
//
// SOLO LECTURA, a propósito. Se excluyen todos los `/store`, `/update` y `/delete`: el objetivo
// es un entorno de validación compartido, y `/adi/scripts/store` escribe cronjobs que se
// ejecutan por SSH en otro servidor. Una prueba de carga que descubre eso a 10 usuarios
// concurrentes es un incidente, no una medición.
//
// Tampoco se toca /adi/analysis/query: ejecuta consultas de análisis contra newintegracion, y
// repetirlas bajo carga mide la base de datos de integración de otro equipo.
import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { BASE, jar, login } from '/seclab-lib/session.js';

export const options = {
  scenarios: {
    pantallas: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '10s', target: Number(__ENV.K6_VUS || 10) },
        { duration: __ENV.K6_DURATION || '30s', target: Number(__ENV.K6_VUS || 10) },
        { duration: '10s', target: 0 },
      ],
      gracefulRampDown: '10s',
    },
  },
  // Umbrales informativos: el veredicto lo da `make gate` con K6_P95_MS y K6_ERR_RATE del
  // perfil, para que el tablero y el pipeline no puedan discrepar.
  thresholds: {
    http_req_failed: ['rate<0.10'],
  },
};

// Una sesión por usuario virtual, no una por iteración: ADI bloquea la IP tras 5 intentos
// fallidos durante 15 minutos ("ADI".login_attempts), y autenticar en cada iteración agota ese
// contador en segundos — la carga se autodeniega y el informe lo pinta como fallo de la app.
export function setup() {
  return {};
}

let autenticado = false;

export default function () {
  if (!autenticado) {
    check(login('A'), { 'sesion iniciada': (x) => x === true });
    autenticado = true;
  }

  group('pantallas de lectura', () => {
    for (const ruta of ['/adi/home', '/adi/users', '/adi/logs', '/adi/seeds', '/adi/notes']) {
      const r = http.get(`${BASE}${ruta}`, { jar, tags: { endpoint: ruta } });
      check(r, { [`${ruta} 200`]: (x) => x.status === 200 });
      sleep(0.5);
    }
  });
}
