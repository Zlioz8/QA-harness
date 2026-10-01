// Carga y capacidad: lo que convierte «un p95» en una medición de capacidad.
//
// session.js resuelve CÓMO se entra. Este módulo resuelve CUÁNTA carga, con QUÉ forma, con
// QUIÉN y qué queda escrito al final. Es genérico: ningún nombre de proyecto aquí dentro.
//
// Tres errores que este módulo existe para impedir, los tres medidos en este laboratorio:
//   1. Todos los usuarios virtuales con UNA cuenta: el backend cachea por persona y la prueba
//      mide la caché, no el sistema. -> una cuenta por usuario virtual (cuentas.json).
//   2. Todos desde UNA IP: el límite por IP entra y se mide el muro. -> IP de cliente declarada
//      (CARGA_IPS), que además permite modelar a propósito un aula detrás de un NAT.
//   3. Un solo summary.json global: el endpoint lento se diluye en el promedio. -> detalle.json
//      con percentiles por endpoint.
//
// Todo se gobierna por entorno para que tools/perf-escalera.sh suba por pasos sin editar guiones:
//   CARGA_TIPO    humo | linea-base | carga | estres | pico | resistencia
//   CARGA_VUS     usuarios virtuales del paso            CARGA_RAMPA / CARGA_MESETA / CARGA_BAJADA
//   CARGA_MODELO  cerrado (usuarios) | abierto (llegadas por segundo, CARGA_TASA)
//   CARGA_PASOS   «50,100,200» para estres en una sola corrida
//   CARGA_IPS     vacío | por-vu | aula:N                 CARGA_CUENTAS  ruta del json de cuentas
//   CARGA_ABORTA  1 = cortar la corrida al cruzar el umbral (obligatorio contra un servidor ajeno)
//   CARGA_RUN     identificador de la corrida; viaja en X-Request-Id para casar con los logs
import http from 'k6/http';
import exec from 'k6/execution';
import { SharedArray } from 'k6/data';
import { Gauge } from 'k6/metrics';

const E = __ENV;
const txt = (k, d) => (E[k] !== undefined && E[k] !== '' ? E[k] : d);
const num = (k, d) => (E[k] !== undefined && E[k] !== '' ? Number(E[k]) : d);

export const TIPO = txt('CARGA_TIPO', 'humo');
export const VUS = num('CARGA_VUS', 1);
export const RUN = txt('CARGA_RUN', 'suelta');
export const BASE = txt('BASE_URL', 'http://app:8000');

// ---------------------------------------------------------------------------------------------
// La forma de la carga. Cada tipo responde UNA pregunta; mezclar dos en una corrida deja sin
// responder las dos.
//   humo         ¿el guion y el entorno funcionan?            1 usuario, segundos
//   linea-base   ¿cuánto cuesta cada petición sin compañía?   1 usuario, N iteraciones
//   carga        ¿cumple el SLO a esta concurrencia?          rampa, meseta (se juzga), bajada
//   estres       ¿dónde se rompe?                             escalones crecientes en una corrida
//   pico         ¿aguanta una avalancha y se recupera?        base, salto, meseta corta, base
//   resistencia  ¿se degrada con el tiempo?                   meseta larga
export function escenarios(tipo = TIPO) {
  const rampa = txt('CARGA_RAMPA', '30s');
  const meseta = txt('CARGA_MESETA', tipo === 'resistencia' ? '2h' : tipo === 'humo' ? '30s' : '2m');
  const bajada = txt('CARGA_BAJADA', '15s');

  if (txt('CARGA_MODELO', 'cerrado') === 'abierto') {
    // Modelo abierto: las llegadas no esperan a que el sistema responda. Es el que se parece a
    // un país entero abriendo la app; el cerrado se autorregula y esconde la saturación.
    const tasa = num('CARGA_TASA', 1);
    return {
      llegadas: {
        executor: 'ramping-arrival-rate',
        startRate: 0,
        timeUnit: '1s',
        preAllocatedVUs: Math.max(VUS, 10),
        maxVUs: Math.max(VUS * 4, 50),
        stages: [
          { duration: rampa, target: tasa },
          { duration: meseta, target: tasa },
          { duration: bajada, target: 0 },
        ],
      },
    };
  }

  switch (tipo) {
    case 'linea-base':
      return { base: { executor: 'per-vu-iterations', vus: 1, iterations: num('CARGA_ITER', 5), maxDuration: '30m' } };
    case 'humo':
      return { humo: { executor: 'constant-vus', vus: VUS, duration: meseta } };
    case 'estres': {
      const pasos = txt('CARGA_PASOS', `${VUS}`).split(',').map((x) => Number(x.trim())).filter((x) => x > 0);
      const stages = [];
      for (const p of pasos) {
        stages.push({ duration: rampa, target: p });
        stages.push({ duration: meseta, target: p });
      }
      stages.push({ duration: bajada, target: 0 });
      return { estres: { executor: 'ramping-vus', startVUs: 1, stages, gracefulRampDown: '20s' } };
    }
    case 'pico': {
      const base = Math.max(1, Math.round(VUS * num('CARGA_PICO_BASE', 0.1)));
      return {
        pico: {
          executor: 'ramping-vus',
          startVUs: base,
          stages: [
            { duration: '1m', target: base },
            { duration: txt('CARGA_PICO_SUBIDA', '10s'), target: VUS },
            { duration: meseta, target: VUS },
            { duration: '10s', target: base },
            { duration: '2m', target: base },
          ],
          gracefulRampDown: '20s',
        },
      };
    }
    case 'carga':
    case 'resistencia':
    default:
      return {
        carga: {
          executor: 'ramping-vus',
          startVUs: 1,
          stages: [
            { duration: rampa, target: VUS },
            { duration: meseta, target: VUS },
            { duration: bajada, target: 0 },
          ],
          gracefulRampDown: '20s',
        },
      };
  }
}

// ---------------------------------------------------------------------------------------------
// La fase. El SLO se juzga en la MESETA: durante la rampa la concurrencia todavía no es la del
// paso, y meter esas peticiones en el percentil lo abarata. Cada petición lleva su fase como
// etiqueta y el resumen publica las cifras de la meseta aparte de las globales.
function seg(d) {
  const m = /^(\d+(?:\.\d+)?)(ms|s|m|h)$/.exec(String(d).trim());
  if (!m) return 0;
  return Number(m[1]) * { ms: 0.001, s: 1, m: 60, h: 3600 }[m[2]];
}
const CON_FASES = TIPO === 'carga' || TIPO === 'resistencia';
const RAMPA_S = seg(txt('CARGA_RAMPA', '30s'));
const MESETA_S = seg(txt('CARGA_MESETA', TIPO === 'resistencia' ? '2h' : '2m'));
const gInicio = new Gauge('carga_inicio_s');
let _marcado = false;

export function fase() {
  if (!_marcado) {
    // Cuándo empezó de verdad el escenario (después de setup): con esto la telemetría del
    // sistema se recorta a la misma ventana que las cifras de k6.
    gInicio.add(exec.scenario.startTime / 1000);
    _marcado = true;
  }
  if (!CON_FASES) return 'todo';
  const t = (Date.now() - exec.scenario.startTime) / 1000;
  if (t < RAMPA_S) return 'rampa';
  if (t < RAMPA_S + MESETA_S) return 'meseta';
  return 'bajada';
}

// ---------------------------------------------------------------------------------------------
// Umbrales. Dos usos distintos y no intercambiables:
//   - los del SLO (p95, p99, error, checks) dan el veredicto del paso;
//   - los «siempre verdaderos» por endpoint existen solo para que k6 publique el submétrico de
//     cada etiqueta en el resumen. Sin un umbral, k6 no emite `http_req_duration{endpoint:x}`.
export function umbrales(endpoints = []) {
  const aborta = txt('CARGA_ABORTA', '') === '1';
  const con = (expr) => (aborta ? [{ threshold: expr, abortOnFail: true, delayAbortEval: '20s' }] : [expr]);
  const t = {
    http_req_duration: con(`p(95)<${num('K6_P95_MS', 1500)}`),
    http_req_failed: con(`rate<${num('K6_ERR_RATE', 0.01)}`),
  };
  if (E.K6_P99_MS) t.http_req_duration.push(`p(99)<${num('K6_P99_MS', 3000)}`);
  if (E.K6_CHECKS_MIN) t.checks = [`rate>=${num('K6_CHECKS_MIN', 0.99)}`];
  if (CON_FASES) {
    t['http_req_duration{fase:meseta}'] = ['max>=0'];
    t['http_req_failed{fase:meseta}'] = ['rate>=0'];
    t['http_reqs{fase:meseta}'] = ['count>=0'];
  }
  const sel = (e) => (CON_FASES ? `endpoint:${e},fase:meseta` : `endpoint:${e}`);
  for (const e of endpoints) {
    t[`http_req_duration{${sel(e)}}`] = ['max>=0'];
    t[`http_req_failed{${sel(e)}}`] = ['rate>=0'];
    t[`http_reqs{${sel(e)}}`] = ['count>=0'];
  }
  return t;
}

export function opciones(endpoints = []) {
  return {
    scenarios: escenarios(),
    thresholds: umbrales(endpoints),
    // p(99) no sale en el resumen si no se pide: sin esto el gate no puede juzgar la cola.
    summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
    insecureSkipTLSVerify: txt('K6_INSECURE_SKIP_TLS_VERIFY', 'false') === 'true',
    setupTimeout: txt('CARGA_SETUP_TIMEOUT', '20m'),
    // Sin esto k6 reutiliza conexiones entre iteraciones de un mismo usuario, como hace una app.
    noConnectionReuse: false,
    userAgent: `k6-carga/${RUN}`,
  };
}

// ---------------------------------------------------------------------------------------------
// Una cuenta por usuario virtual. El archivo NO se versiona (lleva claves): lo genera el perfil.
// Forma: [{ "usuario": "...", "clave": "...", "rol": "aprendiz" }, ...]
// k6 solo deja crear un SharedArray en el contexto de inicio: por eso se crea al cargar el módulo
// y no la primera vez que alguien pide una cuenta (setup() ya no es contexto de inicio).
const _cuentas = new SharedArray('cuentas', () => {
  const ruta = txt('CARGA_CUENTAS', '/scripts/datos/cuentas.json');
  try {
    return JSON.parse(open(ruta));
  } catch (e) {
    // Sin archivo de cuentas el guion sigue pudiendo usar las dos del perfil, pero se dice: una
    // prueba de carga con una sola cuenta mide la caché por persona.
    return [];
  }
});
export function cuentas() {
  return _cuentas;
}
export function cuentaDe(vu = exec.vu.idInTest) {
  const c = cuentas();
  return c.length ? c[(vu - 1) % c.length] : null;
}

// ---------------------------------------------------------------------------------------------
// IP de cliente. Solo tiene efecto si el despliegue BAJO PRUEBA confía en el X-Forwarded-For que
// le llega (un salto de proxy más, declarado en el sobre de la corrida). Contra un servidor real
// la cabecera se ignora y todos los usuarios virtuales comparten la IP del generador: eso ES el
// escenario «aula», y hay que leer los 429 como tal.
//   por-vu   cada usuario virtual su IP             aula:N   grupos de N comparten IP
export function ipDe(vu = exec.vu.idInTest) {
  const modo = txt('CARGA_IPS', '');
  if (!modo) return '';
  let n = vu;
  if (modo.startsWith('aula:')) n = Math.floor((vu - 1) / Math.max(1, Number(modo.slice(5)))) + 1;
  return `10.${(n >> 16) & 255}.${(n >> 8) & 255}.${n & 255}`;
}

// ---------------------------------------------------------------------------------------------
// Peticiones con portador. Cada una lleva: su etiqueta de endpoint y de recorrido (para el
// detalle), su IP de cliente y un X-Request-Id que permite casarla con el log del proxy y del
// backend. Si lo que contó k6 y lo que registró el servidor no coinciden, se midió otra cosa.
let _seq = 0;
export function rid() {
  _seq += 1;
  return `k6-${RUN}-${exec.vu.idInTest}-${exec.vu.iterationInScenario}-${_seq}`;
}

// Cabeceras fijas del cliente que se imita, en JSON (`CARGA_CABECERAS`). k6 no manda
// `Accept-Encoding` por su cuenta y el cliente nativo de una app Android sí (HttpURLConnection
// negocia gzip solo): sin esto k6 mide los bytes sin comprimir y la app los comprimidos
// (medido el 2026-10-01: 56 KB frente a 4 KB en el detalle de un curso).
const FIJAS = (() => {
  try { return JSON.parse(__ENV.CARGA_CABECERAS || '{}'); } catch (e) { throw new Error(`CARGA_CABECERAS no es JSON: ${e}`); }
})();

export function cabeceras(token, extra = {}) {
  const h = { ...FIJAS, 'X-Request-Id': rid(), ...extra };
  const ip = ipDe();
  if (ip) h['X-Forwarded-For'] = ip;
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

// `esperados`: estados que para ESTA petición no son un fallo (p. ej. 403/404 al abrir algo que la
// persona no puede ver). Sin declararlos k6 los cuenta en http_req_failed y la tasa de error del
// paso mezcla «el servidor falló» con «el servidor dijo que no», que son cosas distintas.
export function pedir(metodo, ruta, cuerpo, { token = '', endpoint = ruta, recorrido = '', base = BASE, cabecera = {}, esperados = null } = {}) {
  const tags = { endpoint, recorrido, fase: fase() };
  const params = { headers: cabeceras(token, cabecera), tags };
  if (esperados) params.responseCallback = http.expectedStatuses({ min: 200, max: 299 }, ...esperados);
  if (metodo === 'GET') return http.get(`${base}${ruta}`, params);
  params.headers['Content-Type'] = 'application/json';
  return http.request(metodo, `${base}${ruta}`, cuerpo === undefined || cuerpo === null ? null : JSON.stringify(cuerpo), params);
}

// Varias peticiones A LA VEZ, como hace una pantalla al abrirse (la app no las encadena). Cada
// entrada: [metodo, ruta, cuerpo, endpoint]. Devuelve las respuestas en el mismo orden.
export function lote(entradas, { token = '', recorrido = '', base = BASE } = {}) {
  const f = fase();
  const reqs = entradas.map(([metodo, ruta, cuerpo, endpoint]) => {
    const params = { headers: cabeceras(token), tags: { endpoint: endpoint || ruta, recorrido, fase: f } };
    let body = null;
    if (metodo !== 'GET') {
      params.headers['Content-Type'] = 'application/json';
      body = cuerpo === undefined || cuerpo === null ? null : JSON.stringify(cuerpo);
    }
    return { method: metodo, url: `${base}${ruta}`, body, params };
  });
  return http.batch(reqs);
}

// Espera entre acciones con variación: usuarios reales no pulsan a intervalos exactos, y sin
// variación todos los usuarios virtuales se sincronizan y la carga llega en oleadas.
export function pausa(min, max) {
  const s = max === undefined ? min : min + Math.random() * (max - min);
  return s;
}

// Elegir según pesos: [{ peso: 60, f }, { peso: 40, f }].
export function elegir(opcionesConPeso) {
  const total = opcionesConPeso.reduce((a, o) => a + o.peso, 0);
  let r = Math.random() * total;
  for (const o of opcionesConPeso) {
    r -= o.peso;
    if (r <= 0) return o;
  }
  return opcionesConPeso[opcionesConPeso.length - 1];
}

// ---------------------------------------------------------------------------------------------
// El resumen de la corrida. `--summary-export` (docker-compose.yml) sigue escribiendo el
// summary.json que tools/gate.sh ya sabe leer; esto AÑADE detalle.json, no lo sustituye.
function valores(m) {
  if (!m) return null;
  return m.values || m;
}

export function resumen(data, extra = {}) {
  const M = data.metrics || {};
  const porEndpoint = {};
  for (const nombre of Object.keys(M)) {
    const m = /^(http_req_duration|http_req_failed|http_reqs)\{endpoint:([^,}]+)(?:,fase:meseta)?\}$/.exec(nombre);
    if (!m) continue;
    const e = (porEndpoint[m[2]] = porEndpoint[m[2]] || {});
    const v = valores(M[nombre]);
    if (m[1] === 'http_req_duration') {
      e.ms = { med: v.med, 'p(90)': v['p(90)'], 'p(95)': v['p(95)'], 'p(99)': v['p(99)'], max: v.max, avg: v.avg };
    } else if (m[1] === 'http_req_failed') {
      e.error = v.rate !== undefined ? v.rate : v.value;
    } else {
      e.peticiones = v.count;
      e.por_segundo = v.rate;
    }
  }
  // Un endpoint que el modelo declara pero que esta corrida no llegó a pedir NO tiene «0 ms»:
  // no tiene dato. Se quita, para que nadie lea un cero como una latencia.
  for (const k of Object.keys(porEndpoint)) {
    if (!porEndpoint[k].peticiones) delete porEndpoint[k];
  }
  const d = valores(M.http_req_duration) || {};
  const f = valores(M.http_req_failed) || {};
  const r = valores(M.http_reqs) || {};
  const it = valores(M.iterations) || {};
  const rx = valores(M.data_received) || {};
  const tx = valores(M.data_sent) || {};
  const vm = valores(M.vus_max) || {};
  const c = valores(M.checks) || {};
  // Cifras de la meseta, cuando la corrida tiene fases. Son las que juzgan el SLO.
  let meseta = null;
  const dm = valores(M['http_req_duration{fase:meseta}']);
  if (dm) {
    const fm = valores(M['http_req_failed{fase:meseta}']) || {};
    const rm = valores(M['http_reqs{fase:meseta}']) || {};
    meseta = {
      segundos: MESETA_S,
      peticiones: rm.count,
      por_segundo: MESETA_S > 0 && rm.count !== undefined ? rm.count / MESETA_S : rm.rate,
      ms: { med: dm.med, 'p(90)': dm['p(90)'], 'p(95)': dm['p(95)'], 'p(99)': dm['p(99)'], max: dm.max, avg: dm.avg },
      error: fm.rate !== undefined ? fm.rate : fm.value,
      // Los checks no heredan la etiqueta de fase de la petición: se toma la tasa de toda la corrida.
      checks: c.rate !== undefined ? c.rate : c.value,
    };
  }
  const gi = valores(M.carga_inicio_s) || {};
  const doc = {
    corrida: RUN,
    tipo: TIPO,
    vus: VUS,
    vus_max: vm.max !== undefined ? vm.max : vm.value,
    duracion_ms: data.state ? data.state.testRunDurationMs : null,
    inicio_s: gi.value !== undefined ? gi.value : null,
    rampa_s: RAMPA_S,
    meseta_s: MESETA_S,
    por_endpoint_en: CON_FASES ? 'meseta' : 'toda la corrida',
    meseta,
    global: {
      peticiones: r.count,
      por_segundo: r.rate,
      ms: { med: d.med, 'p(90)': d['p(90)'], 'p(95)': d['p(95)'], 'p(99)': d['p(99)'], max: d.max, avg: d.avg },
      error: f.rate !== undefined ? f.rate : f.value,
      checks: c.rate !== undefined ? c.rate : c.value,
      iteraciones: it.count,
      bytes_recibidos: rx.count,
      bytes_enviados: tx.count,
    },
    por_endpoint: porEndpoint,
    ...extra,
  };
  const linea =
    `\n  ${TIPO} · ${VUS} usuarios · ${Math.round(r.rate || 0)} pet/s · ` +
    `p95 ${Math.round(d['p(95)'] || 0)} ms · p99 ${Math.round(d['p(99)'] || 0)} ms · ` +
    `error ${((doc.global.error || 0) * 100).toFixed(2)} %\n`;
  return { '/reports/detalle.json': JSON.stringify(doc, null, 1), stdout: linea };
}
