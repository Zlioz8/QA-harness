Todo el código es de **Victor Manuel Echeverri** (ramas `lmsActividad`, `centro_resultados`,
`calificaciones`). El orden es por impacto, no por persona.

**1. Cerrar el bypass de autenticación del SSO (P1, Crítica).** Es lo más grave y está **probado en
vivo** contra el servidor del equipo: `login_config.php` inicia sesión como cualquier usuario que se
indique en la URL, sin validar el `sesskey` ni exigir sesión de Moodle. Validar el `sesskey` contra la
sesión del core y tomar la identidad de esa sesión, no del query string. Hasta que se corrija, el
Centro de Actividades es suplantable por cualquiera con acceso a la red.

**2. Rotar las credenciales filtradas y purgar la historia (P2, Crítica).** La contraseña del
superusuario `postgres` (`/76nF6px(&k)Ng_`) y un token de SonarQube están en la historia git y son
recuperables. Rotar y revocar HOY; purgar la historia. Encadena con P5 (si el `.git` se sirve por
HTTP, se descargan sin acceso al repo).

**3. Quitar la credencial `postgres/12345` del FDW y sacar los esquemas del core (P3, Alta).**
`comandos_conexion.sql` versiona la contraseña del superusuario en claro y contamina `public` del LMS.
Rol de solo lectura dedicado, credencial fuera del repo, esquema propio.

**4. Bloquear `.env` y `.git` por HTTP (P5, Media, encadena con P2).** No clonar en el webroot; regla
de ficheros ocultos en el servidor web. Barato y corta la vía remota a las credenciales de la historia.

**5. Reducir la invasividad sobre el core compartido (P4, Alta).** Mover las 45 funciones y los
esquemas a la BD propia; usar el plugin de Moodle para la integración en vez de parchear el core.
Es el trabajo mayor, pero es lo que hace el módulo desplegable y reversible sin romper a los vecinos.

**6. Endurecer la sesión (P6, Media).** Apoyarse en la sesión firmada de Moodle; cookie con
`HttpOnly`/`SameSite`/`Secure`; token CSRF en las escrituras.

**7. Alinear el manual con el destino y arreglar los parches del §5 (P7, Media).** nginx (no Apache),
la versión de PHP real, y los bloques del §5 que hoy no compilan.

**8. Reproducibilidad y CI (P8, Media).** Versionar lockfiles; `composer.json` del sincronizador;
migrar SwiftMailer (abandonado); un pipeline mínimo.

**9. No volcar el detalle de excepciones al log (P9, Baja).** Un identificador de error, no el DSN.
