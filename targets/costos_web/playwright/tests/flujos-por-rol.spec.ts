// RECORRIDO DE PANTALLAS EN NAVEGADOR, ROL POR ROL.
//
// Por qué hace falta además de la matriz de autorización. La matriz habla con el API y responde
// "¿este rol puede?". No abre una sola pantalla. Un cambio que rompa el renderizado —una imagen
// que deja de resolver, un import que no existe, un error de JavaScript al montar— pasa la matriz
// entera en verde y deja la aplicación inservible para el usuario.
//
// Este recorrido se escribió para respaldar la corrección de R8 §3.13: 622 referencias a
// imágenes cambiaron de ruta absoluta "/src/assets/X.svg" a imports con alias "@/assets/X.svg".
// El riesgo de esa clase de cambio no está en el API sino en pantallas internas que ninguna
// prueba de API llega a dibujar. Aquí se entra con cada rol y se comprueba, pantalla a pantalla:
//
//   a) que la ruta se alcanza y no rebota al acceso (la sesión y el guard funcionan),
//   b) que NINGUNA imagen queda rota (naturalWidth === 0 tras la carga),
//   c) que no hay peticiones fallidas de recursos (404 de assets),
//   d) que no hay errores de JavaScript en consola.
//
// El rol 6 (PARTICIPANTE) es un perfil interno que NO debe acceder: se comprueba que se le
// deniega con un motivo visible, que es tan importante como que los demás entren.
import { test, expect, Page } from '@playwright/test';

// Sin BASE_URL no hay objetivo. Fallar aquí es más honesto que traer un valor por defecto:
// una dirección incrustada sobrevive al despliegue que la motivó y acaba midiendo el
// servidor equivocado en verde. Se declara en targets/costos_web/target.env.local.
const BASE = process.env.BASE_URL || '';
if (!BASE) throw new Error('BASE_URL no declarado — ver targets/costos_web/target.env.local.example');

type RolId = 1 | 2 | 3 | 4 | 5 | 6;

const CUENTAS: Record<RolId, { nombre: string; user?: string; pass?: string }> = {
  1: { nombre: 'ADMINISTRADOR', user: process.env.ROL1_ADMINISTRADOR_USER, pass: process.env.ROL1_ADMINISTRADOR_PASS },
  2: { nombre: 'DELEGADO', user: process.env.ROL2_DELEGADO_USER, pass: process.env.ROL2_DELEGADO_PASS },
  3: { nombre: 'DIRECTOR', user: process.env.ROL3_DIRECTOR_USER, pass: process.env.ROL3_DIRECTOR_PASS },
  4: { nombre: 'SUBDIRECTOR', user: process.env.ROL4_SUBDIRECTOR_USER, pass: process.env.ROL4_SUBDIRECTOR_PASS },
  5: { nombre: 'COORDINADOR', user: process.env.ROL5_COORDINADOR_USER, pass: process.env.ROL5_COORDINADOR_PASS },
  6: { nombre: 'PARTICIPANTE', user: process.env.ROL6_PARTICIPANTE_USER, pass: process.env.ROL6_PARTICIPANTE_PASS },
};

// Pantallas que cada rol debe poder abrir. Sale de router/index.js (meta.roles) cruzado con
// routes/api.php: es la política declarada, no lo que la aplicación haga hoy.
const PANTALLAS: Record<RolId, string[]> = {
  1: ['/inicioadmin', '/administradorusuarios', '/seguimientoformularios', '/seguimientointegrantes',
      '/seguimientoapertura', '/crudentidades', '/gestorguias', '/gestorpreguntas',
      '/reporteformularios', '/costocupovigencia', '/reportenivelformacion'],
  2: ['/seguimientoformularios', '/administradorusuarios', '/seguimientointegrantes', '/seguimientoapertura'],
  3: ['/administradorgrupos', '/verificarintegrantes', '/preguntasfrecuentes'],
  4: ['/administradorgrupos', '/verificarintegrantes', '/preguntasfrecuentes'],
  5: ['/verificarintegrantes', '/preguntasfrecuentes'],
  // Rol 6 (PARTICIPANTE): perfil interno, sin acceso. Su comprobación va aparte, al final.
  6: [],
};

// Ruido de terceros que no habla del estado de la aplicación.
const RUIDO = /favicon|fonts\.googleapis|fonts\.gstatic|ERR_INTERNET_DISCONNECTED/i;

async function entrar(page: Page, user: string, pass: string) {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await page.locator('input[type="email"], input[type="text"]').first().fill(user);
  await page.locator('input[type="password"]').first().fill(pass);
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/login'), { timeout: 20_000 }).catch(() => null),
    page.locator('button:has-text("Ingresar")').first().click(),
  ]);
  // La SPA redirige por rol tras cargar /api/me.
  await page.waitForTimeout(2500);
}

// El rol 6 no entra en este recorrido: no debe acceder. Su comprobación va aparte, al final.
for (const rol of [1, 2, 3, 4, 5] as RolId[]) {
  const cuenta = CUENTAS[rol];

  test.describe(`rol ${rol} — ${cuenta.nombre}`, () => {
    test.skip(!cuenta.user || !cuenta.pass, `sin cuenta configurada para el rol ${rol}`);

    test(`recorre sus pantallas sin imágenes rotas ni errores`, async ({ browser }) => {
      test.setTimeout(180_000);
      const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
      const page = await ctx.newPage();

      const errores: string[] = [];
      const fallidas: string[] = [];
      // Las llamadas al API se anotan aparte y CON la ruta: un 403 aquí significa que la
      // pantalla que el rol tiene permitida está pidiendo algo que el API le niega —
      // la misma clase de defecto que R7 §3.16 y §3.18.
      const apiDenegadas: string[] = [];
      page.on('console', (m) => {
        if (m.type() === 'error' && !RUIDO.test(m.text())) errores.push(m.text());
      });
      page.on('response', (r) => {
        if (r.status() < 400 || RUIDO.test(r.url())) return;
        const linea = `${r.status()} ${r.url().replace(BASE, '')}`;
        if (r.url().includes('/api/')) apiDenegadas.push(linea);
        else fallidas.push(linea);
      });

      await entrar(page, cuenta.user!, cuenta.pass!);
      expect(page.url(), `el rol ${rol} no consiguió entrar: sigue en el acceso`).not.toContain('/login');

      const rotas: string[] = [];
      for (const ruta of PANTALLAS[rol]) {
        await page.goto(`${BASE}${ruta}`, { waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(2000);

        // Comprobación fuerte: hay que HABER LLEGADO. Antes solo se miraba que no acabara en
        // el acceso, y una pantalla a la que el guard desviaba se apuntaba como visitada.
        expect(new URL(page.url()).pathname,
          `${ruta}: no se llegó (el guard desvió; revisar meta.roles frente a la política)`).toBe(ruta);

        // Imágenes rotas: cargadas pero sin dimensiones. Es el síntoma exacto de una ruta de
        // asset que ya no resuelve — el fallo que §3.13 podía introducir.
        const malas = await page.evaluate(() =>
          [...document.querySelectorAll('img')]
            .filter((im) => im.complete && im.naturalWidth === 0 && im.src)
            .map((im) => im.getAttribute('src') || im.src)
        );
        for (const m of malas) rotas.push(`${ruta} -> ${m}`);
      }

      expect(rotas, `imágenes rotas:\n    ${rotas.join('\n    ')}`).toEqual([]);
      expect(fallidas, `recursos que no cargaron:\n    ${[...new Set(fallidas)].join('\n    ')}`).toEqual([]);
      expect([...new Set(apiDenegadas)],
        `la interfaz de este rol llama a endpoints que el API le niega:\n    ${[...new Set(apiDenegadas)].join('\n    ')}`)
        .toEqual([]);
      // Los errores de consola provocados por esas mismas llamadas se informan aparte para no
      // duplicar el diagnóstico: si apiDenegadas está vacío, esto solo captura fallos de JS.
      const soloJs = [...new Set(errores)].filter((e) => !/Failed to load resource/.test(e));
      expect(soloJs, `errores de JavaScript:\n    ${soloJs.slice(0, 8).join('\n    ')}`).toEqual([]);

      await ctx.close();
    });
  });
}

test.describe('rol 6 — PARTICIPANTE no accede a la aplicación', () => {
  const c = CUENTAS[6];
  test.skip(!c.user || !c.pass, 'sin cuenta de participante');

  // R8 §3.25 — antes este rol quedaba rebotando contra el acceso sin explicación, porque
  // redireccionPorRol() devolvía '/login' y el guard volvía a pedirle destino. Ahora se le
  // cierra la sesión y se le dice por qué.
  test('se le deniega el acceso indicando el motivo, sin bucle', async ({ browser }) => {
    test.setTimeout(120_000);
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
    const page = await ctx.newPage();

    await entrar(page, c.user!, c.pass!);
    expect(page.url(), 'el participante entró a la aplicación').toContain('/login');
    const aviso = await page.locator('.error-message').first().textContent().catch(() => '');
    expect((aviso || '').toLowerCase(),
      'no se le indica el motivo del rechazo').toContain('no cuenta con acceso');

    await page.goto(`${BASE}/inicioadmin`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    expect(page.url(), 'el participante alcanzó el área administrativa').not.toContain('/inicioadmin');

    await ctx.close();
  });
});
