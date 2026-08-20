Segunda auditoría de `local_slider` + `local_slider_form`. A diferencia de R1 (Moodle efímero en
`:8083`), R2 despliega el módulo sobre el Zajuna real de la máquina de QA (Moodle 4.3.3+, nginx,
PostgreSQL 16) siguiendo el `DEPLOY.md` de la rama auditada, y mide contra él.

**Bloqueantes para producción:**

- **§3.1 — Contraseña de PostgreSQL en la historia de git.** Commit `68505d2`, alcanzable desde
  la rama auditada. HEAD ya usa `$CFG->dbpass`; la historia conserva el literal. Requiere rotar
  la credencial, no solo corregir el código.
- **§3.2 — El despliegue documentado falla.** La secuencia de migraciones de la §8.4 se detiene
  en la 4 de 13 sobre una base limpia (`004_regionales.sql`: `no existe la columna id`). Con
  `ON_ERROR_STOP=1`, las 9 restantes no se ejecutan, incluida la que crea `midb.envios2` (cola de
  correos). El módulo no se despliega siguiendo su propio procedimiento.

**Impiden la operación aunque el esquema se complete:**

- **§3.3 — `send_logs.php` y `table_logs.php` fallan** con `SQLSTATE[42703]: no existe la columna
  «estado»`. Las columnas `envios2.estado` y `envios2.sent_at` no las crea ninguna migración del
  repositorio. Verificado en pantalla con sesión válida.
- **§3.4 — La segmentación opera sobre 7 de 22.912 cursos visibles.** Las categorías fijadas en
  código (`10`, `200`) no existen en esta base: la rama «Complementaria» devuelve `[]` con HTTP
  200. La rama «Titulada» devuelve 4 regionales, correspondientes a los 7 cursos que cumplen el
  formato de `shortname` exigido. Ningún error visible.

**Autorización — medida, sin bypass, NO AUTORITATIVA.** Con dos cuentas de privilegio distinto
(rol `manager` con las capabilities, rol `student` sin ellas) la cuenta baja fue denegada en todas
las rutas: 303 al login en páginas, 403 en AJAX, JSON `nopermissions` en `active_role_users.php`.
No se halló ningún salto de privilegio. Las cuentas las creó QA con la CLI de Moodle (roles
preexistentes), por lo que la medida es NO AUTORITATIVA: valida el mecanismo, no la política del
entorno real (§10.3 — al instalar, las capabilities no se conceden a ningún rol).

**Ceros que no son ausencia de hallazgos:**

- DAST (ZAP): 107 alertas, 0 atribuibles al plugin. Sin sesión, sus pantallas redirigen al login;
  el escaneo midió Moodle core y la portada institucional.
- CVE de dependencias: 0, porque el proyecto no declara manifiesto (no hay `composer.json` ni
  `package.json`). No hay nada que escanear, no «nada vulnerable».

**Sin acción (§2):** SAST sin inyección real (los `tainted-callable` de semgrep son sentencias
preparadas), CSRF presente en los endpoints de escritura, cookie de sesión con `Secure`+`HttpOnly`,
Swiper con SRI y versión fijada, carga con p95 = 73 ms y 0% de error.
