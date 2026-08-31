# Guion de flujos por navegador (MCP) — local_portafolio

El plan de lo que el recorrido de navegador DEBE ejercitar en este plugin. La ejecución y las
capturas están en `reports/portafolio_del_aprendiz/mcp/journeys.md`.

## Por qué ESTE plugin necesita el recorrido de navegador

`local_portafolio` no expone ni un web service (0 funciones `porta*` entre las 416 del sitio): toda
su superficie es HTML renderizado en servidor, y su control de acceso vive en `resolve_target_user()`
(exige `viewother` + `is_enrolled`). Ni ZAP ni k6 pueden decir si un aprendiz alcanza el portafolio
de OTRO — eso solo se ve iniciando sesión con privilegios distintos y recorriendo las pantallas.

## Flujos a recorrer (los ejes de la matriz)

1. **Aprendiz ve lo suyo** — login como aprendiz → `index.php` → `view.php?courseid=<suyo>` →
   dashboard con stats, actividades y RAP. Capturar.
2. **Aprendiz NO ve lo ajeno** — como aprendiz, manipular `view.php?courseid=<suyo>&userid=<otro>`.
   Debe denegar («No tienes permiso para ver el portafolio de otro aprendiz»). Capturar la denegación.
3. **Aprendiz NO entra a Participantes** — `participantes.php?courseid=<suyo>`. Debe denegar por
   `require_capability(:viewother)`. Capturar.
4. **Instructor SÍ entra a Participantes** — login como instructor → `participantes.php` → listado
   de aprendices. Capturar.
5. **Instructor ve el portafolio de un aprendiz de SU curso** — desde el listado, abrir el de un
   aprendiz. Debe permitir. Capturar.
6. **Guardián de matrícula** — instructor pide `view.php?courseid=<otro>&userid=<aprendiz no
   matriculado ahí>`. Debe denegar («no está matriculado en este curso»). Capturar.

## Dónde ejecutarlo, y con qué autoridad

- **AUTORITATIVA** en `zajunavideo.com` con las cuentas REALES (aprendiz 1012375863, instructora
  42007371), verificadas contra el servidor antes de usarlas. Sesión por `tool_mobile_get_autologin_key`
  (el login web rebota por `alternateloginurl`, que NO se toca en ese servidor). Solo lectura.
- **NO AUTORITATIVA** en el core local con `demo_apr_01` / `demo_instructor` / `demo_coordinador`,
  login por formulario. Cubre los ejes negativos que no conviene provocar en el servidor del equipo.

## Regla

Un flujo que no se ve en pantalla no está recorrido: cada eje deja su captura en `mcp/journeys.md`.
Los roles se leen de la BD del servidor (`core_enrol_get_users_courses`), no del rótulo del Excel.
