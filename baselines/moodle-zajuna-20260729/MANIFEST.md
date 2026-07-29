# Baseline: moodle-zajuna-20260729

Snapshot of the platform the audited plugins are deployed on. Read-only extraction; the source
server was not modified.

| | |
|---|---|
| Origen | `zajunapresencialpruebashp` (166) · `/var/www/zajuna` + PostgreSQL `zajunadb` |
| Fecha | 2026-07-29 |
| Moodle | `4.3.3+ (Build: 20240308)` — código y `mdl_config.release` coinciden |
| Plugins instalados | 461 |
| Cursos | 23.111 |
| Usuarios | 39.368 |

## Qué NO se trajo, y por qué

- **`mdl_logstore_standard_log` (64 de los 65 GB)** — sólo el esquema, ninguna fila. Es el
  registro de actividad: irrelevante para una línea base y es la tabla con más rastro de
  comportamiento individual. Excluirla deja el volcado en 110 MB.
- **`config.php`** — lleva las credenciales de la base de producción, el `wwwroot` real y la
  salt del sitio. La receta lo reescribe con lo que la copia necesita y nada más.
- **`moodledata` (9,2 GB)** — archivos subidos. No hace falta para medir el plugin; si algún
  día se necesita, se trae aparte y se decide entonces.

## Estado de los plugins auditados

`local_slider` y `local_slider_form` **no están instalados en el 166**. Este baseline aporta la
plataforma, no el proyecto: la receta instala los plugins desde el checkout bajo auditoría.

## Neutralización

Se aplica al restaurar, antes de que el puerto responda — ver
`recipes/moodle-baseline/db-init/02-neuter.sh`. Correo saliente apagado, tokens de webservice
borrados, sesiones heredadas eliminadas, `wwwroot` reescrito, tareas programadas desactivadas.

## Caducidad

Una línea base miente en cuanto la plataforma cambia. Volver a tomarla tras cada despliegue
mayor del 166. `RUN.md` registra cuál se usó: dos auditorías tomadas contra baselines distintos
no son comparables.
