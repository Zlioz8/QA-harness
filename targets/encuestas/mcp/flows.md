# Guion de flujos de navegador (MCP) — encuestas

Flujos REALES del usuario a recorrer con el servidor MCP del navegador. Dos destinos:

- **SERVIDOR DE PRUEBA del equipo:** `https://zajunavideo5.com` — SPA en `/encuestados/`, API en
  `/api`, Moodle en `/zajuna`. Ya vivo. Cuentas REALES en `target.env.local`.
- **CORE LOCAL** (tras `make up`): el despliegue de validación con la cohorte `demo_*`.

Cada flujo declara qué hallazgo del informe contrasta y qué evidencia deja (consola + red en
`.playwright-mcp/`).

## Lo YA verificado en esta sesión (2026-08-24, zajunavideo5)

- **F1 · La SPA sin sesión cae a Zajuna — y lo hace BIEN.** Navegar a `/encuestados/` sin token
  redirige (JS, `App.tsx:144` `window.location.replace`) a `https://zajuna.sena.edu.co/`. NO es
  el defecto de antiplagio (URL de producción hardcodeada sin salida): `origenZajuna.ts` recuerda
  el origen real de quien entró desde el LMS y solo cae a producción por defecto para el que llega
  por enlace de correo. Y la dirección de vuelta la fija el BACKEND (`config/zajuna_sso.php`),
  no un parámetro de la URL — cierra de raíz el redirect abierto. **Fortaleza, no hallazgo.**
  Evidencia: `console-2026-08-24T14-55-40-902Z.log` (los 16 errores son de la home de producción,
  no de la app).

- **F2 · El origen Apache está publicado EN CLARO (hallazgo ALTO).** `https://.../api/` (con barra)
  responde 301 a `http://zajunavideo5.com:8000/api`, y ese puerto sirve la API ENTERA sin TLS:
  `/api/contact-info` → 200 JSON, `/api/surveys` → 401, `/api/login` procesa autenticación
  (comprobado con credenciales FALSAS). El `Strict-Transport-Security` que devuelve por el 8000 es
  decorativo: un navegador ignora HSTS sobre HTTP. Cualquiera en la red puede capturar la
  contraseña de un login hecho contra el 8000. Recorrer en el navegador para capturar la petición.

- **F3 · La superficie pública responde como debe.** Sin sesión: `/api/surveys` → 401,
  `/api/users` → 401, `/api/contact-info` → 200. Contrasta el eje «lo no autenticado se niega».

## El bloqueo que hay que declarar: SSO web = sesión de Moodle

La entrada de las cuentas REALES a Encuestas es SOLO por SSO: Moodle acuña un pase HMAC (plugin
`local/encuestas`) → la SPA lo canjea en `/api/auth/zajuna` por un token Sanctum. NO hay login por
usuario/contraseña para estas cuentas: `AuthService::login` hace `Auth::attempt` contra la tabla
`users` de la aplicación (comprobado en `AuthController.php:78` y `AuthService.php:22`), donde las
cédulas de Moodle no tienen contraseña utilizable.

Y el SSO web está **bloqueado por el bug de enrutamiento del host**: `/zajuna/login/index.php`
rebota 303 a `https://caplms.sena.edu.co/` (el `alternateloginurl` de este Moodle), y `loginredirect=0`
no lo salta. `tool_mobile_get_autologin_key` responde `apprequired`. El plugin está bien instalado
y falla cerrado (`/api/auth/zajuna` sin pase → «No se pudo validar el acceso desde Zajuna»); el
bloqueo es del enrutamiento del LMS, NO del proyecto Encuestas.

**Consecuencia para el informe:** la matriz de autorización AUTENTICADA contra zajunavideo5 queda
**NO DISPONIBLE por bloqueo de entorno** (no «sin hallazgos»). Se mide en LOCAL con la cohorte
`demo_*` — y esa medida es **NO AUTORITATIVA** (cuentas del laboratorio). El eje NO autenticado
(F3) sí es autoritativo: no necesita sesión.

## Flujos a recorrer en LOCAL tras `make up` (cohorte demo)

- **F4 · Instructor gestiona.** `demo_instructor` entra por SSO local → `/encuestados/`. Debe ver
  la lista de encuestas (`/api/surveys` → 200) y el panel de creación. Evidencia: red con el
  `Authorization: Bearer` y el 200.

- **F5 · El cerco del aprendiz (el hallazgo central).** `demo_apr_01` entra por SSO → debe caer en
  «mis encuestas» y NADA más. Pedir en la barra de red `/api/surveys`, `/api/users`,
  `/api/roleandusers` → los tres deben dar **403** con «Como aprendiz solo puedes ver y responder
  tus encuestas» (`EnsureAprendizAcotado`). Un 200 en cualquiera = cerco roto. Contrasta la matriz
  `playwright/authz-matrix.json` desde el navegador real.

- **F6 · El caso mixto (solo con cuentas REALES, cuando se desbloquee el SSO).** `1038405594cc` es
  `editingteacher` en 3 cursos y `student` en 2. `EnsureAprendizAcotado` decide por el rol GLOBAL
  del usuario en la aplicación, no por curso: ver de qué lado del cerco cae. No se puede deducir
  del código — es exactamente lo que hay que observar.

- **F7 · Responder por enlace de correo (superficie pública, sin SSO).** Es la vía del aprendiz que
  NO necesita sesión: un enlace con hash/token (`/api/survey-email/validate-access` →
  `submit-response`). Recorrer con un enlace real generado por un instructor. OJO: escribe en la
  base; en zajunavideo5 (servidor compartido) NO enviar respuestas — solo `validate-access`.
