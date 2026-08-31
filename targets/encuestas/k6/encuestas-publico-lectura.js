// Perfil de carga de encuestas — SOLO LECTURA y sobre la superficie PÚBLICA.
//
// POR QUÉ PÚBLICA Y NO AUTENTICADA, y es una limitación honesta, no una comodidad:
//
//   La sesión de las rutas autenticadas se obtiene SOLO por el SSO de Zajuna (Moodle acuña un
//   pase HMAC, la SPA lo canjea en /api/auth/zajuna por un token Sanctum). NO hay login por
//   usuario/contraseña para las cuentas de la fábrica: `AuthService::login` hace `Auth::attempt`
//   contra la tabla `users` de la aplicación, donde las cédulas de Moodle no tienen contraseña.
//   Y el SSO web está bloqueado en zajunavideo5 por el rebote de `login/index.php` a caplms.
//   => k6 no puede acuñar una sesión aquí. Medir /api/surveys daría 401 a 100 %, y un p95 sobre
//   401 describe el muro de auth, no la aplicación (lección de reportes_de_cursos).
//
//   Cuando el despliegue LOCAL esté arriba y se pueda inyectar un token Sanctum obtenido por SSO
//   una sola vez, este guion admite BEARER_TOKEN por entorno y añade las rutas autenticadas de
//   lectura. Mientras tanto mide lo que SÍ es alcanzable y real: la superficie pública.
//
// LAS RUTAS SON LAS PÚBLICAS DE `routes/api.php` (fuera del grupo auth:sanctum), y SOLO los GET:
//   · contact-info               lectura simple, la ruta de salud
//   · surveys/{id}/public-details  valida existencia (da 404 «Survey not found» si no está)
//   · survey-themes/survey/{id}   tema de la encuesta
//   · storage/images/{filename}  servido de ficheros — el más pesado por I/O
//
// EXCLUIDO A PROPÓSITO, y por qué:
//   · POST /login              throttle:login 5/min por IP (comprobado X-RateLimit-Limit: 5).
//     Bajo carga lo agota en un segundo y a partir de ahí se mide el limitador; contra
//     zajunavideo5 además BLOQUEA las cuentas reales de la fábrica.
//   · POST survey-email/submit-response, public/survey-responses  ESCRIBEN en la base del equipo.
//   · signed-download          genera un export; es trabajo pesado por petición, no lectura.
//
// LA CORRIDA R1 ENSEÑÓ ALGO DEL PROYECTO, no del rendimiento: con 10 VUs, `contact-info` daba
// 200 solo el 16 % de las veces y JSON el 100 %. No era la app caída — era su LIMITADOR DE TASA.
// TODA la superficie pública lleva `ratelimit:30` (o :60): 30 peticiones por minuto y a partir de
// ahí 429. 10 VUs generan ~360/min, así que el 90 % eran 429 legítimos. Medir carga concurrente
// contra un endpoint limitado mide el limitador, no la aplicación (la lección de #2: el «19,63 %»
// que era el guion). Es además un dato POSITIVO: la superficie pública se defiende de la carga por
// diseño, así que no es cargable sin sesión — y la sesión está bloqueada (SSO, ver el encabezado).
//
// POR ESO ESTE GUION MIDE DOS COSAS DISTINTAS, ninguna de ellas «saturación»:
//   escenario `latencia_base` — UN VU, ritmo por debajo de 30/min, para medir la latencia real de
//     cada ruta sin tocar el limitador. Es el único número de rendimiento honesto disponible.
//   escenario `verifica_ratelimit` — una ráfaga corta a UNA ruta para AFIRMAR que el limitador
//     responde 429 (no 5xx, no 200): que el mecanismo anti-DoS existe y funciona. Un 429 aquí es
//     un ÉXITO, no un fallo.
//
// La carga concurrente AUTENTICADA (el caso real: instructores usando el tablero a la vez) queda
// NO DISPONIBLE mientras el SSO no se pueda completar. Con BEARER_TOKEN puesto, `latencia_base`
// añade las rutas autenticadas.
import http from 'k6/http';
import { check, group, sleep } from 'k6';

const BASE = __ENV.BASE_URL || 'https://zajunavideo5.com';
const SURVEY_ID = __ENV.K6_SURVEY_ID || '1';         // un id cualquiera: mide la ruta, no el dato
const BEARER = __ENV.BEARER_TOKEN || '';             // opcional, para el día que haya sesión local

// QUÉ CUENTA COMO «FALLO» EN ESTA API. Por defecto k6 marca CUALQUIER 4xx como http_req_failed,
// y `make gate` lee esa métrica global. Pero en esta aplicación 401 (sin sesión), 403 (cerco del
// aprendiz), 404 (recurso inexistente) y 429 (limitador haciendo su trabajo) son respuestas
// SANAS de negocio, no caídas — y el escenario `verifica_ratelimit` PROVOCA 429 a propósito.
// Contar esos 429 como error daba un «71 % de fallo» que describía mi propio test, no la
// disponibilidad del sistema (la lección de #2, otra vez). La DISPONIBILIDAD se mide por 5xx:
// solo un error de servidor es una caída. Se declara 200-499 como esperado.
http.setResponseCallback(http.expectedStatuses({ min: 200, max: 499 }));

export const options = {
  scenarios: {
    // Latencia base: 1 VU, 1 iteración/s (con el sleep(1)), = 60 pet/min repartidas en 4 rutas,
    // ~15/min por ruta: por debajo del tope de 30. No dispara el limitador.
    latencia_base: {
      executor: 'constant-vus',
      vus: 1,
      duration: '40s',
      exec: 'lecturaBase',
      gracefulStop: '5s',
    },
    // Verificación del limitador: ráfaga a contact-info tras la ventana anterior. Afirma 429.
    verifica_ratelimit: {
      executor: 'constant-arrival-rate',
      rate: 20, timeUnit: '1s', duration: '5s',
      preAllocatedVUs: 20, maxVUs: 40,
      exec: 'rafagaRateLimit',
      startTime: '42s',
    },
  },
  thresholds: {
    // Solo el escenario de latencia base cuenta para «¿falla?»: se le exige que casi todo sea 2xx.
    'checks{scenario:latencia_base}': ['rate>0.98'],
    'http_req_duration{endpoint:contact-info}': ['p(95)<800'],
    'http_req_duration{endpoint:public-details}': ['p(95)<1200'],
    'http_req_duration{endpoint:theme}': ['p(95)<1200'],
    'http_req_duration{endpoint:image}': ['p(95)<1500'],
    // El limitador debe cortar: al menos la mitad de la ráfaga tiene que ser 429.
    'checks{check:corta_con_429}': ['rate>0.5'],
  },
};

const authHdr = BEARER ? { Authorization: `Bearer ${BEARER}` } : {};

// Latencia base — UN VU, una ruta por iteración (4 s de sleep = 15/min por ruta, bajo el tope
// de 30). Mide la latencia real de cada ruta sin despertar el limitador.
export function lecturaBase() {
  const r1 = http.get(`${BASE}/api/contact-info`, {
    headers: { Accept: 'application/json', ...authHdr },
    tags: { endpoint: 'contact-info' },
  });
  // 200 esperado. Se comprueba que sea JSON para que el catch-all del CMS (que también da 200)
  // no se cuele como éxito.
  check(r1, {
    'contact-info 200 JSON': (r) =>
      r.status === 200 && (r.headers['Content-Type'] || '').includes('application/json'),
  });
  sleep(1);

  const r2 = http.get(`${BASE}/api/surveys/${SURVEY_ID}/public-details`, {
    headers: { Accept: 'application/json', ...authHdr },
    tags: { endpoint: 'public-details' },
  });
  // 200 (existe) o 404 (no existe) son AMBOS sanos: se mide la latencia, no si ese id existe.
  check(r2, { 'public-details no 5xx': (r) => r.status < 500 });
  sleep(1);

  const r3 = http.get(`${BASE}/api/survey-themes/survey/${SURVEY_ID}`, {
    headers: { Accept: 'application/json', ...authHdr },
    tags: { endpoint: 'theme' },
  });
  check(r3, { 'theme no 5xx': (r) => r.status < 500 });
  sleep(1);

  const r4 = http.get(`${BASE}/api/storage/images/inexistente-de-carga.png`, {
    headers: { ...authHdr },
    tags: { endpoint: 'image' },
  });
  // El servido de ficheros: 404 para uno que no existe es correcto. Es el más caro por I/O.
  check(r4, { 'image no 5xx': (r) => r.status < 500 });
  sleep(1);
}

// Verificación del limitador — ráfaga a contact-info. AFIRMA que el mecanismo anti-DoS corta con
// 429 (no con 5xx, que sería el servidor rindiéndose, ni con 200, que sería no tener límite).
export function rafagaRateLimit() {
  const r = http.get(`${BASE}/api/contact-info`, {
    headers: { Accept: 'application/json' },
    tags: { endpoint: 'ratelimit-probe' },
  });
  // Un 429 aquí es ÉXITO: el limitador está haciendo su trabajo. 200 es aceptable (aún dentro de
  // la ventana); lo que NO puede ser es 5xx.
  check(r, {
    'corta_con_429': (res) => res.status === 429,
    'nunca 5xx bajo ráfaga': (res) => res.status < 500,
  });
}
