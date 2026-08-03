// GENERIC — runs against any project, no business knowledge required.
//
// Presupuesto del HILO PRINCIPAL del navegador.
//
// Por qué existe esta spec. Costos Web R8 §3.22: la aplicación "se pegaba" y ni k6 ni ZAP ni
// la matriz de autorización lo veían, porque el servidor estaba sano — php-fpm al 0 %, la API
// respondiendo en 27 ms. El trabajo caro ocurría *dentro del navegador*: 18 MB de imágenes que
// en realidad eran mapas de bits incrustados en un envoltorio SVG, descodificados y rasterizados
// en el hilo principal. Todo el laboratorio medía el lado del servidor; nadie medía el lado del
// usuario, que es donde se sufría el defecto.
//
// Qué la hace ANTICIPATORIA y no meramente descriptiva. Tres decisiones:
//
//   1. No mide solo lo que la primera pantalla descarga: rastrea el bundle en busca de TODAS las
//      imágenes referenciadas. La pantalla de acceso nunca carga el icono de 3 MB del gestor de
//      guías; el usuario lo paga tres pantallas después. Un presupuesto que solo mira la portada
//      declara sano un despliegue que se congelará más tarde.
//
//   2. Cuenta MEGAPÍXELES DESCODIFICADOS, no bytes. Es la magnitud que predice el bloqueo: un PNG
//      de 200 KB y 4000x3000 ocupa 48 MB de mapa de bits en RAM y cuesta lo mismo descodificar
//      esté comprimido como esté. Recomprimir baja los bytes y deja el congelamiento intacto —
//      exactamente lo que pasó en el primer intento de corrección de §3.22.
//
//   3. Mide con la CPU FRENADA (Emulation.setCPUThrottlingRate). En la máquina del equipo de
//      desarrollo nada se congela nunca; el defecto aparece en el portátil del funcionario. El
//      frenado convierte "a mí me funciona" en un número reproducible.
//
// Presupuestos, todos configurables por target.env (los valores por defecto son deliberadamente
// laxos: esta spec debe delatar catástrofes, no imponer una dieta a proyectos sanos).
//
//   PERF_IMG_TOTAL_KB   peso sumado de las imágenes del bundle           (def. 2048 KB)
//   PERF_IMG_MAX_KB     peso de la imagen más pesada                     (def. 300 KB)
//   PERF_IMG_MAX_MPX    megapíxeles descodificados sumados               (def. 8 MPx = 32 MB RAM)
//   PERF_TBT_MS         tiempo total de bloqueo durante la carga         (def. 600 ms)
//   PERF_LONGTASK_MS    peor tarea larga individual                      (def. 250 ms)
//   PERF_CPU_THROTTLE   factor de frenado de CPU                         (def. 4)
//   PERF_BUDGET_PATH    ruta a medir                                     (def. /)
//   PERF_BUDGET_SKIP    "1" para saltar la spec en un target sin frontend
//
import { test, expect } from '@playwright/test';

const BASE = process.env.BASE_URL || 'http://localhost:8099';
const PATH_ = process.env.PERF_BUDGET_PATH || '/';
const N = (v: string | undefined, d: number) => (v && !Number.isNaN(+v) ? +v : d);

const IMG_TOTAL_KB = N(process.env.PERF_IMG_TOTAL_KB, 2048);
const IMG_MAX_KB   = N(process.env.PERF_IMG_MAX_KB, 300);
const IMG_MAX_MPX  = N(process.env.PERF_IMG_MAX_MPX, 8);
const TBT_MS       = N(process.env.PERF_TBT_MS, 600);
const LONGTASK_MS  = N(process.env.PERF_LONGTASK_MS, 250);
const THROTTLE     = N(process.env.PERF_CPU_THROTTLE, 4);

const kb = (b: number) => `${(b / 1024).toFixed(0)} KB`;

type Img = { url: string; bytes: number; mpx: number; w: number; h: number; embedded: boolean };
type Report = {
  images: Img[]; totalBytes: number; totalMpx: number;
  longTasks: number[]; tbt: number; worstTask: number;
  loadMs: number; discovered: number;
};

test.describe('presupuesto del hilo principal (generic)', () => {
  test.skip(process.env.PERF_BUDGET_SKIP === '1', 'target sin frontend: presupuesto no aplica');

  let rep: Report;

  test.beforeAll(async ({ browser }) => {
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
    const page = await ctx.newPage();

    // Las tareas largas hay que observarlas desde antes del primer script de la página:
    // un PerformanceObserver instalado después ya perdió el arranque, que es justo el
    // momento donde se concentra el trabajo de descodificación.
    await page.addInitScript(() => {
      (window as any).__longTasks = [];
      try {
        new PerformanceObserver((l) => {
          for (const e of l.getEntries()) (window as any).__longTasks.push(e.duration);
        }).observe({ entryTypes: ['longtask'] });
      } catch { /* navegador sin longtask: se degrada a solo presupuesto de imagen */ }
    });

    const cdp = await ctx.newCDPSession(page);
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: THROTTLE });

    const t0 = Date.now();
    await page.goto(`${BASE}${PATH_}`, { waitUntil: 'load', timeout: 60_000 }).catch(() => {});
    // Margen para que la SPA hidrate y dispare la descodificación diferida.
    await page.waitForTimeout(3000);
    const loadMs = Date.now() - t0;

    await cdp.send('Emulation.setCPUThrottlingRate', { rate: 1 });

    const measured = await page.evaluate(async () => {
      // Las rutas se resuelven contra el fichero que las contiene, no contra el origen:
      // Vite emite los chunks perezosos como rutas relativas ("./Pantalla-hash.js"), y
      // resolverlas contra la raíz las convierte en 404 silenciosos — con lo que las
      // imágenes de las pantallas internas nunca se llegan a contar.
      const abs = (u: string, base: string) => { try { return new URL(u, base).href; } catch { return ''; } };
      const IMG_RE = /\.{0,2}\/[A-Za-z0-9_\-./]*\.(?:svg|png|jpe?g|webp|gif)/g;
      const found = new Set<string>();

      // (a) lo que la pantalla actual ya descargó
      for (const e of performance.getEntriesByType('resource')) {
        if (/\.(svg|png|jpe?g|webp|gif)(\?|$)/i.test(e.name)) found.add(e.name);
      }
      // (b) lo que el bundle referencia y el usuario pagará en pantallas posteriores.
      //     Este es el paso que convierte la medición en anticipación.
      //
      //     Hay que seguir los chunks de forma TRANSITIVA. La pantalla de acceso solo carga
      //     index-*.js; las pantallas internas viven en chunks que se piden al navegar, y ahí
      //     es donde están las imágenes pesadas. Quedarse en el primer nivel deja pasar
      //     justamente el caso de §3.22 (el icono de 3 MB del gestor de guías).
      const JS_RE = /\.{0,2}\/[A-Za-z0-9_\-./]*\.js/g;
      const vistos = new Set<string>();
      const cola: string[] = [];
      for (const e of performance.getEntriesByType('resource')) {
        if (/\.js(\?|$)/i.test(e.name) && e.name.startsWith(location.origin)) cola.push(e.name);
      }
      while (cola.length) {
        const js = cola.shift()!;
        if (vistos.has(js)) continue;
        vistos.add(js);
        if (vistos.size > 200) break;            // cota de seguridad
        try {
          const txt = await (await fetch(js)).text();
          for (const m of txt.match(IMG_RE) || []) { const u = abs(m, js); if (u) found.add(u); }
          for (const m of txt.match(JS_RE) || []) {
            const u = abs(m, js);
            if (u && !vistos.has(u) && u.startsWith(location.origin)) cola.push(u);
          }
        } catch { /* recurso de otro origen: no es nuestro presupuesto */ }
      }

      const dims = (src: string) => new Promise<{ w: number; h: number }>((res) => {
        const im = new Image();
        im.onload = () => res({ w: im.naturalWidth, h: im.naturalHeight });
        im.onerror = () => res({ w: 0, h: 0 });
        im.src = src;
      });

      const out: any[] = [];
      for (const url of found) {
        let bytes = 0, mpx = 0, w = 0, h = 0, embedded = false;
        try {
          const r = await fetch(url);
          const buf = await r.arrayBuffer();
          bytes = buf.byteLength;

          if (/\.svg(\?|$)/i.test(url)) {
            const txt = new TextDecoder().decode(buf);
            // Un SVG con mapas de bits incrustados NO cuesta lo que dice su atributo width:
            // cuesta lo que midan los rasters de dentro. Es la trampa de §3.22.
            const uris = txt.match(/data:image\/(?:png|jpe?g|webp|gif);base64,[A-Za-z0-9+/=]+/g);
            if (uris && uris.length) {
              embedded = true;
              for (const du of uris) { const d = await dims(du); mpx += (d.w * d.h) / 1e6; w = Math.max(w, d.w); h = Math.max(h, d.h); }
            } else {
              const d = await dims(url); w = d.w; h = d.h; mpx = (d.w * d.h) / 1e6;
            }
          } else {
            const d = await dims(url); w = d.w; h = d.h; mpx = (d.w * d.h) / 1e6;
          }
        } catch { /* inalcanzable: no se contabiliza */ }
        out.push({ url, bytes, mpx, w, h, embedded });
      }

      const lt: number[] = (window as any).__longTasks || [];
      return {
        images: out,
        totalBytes: out.reduce((a, i) => a + i.bytes, 0),
        totalMpx: out.reduce((a, i) => a + i.mpx, 0),
        longTasks: lt,
        // Total Blocking Time: de cada tarea larga solo cuenta lo que excede de 50 ms,
        // que es el umbral a partir del cual el usuario percibe que no responde.
        tbt: lt.reduce((a, d) => a + Math.max(0, d - 50), 0),
        worstTask: lt.length ? Math.max(...lt) : 0,
        discovered: found.size,
      };
    });

    rep = { ...measured, loadMs } as Report;
    await ctx.close();

    const top = [...rep.images].sort((a, b) => b.bytes - a.bytes).slice(0, 8);
    console.log(`\n  presupuesto del hilo principal — ${BASE}${PATH_}  (CPU x${THROTTLE} más lenta)`);
    console.log(`  imagenes descubiertas : ${rep.discovered}`);
    console.log(`  peso total            : ${kb(rep.totalBytes)}   (presupuesto ${IMG_TOTAL_KB} KB)`);
    console.log(`  megapixeles a decodif.: ${rep.totalMpx.toFixed(1)} MPx  =  ${(rep.totalMpx * 4).toFixed(0)} MB de RAM   (presupuesto ${IMG_MAX_MPX} MPx)`);
    console.log(`  tareas largas         : ${rep.longTasks.length}  TBT ${rep.tbt.toFixed(0)} ms  peor ${rep.worstTask.toFixed(0)} ms`);
    console.log(`  carga completa        : ${rep.loadMs} ms`);
    for (const i of top) {
      const flag = i.embedded ? '  <- mapa de bits incrustado en SVG' : '';
      console.log(`     ${kb(i.bytes).padStart(9)}  ${i.w}x${i.h}  ${i.url.replace(BASE, '')}${flag}`);
    }
    console.log('');
  });

  test('el peso total de las imágenes cabe en el presupuesto', () => {
    const mb = (rep.totalBytes / 1048576).toFixed(2);
    expect(rep.totalBytes / 1024,
      `las imágenes del bundle suman ${mb} MB (presupuesto ${IMG_TOTAL_KB} KB). ` +
      `Cada recarga con caché fría vuelve a pagarlo.`
    ).toBeLessThanOrEqual(IMG_TOTAL_KB);
  });

  test('ninguna imagen individual excede el presupuesto', () => {
    const gordas = rep.images.filter((i) => i.bytes / 1024 > IMG_MAX_KB)
      .sort((a, b) => b.bytes - a.bytes)
      .map((i) => `${i.url.replace(BASE, '')} = ${kb(i.bytes)}${i.embedded ? ' (mapa de bits dentro de un SVG)' : ''}`);
    expect(gordas, `imágenes por encima de ${IMG_MAX_KB} KB:\n    ${gordas.join('\n    ')}`).toEqual([]);
  });

  test('los megapíxeles a descodificar caben en el presupuesto', () => {
    // El predictor. Los bytes se arreglan recomprimiendo; los megapíxeles solo bajan
    // redimensionando, y son los que bloquean el hilo principal y ocupan la RAM.
    const peores = [...rep.images].filter((i) => i.mpx > 0.5).sort((a, b) => b.mpx - a.mpx).slice(0, 5)
      .map((i) => `${i.url.replace(BASE, '')} = ${i.w}x${i.h} (${i.mpx.toFixed(1)} MPx)`);
    expect(rep.totalMpx,
      `hay que descodificar ${rep.totalMpx.toFixed(1)} MPx = ${(rep.totalMpx * 4).toFixed(0)} MB de mapa de bits ` +
      `(presupuesto ${IMG_MAX_MPX} MPx). Los mayores:\n    ${peores.join('\n    ')}\n` +
      `  Recomprimir NO baja este número: hay que redimensionar al tamaño en que se pintan.`
    ).toBeLessThanOrEqual(IMG_MAX_MPX);
  });

  test('el hilo principal no se bloquea más allá del presupuesto', () => {
    expect(rep.tbt,
      `tiempo total de bloqueo ${rep.tbt.toFixed(0)} ms con la CPU frenada x${THROTTLE} ` +
      `(presupuesto ${TBT_MS} ms). Mientras bloquea, la pestaña no responde a clics ni scroll.`
    ).toBeLessThanOrEqual(TBT_MS);
  });

  test('ninguna tarea individual congela la interfaz', () => {
    expect(rep.worstTask,
      `la peor tarea larga duró ${rep.worstTask.toFixed(0)} ms (presupuesto ${LONGTASK_MS} ms). ` +
      `Por encima de ~200 ms el usuario lo percibe como que la página se colgó.`
    ).toBeLessThanOrEqual(LONGTASK_MS);
  });
});
