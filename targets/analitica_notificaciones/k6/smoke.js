// Perfil de carga de analitica_notificaciones (Reportes ZAJUNA) — AUTENTICADO y SOLO LECTURA.
//
// AUTENTICADO, que es el punto. Todo /api/reportes, /api/solicitudes y /api/programados exige
// sesión (Depends CurrentUser): sin token responden 401, y un p95 medido sobre 401 describe el
// muro de autenticación, no la aplicación. Se inicia sesión con el rol A (admin_slider) por
// lib/k6/session.js, adaptador `jwt-bearer` — POST /api/auth/moodle-login {username,password}
// -> {access_token}, que viaja como Authorization: Bearer. Comprobado vivo: A da 200.
//
// (Nota medida: el rol B, comunidades1, NO obtiene token — Moodle responde 401 "sin permiso
// para el web service reportes_zajuna". La carga usa por eso solo el rol A; la asimetría de
// privilegio es cosa de la matriz de Playwright, no de la medición de rendimiento.)
//
// SOLO LECTURA, a propósito y por seguridad del sistema medido. Se EXCLUYEN:
//   POST /api/reportes/{codigo}/generar   encola un trabajo pesado (RQ worker) que corre una
//   POST /api/reportes/{codigo}/preview    consulta real contra la BD de Moodle de producción.
// Repetir eso a varios usuarios concurrentes es un incidente contra un servidor compartido, no
// una medición. Además su latencia mediría la profundidad de la cola del worker, no la API.
//
// RAMPA CRECIENTE (no un escalón): con carga autorizada contra producción, subir por tramos deja
// ver la degradación en cuanto empieza, en vez de descubrirla al final. El desglose por endpoint
// (tags) importa más que el agregado: en este laboratorio un "19% de error" resultó ser UN
// endpoint roto al 100% mientras el resto iba perfecto. El agregado habría mentido.
import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { BASE, jar, login, authedGet } from '/seclab-lib/session.js';

const CODIGOS = [
  'fichas_programas', 'ingresos_sistema', 'matriculas_lms', 'participacion_herramientas',
  'registro_usuarios', 'sesiones_online', 'tiempo_permanencia', 'trafico_diario',
  'uso_herramientas', 'usuarios_ambiente',
];

export const options = {
  scenarios: {
    lectura: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '15s', target: Number(__ENV.K6_VUS || 8) },
        { duration: __ENV.K6_DURATION || '40s', target: Number(__ENV.K6_VUS || 8) },
        { duration: '10s', target: 0 },
      ],
      gracefulRampDown: '10s',
    },
  },
  // Umbrales informativos: el veredicto lo da `make gate` con K6_P95_MS y K6_ERR_RATE del perfil,
  // que se fijan DESPUÉS de esta primera corrida, con las cifras reales delante.
  thresholds: {
    http_req_failed: ['rate<0.10'],
  },
};

let autenticado = false;

export default function () {
  if (!autenticado) {
    check(login('A'), { 'sesion iniciada (rol A)': (x) => x === true });
    autenticado = true;
  }

  // /api/health no necesita sesión, pero se mide igual: es el pulso, y su latencia bajo carga
  // separa "la app está saturada" de "una consulta concreta es lenta".
  group('salud y catálogo', () => {
    let r = http.get(`${BASE}/api/health`, { jar, tags: { endpoint: '/api/health' } });
    check(r, { 'health 200': (x) => x.status === 200 });
    r = authedGet('/api/reportes', '/api/reportes');
    check(r, { 'catálogo 200': (x) => x.status === 200 });
    sleep(0.5);
  });

  // Los filtros de cada reporte SÍ tocan la BD de Moodle (hidratan opciones dinámicas:
  // categorías, regionales, roles). Es lectura, y es justo la lectura representativa de lo que
  // hace un usuario antes de generar. Un código por iteración, rotando, para repartir la carga.
  group('filtros de un reporte', () => {
    const codigo = CODIGOS[Math.floor(Math.random() * CODIGOS.length)];
    const r = authedGet(`/api/reportes/${codigo}/filtros`, '/api/reportes/{codigo}/filtros');
    check(r, { 'filtros 200': (x) => x.status === 200 });
    sleep(0.5);
  });

  group('mis solicitudes', () => {
    const r = authedGet('/api/solicitudes', '/api/solicitudes');
    check(r, { 'solicitudes 200': (x) => x.status === 200 });
    sleep(0.5);
  });
}
