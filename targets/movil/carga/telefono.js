#!/usr/bin/env node
/**
 * Conduce la app en el teléfono por CDP y anota cada petición vista desde el teléfono.
 *
 * Lee la consola del WebView: el parche de CapacitorHttp de la app escribe
 *   [trace] <rid> <METODO> <url>              al salir la petición
 *   [trace] <rid> fin <ms> <estado> <ms_servidor>   al volver (movil/src/main.ts)
 * y con eso se tiene, por petición, el tiempo total en el teléfono y el tiempo del servidor
 * (`X-Execution-Time-Ms`). La red de ida y vuelta es la diferencia. El log de nginx y el `[ws]`
 * del backend, casados por `rid`, ponen el resto.
 *
 * Los recorridos son los mismos gestos del modelo de carga (k6/modelo.js), hechos en el DOM
 * real: pulsar pestañas, abrir un curso, abrir Calificaciones. Sin dependencias: Node 22+.
 */
const fs = require('fs');
const path = require('path');

const WS_URL = process.env.CDP_WS;
const SALIDA = process.env.SALIDA;
const RECORRIDOS = (process.env.RECORRIDOS || 'arranque').split(',').map((s) => s.trim()).filter(Boolean);
const REPES = Number(process.env.REPES || 3);
if (!WS_URL || !SALIDA) { console.error('faltan CDP_WS o SALIDA'); process.exit(2); }

const eventos = fs.createWriteStream(path.join(SALIDA, 'eventos.jsonl'), { flags: 'a' });
let ultimoEvento = Date.now();
const anota = (o) => { ultimoEvento = Date.now(); eventos.write(JSON.stringify({ t: Date.now(), ...o }) + '\n'); };

const ws = new WebSocket(WS_URL);
let seq = 0;
const pendientes = new Map();
const peticiones = new Map(); // rid -> {inicio, metodo, url, fin, estado, servidor, recorrido, repe}
let recorridoActual = '';
let repeActual = 0;

function enviar(method, params = {}) {
  return new Promise((res, rej) => {
    const id = ++seq;
    pendientes.set(id, { res, rej });
    ws.send(JSON.stringify({ id, method, params }));
  });
}
async function js(expr) {
  const r = await enviar('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + ' ' + (r.exceptionDetails.exception?.description || ''));
  return r.result?.value;
}
const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

ws.addEventListener('message', (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && pendientes.has(msg.id)) {
    const p = pendientes.get(msg.id); pendientes.delete(msg.id);
    msg.error ? p.rej(new Error(JSON.stringify(msg.error))) : p.res(msg.result);
    return;
  }
  if (msg.method === 'Runtime.consoleAPICalled') {
    const args = (msg.params.args || []).map((a) => (a.value !== undefined ? String(a.value) : a.description || ''));
    if (args[0] !== '[trace]') {
      if (/ionViewDidEnter|ngOnInit|resume/i.test(args.join(' '))) anota({ tipo: 'consola', ts: msg.params.timestamp, texto: args.join(' ').slice(0, 160), recorrido: recorridoActual, repe: repeActual });
      return;
    }
    const rid = args[1];
    if (args[2] === 'fin') {
      const p = peticiones.get(rid) || { rid };
      p.fin = msg.params.timestamp; p.ms = Number(args[3]); p.estado = args[4]; p.servidor = args[5] === '' ? null : Number(args[5]);
      peticiones.set(rid, p);
      anota({ tipo: 'fin', rid, ts: msg.params.timestamp, ms: p.ms, estado: p.estado, servidor: p.servidor, recorrido: recorridoActual, repe: repeActual });
    } else {
      const p = { rid, inicio: msg.params.timestamp, metodo: args[2], url: args[3], recorrido: recorridoActual, repe: repeActual };
      peticiones.set(rid, p);
      anota({ tipo: 'inicio', ...p, ts: p.inicio });
    }
  }
});

// ---- gestos en el DOM real -------------------------------------------------------------------
const pulsar = (sel) => js(`(() => { const el = [...document.querySelectorAll(${JSON.stringify(sel)})].filter(e => e.getBoundingClientRect().width > 0).pop(); if (!el) return false; el.click(); return true; })()`);
const esperarVisible = async (sel, ms = 15000) => {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (await js(`!![...document.querySelectorAll(${JSON.stringify(sel)})].find(e => e.getBoundingClientRect().width > 0)`)) return true;
    await dormir(250);
  }
  return false;
};
const enReposo = async (ms = 1500, tope = 20000) => {
  // Fin de ráfaga: ningún inicio ni fin de petición durante `ms`.
  const t0 = Date.now();
  let ultimo = ultimoEvento;
  while (Date.now() - t0 < tope) {
    await dormir(250);
    if (Date.now() - ultimoEvento > ms && ultimo === ultimoEvento) return true;
    ultimo = ultimoEvento;
  }
  return false;
};

const GESTOS = {
  // Iniciar sesión con la cuenta que pase el entorno (TEL_USUARIO / TEL_CLAVE). Escribe en los
  // inputs nativos de ion-input y dispara `input`, que es lo que escucha el formulario.
  login: async () => {
    if (!(await esperarVisible('input#ion-input-0', 8000))) { anota({ tipo: 'nota', texto: 'sin pantalla de login: ya hay sesión' }); return; }
    await js(`(() => {
      const poner = (sel, v) => { const i = document.querySelector(sel); if (!i) return false;
        const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(i, v);
        i.dispatchEvent(new Event('input', { bubbles: true })); i.dispatchEvent(new Event('change', { bubbles: true })); return true; };
      return poner('input#ion-input-0', ${JSON.stringify(process.env.TEL_USUARIO || '')}) && poner('input#ion-input-1', ${JSON.stringify(process.env.TEL_CLAVE || '')});
    })()`);
    await dormir(300);
    await pulsar('button.login-button');
    await enReposo(2500, 40000);
    const msg = await js(`(document.querySelector('.mensaje-login') || {}).textContent || ''`);
    const dentro = !(await esperarVisible('input#ion-input-0', 500));
    anota({ tipo: 'login', intento: 0, dentro, mensaje: msg.trim().replace(/\s+/g, ' ') });
    if (!dentro) throw new Error(`no entró: ${msg.trim().slice(0, 80) || 'sin mensaje'}`);
  },
  // Volver al inicio desde donde sea.
  inicio: async () => { await pulsar('ion-tab-button[ng-reflect-router-link="/tabs/home"], ion-tab-button[tab="home"]'); await enReposo(); },
  cursos: async () => { await pulsar('ion-tab-button[ng-reflect-router-link="/tabs/courses"], ion-tab-button[tab="courses"]'); await enReposo(); },
  curso: async () => {
    await pulsar('ion-tab-button[ng-reflect-router-link="/tabs/courses"], ion-tab-button[tab="courses"]'); await enReposo(1000, 8000);
    if (!(await esperarVisible('div.course-card'))) throw new Error('no hay tarjetas de curso');
    // La primera tarjeta: para el aprendiz del perfil es el curso estándar 23542.
    await js(`(() => { const c = [...document.querySelectorAll('div.course-card')].find(e => e.getBoundingClientRect().width > 0); c.click(); return true; })()`);
    await enReposo();
  },
  calificaciones: async () => {
    if (!(await esperarVisible('button.grades-button', 3000))) await GESTOS.curso();
    if (!(await pulsar('button.grades-button'))) throw new Error('sin botón de calificaciones');
    await enReposo();
  },
  calendario: async () => { await pulsar('ion-tab-button[ng-reflect-router-link="/tabs/calendar"], ion-tab-button[tab="calendar"]'); await enReposo(); },
  notificaciones: async () => {
    if (!(await esperarVisible('div.notification-bell-container', 3000))) await GESTOS.inicio();
    if (!(await pulsar('div.notification-bell-container'))) throw new Error('sin campana de notificaciones');
    await enReposo();
  },
  arranque: async () => {
    // Recarga la app entera con la sesión guardada: es el arranque en frío del modelo.
    await enviar('Page.reload', { ignoreCache: false });
    await dormir(2500);
    await enReposo(2000, 30000);
  },
  atras: async () => { await js('history.back(); true'); await enReposo(); },
  // ---- flujo de sesión (lo que cambia la fase 0 del plan de capacidad) ----------------------
  // Cerrar sesión desde el menú lateral: debe volver a la pantalla de login.
  salir: async () => {
    if (await esperarVisible('input#ion-input-0', 1500)) { anota({ tipo: 'nota', texto: 'ya estaba en el login' }); return; }
    if (!(await pulsar('ion-tab-button[aria-controls="menu-principal"]'))) throw new Error('sin botón del menú');
    await dormir(600);
    if (!(await pulsar('button.logout-btn'))) throw new Error('sin botón de cerrar sesión');
    await enReposo(1500, 20000);
    if (!(await esperarVisible('input#ion-input-0', 10000))) throw new Error('tras cerrar sesión no apareció el login');
    anota({ tipo: 'nota', texto: 'cerrar sesión → pantalla de login' });
  },
  // Contraseña equivocada N veces (TEL_INTENTOS, 11 por omisión) sobre la cuenta del perfil: el
  // mensaje de cada intento queda anotado. Con el cupo por cuenta (10/min) el undécimo debe
  // decir «Demasiados intentos».
  fuerzaBruta: async () => {
    const n = Number(process.env.TEL_INTENTOS || 11);
    if (!(await esperarVisible('input#ion-input-0', 8000))) throw new Error('no hay pantalla de login');
    for (let i = 1; i <= n; i++) {
      await js(`(() => {
        const poner = (sel, v) => { const el = document.querySelector(sel); if (!el) return false;
          const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(el, v);
          el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); return true; };
        return poner('input#ion-input-0', ${JSON.stringify(process.env.TEL_USUARIO || '')}) && poner('input#ion-input-1', 'contrasena-equivocada-' + ${i});
      })()`);
      await dormir(300);
      await pulsar('button.login-button');
      await enReposo(1200, 30000);
      const msg = await js(`(document.querySelector('.mensaje-login') || {}).textContent || ''`);
      anota({ tipo: 'login', intento: i, mensaje: msg.trim().replace(/\s+/g, ' ') });
      console.log(`    intento ${i}: ${msg.trim().replace(/\s+/g, ' ').slice(0, 90)}`);
    }
  },
  // Deja pasar la ventana del cupo (61 s) antes de volver a entrar.
  esperar: async () => { await dormir(61000); },
};

async function dom() {
  const r = await js(`(() => {
    const vis = (e) => { const b = e.getBoundingClientRect(); return b.width > 0 && b.height > 0; };
    const sel = 'ion-tab-button, ion-button, ion-card, ion-item, a[href], button, [routerlink], ion-segment-button, ion-input, input';
    return [...document.querySelectorAll(sel)].filter(vis).slice(0, 80).map(e => ({
      tag: e.tagName.toLowerCase(), id: e.id || '', cls: (e.className && e.className.baseVal === undefined ? String(e.className) : '').slice(0, 60),
      tab: e.getAttribute('tab') || '', href: e.getAttribute('href') || e.getAttribute('routerlink') || '', texto: (e.innerText || e.getAttribute('aria-label') || '').trim().replace(/\\s+/g, ' ').slice(0, 50),
    }));
  })()`);
  console.log(JSON.stringify({ url: await js('location.href'), elementos: r }, null, 1));
}

async function main() {
  await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej); });
  await enviar('Runtime.enable');
  await enviar('Page.enable');
  if (RECORRIDOS[0] === 'dom') { await dom(); ws.close(); return; }

  console.log(`teléfono: ${RECORRIDOS.join(' → ')} × ${REPES}`);
  for (let repe = 1; repe <= REPES; repe++) {
    repeActual = repe;
    for (const nombre of RECORRIDOS) {
      const g = GESTOS[nombre];
      if (!g) { console.log(`  (gesto desconocido: ${nombre})`); continue; }
      recorridoActual = nombre;
      const t0 = Date.now();
      try { await g(); } catch (e) { anota({ tipo: 'fallo', recorrido: nombre, repe, error: String(e.message) }); console.log(`  ${nombre}: ${e.message}`); }
      const dur = Date.now() - t0;
      const mias = [...peticiones.values()].filter((p) => p.recorrido === nombre && p.repe === repe);
      const fines = mias.filter((p) => p.fin);
      const hasta = fines.length ? Math.max(...fines.map((p) => p.fin)) - Math.min(...mias.map((p) => p.inicio)) : null;
      anota({ tipo: 'recorrido', recorrido: nombre, repe, ms_gesto: dur, peticiones: mias.length, ms_hasta_ultima_respuesta: hasta });
      console.log(`  ${repe}/${REPES} ${nombre.padEnd(15)} ${String(mias.length).padStart(2)} peticiones · hasta la última respuesta ${hasta === null ? '—' : hasta + ' ms'}`);
      await dormir(1500 + Math.random() * 1500);
    }
  }
  // Resumen por petición y por recorrido.
  const filas = [...peticiones.values()].filter((p) => p.inicio);
  const csv = ['rid,recorrido,repe,metodo,url,inicio,fin,ms_telefono,estado,ms_servidor'];
  for (const p of filas) csv.push([p.rid, p.recorrido, p.repe, p.metodo, (p.url || '').replace(/^https?:\/\/[^/]+/, '').split('?')[0], p.inicio, p.fin || '', p.ms ?? '', p.estado ?? '', p.servidor ?? ''].join(','));
  fs.writeFileSync(path.join(SALIDA, 'peticiones.csv'), csv.join('\n') + '\n');
  const porRuta = {};
  for (const p of filas) {
    if (p.ms == null) continue;
    const k = `${p.metodo} ${(p.url || '').replace(/^https?:\/\/[^/]+/, '').split('?')[0].replace(/\/\d+/g, '/{id}')}`;
    (porRuta[k] = porRuta[k] || []).push(p);
  }
  const pct = (xs, q) => { const s = [...xs].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.round(q * (s.length - 1)))]; };
  const L = ['# Extremo a extremo desde el teléfono', '', `Recorridos: ${RECORRIDOS.join(', ')} × ${REPES}. ${filas.length} peticiones.`, '',
    '| Ruta | n | teléfono p50 | teléfono p95 | servidor p50 | red ida y vuelta p50 |', '|---|---:|---:|---:|---:|---:|'];
  for (const [k, xs] of Object.entries(porRuta).sort((a, b) => b[1].length - a[1].length)) {
    const tel = xs.map((p) => p.ms); const srv = xs.filter((p) => p.servidor != null);
    const red = srv.map((p) => p.ms - p.servidor);
    L.push(`| \`${k}\` | ${xs.length} | ${pct(tel, 0.5)} ms | ${pct(tel, 0.95)} ms | ${srv.length ? pct(srv.map((p) => p.servidor), 0.5) + ' ms' : '—'} | ${red.length ? pct(red, 0.5) + ' ms' : '—'} |`);
  }
  fs.writeFileSync(path.join(SALIDA, 'RESUMEN.md'), L.join('\n') + '\n');
  console.log(L.slice(4).join('\n'));
  ws.close();
}

main().catch((e) => { console.error('telefono:', e.message); process.exit(1); });
