// El modelo de carga de Zajuna Móvil: qué pide la app, en qué orden y a qué ritmo.
//
// DE DÓNDE SALE. No del código ni de un documento: del tráfico que la app hizo de verdad en dos
// dispositivos Android contra el despliegue local entre el 24 y el 29 de septiembre de 2026
// (5.240 peticiones), leído del log del proxy y casado por `rid` con las llamadas a Moodle del
// backend. Se regenera con carga/grabacion.py; el resumen queda en carga/grabacion/<fecha>/.
//
// QUÉ ES MEDIDO Y QUÉ ES SUPUESTO — léelo antes de citar una cifra de este modelo:
//   medido    la secuencia de peticiones de cada gesto (cada función de abajo cita su ráfaga),
//             las cadenas de consulta (`?fresco=1`, `?cuantos=15`, `?limit=50`) y su frecuencia,
//             y el ritmo entre gestos (cuartiles 5 / 9 / 18 s).
//   supuesto  la MEZCLA de gestos: es la de quien probaba la app pantalla por pantalla, no la de
//             una población. Por eso los pesos van en una tabla aparte y se pueden cambiar
//             (CARGA_PESOS) sin tocar los gestos. Un probador navega más que un aprendiz: como
//             cota de demanda por usuario peca de alta, que es el lado seguro para dimensionar.
//
// SOLO LECTURAS. Ningún gesto entrega, publica, califica ni marca nada: una prueba de carga que
// escribe deja el Moodle lleno de basura y, contra un servidor compartido, es un daño.
import http from 'k6/http';
import { check, sleep } from 'k6';
import exec from 'k6/execution';
import { Counter } from 'k6/metrics';
import { pedir, lote, elegir, cuentaDe, cabeceras, ipDe, BASE } from '/seclab-lib/carga.js';
import { refrescar } from '/seclab-lib/session.js';

export const ENDPOINTS = [
  'login', 'refresh', 'validate', 'panel', 'agenda', 'conteo', 'curso', 'my_role', 'rap', 'notas',
  'aprendices', 'calendario', 'notif_lista', 'buscar', 'pantallas', 'mi_entrega', 'foro',
  'cuestionario', 'wiki', 'taller', 'glosario', 'encuesta',
];

const limitadas = new Counter('carga_429');       // el limitador entró: se midió el muro
const sin_sesion = new Counter('carga_401');      // la sesión se cayó: el modelo dejó de ser un usuario
const fallos_servidor = new Counter('carga_5xx');

// ---- el estado de UNA persona (en k6 el ámbito de módulo es por usuario virtual) ------------
const yo = { s: null, cuenta: null, cursos: null, abierto: null, modulos: [], ensena: false, aprendices: [], pantallas: false };

function anotar(r) {
  if (r.status === 429) limitadas.add(1);
  else if (r.status === 401) sin_sesion.add(1);
  else if (r.status >= 500) fallos_servidor.add(1);
  return r;
}
const ok = (r, nombre) => check(anotar(r), { [`${nombre} 200`]: (x) => x.status === 200 });
function json(r) {
  try { return r.status === 200 ? r.json() : null; } catch (e) { return null; }
}

// ---- sesión ----------------------------------------------------------------------------------
// El login de verdad. En la app es raro (la sesión dura 8 h y se renueva sola): por eso las
// escaleras abren las sesiones en setup() y el login solo es protagonista en pico-login.js.
export function entrar(cuenta, ip) {
  const h = { 'Content-Type': 'application/json' };
  if (ip) h['X-Forwarded-For'] = ip;
  const r = http.post(`${BASE}/auth/login`,
    JSON.stringify({ type_document: 'CC', document: cuenta.usuario, password: cuenta.clave }),
    { headers: h, tags: { endpoint: 'login', recorrido: 'login', fase: 'todo' } });
  const b = json(anotar(r));
  return b && b.access_token ? { access: b.access_token, refresh: b.refresh_token, t: Date.now() } : null;
}

// Abre N sesiones por lotes, cada una desde su IP: el login está limitado a 10 por minuto e IP
// (movil_api/app/routers/auth_router.py:106). Para setup().
export function abrirSesiones(n, porLote = Number(__ENV.CARGA_LOGIN_LOTE || 8)) {
  const out = [];
  for (let i = 0; i < n; i += porLote) {
    const reqs = [];
    for (let j = i; j < Math.min(n, i + porLote); j++) {
      const c = cuentaDe(j + 1);
      reqs.push({
        method: 'POST', url: `${BASE}/auth/login`,
        body: JSON.stringify({ type_document: 'CC', document: c.usuario, password: c.clave }),
        params: {
          headers: { 'Content-Type': 'application/json', 'X-Forwarded-For': `10.250.${(j >> 8) & 255}.${j & 255}` },
          tags: { endpoint: 'login', recorrido: 'setup', fase: 'setup' },
        },
      });
    }
    for (const r of http.batch(reqs)) {
      const b = json(r);
      out.push(b && b.access_token ? { access: b.access_token, refresh: b.refresh_token, t: Date.now() } : null);
    }
  }
  const malas = out.filter((x) => !x).length;
  if (malas > n * 0.02) throw new Error(`setup: ${malas} de ${n} logins fallaron — no hay población que simular`);
  return out;
}

export function tomarSesion(data) {
  if (yo.s) return true;
  const vu = exec.vu.idInTest;
  yo.cuenta = cuentaDe(vu);
  const s = data && data.sesiones ? data.sesiones[(vu - 1) % data.sesiones.length] : null;
  yo.s = s ? { ...s } : null;
  return !!yo.s;
}

// Para los guiones que conducen a UNA persona concreta (línea base, humo, pico de login).
export function usar(cuenta, sesion) {
  yo.cuenta = cuenta;
  yo.s = sesion;
  yo.cursos = null;
  yo.abierto = null;
  yo.modulos = [];
  yo.aprendices = [];
  yo.pantallas = false;
  return !!sesion;
}
export const tieneSesion = () => !!yo.s;

// La app revisa cada 5 min y renueva cuando al access le quedan 5 min o menos de sus 15
// (movil/src/app/services/auth/token-interceptor.service.ts:17-18). Ráfaga medida 35 veces:
// `POST /auth/refresh + GET /notifications/unread/count`.
function renovarSiToca() {
  if (!yo.s || Date.now() - yo.s.t < 10 * 60 * 1000) return;
  const r = refrescar(yo.s.refresh, cabeceras(''));
  if (r.ok) {
    yo.s.access = r.access;
    yo.s.t = Date.now();
    conteo('sesion');
  }
}

const T = () => ({ token: yo.s.access });
const conteo = (recorrido) => ok(pedir('GET', '/notifications/unread/count', null, { ...T(), endpoint: 'conteo', recorrido }), 'conteo');

function guardarPanel(r) {
  const b = json(r);
  if (b && b.courses) yo.cursos = b.courses.map((c) => ({ id: c.id, ensena: !!c.ensena }));
}

// ---- gestos ----------------------------------------------------------------------------------
// Arranque en frío con sesión guardada. Medido 54 veces: validate + 3 panel + agenda + 2 conteo.
// El primer panel calcula (11 llamadas a Moodle en la muestra); los otros dos salen de caché.
export function arranque() {
  const rec = 'arranque';
  ok(pedir('GET', '/auth/validate', null, { ...T(), endpoint: 'validate', recorrido: rec }), 'validate');
  conteo(rec);
  const r = pedir('GET', '/dashboard/admin', null, { ...T(), endpoint: 'panel', recorrido: rec });
  ok(r, 'panel');
  guardarPanel(r);
  const rs = lote([
    ['GET', '/dashboard/admin', null, 'panel'],
    ['GET', '/dashboard/admin', null, 'panel'],
    ['GET', '/notifications/unread/count', null, 'conteo'],
    ['GET', '/agenda/pendientes?cuantos=15', null, 'agenda'],
  ], { ...T(), recorrido: rec });
  rs.forEach((x) => anotar(x));
  check(rs[3], { 'agenda 200': (x) => x.status === 200 });
}

// Volver a Inicio. Medido 91 veces: agenda + 2 panel + conteo. El 17 % de los paneles de la
// grabación llevan `?fresco=1` (177 de 1.052), que se salta la caché de 45 s del backend.
export function inicio() {
  const rec = 'inicio';
  const fresco = Math.random() < 0.17 ? '?fresco=1' : '';
  const rs = lote([
    ['GET', '/agenda/pendientes?cuantos=15', null, 'agenda'],
    ['GET', '/dashboard/admin', null, 'panel'],
    ['GET', `/dashboard/admin${fresco}`, null, 'panel'],
    ['GET', '/notifications/unread/count', null, 'conteo'],
  ], { ...T(), recorrido: rec });
  rs.forEach((x) => anotar(x));
  check(rs[1], { 'panel 200': (x) => x.status === 200 });
  guardarPanel(rs[1]);
}

// Abrir un curso. Medido 87 veces: detalle + conteo + my_role. El 71 % de los detalles de la
// grabación llevan `?fresco=1` (254 de 359): la pantalla revalida siempre que está en línea.
export function abrirCurso() {
  if (!yo.cursos || !yo.cursos.length) return inicio();
  const rec = 'curso';
  const c = yo.cursos[Math.floor(Math.random() * yo.cursos.length)];
  const fresco = Math.random() < 0.71 ? '?fresco=1' : '';
  const rs = lote([
    ['GET', `/dashboard/cursos/${c.id}${fresco}`, null, 'curso'],
    ['GET', '/notifications/unread/count', null, 'conteo'],
    ['POST', '/grades/my_role', { courseid: c.id }, 'my_role'],
  ], { ...T(), recorrido: rec });
  rs.forEach((x) => anotar(x));
  check(rs[0], { 'curso 200': (x) => x.status === 200 });
  const b = json(rs[0]);
  yo.abierto = c.id;
  yo.ensena = c.ensena;
  yo.modulos = [];
  if (b && b.sections) {
    const rec2 = (x) => {
      if (Array.isArray(x)) x.forEach(rec2);
      else if (x && typeof x === 'object') {
        if (x.modname && x.id && x.visible !== 0) yo.modulos.push({ id: x.id, tipo: x.modname });
        Object.values(x).forEach((v) => { if (v && typeof v === 'object') rec2(v); });
      }
    };
    rec2(b.sections);
  }
  if (!yo.pantallas) {
    // Una vez por sesión, al abrir la primera actividad (movil/src/app/services/pantallas.service.ts:25).
    ok(pedir('GET', '/mobile/pantallas', null, { ...T(), endpoint: 'pantallas', recorrido: rec }), 'pantallas');
    yo.pantallas = true;
  }
}

// Calificaciones. Aprendiz, medido 44 veces: resultados + my_role + notas (+ conteo).
// Instructor, medido 59 veces: lo mismo + course_students; y al cambiar de aprendiz, 18 veces:
// resultados?aprendiz= + notas de esa persona.
export function calificaciones() {
  if (!yo.abierto) return abrirCurso();
  const rec = 'calificaciones';
  const id = yo.abierto;
  if (!yo.ensena) {
    const rs = lote([
      ['POST', '/grades/my_role', { courseid: id }, 'my_role'],
      ['GET', `/cursos/${id}/resultados-de-aprendizaje`, null, 'rap'],
      ['POST', '/grades/parsed_table', { courseid: id }, 'notas'],
      ['GET', '/notifications/unread/count', null, 'conteo'],
    ], { ...T(), recorrido: rec });
    rs.forEach((x) => anotar(x));
    check(rs[2], { 'notas 200': (x) => x.status === 200 });
    return;
  }
  const rs = lote([
    ['POST', '/grades/my_role', { courseid: id }, 'my_role'],
    ['POST', '/grades/course_students', { courseid: id }, 'aprendices'],
  ], { ...T(), recorrido: rec });
  rs.forEach((x) => anotar(x));
  const lista = json(rs[1]);
  const gente = Array.isArray(lista) ? lista : (lista && (lista.students || lista.estudiantes || lista.data)) || [];
  yo.aprendices = gente.map((g) => g.id || g.userid).filter((x) => x);
  verAprendiz(id, rec);
}
function verAprendiz(id, rec) {
  if (!yo.aprendices.length) return;
  const a = yo.aprendices[Math.floor(Math.random() * yo.aprendices.length)];
  const rs = lote([
    ['GET', `/cursos/${id}/resultados-de-aprendizaje?aprendiz=${a}`, null, 'rap'],
    ['POST', '/grades/parsed_table', { courseid: id, userid: a }, 'notas'],
  ], { ...T(), recorrido: rec });
  rs.forEach((x) => anotar(x));
  check(rs[1], { 'notas 200': (x) => x.status === 200 });
}
export function cambiarAprendiz() {
  if (!yo.abierto || !yo.ensena || !yo.aprendices.length) return calificaciones();
  verAprendiz(yo.abierto, 'calificaciones');
}

// Calendario. Medido 104 veces: un mes por gesto (el mes en curso y los vecinos).
export function calendario() {
  const d = new Date();
  d.setMonth(d.getMonth() + Math.floor(Math.random() * 3) - 1);
  ok(pedir('GET', `/calendario/eventos?anio=${d.getFullYear()}&mes=${d.getMonth() + 1}`, null,
    { ...T(), endpoint: 'calendario', recorrido: 'calendario' }), 'calendario');
}

// Notificaciones. Medido 26 veces: la lista se pide DOS veces (ngOnInit del componente e
// ionViewDidEnter de la página) + conteo.
export function notificaciones() {
  const rs = lote([
    ['GET', '/notifications/list?limit=20', null, 'notif_lista'],
    ['GET', '/notifications/list?limit=20', null, 'notif_lista'],
    ['GET', '/notifications/unread/count', null, 'conteo'],
  ], { ...T(), recorrido: 'notificaciones' });
  rs.forEach((x) => anotar(x));
  check(rs[0], { 'notif_lista 200': (x) => x.status === 200 });
}

export function buscar() {
  const q = ['a', 'ev', 'foro', 'guia', 'act'][Math.floor(Math.random() * 5)];
  ok(pedir('GET', `/buscar?q=${q}`, null, { ...T(), endpoint: 'buscar', recorrido: 'buscar' }), 'buscar');
}

// Abrir una actividad del curso (solo su lectura). Las rutas son las que la app pidió de verdad
// para cada tipo; la tarea trae además dos my_role (medido 17 veces).
const RUTA = {
  assign: (id) => [`/evidencias/${id}/mi-entrega`, 'mi_entrega'],
  forum: (id) => [`/evidencias/${id}/foro`, 'foro'],
  quiz: (id) => [`/evidencias/${id}/cuestionario/mi-presentacion`, 'cuestionario'],
  wiki: (id) => [`/evidencias/${id}/wiki`, 'wiki'],
  workshop: (id) => [`/evidencias/${id}/taller`, 'taller'],
  glossary: (id) => [`/evidencias/${id}/glosario`, 'glosario'],
  feedback: (id) => [`/evidencias/${id}/encuesta`, 'encuesta'],
};
export function evidencia() {
  if (!yo.abierto) return abrirCurso();
  const posibles = yo.modulos.filter((m) => RUTA[m.tipo]);
  if (!posibles.length) return abrirCurso();
  const m = posibles[Math.floor(Math.random() * posibles.length)];
  const [ruta, endpoint] = RUTA[m.tipo](m.id);
  const r = pedir('GET', ruta, null, { ...T(), endpoint, recorrido: 'evidencia', esperados: [403, 404] });
  anotar(r);
  // 403/404 aquí no son un fallo del sistema: una actividad puede estar restringida para esta
  // persona. Cuenta como fallo solo el error del servidor.
  check(r, { 'evidencia sin 5xx': (x) => x.status < 500 });
  if (m.tipo === 'assign') {
    lote([
      ['POST', '/grades/my_role', { courseid: yo.abierto }, 'my_role'],
      ['POST', '/grades/my_role', { courseid: yo.abierto }, 'my_role'],
    ], { ...T(), recorrido: 'evidencia' }).forEach((x) => anotar(x));
  }
}

// La app con una pantalla abierta y nadie tocando: el conteo de notificaciones solo. Es la
// ráfaga MÁS frecuente de la grabación (265 veces) y el 31 % de todas las peticiones.
export function reposo() {
  conteo('reposo');
}

// ---- la mezcla (SUPUESTO: frecuencias de un barrido de pruebas, no de una población) ---------
const PESOS = Object.assign(
  { reposo: 265, inicio: 316, curso: 87, calificaciones: 103, cambiarAprendiz: 18, calendario: 104, notificaciones: 26, buscar: 22, evidencia: 190 },
  __ENV.CARGA_PESOS ? JSON.parse(__ENV.CARGA_PESOS) : {},
);
const GESTOS = [
  { peso: PESOS.reposo, f: reposo }, { peso: PESOS.inicio, f: inicio }, { peso: PESOS.curso, f: abrirCurso },
  { peso: PESOS.calificaciones, f: calificaciones }, { peso: PESOS.cambiarAprendiz, f: cambiarAprendiz },
  { peso: PESOS.calendario, f: calendario }, { peso: PESOS.notificaciones, f: notificaciones },
  { peso: PESOS.buscar, f: buscar }, { peso: PESOS.evidencia, f: evidencia },
];

// Tiempo entre gestos: los cuartiles medidos (5 / 9 / 18 s entre ráfagas) y una cola hasta 60 s.
// CARGA_RITMO lo escala: 1 = el del probador; 2 = una persona el doble de lenta.
export function pensar() {
  const tramo = [[2, 5], [5, 9], [9, 18], [18, 60]][Math.floor(Math.random() * 4)];
  sleep((tramo[0] + Math.random() * (tramo[1] - tramo[0])) * Number(__ENV.CARGA_RITMO || 1));
}

let arrancado = false;
export function unGesto(data) {
  if (!tomarSesion(data)) {
    sleep(1);
    return;
  }
  if (!arrancado) {
    // Las personas no abren la app todas en el mismo segundo: se reparte el arranque.
    sleep(Math.random() * Number(__ENV.CARGA_DISPERSION_S || 10));
    arranque();
    arrancado = true;
  } else {
    renovarSiToca();
    elegir(GESTOS).f();
  }
  pensar();
}

// Como unGesto, pero cada persona INICIA SESIÓN ella misma al llegar (pico de login: el lunes a
// primera hora nadie tiene la sesión abierta). El login va con la IP de la persona.
export function unGestoConLogin() {
  if (!yo.s) {
    const vu = exec.vu.idInTest;
    const c = cuentaDe(vu);
    // La IP del login sigue CARGA_IPS: una por persona, o compartida (aula) para ver el límite de
    // 10 logins por minuto e IP (auth_router.py:106) con gente real detrás de un NAT.
    if (!usar(c, entrar(c, ipDe(vu) || `10.251.${(vu >> 8) & 255}.${vu & 255}`))) {
      sleep(5);
      return;
    }
    arranque();
  } else {
    renovarSiToca();
    elegir(GESTOS).f();
  }
  pensar();
}
