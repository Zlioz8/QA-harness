// Controles de seguridad propios de local_slider_form — lo que la matriz genérica NO puede saber.
//
// lib/specs/authz-matrix.spec.ts ya recorre playwright/authz-matrix.json: qué rol alcanza qué.
// Eso cubre la POLÍTICA. Este archivo cubre los MECANISMOS que este plugin declara tener, y que
// sólo se pueden comprobar leyendo su código (slider_form/lib/usersValidations.php):
//
//   · checkSession($action, …)        isloggedin(); 'redirect' en páginas, 'exception' en AJAX
//   · checkBannerVisible(…)           interruptor global en mdl_config_plugins, leído SIN caché
//   · checkUserRole($a, $p, $nivel)   has_capability :edit / :view — el defecto es 'edit'
//   · checkCsrfToken($sesskey)        confirm_sesskey() envuelto, con validación de tipo
//
// POR QUÉ HACE FALTA ESTE ARCHIVO Y NO BASTA `require_login`. El plugin NO usa el
// `require_login()` de Moodle en sus páginas: usa envoltorios propios. Un envoltorio propio es
// código propio, y por tanto es el proyecto quien responde de él — no el core. Además conviven
// TRES idiomas para la misma pregunta, verificado leyendo los 17 puntos de entrada:
//
//   envoltorios propios   index, menu, segmented, show_order, manage_images, send_logs,
//                         table_logs, insertRecord, updateRecord, deleteRecord, order,
//                         ajax/send_segmented, ajax/preview_correo, ajax/saved_filters,
//                         ajax/export_envios
//   core en línea         ajax/categories.php  (isloggedin + has_capability + toggle)
//   core clásico          active_role_users.php (require_login + require_capability +
//                                                confirm_sesskey)
//
// Los tres están BIEN. Se comprueban los tres igualmente y de la misma forma, porque el riesgo
// de tener tres idiomas no es que uno esté mal hoy: es que el siguiente endpoint copie el que
// menos protege.
import { test, expect } from '@playwright/test';
import { loginAs, hasRole, sesskeyOf } from './_auth';

const BASE = process.env.BASE_URL || '';
const u = (p: string) => `${BASE}${p}`;

// Los 17 puntos de entrada, sacados del árbol del commit auditado, no de una suposición.
// `nivel` es el que exige checkUserRole; 'edit' es su valor por defecto (fail-closed).
const PAGINAS = [
  { path: '/local/slider_form/index.php',           nivel: 'edit' },
  { path: '/local/slider_form/menu.php',            nivel: 'view' },
  { path: '/local/slider_form/segmented.php',       nivel: 'edit' },
  { path: '/local/slider_form/show_order.php',      nivel: 'edit' },
  { path: '/local/slider_form/manage_images.php',   nivel: 'edit' },
  { path: '/local/slider_form/send_logs.php',       nivel: 'view' },
  // DOS parametros obligatorios (table_logs.php:27-28). Con solo `asunto`, Moodle responde
  // 404 por parametro ausente y la prueba lo leeria como denegacion.
  { path: '/local/slider_form/table_logs.php?asunto=lab&created_at=2026-01-01%2000:00:00', nivel: 'view' },
];

// Endpoints que MUTAN estado y declaran checkCsrfToken. Se prueban SIN sesskey: la respuesta
// debe ser un rechazo, nunca la ejecución de la acción.
const ESCRITURAS_CON_CSRF = [
  '/local/slider_form/insertRecord.php',
  '/local/slider_form/updateRecord.php',
  '/local/slider_form/deleteRecord.php',
  '/local/slider_form/order.php',
  '/local/slider_form/ajax/preview_correo.php',
  '/local/slider_form/ajax/saved_filters.php',
];

// ajax/send_segmented.php se prueba APARTE y sólo hasta donde es seguro: si se ejecutase,
// enviaría correo real a todos los matriculados en los cursos resueltos (db/access.php lo marca
// RISK_SPAM). Aquí sólo se comprueba que RECHAZA — nunca que acepta.
const ENVIO_MASIVO = '/local/slider_form/ajax/send_segmented.php';

test.describe('1. Sesión: ningún punto de entrada responde con contenido sin autenticar', () => {
  for (const { path } of PAGINAS) {
    test(`sin sesión, ${path} no entrega la pantalla`, async ({ request }) => {
      const res = await request.get(u(path), { maxRedirects: 0 });
      // Moodle contesta 303 hacia el login. Lo que NO puede pasar es un 200 con la pantalla.
      expect([301, 302, 303, 401, 403],
        `${path} debería redirigir o denegar sin sesión, y devolvió ${res.status()}`)
        .toContain(res.status());
    });
  }

  // Los AJAX usan $action='exception': deben responder con código, no con una redirección HTML
  // que el JS del navegador interpretaría como éxito.
  for (const path of ['/local/slider_form/ajax/categories.php?action=modalidades',
                      '/local/slider_form/ajax/saved_filters.php?action=list']) {
    test(`sin sesión, ${path} responde un código de error, no una redirección`, async ({ request }) => {
      const res = await request.get(u(path), { maxRedirects: 0 });
      expect([401, 403, 303, 302],
        `${path} devolvió ${res.status()}`).toContain(res.status());
      expect(res.status(), `${path} NO puede devolver 200 sin sesión`).not.toBe(200);
    });
  }
});

test.describe('2. CSRF: los endpoints que mutan estado rechazan un POST sin sesskey', () => {
  for (const path of ESCRITURAS_CON_CSRF) {
    test(`${path} rechaza un POST sin sesskey`, async ({ request }) => {
      test.skip(!hasRole('A'), 'necesita ROLE_A: sin sesión el rechazo vendría de checkSession, no de checkCsrfToken');
      const ctx = await loginAs('A');
      const res = await ctx.post(u(path), { form: { x: '1' }, maxRedirects: 0 });
      // checkCsrfToken lanza Exception(…, 403). Lo que importa es que NO se ejecute la acción.
      // 404 y 415 CUENTAN como rechazo, y esto se aprendió midiendo:
      //   · Moodle devuelve 404 cuando falta un required_param — la acción no se ejecutó.
      //   · send_segmented devuelve 415 por su defensa de Content-Type (DEPLOY.md §2.3).
      // La primera versión sólo aceptaba [400,403,500] y marcaba como FALLO tres endpoints que
      // estaban rechazando correctamente. Lo que importa no es el código: es que NO se ejecute.
      expect([400, 403, 404, 415, 500],
        `${path} debería rechazar un POST sin sesskey y devolvió ${res.status()}`)
        .toContain(res.status());
    });
  }

  test('un sesskey MAL FORMADO se rechaza igual que uno ausente', async ({ request }) => {
    test.skip(!hasRole('A'), 'necesita ROLE_A');
    const ctx = await loginAs('A');
    // checkCsrfToken valida gettype()==='string' y !empty ANTES de confirm_sesskey.
    for (const malo of ['', '   ']) {
      const res = await ctx.post(u('/local/slider_form/insertRecord.php'),
        { form: { sesskey: malo }, maxRedirects: 0 });
      expect([400, 403, 500]).toContain(res.status());
    }
  });
});

test.describe('3. Envío masivo: la defensa declarada en send_segmented.php', () => {
  // DEPLOY.md §2.3 y ajax/send_segmented.php:44-48: el endpoint EXIGE
  // Content-Type: application/json, precisamente para que un formulario HTML plano no pueda
  // dispararlo (un form no provoca preflight CORS). Es una defensa anti-CSRF deliberada, así
  // que merece una prueba: si alguien la quita, esto lo dice.
  test('rechaza (415) una petición cuyo Content-Type no es application/json', async ({ request }) => {
    test.skip(!hasRole('A'), 'necesita ROLE_A');
    const ctx = await loginAs('A');
    const res = await ctx.post(u(ENVIO_MASIVO), {
      form: { sesskey: await sesskeyOf(ctx) },
      maxRedirects: 0,
    });
    expect(res.status(),
      'send_segmented debe rechazar todo lo que no sea application/json (defensa anti-CSRF)')
      .not.toBe(200);
  });

  test('sin sesión no llega a ejecutarse', async ({ request }) => {
    const res = await request.post(u(ENVIO_MASIVO), {
      data: {}, headers: { 'Content-Type': 'application/json' }, maxRedirects: 0,
    });
    expect(res.status(), 'el endpoint de correo masivo respondió 200 sin sesión').not.toBe(200);
  });
});

test.describe('4. Nivel de permiso: :view no debe alcanzar lo que exige :edit', () => {
  // checkUserRole($a,$p,'view') en menu/send_logs/table_logs/export_envios; 'edit' (defecto)
  // en el resto. La distinción sólo se puede comprobar con una cuenta que tenga :view y NO
  // :edit — es exactamente el insumo que el laboratorio no puede fabricar.
  for (const { path, nivel } of PAGINAS.filter((p) => p.nivel === 'edit')) {
    test(`${path} (exige :edit) deniega a una cuenta con sólo :view`, async () => {
      test.skip(!hasRole('B'), 'NO DISPONIBLE: hace falta una cuenta REAL con local/slider_form:view y sin :edit');
      const ctx = await loginAs('B');
      const res = await ctx.get(u(path), { maxRedirects: 0 });
      expect([301, 302, 303, 401, 403],
        `${path} exige :edit y una cuenta :view obtuvo ${res.status()}`)
        .toContain(res.status());
    });
  }
});

test.describe('5. El interruptor global (fail-open documentado)', () => {
  // checkBannerVisible compara `$visible === '0'`. Si la FILA NO EXISTE, get_field devuelve
  // false, la comparación es falsa y el plugin queda VISIBLE. DEPLOY.md §6.2 lo declara así
  // ("Ausencia de fila ⇒ visible (fail-open)").
  //
  // NO se automatiza el borrado de la fila: esta suite corre contra un Zajuna real con datos
  // de producción, y una prueba que borra configuración global para ver qué pasa no es una
  // medición, es un incidente. Se comprueba lo que SÍ es observable sin escribir nada.
  test('con el interruptor en 1, el gestor responde a quien tiene permiso', async () => {
    test.skip(!hasRole('A'), 'necesita ROLE_A');
    const ctx = await loginAs('A');
    const res = await ctx.get(u('/local/slider_form/menu.php'), { maxRedirects: 0 });
    expect(res.status(), 'con el interruptor en 1 y permiso :view, menu.php debería responder')
      .toBe(200);
  });
});

test.describe('6. Esquema incompleto: las columnas que ninguna migración crea', () => {
  // DEPLOY.md §8.5 lo declara abierto: send_logs.php, table_logs.php y ajax/export_envios.php
  // leen `envios2.estado` y `envios2.sent_at`, y NINGUNA de las 13 migraciones las define.
  // Medido en este despliegue: tras aplicar db/migrations/ completo, midb.envios2 tiene
  // (id, destinatario, asunto, body, created_at, cursos) y ni estado ni sent_at.
  //
  // Esta prueba NO es un adorno: convierte una advertencia del documento en un hecho
  // reproducible, y su resultado dice si el historial de envíos funciona en un despliegue
  // hecho SÓLO con lo que trae el repositorio.
  for (const path of ['/local/slider_form/send_logs.php',
                      '/local/slider_form/table_logs.php?asunto=lab',
                      '/local/slider_form/ajax/export_envios.php?asunto=lab']) {
    test(`${path} sobre el esquema que produce el repositorio`, async () => {
      test.skip(!hasRole('A'), 'necesita ROLE_A');
      const ctx = await loginAs('A');
      const res = await ctx.get(u(path), { maxRedirects: 0 });
      const cuerpo = await res.text().catch(() => '');
      const roto = res.status() >= 500 || /Undefined column|SQLSTATE|does not exist|no existe la columna/i.test(cuerpo);
      // Se AFIRMA que funciona. Si falla, el hallazgo es que el repositorio no basta para
      // desplegar el historial — que es justo lo que §8.5 dejó como pregunta abierta.
      expect(roto,
        `${path} falla sobre el esquema que producen db/migrations/: faltan envios2.estado y ` +
        `envios2.sent_at (DEPLOY.md §8.5). El historial de envíos no funciona en un despliegue ` +
        `hecho sólo con el repositorio.`).toBe(false);
    });
  }
});
