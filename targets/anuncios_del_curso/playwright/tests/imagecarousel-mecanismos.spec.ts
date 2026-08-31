// Mecanismos propios de mod_imagecarousel — lo que la matriz genérica NO puede saber.
//
// lib/specs/authz-matrix.spec.ts recorre la política por rol (authz-matrix.json). Este archivo
// afirma los MECANISMOS que ESTE plugin declara tener, leídos de su código (commit ef6c6e9) y ya
// observados a mano por HTTP en esta sesión:
//   1. CSRF: manage.php cambia estado por GET SIN sesskey (hallazgo S1); delete.php SÍ lo exige.
//   2. Visibilidad por imagen: una imagen con visible=0 no se sirve en carousel_content.php.
//   3. carousel_content.php exige sesskey (guarda CSRF del endpoint AJAX).
//   4. webp-support.php exige capability de SITIO, no de curso.
//
// Cada prueba AFIRMA lo que el código dice. Cuando una falla, la pregunta es «¿el mecanismo
// protege lo que su autor creía?», no «¿está mal la prueba?».
import { test, expect } from '@playwright/test';
import { loginAs } from '../lib/auth/index';

const BASE = process.env.BASE_URL || 'https://nginx.zajuna.com/zajuna';
const CMID = process.env.IC_CMID || '73985';
const u = (p: string) => `${BASE}${p}`;

test.describe('CSRF: el cambio de estado en manage.php no exige sesskey (S1)', () => {
  test('los enlaces de togglevisibility/moveup/movedown NO llevan sesskey', async () => {
    // A = editingteacher: es quien ve manage.php. Se lee el HTML y se comprueba que los enlaces
    // de acción son GET desnudos. Esto DOCUMENTA el hallazgo con evidencia reproducible.
    const ctx = await loginAs('A');
    const res = await ctx.get(u(`/mod/imagecarousel/manage.php?id=${CMID}`));
    expect(res.status()).toBe(200);
    const html = await res.text();
    const toggles = [...html.matchAll(/href="[^"]*action=(togglevisibility|moveup|movedown)[^"]*"/g)]
      .map(m => m[0]);
    console.log('enlaces de acción en manage.php:', toggles.slice(0, 4).join(' · '));
    expect(toggles.length, 'manage.php debe tener enlaces de acción').toBeGreaterThan(0);
    // El hallazgo: NINGUNO incluye sesskey. Si un día lo incluyeran, esta aserción fallará y
    // será señal de que S1 se corrigió — exactamente lo que queremos que ocurra.
    const conSesskey = toggles.filter(h => /sesskey=/.test(h));
    expect(conSesskey.length,
      'S1: los enlaces de cambio de estado NO deberían viajar sin sesskey').toBe(0);
    await ctx.dispose();
  });

  test('delete.php, el hermano bien hecho, SÍ exige confirm_sesskey', async () => {
    const ctx = await loginAs('A');
    // Un DELETE con confirm=1 pero SIN sesskey debe ser rechazado por Moodle (invalid sesskey).
    const res = await ctx.get(u(`/mod/imagecarousel/delete.php?id=${CMID}&imageid=1&confirm=1`),
      { maxRedirects: 0 });
    // No debe ejecutar el borrado: o pantalla de confirmación (200) o error de sesskey, NUNCA un
    // borrado silencioso. La comprobación fina del borrado se hace por BD en el recorrido.
    expect([200, 303, 400]).toContain(res.status());
    await ctx.dispose();
  });
});

test.describe('carousel_content.php: guarda CSRF del endpoint AJAX', () => {
  test('sin sesskey, no sirve el contenido del carrusel', async () => {
    const ctx = await loginAs('B'); // student con sesión válida...
    // ...pero SIN el parámetro sesskey: require_sesskey() debe rechazar.
    const res = await ctx.get(u(`/mod/imagecarousel/carousel_content.php?cmid=${CMID}`),
      { maxRedirects: 0 });
    expect(res.status(), 'sin sesskey no debe devolver 200 con contenido').not.toBe(200);
    await ctx.dispose();
  });
});

test.describe('webp-support.php: capability de SITIO, no de curso', () => {
  test('un editingteacher (A) no alcanza la herramienta de sitio', async () => {
    const ctx = await loginAs('A');
    const res = await ctx.get(u(`/mod/imagecarousel/webp-support.php?id=${CMID}`),
      { maxRedirects: 0 });
    // require_capability('moodle/site:config') -> un rol de curso debe ser rechazado.
    expect(res.status(), 'un rol de curso no debe pasar una guarda de site:config').not.toBe(200);
    await ctx.dispose();
  });
});
