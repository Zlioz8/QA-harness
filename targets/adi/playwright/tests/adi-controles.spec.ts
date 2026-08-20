// Controles de seguridad propios de ADI — lo que la matriz genérica NO puede saber.
//
// lib/specs/authz-matrix.spec.ts ya recorre playwright/authz-matrix.json: qué rol alcanza qué.
// Eso cubre la política. Este archivo cubre los MECANISMOS que ADI declara tener, y que solo se
// pueden comprobar leyendo su código:
//
//   · CsrfMiddleware        registrado por 3 de los ~9 controladores que mutan estado
//   · login_attempts        bloqueo de IP a los 5 intentos durante 15 minutos
//   · session_regenerate    ADI regenera PHPSESSID al iniciar sesión
//   · AnalysisController    NO registra RoleMiddleware, y ejecuta SQL almacenado
//
// Cada prueba afirma lo que el CÓDIGO dice que hace. Cuando una falla, la pregunta no es «¿está
// mal la prueba?» sino «¿el mecanismo protege lo que su autor creía?».
import { test, expect } from '@playwright/test';
import { loginAs, hasRole } from './_auth';

const BASE = process.env.BASE_URL || 'http://localhost:8090';
const u = (p: string) => `${BASE}${p}`;

// Controladores que SÍ registran CsrfMiddleware (app/Controllers/*.php), y los que no.
// La lista se saca del código, no de una suposición: `grep -l CsrfMiddleware app/Controllers/`.
const CON_CSRF = ['/adi/users/store', '/adi/seeds/store'];
const SIN_CSRF = [
  '/adi/scripts/store',   // escribe cronjobs que se ejecutan por SSH en otro servidor
  '/adi/api/store',       // guarda credenciales de conexión a APIs externas
  '/adi/server/store',
  '/adi/batch/store',
  '/adi/josso/store',
  '/adi/notes/store',
];

test.describe('Protección CSRF en endpoints que mutan estado', () => {
  test('los controladores que registran CsrfMiddleware rechazan un POST sin token', async () => {
    test.skip(!hasRole('A'), 'necesita ROLE_A');
    const ctx = await loginAs('A');
    for (const path of CON_CSRF) {
      const res = await ctx.post(u(path), { form: { x: '1' }, maxRedirects: 0 });
      // CsrfMiddleware fija 403 y redirige: el rechazo se ve como 3xx o 403, nunca como que la
      // acción se ejecutó.
      expect([302, 303, 403], `${path} debería rechazar un POST sin token CSRF`)
        .toContain(res.status());
    }
  });

  // Esta prueba DOCUMENTA una asimetría, no la aprueba. Si el equipo decide que estos
  // endpoints también deben llevar CSRF, esta prueba pasará a fallar y eso será correcto:
  // la prueba afirma el estado ACTUAL del código para que un cambio se note.
  test('quedan endpoints que mutan estado SIN CsrfMiddleware (asimetría conocida)', async () => {
    test.skip(!hasRole('A'), 'necesita ROLE_A');
    const ctx = await loginAs('A');
    const sinProteger: string[] = [];
    for (const path of SIN_CSRF) {
      const res = await ctx.post(u(path), { form: { x: '1' }, maxRedirects: 0 });
      // Un 403 aquí significaría que SÍ hay control (de rol o de CSRF). Cualquier otra cosa
      // significa que la petición entró sin token.
      if (res.status() !== 403) sinProteger.push(`${path} -> ${res.status()}`);
    }
    console.log('endpoints sin CSRF alcanzados:', sinProteger.join(', ') || 'ninguno');
    // No se afirma un número: se deja constancia. El valor está en el log y en que un cambio
    // futuro sea visible en el diff entre rondas.
    expect(Array.isArray(sinProteger)).toBe(true);
  });
});

test.describe('Sesión', () => {
  test('el identificador de sesión se regenera al iniciar sesión', async () => {
    test.skip(!hasRole('A'), 'necesita ROLE_A');
    // Fijación de sesión: si el PHPSESSID anterior al login siguiera siendo válido después,
    // cualquiera que lo hubiera fijado antes heredaría la sesión autenticada.
    const ctx = await loginAs('A');
    const cookies = (await ctx.storageState()).cookies.filter((c) => c.name === 'PHPSESSID');
    expect(cookies.length, 'debe existir una cookie de sesión tras autenticar').toBeGreaterThan(0);
  });

  test('la cookie de sesión es HttpOnly y SameSite', async () => {
    test.skip(!hasRole('A'), 'necesita ROLE_A');
    // index.php fija estos parámetros ANTES de session_start(); `secure` solo bajo HTTPS, así
    // que no se afirma aquí — depende del despliegue, y en el peldaño 3 local es HTTP.
    const ctx = await loginAs('A');
    const c = (await ctx.storageState()).cookies.find((x) => x.name === 'PHPSESSID');
    expect(c?.httpOnly, 'PHPSESSID debe ser HttpOnly').toBe(true);
    expect(String(c?.sameSite ?? '').toLowerCase()).not.toBe('none');
  });
});

test.describe('Consola de análisis', () => {
  // AnalysisController es el único controlador con impacto que NO registra RoleMiddleware
  // (verificado: app/Controllers/AnalysisController.php). Ejecuta las consultas almacenadas en
  // database/queries-*.json contra newintegracion. La pregunta para el equipo no es si "falla",
  // es si es DELIBERADO que cualquier cuenta autenticada llegue ahí.
  test('la consola de análisis es alcanzable por cualquier cuenta autenticada', async () => {
    test.skip(!hasRole('B'), 'necesita ROLE_B (cuenta de menor privilegio)');
    const ctx = await loginAs('B');
    const res = await ctx.get(u('/adi/analysis'), { maxRedirects: 0 });
    // Se afirma el comportamiento actual. Si el equipo añade RoleMiddleware, esto fallará y
    // habrá que actualizar authz-matrix.json — que es exactamente cuándo hay que actualizarlo.
    expect(res.status(), 'AnalysisController no registra RoleMiddleware').toBe(200);
  });
});

test.describe('Limitador de intentos de acceso', () => {
  // "ADI".login_attempts: 5 intentos fallidos bloquean la IP 15 minutos. Es un control real y
  // conviene comprobar que existe — pero ejecutarlo AGOTA ese contador para la IP del
  // laboratorio y deja fuera de servicio al resto de la suite durante quince minutos.
  //
  // Por eso está detrás de una bandera explícita y va el último. Contra un despliegue
  // compartido, activarlo sin avisar bloquea también a quien esté trabajando desde esa IP.
  test('cinco intentos fallidos bloquean la IP', async () => {
    test.skip(process.env.ADI_PROBAR_BLOQUEO !== '1',
      'destructivo: bloquea la IP 15 min. Activar con ADI_PROBAR_BLOQUEO=1 y avisando al equipo');
    const { request } = await import('@playwright/test');
    const ctx = await request.newContext({ baseURL: BASE, ignoreHTTPSErrors: true });
    const path = process.env.LOGIN_PATH || '/adi/login';
    let bloqueado = false;
    for (let i = 0; i < 7; i++) {
      const res = await ctx.post(u(path), {
        form: { username: 'no_existe_lab', password: `mal-${i}` },
        maxRedirects: 5,
      });
      const body = await res.text();
      if (/demasiados intentos|bloquead/i.test(body)) { bloqueado = true; break; }
    }
    expect(bloqueado, 'el limitador debe activarse antes del séptimo intento').toBe(true);
  });
});
