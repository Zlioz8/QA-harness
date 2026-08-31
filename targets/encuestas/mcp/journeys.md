# Recorrido de flujos en navegador (MCP) — encuestas · R1 (2026-08-24)

Resultado de recorrer `mcp/flows.md` con el servidor MCP del navegador contra el despliegue del
equipo (`https://zajunavideo5.com`). Evidencia (consola + snapshots + red) en
`reports/encuestas/mcp-evidencia/`.

## Ejecutado y CONCLUYENTE

- **F1 · La SPA sin sesión cae a Zajuna, y bien.** Navegado `/encuestados/` sin token → redirige
  (JS, `App.tsx:144`) a `https://zajuna.sena.edu.co/`. NO es el defecto de antiplagio: recuerda el
  origen real y fija la vuelta desde el backend (redirect abierto cerrado). **Fortaleza.** Los 16
  errores de consola son de la home de producción, no de la app. Evidencia:
  `console-2026-08-24T14-55-40-902Z.log`.

- **F2 · Origen Apache en claro (HALLAZGO, Alta).** `https://.../api/` → 301 a
  `http://zajunavideo5.com:8000/api`, y ese puerto sirve la API entera sin TLS: `/api/contact-info`
  200 JSON, `/api/surveys` 401, `/api/login` procesa auth (probado con credenciales falsas). HSTS
  por el 8000 es decorativo. Recorrido y confirmado.

- **F3 · La superficie pública responde como debe.** `/api/surveys` sin sesión → 401 (snapshot
  `page-2026-08-24T15-00-06-052Z.yml`); path-traversal en `/api/storage/images` → 400/404;
  descarga firmada sin firma → 403; `/api/surveys/1/public-details` inexistente → 404 «Survey not
  found». Todo autoritativo (no requiere sesión).

## Recorrido VISUAL en el navegador — la SPA real, con sesión (F4-F6)

Se construyó la SPA (`npm run build`, apuntada al backend local) y se sirvió en
`http://localhost:4173/encuestados/`, con la API en `http://localhost:8095`. La sesion se inyecta en
`localStorage` (`accessToken` + `userInfo`) con un token real de `/api/login`, tal como la SPA lo
guarda tras el SSO. Asi el flujo es OBSERVABLE — pantallas reales, no `fetch` a ciegas. Capturas en
`mcp-evidencia/0{1,2,3}-*.png`.

- **F4 · Funcionario entra y gestiona.** Con la sesion de `qa_funcionario`, la SPA arranca
  autenticada (deja de rebotar a produccion), muestra **«Con que comunidad deseas trabajar?»**
  (`01-funcionario-community-select.png`) y, elegida la interna, el **dashboard «Sistema de
  Encuestas»** con Nueva Encuesta, Lista de asignaciones, Reportes, Reglas, Banco de preguntas
  (`02-funcionario-dashboard.png`). El funcionario ve la gestion completa.
- **F5 · El aprendiz cercado, VISTO en pantalla.** Con la sesion de `qa_aprendiz`, se pidio
  EXPLICITAMENTE `/encuestados/dashboard` — la SPA lo **redirigio a `/encuestados/mis-encuestas`**:
  su pantalla «Mis encuestas», sin acceso a ninguna herramienta de gestion
  (`03-aprendiz-cercado-mis-encuestas.png`). Mismo intento, dos destinos segun el rol: el cerco es
  visible, no solo un codigo HTTP.
- **F6 · Creacion de encuesta, alimentada de Zajuna.** El funcionario abre `/survey-create`: el
  asistente de 4 pasos «Datos Generales → Preguntas → Asignaciones → Previsualizar»
  (`04-funcionario-crear-encuesta.png`). El paso «Asignaciones» consume los filtros SENA de la
  REPLICA ZAJUNA REAL — comprobado a nivel de API: `/api/sena-filters/modalidades` devuelve las 5
  modalidades reales del SENA leidas de `public.mdl_*` + `midb` sobre 23.112 cursos. Ya NO es
  «localhost aislado»: el despliegue se alimenta de Zajuna (ver COTEJO_DESPLIEGUE.md, hallazgo D8).

## Matriz de autorizacion EJECUTADA contra la API local

Ademas del recorrido visual, la matriz de 9 casos se recorrio sobre la API con los tres roles.
Cuentas de la APP creadas por el laboratorio, por `/api/login` — **NO AUTORITATIVA** (mide el
control sobre los roles que creamos), pero la dimension ya NO esta NO DISPONIBLE: se ejecuto y salio
COHERENTE en los tres ejes. Evidencia: `mcp-evidencia/matriz-autorizacion-local.txt`.

## Pendiente para la matriz AUTORITATIVA (R2)

Las 3 cuentas REALES SI se verificaron por `token.php` (validas; roles reales != rotulos). La
matriz autoritativa exige completar el SSO con ellas: instalar el plugin en el core local +
desactivar el rebote de login a caplms. El adaptador `encuestas-sso` ya esta escrito para ese flujo.

- **F7 · Responder por enlace de correo.** Requiere un enlace real con hash de un instructor; no
  ejecutado (escribe en la base).
