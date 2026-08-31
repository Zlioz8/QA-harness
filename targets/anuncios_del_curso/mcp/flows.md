# Flujos de navegador (MCP) — anuncios_del_curso / mod_imagecarousel

Guion del recorrido VISUAL conducido con el servidor MCP del navegador, contra el CORE LOCAL
(https://nginx.zajuna.com/zajuna). El plugin es interfaz DENTRO de un curso: el recorrido es en
pantalla o no existe. Evidencia en `reports/anuncios_del_curso/mcp-evidencia/`.

Cuentas (core local, NO AUTORITATIVAS): demo_instructor (editingteacher), demo_apr_01 (student
C_0001), demo_apr_05 (student C_0002). Curso de trabajo: C_0001 (id 23535). Instancia: cmid 73985.

## Flujos ejecutados

| # | Flujo | Rol | Evidencia | Resultado |
|---|-------|-----|-----------|-----------|
| 1 | Añadir la actividad (`modedit.php?add=imagecarousel`) | editingteacher | `01-mod_form-anadir-actividad.png` | OK tras recargar php-fpm (P1) |
| 2 | Subir dos imágenes (`adding_image.php`) marcadores A/B | editingteacher | `02-adding_image-subida.png` | 2 filas en mdl_imagecarousel_images |
| 3 | Gestionar imágenes (`manage.php`) | editingteacher | `03-manage-dos-imagenes.png` | enlaces de acción SIN sesskey (S1) |
| 4 | Ocultar imagen B por `togglevisibility` (GET sin sesskey) | editingteacher | BD: visible 1→0 | CSRF confirmado |
| 5 | Ver como student (`view.php`) | student mismo curso | `04-view-como-student-solo-visible.png` | Sólo A; B oculta no aparece |
| 6 | Carrusel embebido (`course/view.php`, fetch AJAX) | student mismo curso | `05-curso-embebido-student.png` | Sólo A; B no aparece |
| 7 | Imagen oculta B vía carousel_content.php | student | curl | B no se sirve; visibilidad respetada |
| 8 | pluginfile.php como student / anónimo | student / anon | curl | 404 (base64=código muerto) / 303 (exige login) |
| 9 | Disponibilidad temporal (`availablefrom` futuro) | student | BD + navegador | Oculto fuera de ventana; reaparece al restaurar |

## Ejes de autorización probados (curl + navegador)

- editingteacher: acceso completo (view, manage, adding_image, edit, delete).
- student mismo curso: view OK; manage/adding_image/edit/delete → nopermission.
- student otro curso (demo_apr_05): todo → 303 (require_login: no matriculado).
- anónimo: 303/404 en todo.
- carousel_content.php sin sesskey: rechazado para todos.
- webp-support.php: exige site:config (ningún rol de curso pasa).

## Flujos, uno por hito (unidad = flujo)

- **F1 · Añadir la actividad al curso.** editingteacher en `course/modedit.php?add=imagecarousel&course=23535`. Contrasta: el despliegue FUNCIONA. Reveló P1 (Invalid component hasta recargar php-fpm). Evidencia `01-mod_form-anadir-actividad.png`.
- **F2 · Subir imágenes con marcadores.** `adding_image.php?id=73985`, imágenes A (visible) y B (a ocultar). Contrasta el flujo del docente y el almacenamiento. Evidencia `02-adding_image-subida.png`.
- **F3 · Gestionar imágenes.** `manage.php?id=73985`. Contrasta S1: los enlaces `action=togglevisibility|moveup|movedown` son GET sin sesskey. Evidencia `03-manage-dos-imagenes.png`.
- **F4 · Ocultar la imagen B.** `manage.php?...&action=togglevisibility` por GET. Contrasta S1 en ejecución (visible 1→0 en BD sin token).
- **F5 · Ver como student.** `view.php?id=73985` con demo_apr_01. Contrasta la visibilidad por imagen: sólo A, B no aparece. Evidencia `04-view-como-student-solo-visible.png`.
- **F6 · Carrusel embebido en el curso.** `course/view.php?id=23535`, contenido por fetch AJAX. Contrasta la vista real de uso. Evidencia `05-curso-embebido-student.png`.
- **F7 · Imagen oculta por carousel_content.php.** student con sesskey. Contrasta que B (oculta) no se sirve — visibilidad respetada en el AJAX.
- **F8 · pluginfile.php.** student y anónimo. Contrasta S2: 404 con sesión (base64=código muerto), 303 sin sesión (exige login).
- **F9 · Disponibilidad temporal.** `availablefrom` futuro. Contrasta la lógica de ventana: oculto fuera de rango, reaparece al restaurar.
