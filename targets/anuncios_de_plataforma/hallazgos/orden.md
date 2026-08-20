Agrupado por quién puede ejecutarlo, y dentro de cada grupo por lo que desbloquea a los demás.

### Hoy — Líder Técnico + Backend

| # | Acción | Por qué primero |
|---|---|---|
| §3.1 | **Rotar la contraseña del usuario `postgres`** en los entornos donde el valor del commit `68505d2` siga siendo válido | Es lo único del informe cuyo riesgo está vivo mientras se lee. No depende de ninguna otra tarea. |
| §3.1 | Retirar o marcar como obsoleto `docs/DESPLIEGUE_PREPROD.md` | Mientras exista, instruye a volver a incrustar la clave y la rotación se deshace sola. |

### Esta semana — Backend (desbloquean el despliegue)

| # | Acción | Por qué en este orden |
|---|---|---|
| §3.2 | Añadir `DROP TABLE IF EXISTS midb.regionales;` al inicio de la migración `004` | Una línea. Sin esto **ninguna** instalación limpia llega a crear la cola de correos, así que bloquea a todo lo demás. |
| §3.3 | Confirmar el contrato de `midb.envios2` con el dueño del proceso de envío y añadir la migración `014` con el tipo real (`midb.env_estado`, no `text`) | Depende de una conversación, no de código. Iniciarla ya; la migración es de diez minutos cuando llegue la respuesta. |
| §3.4 | Sacar `TIPO_CATEGORIAS` del código a `mdl_config_plugins`, y hacer visible el fallo cuando la cascada quede vacía | Es lo que decide si el módulo sirve para algo en esta plataforma. Requiere validación funcional (ver el ⟨PENDIENTE⟩ de §3.4). |
| §3.8 | Decidir **qué rol** de Zajuna recibe `:view` y `:edit`, documentarlo y concederlo | Desbloquea la dimensión de autorización, que es la que este informe no ha podido medir. |

### Cuando se retome el documento — Backend

| # | Acción |
|---|---|
| §3.5 | Escribir `slider/DEPLOY.md`, o absorber lo imprescindible y retirar las tres referencias |
| §3.7 | Añadir `defined('MOODLE_INTERNAL') \|\| die();` a los doce ficheros, y borrar `showSlider_7_noviembre.php` |
| §3.6 | Ampliar las exclusiones de §10.1 con `docs/*.md` y `README.md` |
| — | Corregir en §8.4 la afirmación de que la secuencia funciona en una base limpia, y cerrar en §8.5 la pregunta abierta con la evidencia de `midb.envios1` |

### DevOps / Infraestructura Zajuna — no es del equipo de Anuncios

Estos salieron del escaneo dinámico pero pertenecen al `nginx` de la plataforma y a Moodle core.
Se listan aquí para que tengan dueño, no para que los atienda este equipo:

| Qué | Detalle |
|---|---|
| `X-Frame-Options` **duplicado** | Llegan dos cabeceras, `sameorigin` (Moodle) y `SAMEORIGIN` (el `add_header` de nginx). Repetida, algunos navegadores la ignoran. Se resuelve quitando el `add_header`: Moodle ya la emite. Afecta a toda la plataforma. |
| Sin `Content-Security-Policy` | El `nginx` ya emite HSTS, `X-Content-Type-Options`, `X-Frame-Options` y `Referrer-Policy`. Añadir CSP es el mismo fichero. |
| `Server: nginx/1.24.0 (Ubuntu)` | Se silencia con `server_tokens off`. |
| §3.6 (capa servidor) | Negar `.sql`, `.md` y demás bajo `/local/` — ver la regla propuesta en §3.6 |

### QA — lo que hay que conseguir para la próxima ronda

- **Dos cuentas reales de privilegio distinto** en el Zajuna donde se mida, una con
  `local/slider_form:edit` y otra sin ninguna de las dos capabilities. Depende de §3.8.
- Confirmar con el área funcional si la base de esta máquina es representativa del entorno
  destino (⟨PENDIENTE⟩ de §3.4).
