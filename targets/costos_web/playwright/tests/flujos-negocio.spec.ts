// REGLAS DE NEGOCIO Y CONTRATO — las que ninguna herramienta infiere sola.
//
// Cada prueba de aquí nació de un hallazgo encontrado a mano recorriendo la aplicación
// (R7 §3.15, §3.17, §3.18, §3.19, §3.20). Escribirlas es lo que impide volver a encontrarlos
// a mano: a partir de ahora las verifica `make e2e TARGET=costos_web` en cada entrega.
import { test, expect, request as pwRequest, APIRequestContext } from '@playwright/test';
import { sesionDe, pausa } from './_sesion';

// Sin BASE_URL no hay objetivo. Fallar aquí es más honesto que traer un valor por defecto:
// una dirección incrustada sobrevive al despliegue que la motivó y acaba midiendo el
// servidor equivocado en verde. Se declara en targets/costos_web/target.env.local.
const BASE = process.env.BASE_URL || '';
if (!BASE) throw new Error('BASE_URL no declarado — ver targets/costos_web/target.env.local.example');
const ORIGIN = process.env.ALLOWED_ORIGIN || BASE;

const ADMIN = { user: process.env.ROL1_ADMINISTRADOR_USER!, pass: process.env.ROL1_ADMINISTRADOR_PASS! };
const COORD = { user: process.env.ROL5_COORDINADOR_USER!, pass: process.env.ROL5_COORDINADOR_PASS! };

const INTEGRANTE = Number(process.env.COORD_INTEGRANTE_ID || 15505);   // del grupo del coordinador
const FUERA      = Number(process.env.FUERA_DE_AMBITO_ID || 1);        // usuario de otro ámbito
const GRUPO      = Number(process.env.COORD_GRUPO_ID || 86);

function sesion(cred: { user: string; pass: string }): Promise<APIRequestContext> {
  return sesionDe(cred.user, cred.pass);
}

async function xsrf(ctx: APIRequestContext): Promise<Record<string, string>> {
  const st = await ctx.storageState();
  return {
    'X-XSRF-TOKEN': decodeURIComponent(st.cookies.find((c) => c.name === 'XSRF-TOKEN')?.value ?? ''),
    'Content-Type': 'application/json',
  };
}

test.describe('contrato y reglas de negocio', () => {
  test.skip(!process.env.ROL1_ADMINISTRADOR_USER, 'faltan las cuentas por rol en target.env');
  test.beforeEach(async () => { await pausa(); });   // respeta throttle:60,1

  // R7 §3.15 — sin el id del grupo, el frontend no puede asignar representante.
  test('§3.15 el listado de seguimiento entrega grupo.id, no solo el nombre', async () => {
    const ctx = await sesion(ADMIN);
    const res = await ctx.get('/api/seguimiento-formularios?per_page=1');
    expect(res.status()).toBe(200);
    const body = await res.json();
    const grupo = body.data?.[0]?.usuario?.grupo;
    expect(grupo, 'la fila no trae usuario.grupo').toBeTruthy();
    expect(grupo.id, 'grupo.id ausente: el frontend enviará null y el POST dará 422').toBeTruthy();
  });

  // R7 §3.17 — cada formulario suma 100% POR SEPARADO. La regresión clásica: la suma
  // acumulaba todos los tipos y el segundo formulario era imposible de guardar.
  test('§3.17 dos formularios distintos, cada uno al 100 %, se guardan ambos', async () => {
    const ctx = await sesion(ADMIN);
    const tiempo = await (await ctx.get('/api/tiempo/activa')).json();
    const tiempoId = tiempo?.tiempo?.id;
    expect(tiempoId, 'no hay periodo activo: la prueba no puede concluir nada').toBeTruthy();

    // Se usa el representante del grupo del coordinador: rol 3-5 con grupo, que es lo que
    // el controlador exige como "representante válido".
    const usuarios = await (await ctx.get('/api/usuarios?per_page=1')).json();
    expect(usuarios.data?.length).toBeGreaterThan(0);

    const objetivo = Number(process.env.COORD_REPRESENTANTE_ID || 6955);
    const h = await xsrf(ctx);
    for (const tipo of ['1', '2']) {
      const res = await ctx.post('/api/seguimiento-formularios', {
        headers: h,
        data: { usuario_id: objetivo, tiempo_id: tiempoId, tipo, estado: 'DILIGENCIADO',
                costos: [{ id: 1, porcentaje: 100 }] },
      });
      expect(res.status(), `el formulario tipo ${tipo} suma 100 % y debe guardarse`).toBe(200);
    }
  });

  // R7 §3.19 — un campo faltante es 422 con el mapa de errores, nunca 500.
  test('§3.19 un error de validación responde 422, no 500', async () => {
    const ctx = await sesion(ADMIN);
    const res = await ctx.post('/api/seguimiento-formularios', {
      headers: await xsrf(ctx),
      data: { tipo: '1', costos: [{ id: 1, porcentaje: 100 }] },   // sin usuario_id
    });
    expect(res.status(), 'la validación se está devolviendo como error de servidor').toBe(422);
  });

  // R7 §3.20 — el coordinador puede editar a los suyos, pero no sacarlos de su ámbito.
  test('§3.20 el coordinador no puede mover a un integrante a otra regional', async () => {
    const coord = await sesion(COORD);

    // Requisito previo: el integrante tiene que estar DENTRO del alcance del coordinador.
    // Si no lo está, baseQuery() devuelve 404 y la prueba pasaría sin haber ejercitado nunca
    // la protección — verde por el motivo equivocado. Ocurrió: una corrida anterior movió a
    // este usuario fuera del grupo y no lo restauró, y la prueba quedó vacía sin avisar.
    const previo = await coord.fetch(`${BASE}/api/usuarios/${INTEGRANTE}`);
    expect(previo.status(),
      `el integrante ${INTEGRANTE} no está en el ámbito del coordinador (HTTP ${previo.status()}): ` +
      `restaurar los datos de prueba antes de leer este resultado`).toBe(200);

    const res = await coord.fetch(`${BASE}/api/usuarios/${INTEGRANTE}`, {
      method: 'PUT',
      headers: await xsrf(coord),
      data: { grupo_id: 13, regional_id: 1, dependencia_id: 5 },
      maxRedirects: 0,
    });

    // Si el sistema lo permitió, hay que devolver al integrante a su sitio: una prueba no
    // puede dejar el entorno peor de como lo encontró, aunque el hallazgo sea real.
    if ([200, 201, 204].includes(res.status())) {
      const admin = await sesion(ADMIN);
      await admin.fetch(`${BASE}/api/usuarios/${INTEGRANTE}`, {
        method: 'PUT',
        headers: await xsrf(admin),
        data: { grupo_id: GRUPO, regional_id: 2, dependencia_id: 165 },
      });
    }

    expect([403, 404, 422].includes(res.status()),
      `un coordinador movió a un integrante fuera de su ámbito (HTTP ${res.status()})`).toBeTruthy();
  });

  test('§3.20 el coordinador no alcanza a un usuario de otro ámbito', async () => {
    const coord = await sesion(COORD);
    const res = await coord.fetch(`${BASE}/api/usuarios/${FUERA}`, {
      method: 'PUT',
      headers: await xsrf(coord),
      data: { nombre_completo: 'prueba de alcance' },
      maxRedirects: 0,
    });
    expect([403, 404].includes(res.status()),
      `el coordinador editó a un usuario fuera de su alcance (HTTP ${res.status()})`).toBeTruthy();
  });

  test('§3.20 el coordinador no puede cambiar roles', async () => {
    const coord = await sesion(COORD);
    const yo = await (await coord.get('/api/me')).json();
    const res = await coord.fetch(`${BASE}/api/usuarios/${yo.id}`, {
      method: 'PUT',
      headers: await xsrf(coord),
      data: { rol_id: 1 },
      maxRedirects: 0,
    });
    expect([403, 404, 422].includes(res.status()),
      `un coordinador cambió un rol (HTTP ${res.status()})`).toBeTruthy();
  });

  // R7 §3.14 — el acceso federado debe seguir en pie con la configuración cacheada.
  test('§3.14 el endpoint de acceso con Microsoft responde, no revienta con 500', async () => {
    const ctx = await pwRequest.newContext({ baseURL: BASE, ignoreHTTPSErrors: true,
      extraHTTPHeaders: { Origin: ORIGIN, Referer: `${BASE}/` } });
    const res = await ctx.get('/api/auth/entra/url');
    expect(res.status(), 'un 500 aquí significa que env() devolvió null con la config cacheada').not.toBe(500);
  });

  // R7 §3.13 — los assets que el bundle referencia tienen que existir. Un 200 con text/html
  // es el modo de fallo real: nginx devuelve el index.html y el navegador pinta el icono roto.
  //
  // Esta prueba vigilaba la MITIGACIÓN: que nginx siguiera publicando /src/assets/ en la raíz
  // web. Corregido §3.13 en el código —las imágenes se importan con el alias @ y Vite las emite
  // con hash—, esa ruta ya no debe existir, y exigirla sería pedir que la muleta siga puesta.
  // Se verifica el estado correcto, que además es más fuerte:
  //   a) el bundle no referencia ninguna ruta /src/assets/;
  //   b) las imágenes que sí referencia existen y se sirven como imagen.
  test('§3.13 el bundle no referencia /src/assets/ y sus imágenes resuelven', async () => {
    const ctx = await pwRequest.newContext({ baseURL: BASE, ignoreHTTPSErrors: true });

    const html = await (await ctx.get('/')).text();
    const entry = html.match(/\/assets\/index-[A-Za-z0-9_-]+\.js/)?.[0];
    expect(entry, 'no se encontró el bundle de entrada en index.html').toBeTruthy();

    const js = await (await ctx.get(entry!)).text();

    const absolutas = js.match(/\/src\/assets\/[^"')\s]+/g) || [];
    expect(absolutas, `el bundle conserva rutas absolutas: ${absolutas.slice(0, 5).join(', ')}`)
      .toEqual([]);

    const imgs = [...new Set(js.match(/\/assets\/[A-Za-z0-9_.-]+\.(?:svg|png|jpe?g|webp)/g) || [])];
    expect(imgs.length, 'el bundle no referencia ninguna imagen: revisar el patrón').toBeGreaterThan(0);

    for (const src of imgs.slice(0, 20)) {
      const r = await ctx.get(src);
      expect(r.status(), `${src} no se sirve`).toBe(200);
      expect(r.headers()['content-type'] || '', `${src}: llega HTML donde debería llegar una imagen`)
        .toContain('image/');
    }
  });
});
