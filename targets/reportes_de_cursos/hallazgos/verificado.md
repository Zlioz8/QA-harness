Comprobado y correcto en esta ronda (sin acción para el equipo, salvo mantenerlo):

- **DEPLOY.md entregado y de alta calidad** — `dev:DEPLOY.md`, 818 líneas, contrastado contra el
  código, con una sección honesta de «lo que este documento no puede afirmar». Responsable: Luis
  Andrés Ríos.
- **El despliegue arranca desde el propio repositorio** — plugin + upgrade (9 tablas, 30 funciones
  WS), contenedores sanos, nginx single-origin, `/zea-api/health` → `{"status":"ok"}`. La única
  intervención fuera del manual fue aplicar `login.sql` a mano (ver §C1, que es el hallazgo).
- **Denegación de autorización AUTORITATIVA (cuenta real, servidor del equipo)** — el aprendiz
  real (cédula 1089379340) inicia sesión en `zajunavideo5.com` y `token.php` le niega el token de
  reportes en sus 3 cursos matriculados («no tiene los permisos… viewreports»); la API le da 401
  sin token de curso. La capacidad se comprueba contra la BD real, no el archetype.
- **La API está correctamente cerrada** — las 8 rutas de `/api/v1/reports/*` responden 401 sin
  JWT; el control de acceso es por curso (`AuthorizeCourse`: el JWT lleva un curso y la API
  comprueba que el pedido casa). Una ruta inventada bajo `/zea-api/` da 404, no un 200 de
  catch-all.
- **CSRF de login implementado** — `login.php` rechaza credenciales form-encoded (400, «solo
  acepta JSON»): un `<form>` cross-origin no puede iniciar sesión en el navegador de la víctima.
- **Postura cerrada en producción** — el login autónomo está deshabilitado en el servidor
  (embedded-only); el `.env` no versiona secretos vivos (el único fichero versionado sensible,
  `.env.production`, contiene solo `VITE_API_BASE=/zea-api`).
- **Requisitos de plataforma correctos** — el manual acierta con PHP 8.0–8.2 (site en 8.1),
  `max_input_vars≥5000` y pcov fuera del FPM; el ambiente cumple.
- **Carga (k6) — LIMPIA**: 7 reportes de solo lectura, 10 usuarios concurrentes, 30 s → 0 % de
  error y p95 = 5,5 ms (1401/1401 checks OK). El endpoint por-aprendiz y el catálogo de RAP se
  parametrizaron con ids reales; un 49,86 % de «error» inicial resultó ser el guion sin `userid`/
  `rapid`, no el sistema (la lección de R2, aplicada).
- **Tablero recorrido con navegador (MCP) — sin 502 y sin errores**: como instructor se
  recorrieron las pestañas Ingresos / Avance de actividades / Resultados de aprendizaje; todas las
  llamadas al API respondieron 200, 0 errores de consola, y los reportes sin datos muestran un
  estado vacío correcto («Sin RAPs para mostrar»). A diferencia de #3, la vista previa NO devolvió
  502. La cadena embebida (token.php→200 → /zea-api→200) se verificó en la traza de red.
- **Matriz de autorización automatizada (Playwright) — 6/6**: instructor permitido en su curso,
  aprendiz denegado, y cross-course (token de un curso pidiendo otro) denegado para ambos.
- **Dependencias y SAST bajos** — 1 CVE de dependencia (Go `GO-2026-5932`), 10 hallazgos SAST:
  ambos muy por debajo del presupuesto.
