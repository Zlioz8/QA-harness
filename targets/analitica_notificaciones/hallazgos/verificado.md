Lo que se comprobó y **salió bien** en esta ronda, para que no se relea como pendiente:

- **El despliegue vivo responde y es estable — Responsable: DevOps/Infra.** `/api/health` da 200 y
  la carga autenticada (k6, rol alto, 10 usuarios) sostuvo p95 ≈ 190 ms con **0 % de error** sobre
  salud, catálogo, filtros (que tocan la BD de Moodle) y solicitudes. No hay signos de
  inestabilidad ni de un endpoint roto bajo carga.
- **La autenticación de la cuenta de alto privilegio funciona de extremo a extremo — Responsable:
  Backend.** `admin_slider` obtiene token vía `POST /api/auth/moodle-login`, la sesión revalida
  contra Moodle y los filtros dinámicos se hidratan: el flujo SSO real, contra datos reales,
  funciona.
- **Sin secretos verificados vivos por el proveedor — Responsable: Backend.** TruffleHog no
  confirmó ninguna credencial viva (0 de 54 candidatas). Los secretos del `.env` (§3.1) son reales
  pero de infraestructura interna, no claves de terceros que un tercero pueda verificar.
- **Sin CVE de dependencias por encima del umbral acordado, salvo las tres nombradas — Responsable:
  Backend.** El árbol de dependencias es pequeño y moderno; los problemas se concentran en
  `python-jose` (§3.2) y `python-multipart` (§3.4), no en una lista larga.
- **El catálogo de reportes y sus SQL están íntegros y parametrizados — Responsable: Backend.** Las
  consultas de `api/sql/*.sql` usan parámetros; el SAST no marcó inyección SQL en ellas.

- **El despliegue local reproduce el sistema de extremo a extremo — Responsable: DevOps/Infra +
  Backend.** Se levantó el stack del repositorio (api + worker + redis) con su propio
  `docker-compose.yml` contra el ZAJUNA core de la máquina: Control DB Postgres del host, BD de
  Moodle en **solo lectura** (rol `reportes_ro`, no el superusuario del `.env`), plugin
  `local_reporteszajuna` instalado y web service `reportes_zajuna` creado. `/api/health` 200,
  `Control DB inicializado`, y los filtros dinámicos de un reporte **se hidrataron con datos
  reales de Moodle** (6 opciones dinámicas). El despliegue documentado en `DEPLOY.md` es
  reproducible en este ambiente (con la salvedad del §3.10: aquí se usó rol RO y `MOODLE_DB_NAME=moodle`).
- **El control de acceso de la aplicación funciona — Responsable: Backend.** Medido contra el
  despliegue local con tres cuentas de rol distinto (⚠ *creadas por el laboratorio*, por lo que
  esta medición NO es AUTORITATIVA sobre las asignaciones reales de producción, pero SÍ ejercita
  el código real de autorización):
  · un `student` (capacidad PREVENT) es **denegado con 403** al entrar («Sin permiso para acceder
    al sistema de reportes») — `check_user_access` lee la capacidad de Moodle y la respeta;
  · un `manager` entra y ve el catálogo, filtros y sus solicitudes;
  · **propiedad (IDOR):** una segunda cuenta que pide la solicitud de otra recibe **403** en
    `GET /api/solicitudes/{id}` — el control de `usuario_email` funciona.
  Queda pendiente medir esto con una cuenta REAL de bajo privilegio para que sea autoritativo.

- **El control de acceso también se verificó en el SERVIDOR de pruebas — Responsable: Backend.**
  Se creó una cuenta real (`rz_qa_teacher`) en el Moodle de producción y se comprobó, de forma
  autoritativa: **sin rol con la capacidad → `POST /api/auth/moodle-login` responde 403** «No
  tienes permiso para acceder al sistema de reportes». El control de acceso a nivel de aplicación
  funciona igual que en local. La cuenta se dejó **suspendida** tras la prueba (residuo cero).
- **Hallazgo de método sobre la autorización — Responsable: Backend + Líder Técnico.** El modelo
  de autorización que **declara** el plugin (`reporteszajuna/db/access.php`: archetypes `manager`,
  `coursecreator`, `editingteacher`, `teacher` = ALLOW) **no coincide con producción**: se asignó a
  la cuenta de prueba el rol **Creador de curso** a nivel sistema y **siguió sin acceso** (403). En
  producción, el acceso a reportes lo tienen roles concretos (siteadmin/manager y lo que se haya
  concedido explícitamente), no los archetypes por defecto — más restringido que lo declarado, lo
  cual es bueno, pero significa que **«quién puede ver reportes» debe verificarse contra la BD real,
  no leerse del código del plugin**. En local (instalación limpia) los archetypes sí aplicaban.
