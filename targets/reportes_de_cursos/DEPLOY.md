# Deploy local

Guía para levantar **ZAJUNA Early Alert** en una máquina limpia reproduciendo la
arquitectura del servidor, no el modo desarrollo.

Todo lo de aquí sale del repositorio: `docker-compose.yml`, `setup.sh`,
`scripts/*.sh`, `deploy/*.template`, `zea-api/Dockerfile`, `zea-api/internal/config/config.go`,
`vue-app/vite.config.js`, `plugin/version.php` y los workflows de `.github/`.
**Donde el código y la documentación no coinciden, manda el código**, y así está anotado.

> **Lo que este repositorio NO trae, y hay que saberlo antes de empezar:** este
> proyecto es un **plugin de Moodle más un servicio Go de reportes**. **Moodle y
> PostgreSQL son NATIVOS del host y no los provee ningún compose de este repo**
> (`docker-compose.yml`, cabecera). Una máquina «limpia» necesita, antes de nada, un
> **Moodle 4.3+ funcionando con PostgreSQL**. Montar ese Moodle queda fuera del
> alcance de este documento porque **el repositorio no contiene material para
> hacerlo** — ver §24, «Lo que este documento NO puede afirmar».

---

## 1. Objetivo

Reproducir localmente el comportamiento del servidor:

- una **única puerta de entrada** (single-origin), no tres puertos sueltos;
- el **SPA compilado y servido como estático**, no `vite dev` con HMR;
- la **API Go como binario compilado** en contenedor, no `go run`;
- el **plugin instalado dentro de Moodle** y actualizado por su CLI;
- las **vistas materializadas** creadas antes de arrancar la API.

Por qué single-origin importa: el SPA embebido en Moodle pide los reportes a
`/zea-api` **en ruta relativa** (`VITE_API_BASE=/zea-api`, `.env.production`). Si esa
ruta no existe en el servidor web, la petición cae en `location /` → Moodle → **303 al
login**, y el dashboard recibe una redirección en vez de JSON
(`scripts/install-nginx.sh`, cabecera).

---

## 2. Arquitectura local

```
                    Navegador
                        │
                        ▼
        ┌───────────────────────────────┐
        │  Servidor web (nginx)          │  ← puerta única
        │  puerto del wwwroot de Moodle  │
        └───────────────────────────────┘
             │            │            │
   /         │   /zea-api │  /zea-dashboard
             ▼            ▼            ▼
      ┌───────────┐  ┌─────────┐  ┌──────────┐
      │  Moodle   │  │ API Go  │  │ SPA Vue  │
      │  php-fpm  │  │ zea-api │  │ (estático│
      │  (nativo) │  │ :39097  │  │  :39174) │
      └───────────┘  └─────────┘  └──────────┘
             │            │  │
             ▼            ▼  ▼
      ┌────────────────────┐ ┌───────┐
      │ PostgreSQL (nativo)│ │ Redis │
      │  127.0.0.1:5432    │ │ (contenedor)
      └────────────────────┘ └───────┘
```

Además, **el plugin embebe widgets dentro de las páginas de Moodle**: el bundle
`plugin/js/` se compila desde `vue-app/src` (`vite.config.js`, entorno `widgets`,
`outDir: ../plugin/js`) y esos widgets llaman a `/zea-api` por el mismo origen.

**Autenticación entre capas:** Moodle firma un **JWT RS256** en `plugin/token.php` con
una clave privada; la API Go **verifica** con `JWT_PUBLIC_KEY` (PEM en base64) y
**se niega a arrancar sin ella** (`internal/config/config.go:113`).

**Dos formas de tener la puerta única** — las dos existen en el repo:

| | Cómo | Cuándo |
|---|---|---|
| **A. nginx del host** | `scripts/install-nginx.sh` instala `deploy/nginx-moodle.conf.template` como el site de Moodle | **Es lo que hace el servidor real.** Elegir ésta para paridad |
| **B. nginx en contenedor** | `docker compose --profile proxy up`, sirve en `PROXY_PORT` (por defecto 39088) | Demo autocontenida. **Ver el aviso de §11: hoy está roto para `/zea-api/`** |

---

## 3. Requisitos previos

Versiones tomadas del repositorio, no de costumbre:

| Requisito | Versión | De dónde sale |
|---|---|---|
| **Moodle** | ≥ 4.3 (`$plugin->requires = 2023100900`). La instalación de referencia es **4.3.3+ (Build 20240308)** | `plugin/version.php`; `version.php` del Moodle instalado |
| **PHP** | **8.0.0 mínimo, 8.2.x máximo** — lo fija Moodle 4.3, no este plugin. El proyecto se desarrolla y analiza sobre **8.1** | `admin/environment.xml` de Moodle (mínimo) + [notas de la versión 4.3](https://moodledev.io/general/releases/4.3) (techo); `sonar-project.properties` para el 8.1 |
| **PostgreSQL** | **≥ 13** (mínimo de Moodle 4.3). Es la base de Moodle: este proyecto no tiene una propia | `admin/environment.xml` de Moodle |
| **Docker Engine + Compose** | **Compose ≥ 2.24** (obligatorio: el compose usa `env_file` en forma larga) | `scripts/docker-up.sh` comprueba y aborta si no |
| **Go** | 1.26.6 mínimo — **sólo si compilas fuera de Docker** | `zea-api/go.mod` |
| **Bun** | 1.3.14 (imagen `oven/bun:1.3.14-alpine`) — **sólo si compilas fuera de Docker** | `docker-compose.yml` |
| **nginx** | Opción A: el del host. Opción B: `nginx:1.30-alpine` | `deploy/`, `docker-compose.yml` |
| **openssl** | Para derivar la clave pública del JWT | `scripts/docker-up.sh` |

Comprobación rápida:

```bash
docker compose version    # >= 2.24
php --version             # entre 8.0 y 8.2 — ver el aviso de abajo
psql --version            # >= 13
```

> ### ⚠️ PHP 8.3 NO sirve para este Moodle
>
> **Moodle 4.3 soporta hasta PHP 8.2.x.** En la máquina de referencia conviven
> `php8.1-fpm` y `php8.3-fpm`, y **el site de Moodle tiene que apuntar al 8.1**
> (o a un 8.2), nunca al 8.3. Comprueba a cuál apunta antes de dar nada por bueno:
>
> ```bash
> systemctl list-units --type=service | grep fpm      # qué versiones hay instaladas
> grep -R fastcgi_pass /etc/nginx/sites-enabled/      # a cuál apunta el site
> ```
>
> **`-R` mayúscula, no `-r`.** `sites-enabled/` son SYMLINKS a `sites-available/`, y
> `grep -r` **no los sigue**: devuelve vacío y se lee como «no hay nada configurado»
> cuando lo que hay es un enlace sin seguir. Medido el 2026-08-20 en esta máquina.
>
> `scripts/install-nginx.sh` resuelve el socket **del que exista en el host**; si hay
> varios, revisa que eligió el correcto. Éste es el mismo fallo que ya tumbó Moodle
> una vez en este proyecto (un socket de php-fpm que no existía → 502 en todo el PHP),
> y está contado en la cabecera de `deploy/nginx-moodle.conf.template`.

### `max_input_vars` tiene que ser ≥ 5000 — en CLI **y** en FPM

Moodle lo comprueba y lo marca como «esta prueba debe pasar». El valor por defecto de
PHP es **1000**, y con ese valor un formulario grande —permisos de rol, ajustes de
curso— **descarta las variables sobrantes en silencio**: no da error, guarda menos de
lo que enviaste. Además, el `upgrade` de Moodle **se niega a correr** si no se cumple,
que es como se detecta (`install_to_moodle.sh` → `scripts/phpunit.sh` fallan en el
paso del deploy).

Se pone en `conf.d`, no editando `php.ini`, para que sobreviva a las actualizaciones
del paquete:

```bash
echo 'max_input_vars = 5000' | sudo tee \
  /etc/php/<version>/cli/conf.d/99-zea-moodle.ini \
  /etc/php/<version>/fpm/conf.d/99-zea-moodle.ini
sudo systemctl restart php<version>-fpm
php -r 'echo ini_get("max_input_vars"), "\n";'      # 5000
```

### `pcov` NO puede estar cargado en el FPM

`scripts/coverage-php.sh` necesita pcov **en el CLI** y lo enciende él mismo por
`-d pcov.enabled=1 -d pcov.directory=<plugin>`. Cargado en el **FPM**, en cambio,
`pcov.directory` vale `auto`, que bajo el servidor web resuelve al **docroot de
Moodle**: cada petición instrumenta el árbol entero. Medido el 2026-08-20 al migrar
esta máquina: la portada pasó de responder en 8 s a **agotar 30 s sin contestar**.

```bash
sudo phpdismod -v <version> -s fpm pcov
sudo systemctl restart php<version>-fpm
ls /etc/php/<version>/fpm/conf.d/ | grep -i pcov     # no debe salir nada
```

Es un paso que el propio repositorio ya documentaba (`docs/cobertura-php-pcov-2026-08-19.md`,
y el mensaje de error de `coverage-php.sh`), y que se olvida al instalar una versión
nueva de PHP.

> **Nota:** Go y Bun **no** hacen falta para desplegar: la API se compila dentro de su
> `Dockerfile` (etapa `golang:1.26-alpine`) y el front dentro del contenedor
> `oven/bun`. Sólo se necesitan para correr el gate de calidad (`scripts/gate.sh`).

---

## 4. Preparación de la máquina

1. **Moodle con PostgreSQL funcionando.** El repo lo da por hecho y lo localiza con la
   cascada de `scripts/lib/moodle-root.sh`; se puede forzar con `MOODLE_ROOT=/ruta`.

2. **Clonar el repositorio** en el host (no dentro de Moodle: el instalador copia el
   plugin por `rsync`).

3. **Comprobar que Moodle responde** por su `wwwroot` antes de seguir. Todo lo demás
   depende de ese puerto.

---

## 5. Configuración de hostname

**No hay dominio propio de la aplicación.** El hostname es el de Moodle: la SPA y la
API cuelgan del **mismo origen** que él (`/zea-dashboard/` y `/zea-api/`).

Consecuencia práctica: **el hostname local es el que ya tenga `$CFG->wwwroot`**. En la
instalación de desarrollo de este repo es `localhost:8081`
(`VITE_MOODLE_HOST` por defecto en `docker-compose.yml`).

Sólo si tu Moodle usa un nombre de dominio, añádelo a `/etc/hosts`:

```bash
# Sólo si $CFG->wwwroot NO es localhost.
echo "127.0.0.1  <el-host-de-tu-wwwroot>" | sudo tee -a /etc/hosts
```

> **No inventes un dominio nuevo**: si `wwwroot` dice `localhost:8081` y entras por otro
> nombre, Moodle redirige y la sesión no viaja.

---

## 6. Variables de entorno

Fuente: `.env.example` (plantilla comentada) contrastado con
`zea-api/internal/config/config.go`. **Nunca pongas secretos reales en el repo**: `.env`
está en `.gitignore` y `docker-compose.yml` lo marca `required: false`.

### Obligatorias — sin ellas la API **no arranca**

| Variable | Propósito | Qué pasa si falta |
|---|---|---|
| `JWT_PUBLIC_KEY` | Clave **pública** RSA en PEM **codificado en base64**. Verifica el JWT que firma `plugin/token.php` | `JWT_PUBLIC_KEY environment variable must be set — refusing to start with no verification key` (`config.go:115`) |
| `DB_PASSWORD` | Contraseña de PostgreSQL | `DB_PASSWORD environment variable must be set — refusing to start and try a default credential` (`config.go:139`). **No tiene valor por defecto a propósito** |

Las dos las rellena automáticamente `scripts/docker-up.sh` leyendo el `config.php` de
Moodle y derivando la pública de la privada real con la que **firma** `token.php`.

### Con valor por defecto (`config.go:145-168`)

| Variable | Defecto | Nota |
|---|---|---|
| `APP_PORT` | `8090` (el compose pasa `39097`) | Puerto de la API |
| `BIND_ADDR` | `127.0.0.1` | Admite **varias direcciones separadas por comas** (`cmd/server/main.go:202`) |
| `DB_HOST` / `DB_PORT` | `localhost` / `5432` | El compose fuerza `127.0.0.1` |
| `DB_NAME` / `DB_USER` | `moodle` / `moodle` | |
| `DB_SSLMODE` | `disable` | |
| `DB_PREFIX` | `mdl_` | **Tiene que casar con `$CFG->prefix`** o el preflight falla |
| `REDIS_ADDR` | `localhost:6379` | El compose pasa `127.0.0.1:${REDIS_PORT}` |
| `REDIS_PASSWORD` / `REDIS_DB` | vacío / `0` | |
| `CACHE_TTL_SECONDS` | `600` | |
| `JWT_ISSUER` | `block_zajuna_early_alert` | Debe casar con lo que emite `token.php` |
| `JWT_AUDIENCE` | `zajuna-early-alert-api` | |
| `ALLOW_ORIGIN` | vacío | **Déjalo vacío**: single-origin no necesita CORS. Con `*` el servicio avisa `insecure for production` (`cmd/server/app.go:92`) |
| `LOG_LEVEL` | `info` | |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_DIVERT_TO` | vacío / `587` | Correo saliente. **Opcional** |

### Sólo de despliegue / front (las lee el compose o Vite, no la API Go)

`MOODLE_ROOT`, `MOODLE_WWWUSER`, `FRONT_PORT`, `PROXY_PORT`, `MOODLE_UPSTREAM`,
`REDIS_PORT`, `VITE_API_BASE`, `VITE_MOODLE`, `VITE_GO_API`, `VITE_MOODLE_HOST`,
`VITE_MOODLE_COOKIE`, `E2E_MOODLE_USERNAME`, `E2E_MOODLE_PASSWORD`.

### Contraste `.env.example` ↔ código — **discrepancias reales**

Comprobado el 2026-08-20 leyendo `config.go`:

- **`PLUGIN_SRC`, `ZEA_API_DIR`, `FRONT_HOST`, `BACK_HOST`, `VITE_SESSKEY`,
  `VITE_MOODLE_BASE`, `VITE_WWWROOT`** aparecen en `.env.example` y **la API Go no las
  lee**. No las trates como obligatorias. `install_to_moodle.sh` dice explícitamente que
  **no** usa `PLUGIN_SRC` (usa el directorio del propio script).
- **`DB_PASSWORD` figura en `.env.example` con el valor `moodlepass`.** Es una
  plantilla: en el código **no hay defecto** y arrancar con ese valor es justo lo que
  `config.go` documenta como peligroso («se conecta a la base equivocada y sirve datos
  que no son»). **Cámbialo.**
- **`ALLOW_ORIGIN=*`** aparece en el `.env` de la máquina de desarrollo de este repo.
  **Para paridad con servidor debe ir vacío.**

---

## 7. Dependencias

No hay paso manual de dependencias si usas Docker: **cada capa instala las suyas en su
contenedor**.

- **API Go** — `zea-api/Dockerfile`: `go mod download` y build estático `CGO_ENABLED=0`.
- **Front** — el contenedor corre `bun install --frozen-lockfile` (`docker-compose.yml`,
  `command`). El lockfile manda: si `package.json` y `bun.lock` no casan, **falla**.
- **Plugin PHP** — **no tiene gestor de dependencias**: no hay `composer.json` en el
  repositorio.

Sólo si vas a correr el gate de calidad en el host:

```bash
cd vue-app && bun install --frozen-lockfile
```

---

## 8. Base de datos

**Motor:** PostgreSQL, **nativo del host**, escuchando en `127.0.0.1:5432`. Es la
**misma base que usa Moodle** — la API Go no tiene base propia: lee las tablas de
Moodle (`mdl_*`) y unas vistas materializadas propias.

Por eso el contenedor de la API corre con `network_mode: host`: el Postgres nativo sólo
escucha en loopback y **el bridge de Docker no lo alcanza** (`docker-compose.yml`).

### Credenciales

**No las escribas a mano.** `scripts/docker-up.sh` las lee del `config.php` de Moodle
(`$CFG->dbname`, `dbuser`, `dbpass`, `prefix`, `dboptions[dbport]`) y las escribe en
`./.env`.

### Migraciones — son **dos** cosas distintas y en este orden

1. **Esquema del plugin (PHP)** — lo aplica el **upgrade de Moodle**: tablas
   `block_zajuna_early_alert_*`, servicios web y tareas programadas.

   ```bash
   sudo bash install_to_moodle.sh      # copia el plugin y corre el upgrade
   ```

2. **Vistas materializadas del servicio Go** — DDL en `zea-api/db/migrations/`:
   `login.sql`, `activity.sql`, `outcomes.sql` (+ `outcomes_rename_prefix.sql`,
   `outcomes_unique_indexes.sql`).

   ```bash
   bash scripts/recreate-analytics-mv.sh --check     # diagnóstico, no toca nada
   bash scripts/recreate-analytics-mv.sh --force     # recrea las que estén derivadas
   ```

> **La API se NIEGA a arrancar si falta una MV.** Al arrancar comprueba seis relaciones
> —`mv_zea_login_daily`, `mv_zea_login_resources`, `mv_zea_activity_counts`,
> `mv_zea_course_students`, `mv_zea_rap_detail`, `mv_zea_rap_rollup`— con el prefijo
> configurado, y sale con error si falta alguna (`internal/db/preflight.go`,
> `cmd/server/main.go:59`). Es deliberado: sin ellas los reportes saldrían **vacíos en
> silencio**, y «un dato vacío que parece un dato es lo peor que puede servir este
> servicio, porque alguien decide sobre él».

### Datos iniciales (seeds)

Sin ellos el tablero sale vacío aunque todo funcione.

```bash
sudo bash scripts/seed.sh              # tareas de poblado por defecto
sudo bash scripts/seed.sh --list       # sólo muestra qué correría
sudo bash scripts/seed-all.sh          # SIMULACRO de punta a punta: nadie escribe
sudo bash scripts/seed-all.sh --apply  # aplica
```

**El orden importa**: `seed-all.sh` lo documenta — riesgo y matviews se calculan desde
la participación, así que refrescarlos **antes** de sembrar deja «un tablero que parece
poblado y muestra los números de antes».

### Comprobar la base

```bash
# Existencia de las MV que exige el preflight.
psql -h 127.0.0.1 -U <usuario> -d <base> -c \
  "SELECT matviewname FROM pg_matviews WHERE matviewname LIKE '%mv_zea%' ORDER BY 1;"
```

---

## 9. Servicios auxiliares

| Servicio | ¿Obligatorio? | Cómo se levanta | Puerto | Verificación |
|---|---|---|---|---|
| **Redis** | **Sí** — la API lo abre siempre (`cache.New`, `cmd/server/main.go`) | Contenedor `zea-demo-redis` del compose | `127.0.0.1:${REDIS_PORT}` → 6379 interno | `docker exec zea-demo-redis redis-cli ping` |
| **SMTP** | **No** | Externo. Se configura con `SMTP_*`; hay `scripts/apply-smtp.sh` | `SMTP_PORT` (def. 587) | `GET /api/v1/email/health` (`internal/mailer/http.go:24`) |
| **Cron de Moodle** | **Sí para las notificaciones** | El cron del host | — | `scripts/health.sh` mira la última corrida y el backlog |
| **Worker de envíos** | No | `deploy/zea-notif-worker.service` (systemd, usuario `www-data`) | — | `systemctl status zea-notif-worker` |
| **SonarQube** | **No** — sólo análisis de calidad | `./sonar.sh up` (`docker-compose.sonar.yml`) | 9000 en loopback | `./sonar.sh status` |

Redis arranca con persistencia **desactivada** (`--save "" --appendonly no`) y
`maxmemory 256mb` con `allkeys-lru`: es caché, **no** almacén.

---

## 10. Build

El despliegue **compila**; no usa servidor de desarrollo. Con Docker se hace solo:

- **API Go** — build multi-etapa en `zea-api/Dockerfile`: binario estático, imagen final
  `alpine:3.24`, **usuario no root** (`app`, uid 10001).
- **Front** — el contenedor ejecuta, en este orden (`docker-compose.yml`, `command`):

  ```
  bun install --frozen-lockfile
  bun run scripts/gen-strings.mjs      # deriva las cadenas desde plugin/lang
  bunx vite build --app                # compila LOS DOS entornos
  bunx vite preview --host 0.0.0.0 --port ${FRONT_PORT} --strictPort
  ```

  `vite build --app` produce **dos artefactos** (`vue-app/vite.config.js`):
  **(a)** la SPA en `vue-app/dist` con base `/zea-dashboard/`, y **(b)** el bundle de
  widgets en `../plugin/js`, que es el que sirve Moodle dentro de sus páginas.

> **`vite preview` sirve el build, no el código fuente**: sin HMR y sin watcher, «robusto
> (evita los 502/504 del dev server)». Eso es lo que da la paridad.
>
> El contenedor **no** llama a `bun run build` a propósito: ese script encadena `vue-tsc`
> y un error de tipos tumbaría la demo. Los tipos los comprueba el gate.

Build en el host (sólo si no usas el contenedor del front):

```bash
cd vue-app
bun install --frozen-lockfile
bun run build           # vue-tsc + vite build --app
bun run check:bundle    # presupuesto de tamaño del bundle
```

---

## 11. Reverse proxy / Web server

### Opción A — nginx del host (**la del servidor real**)

```bash
./scripts/install-nginx.sh --dry-run   # renderiza y enseña el diff contra el site vivo
./scripts/install-nginx.sh             # instala (pide sudo, con backup y rollback)
```

Instala `deploy/nginx-moodle.conf.template` **resolviendo en el momento** los valores que
cambian por máquina: puerto y `server_name` del `wwwroot`, `dirroot`, `dataroot` y el
socket real de php-fpm; los puertos de la app salen de `./.env`. El script **valida con
`nginx -t` y revierte si falla**, y **para** si el puerto ya lo sirve otro site.

Rutas que instala:

| Ruta | Destino | Detalle |
|---|---|---|
| `/` | Moodle (php-fpm por socket unix) | `try_files` + `fastcgi_pass` |
| `/zea-api/` | `127.0.0.1:${APP_PORT}/` | **La barra final elimina el prefijo.** Sin ella el Go recibe `/zea-api/reports/...` y devuelve 404 |
| `/zea-dashboard/` | `127.0.0.1:${FRONT_PORT}` | **Sin** barra final: el prefijo se conserva, porque Vite sirve con ese `base` |
| `/dataroot/` | `internal` + `alias` al dataroot | X-Sendfile de Moodle |

Cabeceras que reenvía a la API: `Host`, `X-Real-IP`, `X-Forwarded-For`,
`X-Forwarded-Proto` y **`Authorization`** — sin esta última el JWT no llega y todo
responde 401.

### Opción B — nginx en contenedor (perfil `proxy`)

```bash
docker compose --profile proxy up -d --build
# Puerta única en http://localhost:${PROXY_PORT:-39088}/
```

> ### ⚠️ Aviso verificado: hoy esta opción NO sirve `/zea-api/`
>
> `deploy/nginx.stack.conf.template` resuelve el upstream como `zea-api:${APP_PORT}` por
> el DNS de Docker, pero **el contenedor de la API corre en `network_mode: host`** y por
> tanto **no está en la red del compose**. Comprobado el 2026-08-20:
>
> ```
> docker inspect zea-demo-api  --format '{{.HostConfig.NetworkMode}}'  →  host
> docker inspect zea-demo-front --format '{{.HostConfig.NetworkMode}}' →  blockzajunaearlyalert_default
> ```
>
> El nombre `zea-api` no tiene registro DNS en esa red. nginx **arranca igual** (usa
> `resolver` + variable, a propósito), pero `/zea-api/` devolverá **502**. `/` y
> `/zea-dashboard/` sí funcionan.
>
> **Para paridad con el servidor, usa la opción A.** Si necesitas la B, el upstream de
> `/zea-api/` tendría que apuntar a `host.docker.internal:${APP_PORT}` — **ese cambio no
> está hecho en el repo y no lo he probado**.

---

## 12. HTTP / HTTPS

**Local: HTTP.** Ninguna de las dos rutas de despliegue local genera certificados, y el
repositorio **no trae** ningún mecanismo para emitirlos. `deploy/nginx-moodle.conf.template`
escucha en HTTP y `deploy/nginx.stack.conf.template` en `listen 80`.

**El servidor de producción sí usa HTTPS**: `deploy/nginx-prod-http3.conf.template` define
`listen 443 ssl`, `listen 443 quic` (HTTP/3) y espera certificados reales
(`ssl_certificate` / `ssl_certificate_key`, con Let's Encrypt como ejemplo).

**No se documenta cómo reproducir HTTPS localmente porque el repositorio no lo
soporta**: no hay plantilla de certificados de desarrollo, ni configuración de mkcert, ni
paso equivalente en ningún script. Inventarlo sería salirse de la fuente de verdad.

Consecuencia práctica para QA: si tu Moodle está en HTTPS, `scripts/docker-up.sh` lo
detecta y **avisa** («Moodle parece HTTPS; el perfil proxy espera HTTP»).

---

## 13. Frontend

Ya cubierto en §10. Lo importante para no confundir despliegue con desarrollo:

| | Desarrollo | **Este despliegue** |
|---|---|---|
| Servidor | `vite` (HMR) | `vite preview` sobre el build |
| Artefacto | ninguno | `vue-app/dist` + `plugin/js` |
| Base de rutas | dev | `/zea-dashboard/` |
| API | según `.env` | `/zea-api` **relativo** (`.env.production`) |

El SPA se sirve en `127.0.0.1:${FRONT_PORT}` y **se entra por el proxy**, no por ese
puerto:

```
http://<host-de-moodle>/zea-dashboard/?courseid=<ID>
```

---

## 14. Backend

- **Runtime:** binario Go estático en `alpine:3.24`, usuario no root.
- **Puerto:** `APP_PORT` (39097 en el compose; `8090` es el defecto del código y `8097` el
  `ENV` del Dockerfile).
- **Interfaz de escucha:** `BIND_ADDR`, **por defecto `127.0.0.1`**.

> **Sobre `0.0.0.0`:** el compose documenta que **no** debe usarse aquí. Estuvo clavado a
> `0.0.0.0` y contradecía el endurecimiento del propio proyecto: con `network_mode: host`
> el puerto queda publicado tal cual, y en WSL con `networkingMode=Mirrored` eso **saca la
> API a la LAN** con el JWT como única defensa. El valor correcto detrás de un proxy en el
> mismo host es el **loopback**.
>
> Excepción documentada: si el SPA lo sirve el contenedor del front (red bridge), éste
> llega por `host.docker.internal` → gateway `172.17.0.1`, así que en ese escenario
> `BIND_ADDR=127.0.0.1,172.17.0.1`. Sigue sin ser enrutable desde la LAN.

Arranque manual sin Docker (sólo si lo necesitas):

```bash
cd zea-api
set -a; . ../.env; set +a
CGO_ENABLED=0 go build -o /tmp/zea-api ./cmd/server && /tmp/zea-api
```

---

## 15. Inicio del entorno

### Camino recomendado — un solo comando

```bash
./setup.sh            # se auto-eleva a sudo
```

`setup.sh` orquesta, **en orden** (su propia cabecera):

1. libera los puertos de un `dev-up` previo (39174/39097);
2. despliega el plugin a Moodle y corre el **upgrade** + purga cachés;
3. provisiona `./.env` (credenciales de BD) y la **clave JWT** (la genera si falta);
4. levanta el stack en Docker (Redis + API + Front);
5. **puebla** las tablas;
6. **verifica** el despliegue;
7. imprime los pasos finales de nginx.

Variantes: `--proxy` (levanta también el nginx del compose), `--no-plugin`, `--no-seed`.

### Camino por partes

```bash
sudo bash install_to_moodle.sh          # 1. plugin + upgrade de Moodle
bash scripts/recreate-analytics-mv.sh --check   # 2. estado de las MV
sudo bash scripts/docker-up.sh          # 3. .env + JWT + docker compose up
sudo bash scripts/seed.sh               # 4. datos iniciales
bash scripts/install-nginx.sh           # 5. puerta única en el nginx del host
bash scripts/verify_deploy.sh           # 6. verificación post-upgrade
```

`docker-up.sh` **espera a que los contenedores estén sanos** antes de decir «listo», y
si alguno queda `unhealthy` o en bucle de reinicio lo dice con el comando para
diagnosticarlo.

---

## 16. Puertos

| Servicio | Puerto | Interno/Externo | ¿Publicado al host? | Quién lo consume |
|---|---|---|---|---|
| **nginx del host** (opción A) | el del `wwwroot` de Moodle | **Entrada pública** | sí | El navegador |
| **nginx del compose** (opción B) | `PROXY_PORT` (39088) | **Entrada pública** | sí (`${PROXY_PORT}:80`) | El navegador |
| Moodle / php-fpm | socket unix de php-fpm | interno | no | nginx |
| **API Go** | `APP_PORT` (39097) | interno | sí, **en loopback** vía `BIND_ADDR` | nginx, y el front |
| **SPA (vite preview)** | `FRONT_PORT` (39174) | interno | sí, `127.0.0.1:39174` | nginx |
| **Redis** | `REDIS_PORT` (def. 6380) → 6379 en el contenedor | interno | sí, **`127.0.0.1` sólo** | API Go |
| **PostgreSQL** | 5432 | interno | escucha sólo en `127.0.0.1` | Moodle y API Go (versión ≥ 13) |
| SonarQube | 9000 | herramienta | loopback | Navegador y escáner |
| Playwright (pruebas) | 39176 local / 39177 CI | herramienta | temporal | El gate |

Ninguno de los internos debe exponerse a la LAN. La publicación en `127.0.0.1:` de Redis
y del front es deliberada y está comentada en el compose.

---

## 17. Verificación

### Health checks reales

| Qué | Comando | Esperado |
|---|---|---|
| **API (directo)** | `curl -s http://127.0.0.1:39097/health` | `{"status":"ok"}` |
| **API (por el proxy)** | `curl -s -o /dev/null -w '%{http_code}\n' http://<host-moodle>/zea-api/health` | **200**. Un **303** significa que falta la `location` de nginx |
| **Métricas** | `curl -s http://127.0.0.1:39097/metrics \| head` | Texto formato Prometheus |
| **Correo** (si hay SMTP) | `GET /api/v1/email/health` **con JWT** | Ver `internal/mailer/http.go` |
| **Redis** | `docker exec zea-demo-redis redis-cli ping` | `PONG` |
| **Contenedores** | `docker compose ps` | `healthy` en `zea-demo-api` y `zea-demo-redis` |
| **Toda la pila** | `sudo bash scripts/health.sh` | php-fpm, front, API, cron de Moodle y matviews |
| **Despliegue del plugin** | `bash scripts/verify_deploy.sh` | Versión, tablas, servicios web y tareas |

`scripts/health.sh` es de **sólo lectura** y revisa lo que suele colgarse: workers de
php-fpm bloqueados (que tumban **todo** Moodle), el reenvío de puerto del front, `/health`
de la API, el cron de Moodle y el esquema de las matviews.

> **Córrelo con `sudo`** si quieres el chequeo de workers. Mide la **duración de la
> petición en curso** preguntando a php-fpm por su página de estado a través de su
> socket, y ese socket es del usuario del pool con modo `0660`: sin permiso, el script
> lo dice —con el comando para medirlo como su dueño— en vez de fingir un veredicto.
> Requiere además `pm.status_path` habilitado en el pool; si no lo está, también lo dice.
> Los demás chequeos no necesitan sudo.

> `/health` y `/metrics` son **públicos** — no piden JWT. Están a salvo porque el servicio
> escucha en loopback (`cmd/server/app.go:105`). Todo `/api/v1/*` **sí** exige JWT.

---

## 18. Smoke test

**Desde la puerta de entrada, nunca desde el puerto interno.**

```bash
MOODLE="http://<host-de-tu-wwwroot>"    # p. ej. http://localhost:8081

# 1. Moodle responde por la puerta.
#    OJO CON EL TIMEOUT: la portada de Moodle puede tardar VARIOS SEGUNDOS en frío
#    (medido en esta instalación: 9,5 s la primera vez). Con `-m 5` curl devuelve
#    000 y parece caída una portada perfectamente sana. Por eso -m 30.
curl -s -o /dev/null -m 30 -w 'moodle:      %{http_code} en %{time_total}s\n' "$MOODLE/"

# 2. La API responde POR EL PROXY (303 = falta la location de nginx).
curl -s -o /dev/null -m 10 -w 'zea-api:     %{http_code}\n' "$MOODLE/zea-api/health"

# 3. El SPA se sirve por el proxy.
curl -s -o /dev/null -m 10 -w 'dashboard:   %{http_code}\n' "$MOODLE/zea-dashboard/"

# 4. La API está viva de verdad (no un 200 del proxy).
curl -s -m 10 "$MOODLE/zea-api/health"      # {"status":"ok"}

# 5. La base responde: las seis MV que exige el preflight.
psql -h 127.0.0.1 -U <usuario> -d <base> -tAc \
  "SELECT count(*) FROM pg_matviews WHERE matviewname LIKE '%mv_zea%';"
```

**Los tres códigos deben ser 200.** Si el paso 4 responde `{"status":"ok"}`, la API está
arrancada — y **si arrancó, el preflight de esquema ya pasó**, porque si no el proceso
habría salido con error.

**Funcionalidad, en el navegador** (esto no se puede afirmar con `curl`: los reportes
exigen un JWT que emite Moodle para un usuario con sesión):

1. Entra a Moodle y **abre un curso** con el bloque añadido.
2. El bloque debe pintar sus widgets (vienen de `plugin/js`, mismo origen).
3. Abre `.../zea-dashboard/?courseid=<ID>` y comprueba que carga datos.
4. Si sale vacío: falta poblar → §8 «seeds».
5. Si sale 401: el JWT no valida → §21, «Troubleshooting».

---

## 19. Logs

```bash
# Contenedores (todos, en vivo).
docker compose logs -f
docker compose logs -f zea-api          # sólo la API
docker compose logs -f front            # build + preview del SPA
docker compose logs -f redis

# Detalle de salud de un contenedor concreto.
docker inspect --format '{{json .State.Health}}' zea-demo-api

# nginx del host (opción A) — rutas por defecto de la distribución.
sudo tail -f /var/log/nginx/error.log /var/log/nginx/access.log

# Moodle: php-fpm. AVERIGUA la unidad, no la supongas — en una misma máquina
# puede haber varias versiones instaladas (aquí conviven php8.1-fpm y php8.3-fpm).
systemctl list-units --type=service | grep fpm
sudo journalctl -u php8.1-fpm -f          # sustituye por la que sirva TU Moodle
# El log de Moodle depende de su configuración ($CFG->debug / debugdisplay).

# PostgreSQL: depende de la instalación del host.
sudo journalctl -u postgresql -f

# Worker de envíos (si lo instalaste).
sudo journalctl -u zea-notif-worker -f

# Última corrida de PHPUnit del plugin (la deja el gate).
cat tools/.phpunit-last.log
```

> **No inventes rutas de log:** las de nginx, php-fpm y PostgreSQL las fija la
> distribución, no este repositorio.

---

## 20. Reinicio del entorno

Simular un reinicio del servidor:

```bash
# 1. Parar (conserva volúmenes y datos).
docker compose down

# 2. Volver a levantar.
docker compose up -d          # o: sudo bash scripts/docker-up.sh

# 3. Dependencias: Moodle y PostgreSQL son del HOST, no del compose.
systemctl status postgresql nginx
systemctl list-units --type=service | grep fpm    # y la unidad de php-fpm que sirva tu Moodle

# 4. Migraciones: ¿siguen las MV?
bash scripts/recreate-analytics-mv.sh --check

# 5. Health checks (§17).
bash scripts/health.sh

# 6. Smoke test (§18).
```

Los contenedores llevan `restart: unless-stopped`, así que tras reiniciar la máquina
vuelven solos **si el demonio de Docker arranca**.

---

## 21. Troubleshooting

Problemas deducidos del propio repositorio, no genéricos:

| Síntoma | Causa | Arreglo |
|---|---|---|
| **La API no arranca; log: `JWT_PUBLIC_KEY ... refusing to start`** | Falta la clave pública | `sudo bash scripts/docker-up.sh` la deriva de la privada real de Moodle |
| **`DB_PASSWORD ... refusing to start`** | Falta la contraseña; **no tiene defecto a propósito** | Deja que `docker-up.sh` la lea del `config.php` |
| **`esquema incompleto` al arrancar** | Falta alguna de las 6 MV, o `DB_PREFIX` no casa con `$CFG->prefix` | `bash scripts/recreate-analytics-mv.sh --force` |
| **`/zea-api/health` devuelve 303** | Falta la `location` en nginx: la petición cae en Moodle y redirige al login | `bash scripts/install-nginx.sh` |
| **401 en todos los reportes** | La pública de `.env` no corresponde a la privada con la que firma `token.php` | `sudo bash scripts/docker-up.sh` (respeta la precedencia fichero→BD, igual que `token.php`) |
| **502 en `/zea-api/` con el perfil `proxy`** | El contenedor de la API está en red `host` y nginx no resuelve `zea-api` | Usa la **opción A** (§11) |
| **`docker compose` falla al parsear el YAML** | Compose < 2.24 no entiende `env_file` en forma larga | Actualiza Compose |
| **El dashboard carga pero sale vacío** | Falta poblar | `sudo bash scripts/seed.sh` |
| **Todo Moodle deja de responder (504/000)** | Workers de php-fpm bloqueados en I/O (típico: SMTP muerto) | `bash scripts/health.sh` lo detecta y sugiere la mitigación |
| **Editaste la configuración de nginx equivocada** | En la máquina puede haber **varias versiones de php-fpm** y varios sites | No claves valores: usa `scripts/install-nginx.sh`, que los resuelve de la propia máquina |
| **`bun run build` falla con `EACCES` en `vue-app/dist`** | **Arreglado el 2026-08-20**: el contenedor del front construye como root y su `dist` invadía el árbol del host. Ahora ese contenedor escribe en un `tmpfs` propio y `docker-up.sh` crea `vue-app/dist` y `vue-app/node_modules` como el usuario real | Si aparece en un árbol antiguo: `sudo chown -R "$USER" vue-app/dist` y vuelve a levantar con `scripts/docker-up.sh` |
| **`unhealthy` permanente con la API respondiendo 200** | `BIND_ADDR` con varias direcciones; el healthcheck prueba **la primera** | Ver el `HEALTHCHECK` del `Dockerfile` |
| **El contenedor del front no arranca: lockfile** | `bun install --frozen-lockfile` con `package.json` y `bun.lock` desincronizados | Regenera el lockfile y vuelve a construir |
| **Dos APIs escuchando** | Un compose antiguo en `zea-api/` (ya eliminado) | Sólo hay **un** compose: el de la raíz |
| **Moodle redirige al entrar** | Entraste por un host distinto del `$CFG->wwwroot` | §5 |
| **`curl` devuelve `000` en la portada de Moodle** | **No es una caída**: es el timeout de curl. La portada tarda varios segundos en frío (9,5 s medidos aquí) | Sube el timeout (`-m 30`). Si de verdad no responde, `bash scripts/health.sh` mira los workers de php-fpm |

---

## 22. Limpieza

### Segura — no borra datos

```bash
docker compose down                 # para y elimina contenedores; CONSERVA volúmenes
docker compose stop                 # sólo para
docker compose up -d --build        # reconstruye imágenes y vuelve a levantar
```

### ⚠️ Destructivas — leer antes de ejecutar

> **`docker compose down -v` borra el volumen `zea_front_node_modules`.** No hay datos de
> la aplicación ahí (Redis corre **sin persistencia** y PostgreSQL es del host), así que
> se pierde sólo la caché de dependencias del front: la siguiente subida tardará más.
>
> **`./sonar.sh destroy` borra los volúmenes de SonarQube**, incluido el **histórico de
> análisis**. Pide confirmación escrita.
>
> **`scripts/recreate-analytics-mv.sh --force` recrea vistas materializadas** en la base
> **compartida con Moodle**. No toca tablas de Moodle, pero opera sobre la base real:
> hazlo fuera de horas de uso.
>
> **Nunca** ejecutes `DROP` sobre las tablas `mdl_*`: son las de Moodle.

Reconstruir desde cero, sin tocar la base:

```bash
docker compose down
docker compose build --no-cache
sudo bash scripts/docker-up.sh
```

---

## 23. Server parity checklist

- [ ] Máquina preparada (Moodle 4.3+ y PostgreSQL nativos y funcionando).
- [ ] Docker Engine y **Compose ≥ 2.24** instalados.
- [ ] `./.env` provisionado (por `scripts/docker-up.sh`, no a mano).
- [ ] `JWT_PUBLIC_KEY` presente y **derivada de la privada real** de `token.php`.
- [ ] `DB_PASSWORD` presente y **distinta** del ejemplo.
- [ ] `ALLOW_ORIGIN` **vacío** (single-origin, sin CORS).
- [ ] `DB_PREFIX` igual a `$CFG->prefix`.
- [ ] Hostname: se entra por el `$CFG->wwwroot` de Moodle (§5).
- [ ] Plugin desplegado y **upgrade de Moodle** ejecutado.
- [ ] Las **6 vistas materializadas** existen (`recreate-analytics-mv.sh --check`).
- [ ] Seeds ejecutados (si el entorno debe tener datos).
- [ ] Redis levantado y respondiendo `PONG`.
- [ ] API construida y **escuchando en loopback**, no en `0.0.0.0`.
- [ ] Frontend **construido** (`vite build --app`) y servido con `vite preview`.
- [ ] Bundle de widgets presente en `plugin/js`.
- [ ] Reverse proxy configurado con `/zea-api/` y `/zea-dashboard/` (opción A).
- [ ] HTTPS: **no aplica en local** — el repo no lo soporta (§12).
- [ ] `curl <moodle>/zea-api/health` devuelve **200**, no 303.
- [ ] `docker compose ps` sin contenedores `unhealthy`.
- [ ] `bash scripts/health.sh` sin fallas.
- [ ] `bash scripts/verify_deploy.sh` en verde.
- [ ] Smoke test completo (§18), incluida la comprobación en navegador.
- [ ] Reinicio completo probado (§20).

---

## 24. Lo que este documento NO puede afirmar

Escrito aparte, en vez de rellenado con suposiciones:

1. **Cómo instalar Moodle y PostgreSQL desde cero.** El repositorio los da por existentes
   en el host y **no contiene** compose, Dockerfile ni script que los provisione.
2. **HTTPS local.** No hay ningún mecanismo de certificados de desarrollo en el repo
   (§12). El único fichero con TLS es la plantilla de **producción**.
3. **Rutas de log de nginx, php-fpm y PostgreSQL.** Las fija la distribución.
4. **La versión exacta de PostgreSQL** del servidor. Lo que sí consta: el **mínimo es
   13** (`admin/environment.xml` de Moodle 4.3). La imagen `postgres:17-alpine` que
   vigila `check-base-images.sh` **no** es la base que usa la aplicación — ésa es
   nativa del host.
5. **Si el perfil `proxy` alguna vez sirvió `/zea-api/`.** Está roto hoy por lo del §11;
   no he encontrado en el repo constancia de cuándo cambió.
6. **CI/CD como fuente de despliegue.** Los dos workflows son de **calidad**, no de
   despliegue: `ci.yml` está **desactivado por presupuesto** (sólo `workflow_dispatch`) y
   `gate.yml` corre `scripts/gate.sh` en un runner self-hosted. **No hay ningún pipeline
   que despliegue**, así que la referencia de despliegue son `setup.sh` y los scripts.
