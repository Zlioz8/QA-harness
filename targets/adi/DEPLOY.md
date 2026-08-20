# Deploy local

> Este documento cubre **exclusivamente** la ejecución local de ADI reproduciendo el
> comportamiento del servidor real. Para instalación de Ubuntu Server desde cero, HTTPS
> con dominio propio y el detalle operativo diario, ver **`DESPLIEGUE_UBUNTU.md`** y
> **`COMO_FUNCIONA_ADI.md`** en esta misma raíz — este documento resume y reordena esa
> información con foco en "levantar el proyecto en una máquina local", y añade lo que
> esos dos no cubren (test runner, checklist de paridad, qué archivos no se usan).
>
> Toda la evidencia de este documento viene de: `composer.json`, `composer.lock`,
> `.env.example`, `dashboard/config/define.php`, `index.php`, `.htaccess`,
> `dashboard/.htaccess`, `docker-compose.yml`, `Dockerfile-webserver`,
> `docker/apache2.conf`, `database/migrations/`, `dashboard/phpunit.xml`, `.gitignore`,
> `DESPLIEGUE_UBUNTU.md` y `COMO_FUNCIONA_ADI.md` (ambos ya validados contra el código).
> Donde el repo no da evidencia suficiente, se indica explícitamente **"sin evidencia"**
> en vez de inventar.

---

## Arquitectura real

Determinada del código, no asumida:

```
Cliente (navegador)
    │  HTTP :80  (HTTPS :443 solo si hay dominio propio, opcional — sección 6)
    ▼
Apache 2.4 + mod_php 8.2  ← ÚNICO componente de servidor. No hay reverse proxy,
    │                        ni Node, ni proceso separado: Apache ejecuta el PHP
    │                        directamente (mod_php), sirviendo también los estáticos.
    ├─ index.php  (router propio en app/Core/Router.php)      → ADI
    └─ dashboard/index.php (mismo .env, misma sesión PHP)      → Panel de reportes
    ▼
PostgreSQL 16 (localhost:5432, no expuesto a red externa)
    5 bases: adi_db · newintegracion · dbadireporte ·
             Presencialformacion · resultadoscalificaciones
```

No hay build step, no hay SPA, no hay proceso Node en producción, no hay cola de
mensajes ni cache externa (Redis/etc. no aparecen en ningún archivo del repo). El único
"servicio auxiliar" es PostgreSQL.

`docker-compose.yml`, `Dockerfile-webserver`, `docker/` y `database/liquibase.*`
**existen en el repo pero no se usan** — así lo dice explícitamente
`COMO_FUNCIONA_ADI.md` (sección 8, "Archivos del repositorio que NO se usan"). Se
documentan más abajo como alternativa, pero el flujo real y soportado es Apache nativo.

---

## 1. Requisitos previos

Evidencia: `composer.json` (`"php": "^8.0"`), `Dockerfile-webserver` (`php:8.2-apache`),
`DESPLIEGUE_UBUNTU.md` sección 5 (fija PHP 8.2 exacto porque es la versión de
producción), `docker-compose.yml` (`postgres:16`).

- **SO soportado:** Linux (Ubuntu 24.04 LTS documentado; cualquier Debian/Ubuntu con
  Apache+PHP+PostgreSQL sirve). Windows solo vía XAMPP como entorno de desarrollo, no
  reproduce el servidor real (sin Apache/mod_rewrite tal cual, sin systemd).
- **PHP 8.2** (composer permite `^8.0`, pero producción usa 8.2 — usar 8.2 para
  reproducir fielmente).
- **Extensiones PHP obligatorias:** `pdo_pgsql`, `pgsql`, `gd`, `zip`, `xml`,
  `mbstring`, `soap`, `curl`, `intl`, más `libapache2-mod-php8.2` para que Apache
  ejecute PHP.
- **Apache 2.4** con `mod_rewrite`.
- **PostgreSQL 16.**
- **Composer 2.x.**
- **Docker/Docker Compose:** no necesario para el flujo real (ver nota arriba). Solo si
  se opta deliberadamente por la alternativa Docker (Anexo A).
- **Dependencias externas:** ninguna obligatoria. Oracle SOFIA es opcional
  (`SOFIA_ENGINE=pgsql` por defecto evita necesitar Oracle/`pdo_oci`).

```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:ondrej/php -y
sudo apt update
sudo apt install -y apache2 php8.2 libapache2-mod-php8.2 \
    php8.2-cli php8.2-pgsql php8.2-xml php8.2-curl php8.2-mbstring \
    php8.2-zip php8.2-gd php8.2-soap php8.2-intl \
    postgresql postgresql-client unzip git curl
```

Verificación:

```bash
php -v
php -m | grep -cE '^(pdo_pgsql|pgsql|zip|gd|soap|dom|mbstring|curl|xml)$'   # debe dar 9
```

---

## 2. Obtener el proyecto

```bash
cd /var/www/html
sudo git clone <URL_DEL_REPOSITORIO> adi
cd adi
sudo git checkout AdiDash
sudo git config --system --add safe.directory /var/www/html/adi
sudo mkdir -p dashboard/cache
```

> ⚠️ **`composer.json` y `composer.lock` NO están en el repositorio** — están en
> `.gitignore` (verificado: ambos aparecen listados ahí). Un clon nuevo **no los trae**,
> y `composer install` falla con *"could not find a composer.json file"*. Hay que
> copiarlos aparte desde una máquina que ya tenga el proyecto funcionando (`scp` o
> similar) antes del paso 4.

> ⚠️ **Migración `008_users_username.sql` sin commitear.** En este checkout local existe
> `database/migrations/008_users_username.sql` pero `git status` la marca como archivo
> sin trackear (no está en ningún commit). Sin ella, `AuthService::authenticate()` falla
> con *"column username does not exist"* (error 500 genérico). Si clonas desde el
> repositorio remoto tal cual está commiteado, **esta migración no llegará** — cópiala
> aparte o pídesela a quien tenga este checkout.

---

## 3. Configuración de variables de entorno

Fuente: `.env.example` (plantilla real del repo) y `dashboard/config/define.php`
(valores por defecto cuando una variable falta).

```bash
sudo cp .env.example .env
sudo nano .env
```

**El `.env` es la única fuente de configuración.** Lo leen tanto `index.php` (ADI) como
`dashboard/config/define.php` (panel), que carga `../../.env`. No existe un segundo
archivo.

Variables **[OBLIGATORIO]** según los comentarios de `.env.example`:

| Bloque | Variables | Para qué |
|---|---|---|
| ADI → `adi_db` | `DB_DRIVER, DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_DATABASE` | BD principal: login, todo |
| ADI → `newintegracion` | `DBI_DRIVER, DBI_HOST, DBI_PORT, DBI_USER, DBI_PASS, DBI_DATABASE` | Datos reales de integración |
| Moodle/Zajuna | `ZAJUNA_*` | **Dejar vacías a propósito** — módulos que las usaban están deshabilitados. No borrar las líneas: si faltan por completo, el código genera un aviso de error en cada petición |
| LMS | `LMS_URL` | URL del LMS Zajuna, usada para la tarjeta de estado en Inicio |
| Rutas | `SRC_DIRECTORY` | Nombre de carpeta del proyecto con `/` inicial, sin `/` final (p.ej. `/adi`). Si no coincide con la carpeta real: la página carga **sin estilos** y los botones no responden |
| Rutas | `APP_URL` | Dominio base **sin slash final** (p.ej. `http://localhost`). Con slash final: el login se queda dando vueltas |
| Dashboard → `newintegracion` | `DASH_PG_HOST, DASH_PG_PORT, DASH_PG_NAME, DASH_PG_USER, DASH_PG_PASS` | Reportes de integración. `DASH_PG_NAME` debe decir `newintegracion`; si falta, el sistema asume `adi_db` y esos reportes salen **vacíos sin ningún error** |
| Dashboard → `adi_db` | `DASH_ADI_*` | Batch, Josso, Semillas. Sin este bloque el panel queda prácticamente inútil |

Variables **[OPCIONAL]** (dejar vacías desactiva solo su módulo, no rompe el resto):

| Variable | Módulo que desactiva si está vacía |
|---|---|
| `SOFIA_ENGINE` / `SOFIA_*` | Con `SOFIA_ENGINE=pgsql` (valor por defecto documentado) NO requiere Oracle; usa vistas replicadas dentro de `newintegracion` |
| `CRONJOB_*` | SSH al servidor de cronjobs |
| `API_URL` | Integración con API externa |
| `JOSSO_INGEST_TOKEN`, `SEMILLAS_INGEST_TOKEN` | Endpoints de ingesta externa (`dashboard/server/josso_ingest.php`, `dashboard/server/semillas_ingest.php`) |
| `DASH_REP_*` | Informe Auditoría, Reporte Semillas (BD `dbadireporte`) |
| `DASH_PRES_*` | Titulada presencial (BD `Presencialformacion`, nombre con mayúsculas — crear entre comillas dobles en PostgreSQL) |
| `DASH_RES_*` | Resultados Calificaciones |
| `DASH_ORA_*` | Solo si `SOFIA_ENGINE=oracle` |
| `DOCKER_WEBSERVER_HOST_PORT`, `DOCKER_PGDB_HOST_PORT` | Legado del `docker-compose.yml` no usado. Dejar vacías |

**Valores locales recomendados** (los defaults que ya trae el código en
`dashboard/config/define.php` cuando una variable falta — evidencia directa de fuente):

```env
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASS=<tu-clave-local>
DB_DATABASE=adi_db

DBI_HOST=localhost
DBI_PORT=5432
DBI_USER=postgres
DBI_PASS=<tu-clave-local>
DBI_DATABASE=newintegracion

SRC_DIRECTORY=/adi
APP_URL=http://localhost
LMS_URL=http://192.168.1.170
```

> El resto de bloques `DASH_*` deben apuntar a los mismos `host/user/pass` que
> `DB_*`/`DBI_*` si usas un único PostgreSQL local con las 5 bases.

**Sobre secretos:** este repo ya trae un `.env` real en el servidor que corre
actualmente (`/var/www/html/adi/.env`, no versionado, permisos `640`). Si vas a
reproducir exactamente esta instancia (no una instancia nueva), la forma correcta es
**copiar ese `.env` existente tal cual** en vez de rellenar la plantilla a mano — así no
se transcriben contraseñas a mano ni se arriesga un typo. Para una máquina de desarrollo
nueva, generar valores propios (no reales) es lo correcto.

---

## 4. Dependencias

Solo en la raíz — el `dashboard/` **no tiene `composer.json` propio**, usa la misma
carpeta `vendor/` de la raíz (confirmado: `find` no encontró ningún `composer.json` bajo
`dashboard/`).

```bash
cd /var/www/html/adi
sudo composer install --no-dev --optimize-autoloader
ls vendor/autoload.php
```

Librerías reales (`composer.json`): `vlucas/phpdotenv` (leer `.env`),
`phpoffice/phpspreadsheet` (exportar Excel — por eso `gd`/`zip`/`xml` son obligatorias),
`phpseclib/phpseclib` (conexiones SSH, usadas por el módulo de cronjobs).

No hay `package.json` en ningún nivel del repo (verificado con `find`) — no hay paso de
build de frontend.

---

## 5. Servidor web (Apache) — no hay reverse proxy separado

El servidor real **es** Apache con `mod_php`; no existe una capa de reverse proxy
(Nginx/Traefik/etc.) delante en ningún archivo del repo. Apache sirve tanto el PHP como
los estáticos (`assets/`, `img/`, `public/`) directamente.

```bash
sudo a2enmod rewrite
sudo sed -i '/<Directory \/var\/www\/>/,/<\/Directory>/ s/AllowOverride None/AllowOverride All/' /etc/apache2/apache2.conf
sudo apache2ctl configtest
sudo systemctl restart apache2
```

**`.htaccess` (raíz y `dashboard/`) hace el enrutamiento real** — ya vienen en el repo,
no se editan:

- Raíz: enruta todo lo que no sea archivo/carpeta real hacia `index.php`; bloquea
  `app/`, `vendor/`, `database/`, `composer.json/lock` y todo archivo que empiece con
  punto (incluido `.env`).
- `dashboard/.htaccess`: bloquea `config/vendor/src/cache/tests/pages/Consultas/...` y
  enruta el resto a `dashboard/index.php`.

Sin `AllowOverride All`, Apache ignora ambos `.htaccess`: el sitio da 404 en todo **y
`.env` queda descargable desde el navegador con todas las contraseñas**.

**Puerto de entrada:** 80 (HTTP). No hay puerto interno distinto — mod_php corre dentro
del propio proceso Apache, no en un puerto separado que haya que proxyar.

**Hostname/dominio local:** sin evidencia de que el proyecto dependa de un hostname
específico. `APP_URL` acepta cualquier valor (`http://localhost`, una IP, o un dominio
real); no hay ningún `.local` hardcodeado en el código. No se documenta un hostname
inventado — usa `http://localhost/adi/` o la IP de tu máquina.

---

## 6. HTTPS

Sin evidencia de que el proyecto requiera HTTPS para funcionar en local: el código
detecta HTTP vs HTTPS dinámicamente (`index.php`, variable `$__isHttps`) y ajusta la
cookie de sesión (`secure` solo si hay HTTPS), sin romper el login por HTTP.

En producción, HTTPS es **opcional** y solo aplica si hay dominio propio con DNS
apuntando al servidor (`DESPLIEGUE_UBUNTU.md`, sección 18, vía `certbot --apache`). Para
un despliegue local por IP, como el que cubre este documento, **no aplica** — no
inventar un flujo HTTPS que el proyecto no usa en ese escenario.

Si igualmente quieres validar el flujo HTTPS localmente (fuera del alcance normal de
"máquina local"), usa un certificado autofirmado con `a2ensite`/`ssl-cert` de Ubuntu; no
uses certificados ni dominios reales de producción.

---

## 7. Process manager

No hay uno separado. Apache corre como servicio `systemd` (`apache2.service`), que ya
resuelve "proceso persistente que sobrevive a cerrar la terminal" — no depende de dejar
un `php -S` o similar corriendo en primer plano.

```bash
sudo systemctl enable apache2
sudo systemctl start apache2
sudo systemctl status apache2 --no-pager
```

---

## 8. Base de datos y servicios requeridos

**5 bases en el mismo PostgreSQL 16** (`COMO_FUNCIONA_ADI.md` sección 2):

| Base | ¿Obligatoria? | Se puede construir desde el repo | Alimenta |
|---|---|---|---|
| `adi_db` | Sí | **Sí**, con las migraciones (única de las 5) | Login, todo el sistema |
| `newintegracion` | Sí | No — solo con respaldo | Análisis, Buscador, reportes de integración |
| `dbadireporte` | Recomendada | No — solo con respaldo | Informe Auditoría, Reporte Semillas |
| `Presencialformacion` | Recomendada | No — solo con respaldo | Titulada presencial |
| `resultadoscalificaciones` | Recomendada | No — solo con respaldo | Resultados Calificaciones |

Solo faltando `newintegracion` o `adi_db` la app deja de servir; las otras tres solo
apagan su propio reporte con "no se pudieron cargar los datos".

**Crear las bases:**

```bash
sudo -u postgres psql -c "ALTER USER postgres PASSWORD '<tu-clave-local>';"
for b in adi_db newintegracion dbadireporte resultadoscalificaciones; do
  sudo -u postgres psql -c "CREATE DATABASE ${b};"
done
sudo -u postgres psql -c 'CREATE DATABASE "Presencialformacion";'   # comillas: nombre con mayúsculas
```

**Camino A — tienes los 5 respaldos (`.sql`/`.dump`):** restaurar cada uno según su
formato (texto plano, `pg_dump -Fc`, o `.gz`):

```bash
sudo -u postgres psql -d newintegracion -f /ruta/newintegracion.sql
sudo -u postgres pg_restore -d newintegracion --no-owner /ruta/newintegracion.dump
```

**Camino B — no tienes respaldo de `newintegracion`/`dbadireporte`/etc.:** esas bases
**no se pueden construir desde el repo** (no son datos generados por la app, son datos
reales de integración). Solo `adi_db` sí se puede construir desde cero — ver sección 9.

**Nunca exponer el puerto 5432 a una red externa** (`DESPLIEGUE_UBUNTU.md`, nota de la
sección 18). En local, PostgreSQL debe escuchar solo en `localhost`.

---

## 9. Migraciones y datos iniciales

`adi_db` es la única base construible desde el repositorio (schema `ADI` +
`INTEGRACION`):

```bash
sudo -u postgres psql -d adi_db -c 'CREATE SCHEMA IF NOT EXISTS "ADI"; CREATE SCHEMA IF NOT EXISTS "INTEGRACION";'

cd /var/www/html/adi
for m in 001_initial_migration 002_seed_default_data 003_performance_indexes \
         004_log_histories_indexes 005_batch_schedule 006_josso_event 007_ficha_semilla; do
  sudo -u postgres psql -d adi_db -f database/migrations/${m}.sql
done
```

> ⚠️ **`001` y `002` NUNCA sobre una base ya restaurada desde respaldo** — `001` falla
> con *"relation already exists"* y `002` duplica/falla por clave repetida. Solo sirven
> para construir `adi_db` desde cero, como aquí.

**Migración `008` (ver aviso de la sección 2 — sin commitear en este checkout):**

```bash
sudo -u postgres psql -d adi_db -f database/migrations/008_users_username.sql
```

**Dos tablas que ningún respaldo trae** (`manual_integration`, `login_attempts`): el
código las crea solo si el usuario de PostgreSQL tiene permiso `CREATE` sobre el schema
`ADI`; si no, el módulo falla con *"no se pudieron cargar"* sin más pista. Crearlas a
mano evita depender de ese permiso:

```bash
sudo -u postgres psql -d adi_db -c 'GRANT CREATE, USAGE ON SCHEMA "ADI" TO postgres;'
sudo -u postgres psql -d adi_db <<'SQL'
CREATE TABLE IF NOT EXISTS "ADI".manual_integration (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    inicio TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    fin TIMESTAMP WITHOUT TIME ZONE,
    estado VARCHAR(30) NOT NULL,
    observacion TEXT,
    created_by VARCHAR(30),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS "ADI".login_attempts (
    ip varchar(64) PRIMARY KEY, attempts integer NOT NULL DEFAULT 0,
    locked_until timestamptz NULL, updated_at timestamptz NOT NULL DEFAULT now()
);
SQL
```

**Módulo Informe Auditoría (opcional, requiere `dbadireporte` ya restaurada):**

```bash
sudo -u postgres psql -d dbadireporte -f database/manual/008_auditoria_evento_horario.sql
```

**Crear un usuario con contraseña conocida** — los usuarios que trae cualquier respaldo
tienen hash con contraseña original desconocida; sin este paso no se puede iniciar
sesión:

```bash
HASH=$(php -r "echo password_hash('TuClaveLocal123', PASSWORD_DEFAULT);")
sudo -u postgres psql -d adi_db <<SQL
INSERT INTO "ADI".users (num_id, tipe_id, name, email, password, role)
VALUES (12345678, 'cc', 'Dev Local', 'dev@local.test', '${HASH}', 'super')
ON CONFLICT (num_id) DO UPDATE SET password = EXCLUDED.password, role = 'super';
SQL
```

> Contraseña mínima 10 caracteres, con mayúscula, minúscula y número (lo exige la
> política de la app para crear usuarios desde la interfaz).

---

## 10. Permisos

Apache ejecuta PHP como `www-data`. Archivos de `root` rompen la escritura de sesión y
caché; permisos abiertos exponen el `.env`.

```bash
sudo chown -R www-data:www-data /var/www/html/adi
sudo find /var/www/html/adi -type d -exec chmod 755 {} \;
sudo find /var/www/html/adi -type f -exec chmod 644 {} \;
sudo chmod -R 775 /var/www/html/adi/dashboard/cache
sudo chown -R www-data:www-data /var/www/html/adi/dashboard/cache
sudo chmod 640 /var/www/html/adi/.env
sudo chown www-data:www-data /var/www/html/adi/.env
```

---

## 11. Build

No aplica: no hay `package.json` ni paso de compilación en ningún nivel del repo. El
frontend es PHP renderizado en servidor + JS/CSS ya presentes en `assets/`, `helpers/`,
`dashboard/assets/`; librerías como Bootstrap y Chart.js se cargan por CDN directo en
`dashboard/index.php` (`<script src="https://cdnjs...">`), no por bundling local.

---

## 12. Ejecución local

```bash
sudo systemctl restart apache2
```

- **URL:** `http://localhost/adi/` (o `http://<IP-local>/adi/`) según `SRC_DIRECTORY=/adi`.
- **Puerto:** 80.
- **Verificar que responde:**

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/adi/
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/adi/dashboard/
```

Ambos deben dar `200`. ADI y el panel **no son procesos separados**: ambos corren dentro
de la misma petición Apache/PHP, comparten sesión y `.env`.

---

## 13. Verificación / Smoke test

Desde el mismo punto de entrada que usaría un usuario real
(`http://localhost/adi/`, **no** un puerto interno distinto — no existe tal puerto en
esta arquitectura):

| # | Acción | Resultado esperado |
|---|---|---|
| 1 | Abrir `http://localhost/adi/` | Login con estilos (logo, fondo, campos formateados) |
| 2 | Iniciar sesión con el usuario creado en la sección 9 | Pantalla de Inicio con el nombre del usuario |
| 3 | Ver la pantalla de Inicio | Tarjetas Sofia Plus y LMS con su estado |
| 4 | `curl http://localhost/adi/.env` | **403** (si da 200 o descarga el archivo, repetir sección 5 — es crítico) |
| 5 | `curl http://localhost/adi/app/App.php` | **403** |
| 6 | Informes → Reportes Integración (si `newintegracion` está cargada) | Indicadores y gráficas |
| 7 | Cerrar sesión | Vuelve al login |

No hay un endpoint `/health` dedicado en el código (verificado con grep sobre
`app/`, `dashboard/`, `index.php` — no aparece). Lo más cercano es
`Routes::PLATFORM_STATUS` (`DashboardController::indexJSON`), que reporta el estado de
LMS/Sofia consumidos por la tarjeta de Inicio, no un healthcheck de infraestructura.

---

## 14. Tests

Existen dos suites de test en el repo, pero **ninguna tiene un runner configurado
listo para ejecutar** — evidencia, no invención:

- `dashboard/tests/*.php` — hay `dashboard/phpunit.xml` (bootstrap
  `vendor/autoload.php`, suite apuntando a `tests/`), pero `dashboard/` no tiene
  `composer.json` propio y la raíz **no** declara `phpunit/phpunit` en
  `require-dev` (no existe ese bloque en `composer.json`). No hay
  `vendor/bin/phpunit` tras `composer install`.
- `test/testApp`, `test/testComponents`, `test/testHelpers` (raíz) — usan
  `PHPUnit\Framework\TestCase` pero no hay `phpunit.xml` en la raíz.

Para poder correrlos habría que instalar PHPUnit aparte, p.ej.:

```bash
composer require --dev phpunit/phpunit ^9
vendor/bin/phpunit --configuration dashboard/phpunit.xml
```

**Sin evidencia** de que esto se ejecute en CI: no hay carpeta `.github/workflows`, ni
`.gitlab-ci.yml`, ni `Jenkinsfile` en el repo.

---

## 15. Problemas comunes

Resumen de `DESPLIEGUE_UBUNTU.md` sección 17 (ahí está el detalle completo):

| Síntoma | Causa / solución |
|---|---|
| Pantalla en blanco | Falta `php8.2-pgsql` o la carpeta `vendor/` — revisar `/var/log/apache2/error.log` |
| 404 en todas las páginas | `.htaccess` ignorado — falta `AllowOverride All` (sección 5) |
| Carga sin estilos, botones sin respuesta | `SRC_DIRECTORY` no coincide con la carpeta real |
| Login se queda dando vueltas | `APP_URL` con slash final, o cookies viejas del navegador |
| "Credenciales incorrectas" | Repetir creación de usuario (sección 9) |
| "Demasiados intentos fallidos" | 5 intentos bloquean la IP 15 min: `DELETE FROM "ADI".login_attempts;` |
| Reporte dice "no se pudieron cargar los datos" | Ver qué BD usa ese módulo en `COMO_FUNCIONA_ADI.md` sección 3, y probar esa conexión |
| Reportes de integración vacíos sin error | `DASH_PG_NAME` no dice `newintegracion` |
| `http://.../adi/.env` se descarga | **Crítico** — repetir sección 5 y dar las contraseñas por comprometidas |
| `could not find a composer.json file` | Ese archivo está gitignored, copiarlo aparte (sección 2) |
| `detected dubious ownership in repository` | `sudo git config --system --add safe.directory /var/www/html/adi` |

---

## 16. Detener y limpiar el entorno

```bash
sudo systemctl stop apache2
```

**Borrar solo la app** (conserva las bases):

```bash
sudo rm -rf /var/www/html/adi
```

**Borrar también las bases** (se pierde todo lo importado):

```bash
for b in adi_db newintegracion dbadireporte resultadoscalificaciones; do
  sudo -u postgres psql -c "DROP DATABASE IF EXISTS ${b};"
done
sudo -u postgres psql -c 'DROP DATABASE IF EXISTS "Presencialformacion";'
```

**Limpiar caché del panel** (sin borrar nada más):

```bash
sudo rm -f /var/www/html/adi/dashboard/cache/*
```

---

## 17. Logs

- **Apache + PHP (errores de la app, `error_log()` de PHP):**
  `/var/log/apache2/error.log` — con `display_errors=Off` y `log_errors=On`
  (recomendado en `DESPLIEGUE_UBUNTU.md` sección 5), todo error de PHP va aquí, no a
  pantalla.
- **Acceso Apache:** `/var/log/apache2/access.log`.
- **PostgreSQL:** ubicación estándar de la instalación (`/var/log/postgresql/` en
  Ubuntu vía apt).
- **Aplicación:** no hay archivo de log propio distinto del `error_log` de PHP; el
  "Registro de Auditoría" que menciona `README.txt` vive en base de datos
  (tabla `audit` de `adi_db`), no en filesystem.

```bash
sudo tail -f /var/log/apache2/error.log
```

---

## 18. Reinicio

```bash
sudo systemctl stop apache2 postgresql
sudo systemctl start postgresql
sudo systemctl start apache2
sudo systemctl status postgresql apache2 --no-pager
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/adi/
```

Orden obligatorio: PostgreSQL antes que Apache (la app abre conexión `PDO` al primer
request; si PostgreSQL no está arriba, esa petición falla con "Connection refused" pero
Apache sigue sirviendo el resto normalmente en el siguiente intento).

---

## Anexo A — Alternativa Docker (no es el flujo real, documentada porque el repo la trae)

`docker-compose.yml` levanta `webserver` (`Dockerfile-webserver`, PHP 8.2 + Apache) y
`pgdb` (`docker/Dockerfile-postgresql`, Postgres 16). Requiere `SRC_DIRECTORY`,
`DOCKER_WEBSERVER_HOST_PORT`, `DOCKER_PGDB_HOST_PORT` en el `.env` (vacías por defecto
en `.env.example`, marcadas como legado sin mantenimiento).

```bash
docker compose up -d --build
```

La app queda en `http://localhost:<DOCKER_WEBSERVER_HOST_PORT>/adi/`. La red interna
Docker conecta `webserver` → `pgdb` por nombre de servicio (`DB_HOST=pgdb` en ese
escenario); no hay reverse proxy adicional tampoco en este camino.
`COMO_FUNCIONA_ADI.md` marca esta ruta como no usada actualmente — úsala solo si
decides deliberadamente containerizar en vez de reproducir el servidor real.

---

## Server parity checklist

- [ ] Apache + mod_php 8.2 corriendo como único servidor (no hay reverse proxy que
      configurar aparte — confirmarlo, no asumirlo)
- [ ] HTTPS: **no aplica** salvo que se pruebe deliberadamente con dominio propio
- [ ] Hostname: sin requisito específico — cualquier `APP_URL` válido sirve
- [ ] `AllowOverride All` activo (`.htaccess` obedecido en raíz y `dashboard/`)
- [ ] `.env` con `SRC_DIRECTORY` y `APP_URL` correctos, sin slash final en `APP_URL`
- [ ] `composer.json`/`composer.lock` presentes (no vienen del clone — copiarlos)
- [ ] `vendor/autoload.php` generado en la máquina local (no copiado de otra)
- [ ] `adi_db` con migraciones 001–007 (+ 008 si aplica) y `newintegracion` restaurada
      como mínimo
- [ ] Tablas `manual_integration` y `login_attempts` creadas
- [ ] Usuario de login con contraseña conocida y rol `super`
- [ ] `www-data` dueño del proyecto; `dashboard/cache/` en `775`; `.env` en `640`
- [ ] PostgreSQL escuchando solo en `localhost`, puerto 5432 no expuesto
- [ ] `.env` y `app/App.php` responden `403` por HTTP
- [ ] Smoke test de la sección 13 completo, desde `http://localhost/adi/` (el mismo
      punto de entrada que un usuario real, no un puerto interno)
- [ ] `/var/log/apache2/error.log` revisado sin errores tras el smoke test
- [ ] Servicio sobrevive a `systemctl restart apache2` sin reconfiguración manual
