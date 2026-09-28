# Registro de puertos y nombres — la convivencia se comprueba mirando, no recordando

> **La regla cambió el 21/08/2026.** Antes: «un proyecto a la vez» (METODOLOGIA §7). Ahora los
> despliegues de los proyectos ZAJUNA **conviven** en esta máquina hasta donde el procesamiento
> aguante, y ninguno hace `make down` del otro. Eso convierte los puertos y los nombres de
> contenedor en un recurso compartido, y un recurso compartido sin registro se agota en silencio:
> el síntoma de una colisión (un `bind: address already in use`, o peor, una aplicación que
> contesta donde no debe) aparece muy lejos de su causa.
>
> **Antes de levantar cualquier despliegue nuevo**: mira esta tabla y `ss -ltnp`. Después de
> levantarlo: apúntalo aquí. Es todo el procedimiento.

## Ocupado ahora

| Proyecto | Contenedores | Puertos publicados | Notas |
|---|---|---|---|
| **#3 analitica_notificaciones** | `reportes_api`, `reportes_worker`, `reportes_redis` | `0.0.0.0:8089` (API) | **Permanente.** Redis y worker sin publicar. No se baja. |
| **#2 reportes_de_cursos** (ZAJUNA Early Alert) | `zea-demo-api`, `zea-demo-front`, `zea-demo-redis` | `39097` API (loopback), `39174` front (loopback), `6380` Redis (loopback), `39088` solo con perfil `proxy` | La API corre en `network_mode: host` porque el PostgreSQL nativo solo escucha en loopback. |
| **#8 centro_calificaciones** | `calif_web`, `calif_mongo` | `127.0.0.1:8097` (Apache+PHP8.2, 2 apps), `127.0.0.1:27117` (MongoDB 7) | Despliegue de auditoría, efímero (Mongo en tmpfs). BDs sandbox `calif_zajuna`/`calif_integracion` propias; NO toca el core ni la BD `integracion` de #7. NO funcional sin las 45 funciones que el manual mete en el core (P4): sirve superficie, no datos. |
| Infra ajena al laboratorio | `app0/app1/app2`, `kafka`, `zookeeper` | `5000`, `9092`, `29092`, `2181` (todos en loopback salvo lo indicado) | No es de ningún perfil del laboratorio. `make doctor` los reporta como huérfanos: no lo son. |
| Core ZAJUNA (bare metal) | — | `80`/`443` nginx (`zajuna.conf`), `5432` PostgreSQL (loopback) | `/` sirve un CMS; **Moodle vive bajo `/zajuna`**. Ver el aviso de abajo. |
| **#7 portafolio_del_aprendiz** | — (plugin, sin contenedor) | **ninguno** | `local_portafolio` es PHP DENTRO del core: no reserva puerto ni contenedor. Vive en `/var/www/zajuna/local/portafolio`, servido por el `location ~ ^/zajuna(...)\.php` existente. Su BD réplica es `integracion` en el PostgreSQL del core (5432), con rol de solo lectura `portafolio_integ_ro`. La convivencia se comprobó: 18 contenedores y los vecinos (`/encuestados`, `/zea-*`, `:8089`) igual antes y después. |

## Del propio laboratorio (solo mientras corre una dimensión)

| Servicio | Puerto | Fijado por |
|---|---|---|
| SonarQube | `SONAR_PORT` (9000 por defecto, se libera solo con `tools/sonar-free-port.sh`) | perfil |
| MobSF | `MOBSF_PORT` (8010) | perfil |
| Interfaz de triaje | `UI_PORT` (7777) | perfil |

Todos en `127.0.0.1`. `COMPOSE_PROJECT_NAME=seclab_<target>` ya evita el choque de **nombres**
entre perfiles; lo que no evita es el choque de **puertos**, porque esos sí son del host.

## El recurso compartido que no es un puerto: el nginx del core

`/etc/nginx/sites-available/zajuna.conf` es **un solo archivo para todos los proyectos**. Varios
manuales de despliegue traen un script que lo **reescribe entero** (el de #2 es
`scripts/install-nginx.sh`), y hacerlo tumbaría el CMS de `/` y las rutas que otro proyecto ya
tenga puestas.

**Regla:** a `zajuna.conf` se le **añaden `location`**, con copia previa y `nginx -t` antes de
recargar. No se sustituye. Quién ha añadido qué:

| Ruta | Proyecto | Destino | Estado |
|---|---|---|---|
| `/zea-api/` | #2 reportes_de_cursos | `127.0.0.1:39097/` (con barra final: quita el prefijo) | **puesto 2026-08-21** |
| `/zea-dashboard/` | #2 reportes_de_cursos | `127.0.0.1:39174` (sin barra final: Vite sirve con ese `base`) | **puesto 2026-08-21** |

`pendiente` = decidido y documentado, **todavía no escrito en el nginx**. Se marca `puesto
<fecha>` cuando `nginx -t` pase y la ruta responda. Esta columna es la diferencia entre un
registro y una intención.
