// Perfil de carga de reportes_de_cursos (ZAJUNA Early Alert) — AUTENTICADO y SOLO LECTURA.
//
// AUTENTICADO, que es el punto. Las ocho rutas de /api/v1/reports exigen un JWT DE CURSO: sin él
// responden 401, y un p95 medido sobre 401 describe el muro de autenticación, no la aplicación.
// La sesión la monta `lib/k6/session.js` con el adaptador `zea-standalone` (login.php ->
// token.php -> Bearer).
//
// UN SOLO LOGIN PARA TODA LA PRUEBA, en `setup()`. `login.php` tiene throttle por usuario y por
// barrido de IP (`plugin/classes/local/login_guard.php`): si cada VU se autenticara, esta prueba
// sería un ataque de fuerza bruta contra el login, el guarda entraría y mediríamos el bloqueo.
// Contra el servidor de pruebas, además, dejaría fuera a una cuenta de instructor REAL.
//
// EL JWT DE CURSO DURA 600 s (`plugin/token.php`). La prueba tiene que caber dentro de esa
// ventana: con K6_DURATION por encima de ~9 minutos, las últimas iteraciones medirían 401 de
// token caducado y el informe leería «la API falla bajo carga» cuando lo que caducó fue la
// credencial. Si hace falta una prueba más larga, hay que renovar el token, no subir la duración.
//
// SOLO LECTURA, a propósito. Todo lo que ejecuta son GET de reportes. Quedan EXCLUIDOS a mano:
//   · /api/v1/email/send            envía correo real a aprendices reales
//   · las funciones `send_*` del plugin (send_notification_now, run_notification_test…)
//   · `recreate-analytics-mv.sh`    recrea vistas materializadas sobre la BD compartida
// Repetir cualquiera de esas a varios usuarios concurrentes es un incidente, no una medición.
//
// RAMPA CRECIENTE y DESGLOSE POR ENDPOINT (tags). El agregado miente: en este laboratorio un
// «19% de error» resultó ser UN endpoint roto al 100% mientras el resto iba perfecto. Aquí los
// ocho reportes tienen costes muy distintos —`activity-matrix` y `rap-detail` cruzan matrices por
// aprendiz; `login` lee una vista materializada— así que el p95 agregado no describe a ninguno.
import { check, group, sleep } from 'k6';
import { BASE, login, authedGet, tokenActual, usarToken } from '/seclab-lib/session.js';

const CURSO = __ENV.ZEA_COURSE_A || '';
// Un aprendiz REAL del curso, para los reportes por-aprendiz (learner-*). Sin un userid válido la
// API responde 400 «invalid query parameters: userid» — y ese 400 NO es un fallo del sistema, es
// del guion (la lección de R2: un 19,63% de error resultó ser el guion, no el proyecto). Se
// declara en target.env.local (no es secreto: es un id de usuario de prueba del propio despliegue).
const USERID = __ENV.ZEA_USERID_B || '';

// Las rutas del contrato (docs/api/openapi.json) con los parámetros que CADA UNA exige de verdad,
// leídos de la validación del Go (`internal/reports/*_http.go`, `activity_detail_paged.go`):
//   · login/activity-progress/activity-matrix/learning-outcomes → solo courseid
//   · activity-detail → kind de un conjunto cerrado (evidencias|foros_tematicos|foros_blog|
//     pruebas|encuestas|wikis|scorm); es `omitempty`, así que sin kind también es 200
//   · learner-activity / learner-resources → exigen userid (un aprendiz del curso)
//   · rap-detail → exige `rapid` de un RAP existente; el curso de carga (9708) tiene el catálogo
//     de RAP VACÍO, así que NO se puede ejercitar aquí sin inventar un id. Se DECLARA fuera del
//     perfil de carga: medir un 400 forzado no dice nada del rendimiento del endpoint.
const REPORTES = [
  ['login', `mode=daily&granularity=day`],
  ['activity-progress', ''],
  ['activity-matrix', ''],
  ['activity-detail', 'kind=pruebas'],
  ['learner-activity', USERID ? `userid=${USERID}` : null],
  ['learner-resources', USERID ? `userid=${USERID}` : null],
  ['learning-outcomes', ''],
  // rap-detail: fuera del perfil de carga — requiere un rapid real, ausente en este curso.
];

export const options = {
  scenarios: {
    lectura: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '15s', target: Number(__ENV.K6_VUS || 10) },
        { duration: __ENV.K6_DURATION || '30s', target: Number(__ENV.K6_VUS || 10) },
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

export function setup() {
  const ok = login('A');
  const t = tokenActual();
  if (!ok || !t) {
    // Abortar es lo correcto: sin token, las 8 rutas devolverían 401 y el resumen diría
    // «100% de error» como si la aplicación estuviera rota. Un fallo de credenciales tiene que
    // parecer un fallo de credenciales.
    throw new Error(
      'no se obtuvo JWT de curso para el rol A: revisa ROLE_A_USER/PASS y ZEA_COURSE_A ' +
        '(un 403 en token.php significa que esa cuenta no tiene viewreports en ese curso)',
    );
  }
  return { token: t, curso: CURSO };
}

export default function (data) {
  usarToken(data.token);
  group('reportes', () => {
    for (const [ruta, extra] of REPORTES) {
      if (extra === null) continue; // reporte por-aprendiz sin ZEA_USERID_B declarado: se omite
      const q = `courseid=${encodeURIComponent(data.curso)}${extra ? '&' + extra : ''}`;
      const r = authedGet(`/zea-api/api/v1/reports/${ruta}?${q}`, ruta);
      check(r, {
        [`${ruta}: 200`]: (x) => x.status === 200,
        // Un 401 aquí no es «la API falla»: es el token caducado. Se distingue para que el
        // triaje no confunda una credencial vencida con un fallo del servicio.
        [`${ruta}: no es 401 de token caducado`]: (x) => x.status !== 401,
      });
      sleep(0.3);
    }
  });
  sleep(1);
}
