// Perfil de carga de local_portafolio — AUTENTICADO y SOLO LECTURA.
//
// AUTENTICADO, que es el punto. Todas las páginas del plugin llaman a
// local_portafolio_require_login() como primera instrucción: sin sesión responden 303 a
// login/index.php. Un p95 medido sobre ese 303 describe la redirección, no el plugin. La sesión
// la monta lib/k6/session.js con el adaptador `moodle-session` (logintoken -> cookie MoodleSession).
//
// UN LOGIN POR VU, NO POR ITERACIÓN. Moodle NO limita la navegación, pero SÍ hace throttling de
// intentos de login. Si cada iteración se autenticara, con la rampa esto sería un ataque de fuerza
// bruta contra el login del core COMPARTIDO —el mismo que usan #1/#2/#3/#6— y mediríamos el
// limitador, no las páginas (lección de #6, defecto L-R5-c: k6 sobre un endpoint rate-limitado dio
// «90% error» que era el limitador). Con K6_VUS=5 son 5 logins en toda la prueba: navegación, no
// fuerza bruta. El flag `identificado` es módulo-por-VU en k6, así que cada VU entra una vez.
//
// SOLO LECTURA, a propósito: solo GET. El plugin no tiene endpoints de escritura propios, pero
// aun así se listan EXPLÍCITAMENTE las rutas ejercitadas para que el alcance de la carga se vea:
// ninguna de estas modifica estado.
//
// DESGLOSE POR PÁGINA (tags), NO AGREGADO. El agregado miente: en este laboratorio un «19% de
// error» resultó ser UN endpoint roto al 100% mientras el resto iba perfecto. Aquí las páginas
// tienen costes muy distintos —`resultados` cruza la BD externa `integracion`; `index` solo lista
// cursos matriculados— así que el p95 agregado no describe a ninguna.
//
// SOBRE ESTE DESPLIEGUE LOCAL: los cursos demo (23535/23536) tienen 0 calificaciones y sin FIC_ID,
// así que `resultados`/`actividades` devuelven vistas vacías pero 200 — se mide el COSTE DE RENDER
// del plugin, no el de los datos. La carga con datos reales solo se puede medir contra el servidor
// del equipo, y ahí NO se lanza k6 (no controlamos ese servidor). Se declara en el informe.
import { check, group, sleep } from 'k6';
import { BASE, login, authedGet } from '/seclab-lib/session.js';

// El prefijo bajo el que vive Moodle en este host: el core Zajuna se sirve en `/zajuna`. Va
// delante de TODAS las rutas del plugin y del login. BASE_URL no puede llevarlo porque
// require-live construye ${BASE_URL}${HEALTH_PATH} y HEALTH_PATH ya incluye /zajuna — duplicarlo
// daría /zajuna/zajuna. Por eso el prefijo es una variable propia, igual que ZEA_MOODLE_BASE.
const MB = __ENV.MOODLE_BASE || '';

// El curso demo donde demo_apr_01 está matriculado (leído de mdl_user_enrolments, no inventado).
const CURSO = __ENV.PORTAFOLIO_COURSE || '23535';

// Las páginas del plugin con los parámetros que cada una exige de verdad, leídos del código:
//   · index/cursos           sin parámetros (contexto de sistema)
//   · las de tipo actividad   courseid (contexto de curso; require_capability :use)
// Se excluye voice.php: exige `id` de una grabación concreta, que este curso demo no tiene —
// forzar un id daría un 404 que es del guion, no del plugin (lección de R2).
const PAGINAS = [
  ['index', `${MB}/local/portafolio/index.php`],
  ['cursos', `${MB}/local/portafolio/cursos.php`],
  ['view', `${MB}/local/portafolio/view.php?courseid=${CURSO}`],
  ['actividades', `${MB}/local/portafolio/actividades.php?courseid=${CURSO}`],
  ['pendientes', `${MB}/local/portafolio/pendientes.php?courseid=${CURSO}`],
  ['resultados', `${MB}/local/portafolio/resultados.php?courseid=${CURSO}`],
  ['evidencias', `${MB}/local/portafolio/evidencias.php?courseid=${CURSO}`],
  ['logros', `${MB}/local/portafolio/logros.php?courseid=${CURSO}`],
  ['quiz', `${MB}/local/portafolio/quiz.php?courseid=${CURSO}`],
  ['foros', `${MB}/local/portafolio/foros.php?courseid=${CURSO}`],
  ['scorm', `${MB}/local/portafolio/scorm.php?courseid=${CURSO}`],
];

export const options = {
  scenarios: {
    lectura: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '15s', target: Number(__ENV.K6_VUS || 5) },
        { duration: __ENV.K6_DURATION || '60s', target: Number(__ENV.K6_VUS || 5) },
        { duration: '10s', target: 0 },
      ],
      gracefulRampDown: '10s',
    },
  },
  // Umbrales informativos: el veredicto lo da `make gate` con K6_P95_MS y K6_ERR_RATE del perfil,
  // fijados DESPUÉS de esta primera corrida, con las cifras reales delante.
  thresholds: {
    http_req_failed: ['rate<0.10'],
  },
};

let identificado = false;

export default function () {
  // Login una vez por VU. `login()` deja la cookie MoodleSession en el jar del módulo, que en k6
  // es por-VU, así que las peticiones siguientes de este VU van autenticadas.
  if (!identificado) {
    const ok = login('B'); // rol B = privilegio bajo (aprendiz demo_apr_01)
    if (!ok) {
      // Sin sesión, las 11 páginas redirigirían a login (303) y el resumen diría «100% de error»
      // como si el plugin estuviera roto. Un fallo de credenciales tiene que parecerlo.
      throw new Error(
        'no se inició sesión con el rol B: revisa ROLE_B_USER/PASS en target.env.local ' +
          '(demo_apr_01 / DemoAntiplagio2026#, verificadas contra el core el 2026-08-25)',
      );
    }
    identificado = true;
  }

  group('portafolio', () => {
    for (const [nombre, ruta] of PAGINAS) {
      const r = authedGet(ruta, nombre);
      check(r, {
        [`${nombre}: 200`]: (x) => x.status === 200,
        // Un 303 aquí significa que la sesión se perdió: se distingue para que el triaje no lo
        // confunda con un fallo de rendimiento de la página.
        [`${nombre}: no es 303 (sesión perdida)`]: (x) => x.status !== 303,
      });
      sleep(0.3);
    }
  });
  sleep(1);
}
