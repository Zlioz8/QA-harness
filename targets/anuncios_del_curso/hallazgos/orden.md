Todo el código y la documentación son de **Carlos Eduardo Ortiz**. El orden es por impacto, no por
persona:

**1. Rotar el secreto SSH y purgar la historia (I6, Alta).** `REPORTE_QA_SEGURIDAD.md` versiona en
la raíz del repo `sshpass -p 'Anti2025' ssh admin@10.217.78.124`. Rotar esa contraseña HOY, purgar
el fichero de la historia de git (`git filter-repo`/BFG) y sacar el informe interno del repositorio
del plugin. Un secreto en git es permanente aunque se borre del árbol.

**2. Arreglar el contrato de despliegue (C1, C2, C3, C5, Alta/Media).** Dejar UN solo manual
vigente que describa el entorno REAL —Linux + **nginx + php8.1-fpm** + PostgreSQL + CLI de Moodle—
y retirar (o archivar como histórico) los tres de WAMP/Windows. En el manual vigente: corregir la
pila (hoy dice Apache+mod_php), alinear los requisitos con `version.php` (Moodle 4.1+, PHP 8.0+,
PostgreSQL) y **añadir el paso `systemctl reload php8.1-fpm` tras instalar/actualizar** — sin él la
actividad no se puede añadir aunque el upgrade y el purge_caches hayan ido bien (lo vivimos: nota P1).

**3. Cerrar el CSRF de manage.php (I1, Media).** Exigir `require_sesskey()` antes de ejecutar
`togglevisibility`/`moveup`/`movedown` y construir los enlaces con `sesskey()`; idealmente pasarlas
a POST. El fichero hermano `delete.php` ya lo hace bien: es aplicar su propio patrón.

**4. Migrar el almacenamiento de imágenes al file storage (I3, Media).** Guardar las imágenes con
`file_storage` y servirlas por `pluginfile.php`, en vez de base64 en columnas TEXT de la base
`moodle` compartida. Descarga la base y sus backups (que #2/#3/#6 comparten) y da sentido al control
de acceso por fichero.

**5. Corregir pluginfile.php (I2, Media, latente).** Servir sólo el fichero de `itemid`+nombre+
contexto exactos (eliminar el bucle que busca por nombre en todas las imágenes) y comprobar
`$image->visible`. Hoy es código muerto por (4), pero al migrar a ficheros se vuelve la vía de
servido y el defecto se activaría.

**6. Añadir integración continua (C6, Media).** Un pipeline mínimo (`moodle-plugin-ci` + gitleaks +
semgrep) que bloquee el merge ante secretos o errores de sintaxis. Habría atrapado I6, I1 e I4 antes
de la rama; es el control que sostiene a los demás.

**7. Higiene menor (I4, I5, Baja).** Quitar los `error_log()` de depuración (o pasarlos a
`debugging()`); añadir `require_capability('mod/imagecarousel:view')` a `view.php` por simetría con
`carousel_content.php`; añadir `rel="noopener noreferrer"` a los dos `target="_blank"` de
`carousel.mustache` que no lo tienen.

**8. Triar la señal de calidad.** SonarQube reporta calidad sobre el plugin (93 contados por el gate
tras deduplicar la misma regla en el mismo fichero, de 221 brutos: 98 `error` + 123 `note`); no son
bloqueantes por sí solos, pero conviene una
pasada. Las 12 alertas de ZAP son de la PLATAFORMA (nginx: falta CSP, versión expuesta), no del
plugin, y se corrigen en la configuración del core, no en este código.
