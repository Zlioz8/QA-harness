**Estado: GATE FAILED (R1).** `mod_imagecarousel` (v0.3.3, "Slider de Curso", desarrollador Carlos
Eduardo Ortiz) es un plugin de actividad de Moodle que se instala dentro del árbol del core y ejecuta
su upgrade contra la base `moodle`. Es el despliegue más invasivo de los seis primeros proyectos: no
publica puertos, comparte base de datos y árbol con reportes_de_cursos (#2), analitica_notificaciones
(#3) y encuestas (#6). Se desplegó de verdad sobre el Zajuna local siguiendo su propio manual, y se
auditó ahí y —en lo que fue posible— contra el servidor de prueba del equipo (zajunavideo5.com).

**La buena noticia: el control de acceso del plugin es sólido.** La matriz de autorización se ejecutó
en 14 casos (editingteacher / student / student-de-otro-curso / anónimo) y NO se halló ningún salto:
los endpoints de gestión exigen la capability `manageitems`, la vista exige matrícula, el endpoint
AJAX exige `sesskey`, y la herramienta de sitio exige `site:config`. La visibilidad por imagen que
introdujo v0.3.2 —el punto donde más fácil se cuela un fallo en esta familia— se probó explícitamente
ocultando una imagen y pidiéndola por todas las vías: se respeta en la vista, en el carrusel embebido
y en el servido. La latencia en lectura es excelente (p95 40 ms).

**Por qué falla la compuerta.** Dos cosas la cierran, y las dos son reales: (1) una **contraseña SSH
en claro versionada en la historia de git** (`Anti2025`, admin@10.217.78.124, en un informe interno
que viaja en la raíz del repo) — hay que rotarla y purgar la historia; y (2) el **contrato de
despliegue está roto**: de los cuatro manuales que trae la rama, tres describen una pila WAMP/Windows/
MySQL que no existe en la fábrica, y hasta el manual gobernante describe Apache+mod_php cuando el
servidor real es nginx+php-fpm — un error que ya se pagó en el despliegue (la actividad no se podía
añadir hasta recargar php-fpm, paso que el manual omite porque cree que el servidor es otro).

El resto son defectos de código de severidad media-baja que el equipo debe corregir: un CSRF en
`manage.php` (cambia visibilidad/orden por GET sin token, mientras su hermano `delete.php` sí lo
exige), imágenes almacenadas como base64 en la base compartida en vez de en el file storage de
Moodle, una guarda de servido de ficheros mal escrita (hoy latente), y restos de depuración. Y un
riesgo de proceso que los engloba: **no hay integración continua** que habría atrapado varios de
estos antes de llegar a la rama.
