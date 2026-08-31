// Perfil de carga de mod_imagecarousel — SOLO LECTURA, autenticado con sesión de Moodle.
//
// QUÉ MIDE. La latencia de las rutas de LECTURA del plugin dentro de un curso, con una sesión
// real de student. No es una prueba de saturación: el blanco es el core Zajuna COMPARTIDO por
// otros tres proyectos (#2, #3, #6) y una prueba de estrés lo degradaría para todos. Mide la
// latencia base de:
//   · view.php               la vista individual de la actividad
//   · carousel_content.php   el fetch() que rellena el carrusel embebido (requiere sesskey)
//   · course/view.php        la página del curso que embebe la actividad
//
// AUTENTICADO, y por qué se puede aquí y no en encuestas: este plugin usa la sesión NATIVA de
// Moodle (require_login), y en el core LOCAL el login por usuario/contraseña SÍ funciona
// (verificado: demo_apr_01 inicia sesión y obtiene sesskey). Sin sesión, view.php redirige (303)
// y carousel_content.php exige sesskey — medir eso daría la latencia del muro de auth, no del
// plugin. El login se hace UNA vez en setup() y se reutiliza la cookie.
//
// SOLO LECTURA, sin escritura: NUNCA se tocan adding_image.php (INSERT), edit.php (UPDATE),
// delete.php (DELETE) ni manage.php?action=... (UPDATE). Un /store bajo carga es un incidente,
// no una medición (METODOLOGÍA §3).
//
// RATE-LIMIT: el core Moodle no impone throttle por ruta a las páginas del plugin, pero si
// apareciera un 429 se marca como ESPERADO (200-499) para no leer el limitador como fallo de la
// app (lección #6). Umbral de error sólo sobre 5xx reales.
//
// UN SOLO VU a ritmo bajo: latencia base honesta, cero riesgo para la base compartida.

import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE = __ENV.BASE_URL || 'https://nginx.zajuna.com/zajuna';
const CMID = __ENV.IC_CMID || '73985';
const COURSEID = __ENV.IC_COURSEID || '23535';
const USER = __ENV.LOCAL_ROLE_BAJO_USER || 'demo_apr_01';
const PASS = __ENV.LOCAL_ROLE_BAJO_PASS || 'DemoAntiplagio2026#';

export const options = {
  scenarios: {
    latencia_base: { executor: 'constant-vus', vus: 1, duration: __ENV.K6_DURATION || '30s' },
  },
  insecureSkipTLSVerify: true, // cert autofirmado del core local (ver target.env)
  thresholds: {
    // p95 de LECTURA; error sólo sobre 5xx reales (un 429/403 no es fallo de la app).
    http_req_duration: ['p(95)<1500'],
    checks: ['rate>0.95'],
  },
};

// setup(): login nativo de Moodle (logintoken -> POST) y devuelve las cookies + sesskey.
export function setup() {
  const r1 = http.get(`${BASE}/login/index.php`);
  const m = r1.body.match(/name="logintoken" value="([^"]+)"/);
  const logintoken = m ? m[1] : '';
  const r2 = http.post(`${BASE}/login/index.php`, {
    username: USER, password: PASS, logintoken: logintoken,
  }, { redirects: 5 });
  const my = http.get(`${BASE}/my/`);
  const sk = (my.body.match(/"sesskey":"([^"]+)"/) || [])[1] || '';
  return { sesskey: sk, ok: my.body.includes('sesskey') };
}

export default function (data) {
  const sk = data.sesskey;

  const view = http.get(`${BASE}/mod/imagecarousel/view.php?id=${CMID}`);
  check(view, { 'view.php no es 5xx': (r) => r.status < 500 });

  const content = http.get(`${BASE}/mod/imagecarousel/carousel_content.php?cmid=${CMID}&sesskey=${sk}`);
  check(content, {
    'carousel_content no es 5xx': (r) => r.status < 500,
    'carousel_content sirve HTML con sesión': (r) => r.status === 200,
  });

  const course = http.get(`${BASE}/course/view.php?id=${COURSEID}`);
  check(course, { 'course/view no es 5xx': (r) => r.status < 500 });

  sleep(2); // ritmo bajo: latencia base, no saturación del core compartido
}
