# Deploy local — Reportes ZAJUNA

> QA técnico: reproducir localmente, con la mayor fidelidad razonable, la arquitectura
> real del servidor de producción descrita en `docs/MANUAL_DESPLIEGUE.md`. Este documento
> se basa **exclusivamente** en lo que existe en el repositorio (código, `docker-compose.yml`,
> `Dockerfile`, `.env` / `.env.local`, `docs/*.md`). Donde falta información se indica
> explícitamente en vez de inventarla.

---

## 1. Objetivo

Permitir que un desarrollador/QA tome una máquina Linux limpia y levante:

- el mismo stack de contenedores que usa producción (API + Worker + Redis),
- la misma base de datos de control fuera de Docker (Postgres del host),
- opcionalmente, el mismo patrón de reverse proxy que usa producción (nginx/apache
  sirviendo bajo un path, no el puerto interno directo),

de forma que el comportamiento observado en local sea representativo del comportamiento
en el servidor real, y no solo un `uvicorn --reload` suelto.

**Límite honesto de esta paridad:** la fuente de datos de negocio (`MOODLE_DB_*`, el SSO
contra Moodle/ZAJUNA) es una **base de datos y un sitio Moodle externos al repositorio**.
No hay ningún artefacto en este repo para levantar Moodle/ZAJUNA localmente (no hay
Dockerfile de Moodle, ni dump, ni instalador). Ver §9 y §22 ("Información faltante").

---

## 2. Arquitectura local

Arquitectura real, tomada de `docs/MANUAL_DESPLIEGUE.md` §1 y verificada contra
`docker-compose.yml` / `api/config.py` / `api/main.py`:

```
                    ┌─────────────────────────────────────────────┐
   Navegador  ──►   │  Reverse proxy (nginx/apache)  /analitica    │   ← NO está en el repo
                    └───────────────┬─────────────────────────────┘     (config de ejemplo,
                                    │                                    ver §11)
                    ┌───────────────▼──────────────┐
                    │  reportes-api (FastAPI:8089)  │  UI estática + REST + SSO
                    └───────┬───────────────┬───────┘
                            │               │
                 ┌──────────▼───┐   ┌───────▼─────────┐
                 │ Redis (cola) │   │ reportes-worker │  genera CSV/XLSX + scheduler (hilo)
                 └──────────────┘   └───────┬─────────┘
                                            │
        ┌───────────────────────────────────┼───────────────────────────┐
        │                                    │                           │
┌───────▼────────────┐          ┌────────────▼──────────┐   ┌────────────▼─────────┐
│ Control DB          │          │ Moodle/ZAJUNA DB      │   │ Volumen Docker       │
│ Postgres del HOST    │          │ Postgres (solo lect.) │   │ reportes_generados   │
│ (fuera de Docker)   │          │ EXTERNA al repo       │   │                      │
└─────────────────────┘          └───────────────────────┘   └──────────────────────┘
```

Componentes (código real):

| Componente | Contenedor | Rol | Fuente |
|---|---|---|---|
| `reportes-api` | `reportes_api` | FastAPI: sirve el frontend estático + `/api/*`. `uvicorn --host 0.0.0.0 --port 8089 --workers 2` | `Dockerfile` |
| `reportes-worker` | `reportes_worker` | `python worker_start.py` — RQ worker sobre la cola `reportes` + hilo `scheduler` (revisa programados cada 60s) | `worker_start.py`, `api/scheduler.py` |
| `redis` | `reportes_redis` | Cola RQ, DB Redis nº 2 | `docker-compose.yml`, `api/config.py:redis_url` |
| Control DB | — (host) | Tablas `reportes_zajuna_solicitudes`, `reportes_users`, `reportes_programados` (SQLAlchemy, `create_all` al arrancar) | `api/database.py:init_control_db()` |
| Moodle DB | — (externa) | Fuente de datos de los reportes, solo lectura + SSO | `api/moodle_auth.py`, `api/database.py:get_moodle_conn` |
| Frontend | dentro de `reportes-api` | HTML/CSS/JS **estático, sin build** (sin `package.json`, sin bundler) servido por rutas explícitas de FastAPI | `frontend/`, `api/main.py` |

Diferencia clave dev vs. prod, tomada de `.env` vs `.env.local` (ver §6):

| | Producción (`.env`) | Local (`.env.local`) |
|---|---|---|
| Reverse proxy | Sí, bajo `/analitica` | No, por defecto (`REPORTES_BASE_PATH=`) |
| `MOODLE_URL` / `MOODLE_PUBLIC_URL` | `https://zajunavideo5.com/zajuna` | `http://localhost/zajuna` |
| `REPORTES_FRONTEND_URL` | `https://zajunavideo5.com/analitica` | `http://localhost:8089` |
| CORS | `https://zajunavideo5.com` | `http://localhost:8089` |
| Docs Swagger (`REPORTES_DOCS_ENABLED`) | no debe activarse | activable en local |

---

## 3. Requisitos previos

Tomados de `docs/MANUAL_DESPLIEGUE.md` §2 y verificados contra `Dockerfile`/`docker-compose.yml`:

| Componente | Versión mínima | Motivo |
|---|---|---|
| Docker Engine | 24.x | Ejecuta `docker compose` v2 |
| Docker Compose plugin | v2 (`docker compose`, no `docker-compose`) | Sintaxis usada en `docker-compose.yml` |
| PostgreSQL (en el HOST, no en Docker) | 14+ | Aloja la Control DB `reportes` (§8) |
| Git | cualquiera | Clonar el repo |
| Acceso a una base de datos Moodle/ZAJUNA (externa) | — | Requerido para SSO y datos de reportes (§9) |

No se instala Python en el host — todo corre dentro de la imagen (`python:3.12-slim`,
`Dockerfile`). El único software Python usado fuera de Docker es opcional: `pytest`
para correr los tests unitarios en el host (§16), que **no** está en `requirements.txt`
(el `README.md` indica instalarlo aparte: `pip install pytest`).

---

## 4. Preparación de la máquina

```bash
# 1. Clonar
git clone <URL_DEL_REPO> analitica_notificaciones
cd analitica_notificaciones

# 2. Verificar Docker / Compose v2
docker --version
docker compose version

# 3. Verificar Postgres en el host (§8)
psql --version || sudo apt install postgresql
```

> El repo trae `docker-compose.yml` y `Dockerfile` en la raíz — no hay variantes por
> ambiente (`docker-compose.prod.yml`, etc.). El mismo archivo se usa en local y en
> producción; lo que cambia es el archivo de variables (`ENV_FILE`, ver §6).

---

## 5. Configuración de hostname

**No hay ningún hostname propio de este repo** que deba añadirse a `/etc/hosts` para
la aplicación en sí: `REPORTES_BASE_PATH` en `.env.local` viene vacío (`REPORTES_BASE_PATH=`),
lo que según `docs/MANUAL_DESPLIEGUE.md` §7 significa **"acceso directo/local"**, es
decir `http://localhost:8089` sin reverse proxy ni dominio propio.

Si se quiere reproducir con más fidelidad el patrón de producción (proxy + path
`/analitica`, ver §11), se puede usar el propio `localhost` — no hace falta un hostname
inventado, porque el `location /analitica/` de nginx/apache funciona igual sobre
`http://localhost/analitica/`. **No se modifica `/etc/hosts`** para este repo.

El único hostname/dominio real que aparece en el código es el de **Moodle**
(`MOODLE_URL`, `MOODLE_PUBLIC_URL`, `MOODLE_HOST_HEADER`), y ese depende de dónde esté
la instancia Moodle/ZAJUNA que se use para pruebas — algo externo a este repo. No se
inventa un dominio aquí; usar el que realmente sirva esa instancia (ver §9).

---

## 6. Variables de entorno

### 6.1 Cómo se seleccionan

`docker-compose.yml` usa `${ENV_FILE:-...}` como archivo de variables, por servicio:

```yaml
reportes-api:
  env_file: ${ENV_FILE:-.env..env.local}     # línea 19
reportes-worker:
  env_file: ${ENV_FILE:-.env}                # línea 43
```

> ⚠️ **Inconsistencia real detectada en el repo**: el valor por defecto del servicio
> `reportes-api` es literalmente el archivo `.env..env.local` (con doble punto), que
> **no existe** en el repositorio. Si se corre `docker compose up` sin definir
> `ENV_FILE`, el servicio `reportes-api` fallará al no encontrar ese archivo, mientras
> que `reportes-worker` sí levantaría (usa `.env`). **Nunca dependas del default**:
> siempre exporta `ENV_FILE` explícitamente, como ya recomienda `docs/MANUAL_DESPLIEGUE.md`:
> ```bash
> ENV_FILE=.env.local docker compose up -d --build --remove-orphans
> ```
> `docker compose restart` **no** relee `ENV_FILE` (usa el que ya tenía el contenedor) —
> usar siempre `up -d`.

### 6.2 Archivos existentes

El repo trae **`.env`** (valores de producción) y **`.env.local`** (valores de
desarrollo local) ya en el repositorio raíz. **No existe un `.env.example`.**
`.gitignore` ignora `.env.local` pero **no ignora `.env`** — `.env` está versionado en
git con secretos reales de ejemplo (`REPORTES_SECRET_KEY`, contraseñas de DB). Esto es
un riesgo de seguridad del repo tal como está (ver §22 "Riesgos"); para este documento
se tratan esos valores como **no reutilizables** — rota cualquier secreto antes de
usarlo en un entorno real.

Para trabajar en local: parte de `.env.local` (ya existe) y ajusta según tu entorno
(host y credenciales de tu Postgres, y la instancia Moodle a la que apuntes). Nunca
pegues secretos reales de producción en `.env.local`.

### 6.3 Variables realmente usadas por el código (`api/config.py`)

| Variable | Uso | Obligatoria | Default en código | Nota |
|---|---|---|---|---|
| `DATABASE_HOST` | Host Postgres Control DB | No | `host.docker.internal` | |
| `DATABASE_PORT` | Puerto Postgres Control DB | No | `5432` | |
| `DATABASE_DB` | Nombre BD control | No | `superset` | El default de código es un resto histórico ("superset"); en `.env`/`.env.local` reales el valor es `reportes` — usa el de esos archivos, no el default. |
| `DATABASE_USER` | Usuario Control DB | No | `superset` | Idem — en la práctica usa `reportes` |
| `DATABASE_PASSWORD` | Password Control DB | No | `superset` | **No dejar el default en ningún entorno real** |
| `MOODLE_DB_HOST` | Host Postgres Moodle | Sí (sin esto no hay reportes ni login) | `""` (vacío → error explícito al conectar) | |
| `MOODLE_DB_PORT` | Puerto Postgres Moodle | No | `5432` | |
| `MOODLE_DB_NAME` | Nombre BD Moodle | Sí | `moodle` | En `.env`/`.env.local` del repo el valor actual es `zajunadb`. **`docs/CONTEXTO_TRASPASO.md` y `docs/MANUAL_DESPLIEGUE.md` documentan explícitamente que el nombre correcto es `zajuna`, no `zajunadb`**, y que ese error histórico causaba fallos de login. Verifica el nombre real de tu base antes de usarlo (ver §20 troubleshooting). |
| `MOODLE_DB_USER` | Usuario solo-lectura Moodle | Sí | `""` | Producción documenta usar un rol dedicado `reportes_ro` (§8.3); el `.env` del repo usa `postgres` (superusuario) — no recomendado, ver §22 |
| `MOODLE_DB_PASSWORD` | Password Moodle DB | Sí | `""` | |
| `AMBIENTE` | Texto mostrado en columna "Ambiente" de los reportes | No | `ZAJUNA` (código) | `.env`/`.env.local` del repo traen `ZAJUNA PRODUCTION` en ambos — considera diferenciarlo en tu copia local si quieres distinguir reportes generados en pruebas |
| `MOODLE_URL` | URL interna (desde el contenedor) al Moodle, para `login/token.php` | Sí para login por usuario/clave (`/api/auth/moodle-login`) | `http://host.docker.internal/zajuna` | |
| `MOODLE_WS_SERVICE` | Shortname del Web Service en Moodle | Sí | `reportes_zajuna` | Debe existir y estar habilitado en el Moodle apuntado (§9.1) |
| `MOODLE_HOST_HEADER` | Header `Host` forzado en la petición a Moodle | No | `""` | Necesario si `MOODLE_URL` no coincide con el `wwwroot` real |
| `MOODLE_PUBLIC_URL` | URL de Moodle vista por el navegador (login SSO, botón "Volver a ZAJUNA") | Sí | `http://localhost/zajuna` | |
| `REPORTES_FRONTEND_URL` | A dónde redirige tras el autologin de Moodle | No | `/` | |
| `REPORTES_BASE_PATH` | Prefijo de ruta detrás de un reverse proxy | No | `""` | Vacío = acceso directo (§5, §11) |
| `REDIS_HOST` | Host Redis | No | `redis` | Nombre del servicio Docker |
| `REDIS_PORT` | Puerto Redis | No | `6379` | |
| `REPORTES_OUTPUT_DIR` | Directorio de archivos generados | No | `/app/reportes_generados` | Fijado también por `docker-compose.yml` (`environment:`) |
| `REPORTES_MAX_FILES_PER_USER` | Retención por usuario | No | `100` | |
| `REPORTES_XLSX_ROWS_PER_FILE` | Filas por parte XLSX | No | `900000` | |
| `REPORTES_CSV_ROWS_PER_FILE` | Filas por parte CSV | No | `2000000` | |
| `REPORTES_AUTO_CSV_ROW_THRESHOLD` | Umbral para forzar CSV en vez de XLSX | No | `500000` | |
| `REPORTES_SECRET_KEY` | Clave HS256 del JWT propio | **Sí, crítica** | `change-me-in-production` | Si queda en el valor por defecto, **el API no arranca** (`api/main.py` lo valida en `lifespan` y lanza `RuntimeError`) |
| `REPORTES_DOCS_ENABLED` | Habilita `/api/docs` y `/api/redoc` | No | `false` | Solo activar en local |
| `REPORTES_CORS_ORIGINS` | Orígenes CORS permitidos (coma-separado) | No | `http://localhost:8088,http://localhost:8089` | |
| `TZ` | Zona horaria del contenedor | No (fijada en compose) | — | `docker-compose.yml` la fija a `America/Bogota` en ambos servicios; **no cambiarla** — el código asume esa zona en varias consultas SQL |

### 6.4 Variables en `.env`/`.env.local` que el código NO lee vía `Settings`

| Variable | Presente en `.env`/`.env.local` | Uso real |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Sí | No los consume `api/config.py`. Son residuo de un esquema anterior donde la Control DB corría **dentro** de Docker con imagen oficial `postgres` (variables típicas de esa imagen). Ese servicio ya **no existe** en `docker-compose.yml` actual (ver `docs/bd-externa.md`: "se eliminó el servicio `db`"). No son necesarias para el despliegue actual, pero no hace daño dejarlas. |
| `REPORTES_ROWS_PER_FILE` | Sí (`.env`, `.env.local`) | No existe en `api/config.py` (el código usa `REPORTES_XLSX_ROWS_PER_FILE` / `REPORTES_CSV_ROWS_PER_FILE` por separado). Variable obsoleta — no confundir con las dos anteriores. |

No se detectaron variables usadas por el código que falten en `.env`/`.env.local`.

---

## 7. Dependencias

No se instala nada de Python en el host; todo vive en la imagen Docker
(`Dockerfile`, `python:3.12-slim` + `requirements.txt`):

```
fastapi==0.115.5, uvicorn[standard]==0.32.1, sqlalchemy==2.0.36, psycopg2-binary==2.9.10,
rq==2.0.0, redis==5.2.0, pandas==2.2.3, openpyxl==3.1.5, xlsxwriter==3.2.0,
python-multipart==0.0.17, pydantic==2.10.3, pydantic-settings==2.6.1,
python-jose[cryptography]==3.3.0, httpx==0.27.2, passlib[bcrypt]==1.7.4, bcrypt==3.2.2
```

No hay `package.json` ni dependencias de frontend — el frontend es HTML/CSS/JS puro
sin build (§12).

---

## 8. Base de datos

### 8.1 Motor y diseño

- **Motor**: PostgreSQL. Versión mínima documentada: **14+** (`docs/MANUAL_DESPLIEGUE.md` §2).
- **Dos bases distintas, ambas Postgres, ambas FUERA de los contenedores**:
  1. **Control DB** (`reportes`): propiedad de esta app. Vive en el Postgres del host.
     Las tablas se crean solas (`api/database.py:init_control_db()`, `CREATE TABLE IF NOT EXISTS`),
     no hay migraciones tipo Alembic en el repo.
  2. **Moodle DB** (`zajuna`, según docs — ver nota de §6.3 sobre `zajunadb`): externa,
     ajena a este repo, solo lectura.

### 8.2 Levantar la Control DB en el host

```bash
sudo apt install postgresql   # si no está instalado

sudo -u postgres psql -c "CREATE ROLE reportes LOGIN PASSWORD '<password_local_segura>';"
sudo -u postgres psql -c "CREATE DATABASE reportes OWNER reportes;"
```

> Usa una contraseña propia para tu entorno local — **no reutilices** la que aparece en
> `.env`/`.env.local` del repo.

### 8.3 Permitir que los contenedores lleguen al Postgres del host

Los contenedores llegan al host por `host.docker.internal` (mapeado en
`docker-compose.yml` con `extra_hosts: host.docker.internal:host-gateway` en ambos
servicios). Hay que abrir Postgres a la subred bridge de Docker:

`postgresql.conf`:
```
listen_addresses = '*'
```

`pg_hba.conf` (agregar):
```
host    reportes    reportes    172.16.0.0/12    scram-sha-256
```

```bash
sudo systemctl restart postgresql
```

### 8.4 Variables de conexión (Control DB)

En tu `.env.local`:
```
DATABASE_HOST=host.docker.internal
DATABASE_PORT=5432
DATABASE_DB=reportes
DATABASE_USER=reportes
DATABASE_PASSWORD=<tu_password_local>
```

### 8.5 "Migraciones" / creación de tablas

No hay Alembic ni carpeta `migrations/`. La creación de esquema ocurre en runtime, al
arrancar tanto el API (`api/main.py: lifespan → init_control_db()`) como el worker
(`worker_start.py: main() → init_control_db()`), protegida por un advisory lock de
Postgres (`pg_advisory_xact_lock(7261836450)`) para evitar condiciones de carrera si
API y worker arrancan a la vez. **No hay comando de migración separado que deba
correrse antes de iniciar la app** — basta con levantar los contenedores.

Tablas creadas: `reportes_zajuna_solicitudes`, `reportes_users`, `reportes_programados`
(DDL completo en `api/database.py`).

### 8.6 Seeds / datos iniciales

No hay script de seed en el repo. La tabla `reportes_users` se puebla sola en el primer
login SSO exitoso (`api/routers/auth.py`, autocreación de usuario). No hay usuarios
precargados ni fixtures de datos de reportes (esos vienen de la Moodle DB externa).

### 8.7 Verificar que la Control DB funciona

```bash
docker logs reportes_api | grep "Control DB inicializado"
docker logs reportes_worker | grep "Control DB inicializado"

# o directo contra Postgres
PGPASSWORD=<tu_password_local> psql -h localhost -U reportes -d reportes -c "\dt"
```

---

## 9. Servicios auxiliares

### 9.1 Redis (obligatorio, provisto por Docker Compose)

- Imagen `redis:7`, contenedor `reportes_redis`, sin publicar puerto al host (permanece
  interno a la red de Compose — ver §10 puertos).
- Usado como broker de colas RQ, **DB lógica número 2** (`redis://redis:6379/2`,
  `api/config.py:redis_url`).
- Verificación:
  ```bash
  docker exec reportes_redis redis-cli ping        # PONG
  docker exec reportes_redis redis-cli -n 2 llen reportes  # tamaño de la cola
  ```

### 9.2 Moodle/ZAJUNA (obligatorio para funcionalidad real, EXTERNO al repo)

Este repo **no contiene** Moodle. Todo el SSO y los datos de los reportes dependen de:

1. Un Postgres de Moodle/ZAJUNA accesible desde los contenedores (`MOODLE_DB_*`).
2. Un Moodle corriendo con **Web Services REST habilitados** y un servicio externo
   `reportes_zajuna` (shortname configurable vía `MOODLE_WS_SERVICE`) con las funciones
   `core_user_get_users_by_field` y `core_webservice_get_site_info` agregadas
   (`docs/MANUAL_DESPLIEGUE.md` §6.1).
3. Opcionalmente, el plugin Moodle `local_reporteszajuna` (código en `reporteszajuna/`
   de este mismo repo, en PHP) instalado dentro de ese Moodle para el botón/redirect de
   entrada por SSO (`docs/MANUAL_DESPLIEGUE.md` §6.2–§6.4). Este plugin **no se instala
   con Docker Compose**: se copia manualmente al `local/` del Moodle destino.

**No hay forma de reproducir esto "de fábrica" en una máquina limpia solo con lo que
trae el repo.** Para QA local hay dos caminos, ninguno documentado como script
automático en el repo:

- **Opción A (recomendada si ya existe)**: apuntar `MOODLE_DB_*`, `MOODLE_URL`,
  `MOODLE_PUBLIC_URL` a una instancia Moodle/ZAJUNA de pruebas ya existente y accesible
  desde tu máquina (réplica, staging, o una instalación Moodle local tuya con la BD
  `zajuna`). Es el escenario que documentan `docs/CONTEXTO_TRASPASO.md` (dos
  instalaciones Moodle en `/var/www/zajuna` y `/var/www/html/zajuna` leyendo la misma
  BD) y `docs/MANUAL_BD_PRIMARIA.md`.
- **Opción B (smoke test parcial, sin SSO real)**: sin un Moodle real, solo se puede
  verificar que el API/Worker/Redis/Control DB arrancan y que `/api/health` responde
  (§17); **no** se puede probar login, listado de reportes reales, ni generación,
  porque todo pasa por `MOODLE_DB_*` (`api/database.py:get_moodle_conn` lanza
  `RuntimeError` si `MOODLE_DB_HOST` no está configurado, y las consultas de reportes
  leen directamente `mdl_*`).

Esto se declara explícitamente como **información faltante del repositorio** (ver §22),
no se inventa una base Moodle de prueba.

---

## 10. Puertos

| Puerto | Servicio | Interno/Externo | ¿Se publica al host? | Quién lo consume |
|---|---|---|---|---|
| `8089` | `reportes-api` (uvicorn) | Entrada de la app | **Sí** — `docker-compose.yml`: `"8089:8089"` | Navegador (directo, sin proxy) o el reverse proxy local (§11) |
| `6379` | `redis` | Interno a la red Compose | **No** — no aparece `ports:` en el servicio `redis` | Solo `reportes-api` y `reportes-worker`, vía nombre de servicio Docker `redis` |
| `5432` | Postgres del host (Control DB **y**, si aplica, Moodle DB) | Externo a Docker, en el host | N/A (no es un puerto de contenedor) — los contenedores lo alcanzan vía `host.docker.internal:5432` | `reportes-api`, `reportes-worker` |
| `80` / `443` (reverse proxy) | nginx/apache local, si se monta (§11) | Entrada pública | Depende de tu instalación local del proxy | Navegador → proxy → `127.0.0.1:8089` |

No hay más puertos: no hay panel de administración, ni métricas expuestas, ni otro
servicio en el `docker-compose.yml`.

---

## 11. Reverse proxy / Web server

### 11.1 Qué usa producción

`docs/MANUAL_DESPLIEGUE.md` §7 documenta nginx **o** apache como opciones equivalentes,
proxyando el path `/analitica` hacia `127.0.0.1:8089`. **El repo no contiene un archivo
de configuración de nginx/apache real** — solo los bloques de ejemplo de ese manual. No
hay `Caddyfile` ni configuración de Traefik en el repo.

### 11.2 Modo A — Sin proxy (el modo local "de fábrica" del repo)

Es el modo que trae `.env.local` tal cual (`REPORTES_BASE_PATH=` vacío,
`REPORTES_FRONTEND_URL=http://localhost:8089`). Acceso directo al puerto publicado:

```
http://localhost:8089
```

Válido para desarrollo rápido, pero **no reproduce el patrón de proxy** que usa
producción.

### 11.3 Modo B — Con proxy local (mayor paridad con el servidor)

Para reproducir el patrón real (usuario nunca toca el puerto interno de la app),
instala nginx en el host y crea una config basada **textualmente** en el bloque que ya
documenta el proyecto (`docs/MANUAL_DESPLIEGUE.md` §7):

```bash
sudo apt install nginx
```

`/etc/nginx/sites-available/reportes-local.conf`:
```nginx
server {
    listen 80;
    server_name localhost;

    location /analitica/ {
        proxy_pass http://127.0.0.1:8089/;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;   # reportes/preview pesados
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/reportes-local.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Y ajusta `.env.local` para que la app sepa que corre detrás de ese prefijo:
```
REPORTES_BASE_PATH=/analitica
REPORTES_FRONTEND_URL=http://localhost/analitica
```

`api/main.py:_inject_base_path()` usa `REPORTES_BASE_PATH` para reescribir las rutas de
`app.js`/`styles.css`/`logo.svg` en el HTML servido — **debe coincidir exactamente**
con el `location` del proxy, igual que en producción.

Acceso (punto de entrada tipo usuario final, no el puerto interno):
```
http://localhost/analitica/
```

> El equivalente en apache (`ProxyPass`/`ProxyPassReverse`) está en
> `docs/MANUAL_DESPLIEGUE.md` §7 — mismo patrón, otro binario.

---

## 12. HTTP / HTTPS

El repo **no** implementa ni documenta terminación TLS propia: ni `Dockerfile`, ni
`docker-compose.yml`, ni el `Dockerfile` exponen 443, ni hay certificados, claves o
config de TLS en ningún archivo. En producción, si `MOODLE_PUBLIC_URL`/`MOODLE_URL`
usan `https://zajunavideo5.com/...`, esa terminación TLS ocurre en infraestructura
**fuera de este repositorio** (el reverse proxy de producción, no incluido aquí).

Por lo tanto, siguiendo la regla de no inventar lo que no está: **no se documenta
HTTPS local** porque no hay ningún artefacto de este proyecto que lo requiera o lo
configure. El flujo documentado localmente (§11, `.env.local`) es HTTP puro, igual que
lo describe `docs/MANUAL_DESPLIEGUE.md` §6.3 para el caso local
(`reportes_url: http://localhost:8089`).

Si tu instancia Moodle de pruebas (externa, §9.2) exige HTTPS, eso se resuelve en la
configuración de esa instancia Moodle, no en este stack.

---

## 13. Build

No hay paso de build de frontend (sin bundler, sin `npm run build`). El "build" real es
la imagen Docker:

```bash
# Construir imágenes (api y worker comparten la misma imagen, misma Dockerfile)
ENV_FILE=.env.local docker compose build

# Build + levantar en un solo paso (recomendado, igual que documenta el proyecto)
ENV_FILE=.env.local docker compose up -d --build --remove-orphans
```

`Dockerfile` instala dependencias de sistema (`libpq-dev gcc curl`), luego
`pip install -r requirements.txt`, copia todo el repo (`COPY . .`) y crea
`/app/reportes_generados`. No hay artefacto compilado que "generar" aparte de la propia
imagen.

> Recordatorio del propio manual: `--build` es obligatorio tras cambios en
> `api/routers`, `api/main.py`, `jobs.py` o `frontend/` — esos paths **no** están
> montados como volumen. `api/sql` y `api/reportes` sí están montados (`:ro`) pero con
> caché por proceso: basta reiniciar el contenedor (`docker restart`), no hace falta
> rebuild.

---

## 14. Inicio del entorno

### 14.1 Orden recomendado

1. Postgres del host arriba y accesible (§8).
2. `.env.local` completo y correcto (§6).
3. Levantar Compose:

```bash
cd analitica_notificaciones
ENV_FILE=.env.local docker compose up -d --build --remove-orphans
```

Esto levanta, en orden de dependencia real (`depends_on: redis: condition: service_started`):
`redis` → `reportes-api` y `reportes-worker` (ambos dependen solo de `redis`; la Control
DB y la Moodle DB no están en `depends_on` porque son externas — el `init_control_db()`
falla en runtime si Postgres del host no está accesible).

### 14.2 Solo un servicio (equivalente a lo que documenta el `README.md`)

```bash
ENV_FILE=.env.local docker compose up -d --build reportes-api reportes-worker
```

---

## 15. Verificación

```bash
docker compose ps
# los 3 servicios (redis, reportes-api, reportes-worker) deben estar "Up"
# reportes-api además debe mostrar "healthy" (tiene healthcheck definido)

curl -s http://localhost:8089/api/health
# {"status":"ok","timestamp":"..."}

curl -s http://localhost:8089/api/reportes
# lista de reportes disponibles (requiere que MOODLE_DB_* esté accesible
# para hidratar filtros dinámicos; el listado base no depende de sesión)

docker logs reportes_worker | grep -E "Scheduler thread iniciado|Worker listo"
```

---

## 16. Smoke test

**Punto de entrada**: usa siempre el mismo punto por el que entraría un usuario real,
no el puerto interno si estás en Modo B (§11.3):

- Modo A (sin proxy, default del repo): `http://localhost:8089`
- Modo B (con proxy local): `http://localhost/analitica/`

Pasos, usando solo endpoints/funcionalidad reales del repo:

1. **Health check**: `GET /api/health` → `{"status":"ok",...}` (§17).
2. **Frontend accesible**: abrir la URL de entrada en el navegador → debe cargar
   `index.html` con la pantalla "Ingresa desde Moodle ZAJUNA" (login SSO-only, sin
   formulario de usuario/clave — `frontend/index.html`).
3. **Backend + catálogo**: `GET /api/reportes` → JSON con la lista de reportes
   definidos en `api/reportes/registry.py` (no requiere sesión).
4. **Conexión a la Control DB**: confirmada indirectamente por `docker logs reportes_api`
   mostrando `Control DB inicializado` al arrancar (§8.7); no hay endpoint que la
   exponga directamente.
5. **Flujo funcional completo (requiere Moodle real, §9.2)**: entrar por el botón
   "Reportes" del Moodle configurado → SSO vía `redirect.php` →
   `/api/auth/moodle-autologin` → catálogo de reportes → generar un reporte pequeño →
   verificar transición `PENDIENTE → PROCESANDO → FINALIZADO` (polling cada 4s,
   `docs/flujo-generacion-reportes.md`) → descargar.

Si no cuentas con una instancia Moodle de prueba, los pasos 1–4 son el smoke test
alcanzable con lo que trae el repo; el paso 5 queda documentado como pendiente de
infraestructura externa (§9.2, §22).

### Tabla de endpoints reales (`README.md`, verificados contra los routers)

| Método | Ruta | Requiere sesión |
|---|---|---|
| GET | `/api/health` | No |
| GET | `/api/reportes` | No |
| GET | `/api/reportes/{codigo}/filtros` | No |
| POST | `/api/reportes/{codigo}/generar` | Sí |
| GET | `/api/solicitudes` (`?usuario_email=`) | Sí |
| GET | `/api/solicitudes/{id}` | Sí |
| GET | `/api/solicitudes/{id}/descargar-email?email=` | No (por email) |
| GET | `/api/solicitudes/{id}/descargar?token=` | No (por token) |
| POST | `/api/auth/moodle-login` | No (usuario/clave Moodle) |
| GET | `/api/auth/moodle-autologin?token=` | No (token de Moodle) |
| POST | `/api/auth/logout` | Sí |
| GET | `/api/auth/me` | Sí |

Swagger (`/api/docs`, `/api/redoc`) solo disponible si `REPORTES_DOCS_ENABLED=true`
(§6.3) — recomendado activarlo en tu `.env.local` para QA exploratorio, nunca en `.env`
de producción.

---

## 17. Logs

```bash
# API
docker logs -f reportes_api

# Worker (incluye el hilo scheduler de programados)
docker logs -f reportes_worker

# Redis
docker logs -f reportes_redis

# Reverse proxy local, si se montó (Modo B, §11.3)
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log

# Postgres del host (Control DB / Moodle DB si corre ahí también)
sudo journalctl -u postgresql -f
```

No hay agregador de logs (ELK, Loki, etc.) en el repo — todo va a stdout/stderr de cada
contenedor (`logging.basicConfig(..., stream=sys.stdout)` en `api/main.py` y
`worker_start.py`), que es lo que captura `docker logs`.

---

## 18. Reinicio

Simular un reinicio completo del "servidor" local:

```bash
# 1. Detener los servicios de la app (sin tocar Postgres del host)
docker compose stop

# 2. Volver a iniciar
ENV_FILE=.env.local docker compose up -d --remove-orphans

# 3. Verificar dependencias
docker exec reportes_redis redis-cli ping
PGPASSWORD=<tu_password_local> psql -h localhost -U reportes -d reportes -c "SELECT 1;"

# 4. Verificar que el esquema de la Control DB sigue íntegro
#    (init_control_db() es idempotente — CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS)
docker logs reportes_api | grep "Control DB inicializado"

# 5. Health check + smoke test (§15, §16)
curl -s http://localhost:8089/api/health
```

> Recuerda: `docker compose restart` conserva el `ENV_FILE` con el que arrancó cada
> contenedor pero no lo relee del entorno actual del shell — si cambiaste variables,
> usa `up -d` con `ENV_FILE` explícito, no `restart`.

---

## 19. Troubleshooting

Tabla basada en `docs/MANUAL_DESPLIEGUE.md` §11 + hallazgos propios de este análisis:

| Síntoma | Causa probable | Fix |
|---|---|---|
| `reportes-api` no arranca al hacer `docker compose up` sin `ENV_FILE` | Bug real del repo: el default de `env_file` para `reportes-api` es `.env..env.local`, archivo inexistente (§6.1) | Siempre exportar `ENV_FILE=.env.local` (o `.env`) explícitamente |
| API no arranca, error relacionado con `secret_key` | `REPORTES_SECRET_KEY=change-me-in-production` | Poner una clave real: `openssl rand -hex 32` |
| "No se pudo verificar el token en la base de datos de Moodle" | `.env`/`.env.local` apunta a la BD de Moodle equivocada. **El repo actual tiene `MOODLE_DB_NAME=zajunadb` en ambos archivos**, pero la documentación (`docs/CONTEXTO_TRASPASO.md`, `docs/MANUAL_DESPLIEGUE.md`) indica que el nombre correcto histórico es `zajuna` | Confirma el nombre real de tu base Moodle de pruebas y ajusta `MOODLE_DB_NAME` en consecuencia; no asumas ninguno de los dos sin verificar |
| "Sesión de Moodle finalizada" apenas se entra | El usuario `MOODLE_DB_USER` no puede leer `mdl_sessions`/`mdl_config`, o el `uid` no tiene sesión fresca | Verificar permisos de lectura sobre esas tablas en la BD Moodle usada |
| Puerto `8089` ocupado | Otro proceso/contenedor usando el puerto | `sudo lsof -i :8089` y liberar, o cambiar el mapeo en `docker-compose.yml` (`"8089:8089"`) — si cambias el puerto externo, actualiza también `REPORTES_FRONTEND_URL`/CORS |
| `MOODLE_DB_HOST no configurado` (excepción en runtime) | Variable vacía o no cargada — normalmente porque `ENV_FILE` no se pasó (ver primer síntoma) | Confirmar `docker exec reportes_api env | grep MOODLE_DB` |
| Contenedor no conecta al Postgres del host | `pg_hba.conf` / `listen_addresses` no abiertos a la subred del bridge de Docker | Ver §8.3 |
| Cambios en `frontend/`, `api/main.py`, `api/routers/*` o `jobs.py` no se reflejan | Esos paths no están montados como volumen — solo `api/sql` y `api/reportes` lo están | `docker compose up -d --build`; si solo cambiaste SQL o definición de reportes, basta `docker restart reportes_worker reportes_api` |
| Preview de un reporte da 503 tras ~30s | Comportamiento **por diseño** (`api/routers/reportes.py: _PREVIEW_TIMEOUT_MS = 30000`), no un bug | Acotar filtros, o usar generación completa (asíncrona, sin ese límite) |
| `pytest` no encontrado al correr los tests | No está en `requirements.txt` (README lo instala aparte) | `pip install pytest` en el host, fuera del contenedor (los tests de `tests/` no requieren DB real — usan cursores mock) |
| Login por usuario/clave falla con timeout | `MOODLE_URL` no alcanzable desde dentro del contenedor, o `MOODLE_HOST_HEADER` no coincide con el `wwwroot` real de Moodle | Verificar conectividad desde el contenedor: `docker exec reportes_api curl -I $MOODLE_URL` |

---

## 20. Limpieza

### Segura (no borra datos persistentes)

```bash
# Detener contenedores (conserva volúmenes e imágenes)
docker compose stop

# Detener y eliminar contenedores (conserva volúmenes nombrados: reportes_redis, reportes_generados)
ENV_FILE=.env.local docker compose down
```

### ⚠️ Destructiva — borra datos locales, usar con cuidado

```bash
# Elimina también los volúmenes nombrados: pierde la cola Redis en curso y
# TODOS los archivos de reportes generados localmente
ENV_FILE=.env.local docker compose down -v

# Reconstruir desde cero después de una limpieza destructiva
ENV_FILE=.env.local docker compose up -d --build --remove-orphans
```

> La Control DB **no** se toca con nada de lo anterior — vive en el Postgres del host,
> fuera del ciclo de vida de Docker (ese es justamente el propósito de `docs/bd-externa.md`).
> Para borrarla de verdad: `sudo -u postgres psql -c "DROP DATABASE reportes;"` —
> **irreversible**, solo si estás seguro de que es tu entorno local descartable.

---

## 21. Server parity checklist

- [ ] Máquina preparada (Docker 24.x + Compose v2, Postgres 14+ en el host).
- [ ] Dependencias de imagen construidas (`docker compose build` sin errores).
- [ ] `.env.local` completo y con `REPORTES_SECRET_KEY` real (no el default).
- [ ] `MOODLE_DB_NAME` verificado contra la base Moodle real que estás usando (no asumido).
- [ ] Hostname local configurado si aplica (§5 — normalmente no hace falta para este repo).
- [ ] Reverse proxy local configurado si se busca paridad con producción (§11, Modo B).
- [ ] HTTPS: **no aplica** a este stack (§12) — no marcar como pendiente si no vas a montar proxy externo con TLS.
- [ ] Frontend servido por el API (sin build) — verificado que `index.html` carga con las variables `__REPORTES_BASE__`/`__MOODLE_*__` sustituidas.
- [ ] Imagen backend construida y contenedores `reportes-api`/`reportes-worker` "Up" y `healthy`.
- [ ] Control DB (Postgres del host) accesible y `Control DB inicializado` en los logs.
- [ ] Tablas creadas automáticamente verificadas (`\dt` en la Control DB).
- [ ] Seeds: N/A — no hay seeds en el repo (§8.6).
- [ ] Redis disponible (`PING` → `PONG`).
- [ ] Moodle DB externa accesible **o** limitación documentada y aceptada para este ciclo de QA (§9.2).
- [ ] `/api/health` responde `{"status":"ok"}`.
- [ ] `/api/reportes` responde con el catálogo.
- [ ] Logs accesibles para los 3 contenedores + Postgres del host (+ proxy si aplica).
- [ ] Aplicación accesible desde el punto de entrada usado por un usuario real (puerto directo en Modo A, o `/analitica/` vía proxy en Modo B) — no solo por el puerto interno si hay proxy.
- [ ] Smoke test §16 ejecutado (pasos 1–4 mínimo; paso 5 si hay Moodle de prueba disponible).
- [ ] Reinicio completo probado (§18) sin pérdida del esquema de la Control DB.

---

## 22. Auditoría — hallazgos de la segunda pasada

Repasado como si fuera un QA que solo tiene el repo, una máquina limpia y este
documento.

### Archivos analizados

- `README.md`, `docker-compose.yml`, `Dockerfile`, `requirements.txt`, `.gitignore`,
  `worker_start.py`
- `.env`, `.env.local` (leídos para extraer nombres de variables reales; valores
  sensibles no se reproducen en este documento)
- `docs/MANUAL_DESPLIEGUE.md`, `docs/bd-externa.md`, `docs/MANUAL_BD_PRIMARIA.md`,
  `docs/CONTEXTO_TRASPASO.md`, `docs/flujo-generacion-reportes.md`
- `api/config.py`, `api/main.py`, `api/database.py`, `api/auth.py`, `api/moodle_auth.py`,
  `api/models.py`, `api/jobs.py`, `api/scheduler.py`
- `api/routers/auth.py`, `api/routers/reportes.py`, `api/routers/solicitudes.py`,
  `api/routers/programados.py`
- `frontend/index.html`, `frontend/app.js` (grep dirigido sobre `API`, `fetch`,
  placeholders `__REPORTES_BASE__`/`__MOODLE_*__`)
- `tests/test_health.py`, `tests/test_streaming.py`
- `reporteszajuna/*` (plugin Moodle — confirmado que vive fuera del stack Docker)
- Búsqueda explícita (y resultado negativo) de: `.github/workflows`, GitLab CI,
  Jenkinsfile, Terraform, Kubernetes/Helm, unidades `systemd`, Supervisor, PM2,
  `package.json`, configs de nginx/apache/Caddy/Traefik reales en el repo
- `git log`, `git ls-files` (para confirmar que `.env` está versionado)

### Arquitectura identificada

FastAPI (`reportes-api`, puerto 8089) sirve API REST + frontend estático sin build.
Un worker RQ separado (`reportes-worker`) consume una cola Redis y ejecuta consultas
pesadas contra una base Moodle/ZAJUNA externa de solo lectura, escribiendo archivos
CSV/XLSX en un volumen Docker. Un hilo *scheduler* dentro del worker dispara reportes
programados cada 60s. El estado de las solicitudes vive en una Control DB Postgres que
corre **fuera** de Docker, en el host, por diseño explícito (para sobrevivir al ciclo de
vida de los contenedores). En producción, todo el tráfico entra por un reverse proxy
(nginx o apache, no incluido en el repo) bajo el path `/analitica`.

### Paridad servidor/local

- Mismos contenedores (`docker-compose.yml` sin variantes por ambiente) — solo cambia
  el archivo de variables.
- Misma separación Control DB (host) / Moodle DB (externa) que en producción.
- Mismo patrón de reverse proxy reproducible localmente con nginx (Modo B, §11.3),
  usando el bloque de configuración que ya documenta el propio proyecto.
- Mismo comportamiento de creación de esquema en runtime (no hay diferencia dev/prod
  en migraciones porque no existen migraciones formales).
- **No reproducible localmente sin infraestructura externa**: la instancia Moodle/ZAJUNA
  real con datos y el web service SSO configurado.
- **No aplica**: HTTPS/TLS — no es parte de este stack en ningún ambiente documentado
  en el repo.

### Supuestos

- Se asume que quien despliega tiene o puede obtener acceso a una base Moodle/ZAJUNA de
  pruebas para el smoke test completo (paso 5, §16); el documento no la provee porque
  el repo no la provee.
- Se asume Linux como SO de la máquina limpia (comandos `apt`, `systemctl`), acorde al
  entorno de trabajo real documentado en `docs/CONTEXTO_TRASPASO.md`.
- Para el Modo B de reverse proxy (§11.3) se asume nginx por ser el primer ejemplo
  listado en `docs/MANUAL_DESPLIEGUE.md`; apache es intercambiable con el bloque
  equivalente del mismo manual.

### Información faltante

- No hay `.env.example` en el repo — se documentaron las variables a partir del código
  (`api/config.py`) y de los dos archivos reales (`.env`, `.env.local`).
- No hay ningún artefacto (Dockerfile, dump, instalador) para levantar Moodle/ZAJUNA
  localmente — es una dependencia externa real de este sistema.
- No hay configuración de reverse proxy versionada en el repo (solo ejemplos en Markdown).
- No hay CI/CD, IaC (Terraform/Kubernetes/Helm) ni process manager (systemd/Supervisor/PM2)
  en el repo — el único "process manager" es el propio `uvicorn --workers 2` dentro del
  contenedor API, y el proceso único de `worker_start.py` en el contenedor worker.
- No se pudo determinar la versión exacta de PostgreSQL en uso en producción, más allá
  del mínimo documentado ("14+") en `docs/MANUAL_DESPLIEGUE.md`.

### Riesgos

- **`.env` está versionado en git** (`git ls-files` lo confirma) con valores que
  parecen credenciales reales (contraseñas de Postgres, secreto JWT). Cualquier QA que
  clone el repo tiene acceso a esos valores en el historial. Esto no se resuelve en
  este documento (está fuera de alcance de "cómo desplegar"), pero se señala como
  hallazgo de seguridad que el equipo debería remediar (rotar secretos, sacar `.env`
  del control de versiones).
- El bug del `env_file` por defecto (§6.1) puede llevar a un despliegue "roto" si
  alguien corre `docker compose up` sin `ENV_FILE`, con un mensaje de error que no
  apunta obviamente a la causa real.
- `MOODLE_DB_NAME=zajunadb` en los archivos actuales contradice la documentación propia
  del proyecto (`zajuna` es el nombre correcto según `docs/CONTEXTO_TRASPASO.md`) — un
  QA que confíe ciegamente en el `.env` tal cual está puede reproducir el bug histórico
  ya documentado como resuelto.
- `MOODLE_DB_USER=postgres` en `.env`/`.env.local` usa el superusuario de Postgres para
  una conexión que la documentación de producción (`docs/MANUAL_DESPLIEGUE.md` §4.3)
  indica que debería ser un rol de **solo lectura** dedicado (`reportes_ro`). El repo tal
  como está no sigue su propia recomendación de seguridad.
