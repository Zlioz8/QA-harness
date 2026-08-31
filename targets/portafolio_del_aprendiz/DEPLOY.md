# Deploy local

> Plugin: `local_portafolio` (Moodle local plugin, solo lectura).
> Este documento describe cómo reproducir localmente, con la mayor fidelidad
> posible, la arquitectura real en la que corre este plugin: un Apache con
> `mod_php` sirviendo una instalación Moodle 4.3, respaldada por PostgreSQL.
> **Este repositorio no contiene Docker, CI/CD, reverse proxy ni HTTPS.**
> Cuando una sección del checklist estándar de deploy no aplica a este
> proyecto, se indica explícitamente por qué, en vez de inventar infraestructura
> que no existe.

---

## 1. Objetivo

Permitir que un desarrollador, partiendo de una máquina limpia, levante:

1. Una instalación Moodle 4.3.x (host del plugin) — **prerequisito**, no
   forma parte de este repositorio.
2. El código de `local_portafolio` dentro de esa instalación
   (`<moodle_root>/local/portafolio`).
3. El mismo stack de servicio que corre en el entorno de referencia
   inspeccionado (Apache + PostgreSQL), de modo que el comportamiento
   observado localmente sea equivalente al de un servidor real, no solo al
   de un entorno de desarrollo simplificado.

## 2. Arquitectura local (identificada)

Arquitectura real determinada por inspección directa del entorno donde vive
este plugin (Apache activo, `apache2ctl -M`, `ss -tlnp`, `psql -l`,
`config.php` de Moodle, `settings.php`/`IntegracionDbConnection.php` del
plugin):

```
Navegador
   │  http://localhost/zajuna/...  (puerto 80, HTTP, sin TLS)
   ▼
Apache 2.4 (mod_php, sin mod_rewrite/mod_ssl/mod_headers)
   DocumentRoot: /var/www/html            (portal institucional, fuera de alcance)
   └── /zajuna  → symlink → /var/www/zajuna   (raíz de Moodle)
         └── /zajuna/local/portafolio         (este plugin, código PHP puro)
   │
   ▼
Moodle 4.3.3 (PHP 8.2, ejecutado in-process por mod_php; no hay proceso
              backend separado ni puerto propio para el plugin)
   │
   ├──▶ PostgreSQL 16, cluster "main", puerto 5433, BD `moodle`
   │     (conexión principal $DB, configurada en <moodle_root>/config.php)
   │
   └──▶ PostgreSQL "integracion" (BD externa de solo lectura, copia de la
         integración SENA/Sofia Plus) — OPCIONAL, configurada por
         Site administration → Plugins → Local plugins → Portafolio
         (`classes/infrastructure/IntegracionDbConnection.php`)
```

Puntos clave de esta arquitectura (verificados, no asumidos):

- **No hay reverse proxy independiente.** No se encontró Nginx, Caddy ni
  Traefik en el host (`nginx -v` → comando no encontrado) ni configuración
  alguna de ellos en el repo. Apache mismo es el único punto de entrada, con
  `mod_php` ejecutando el PHP directamente (no PHP-FPM). El requisito del
  enunciado de "documentar el reverse proxy real" no aplica: el reverse
  proxy real de este proyecto **es Apache actuando como servidor único**.
- **No hay HTTPS.** Solo el puerto 80 está en escucha para el sitio
  (`ss -tlnp`), no hay módulo `ssl_module` cargado en Apache y `config.php`
  define `$CFG->wwwroot = 'http://localhost/zajuna'` (HTTP explícito). No se
  documentan certificados porque el entorno real inspeccionado no los usa.
- **No hay build de frontend.** Moodle es una aplicación PHP renderizada en
  servidor; el plugin no trae `package.json`, ni bundler, ni SCSS propio.
  Sus únicos assets (`javascript/activity-grades.js`, `css/styles.css`) son
  JS/CSS planos, cargados directamente vía `$PAGE->requires->js()/css()` en
  `lib.php` — no requieren paso de compilación.
- **No hay Docker.** No existe `Dockerfile`, `docker-compose.yml` ni
  equivalente en este repositorio ni en la raíz de Moodle. No se agrega
  Docker en este documento porque el entorno real no lo usa (regla: no
  inventar infraestructura).
- **El plugin no tiene tablas propias.** `db/` solo contiene `access.php`,
  `hooks.php`, `install.php` y `upgrade.php` (hooks de instalación/actualización,
  no esquema). No hay `db/install.xml`. Esto es una decisión de diseño
  documentada en `CLAUDE.md` de este repo.

## 3. Requisitos previos

Determinados por inspección directa del entorno de referencia
(`php -v`, `apache2ctl -v`, `psql --version` vía `pg_lsclusters`,
`version.php` de Moodle y del plugin):

| Componente | Versión verificada en el entorno de referencia |
|---|---|
| PHP | 8.2.32 (CLI y Apache `mod_php`, mismo binario/config base) |
| Apache | 2.4.58 (Ubuntu), con `mod_php` (no PHP-FPM) |
| PostgreSQL | 16 (cluster `16-main`, puerto **5433**, no el 5432 por defecto) |
| Moodle | 4.3.3+ (Build: 20240308), branch `403` |
| Requisito del plugin | `$plugin->requires = 2023100900` (`version.php`) → Moodle 4.3 |

Módulos PHP cargados en el entorno de referencia (`php -m`), que Moodle 4.3 +
este plugin requieren en tiempo de ejecución: `pgsql`, `pdo_pgsql`, `curl`,
`gd`, `intl`, `mbstring`, `xml`, `xmlreader`, `xmlwriter`, `xsl`, `zip`,
`soap`, `sockets`, `sodium`, `openssl`, `gettext`, `exif`, `fileinfo`, `ftp`,
`FFI`. En Ubuntu, el paquete equivalente sería `php8.2` +
`libapache2-mod-php8.2` + `php8.2-{pgsql,curl,gd,intl,mbstring,xml,zip,soap}`.
**Nota:** esta lista es una inferencia a partir de los módulos ya cargados en
el host inspeccionado (`php -m`); el proyecto no trae un manifiesto de
dependencias PHP (no hay `composer.json` propio del plugin — el
`composer.json` que existe es el de Moodle core, y solo declara
dependencias de desarrollo/test: PHPUnit, Behat, Mink).

Software a instalar en la máquina limpia:

- PHP 8.2 + extensiones listadas arriba.
- Apache 2.4 con `mod_php` habilitado.
- PostgreSQL 16 (o el motor/versión real usado por el equipo si difiere;
  ver sección 8).
- Una instalación de Moodle 4.3.x en la que insertar este plugin (ver
  sección 4 — no se incluye en este repo).
- `git`.

No se requiere Node/npm para correr el plugin. `npm-shrinkwrap.json`,
`Gruntfile.js` y `.nvmrc` (`lts/iron`) existen en la raíz de Moodle core
para el build de temas/JS del core de Moodle, no de este plugin — fuera de
alcance salvo que también se esté modificando el core.

## 4. Preparación de la máquina

1. Instalar el software del punto 3 (comandos exactos dependen de la
   distribución; en el entorno de referencia se usó Ubuntu vía `apt`).
2. Obtener una instalación de Moodle 4.3.x. Este repositorio **no** incluye
   el core de Moodle. Opciones razonables:
   - Clonar/copiar el mismo Moodle 4.3.3 usado por el equipo (fuente no
     documentada en este repo — coordinar con el equipo de infraestructura).
   - Descargar Moodle 4.3.x oficial desde `https://download.moodle.org` si
     no se dispone de la copia interna.
3. Clonar este repositorio dentro de `<moodle_root>/local/`:
   ```bash
   git clone ssh://git@git.fsrisaralda.com:2222/fabrica_zajuna/portafolio_del_aprendiz.git \
     <moodle_root>/local/portafolio
   ```
   (URL del remoto verificada con `git remote -v` en este repo). El
   directorio final debe llamarse `portafolio` — el `component` declarado en
   `version.php` es `local_portafolio`, y Moodle resuelve el nombre del
   plugin a partir de la ruta `local/<nombre>`.
4. Verificar permisos: en el entorno de referencia, `moodledata` es propiedad
   de `www-data:www-data`. El código de `local/portafolio` debe ser al menos
   legible por el usuario que ejecuta Apache/PHP.

## 5. Configuración de hostname

No se requiere un dominio personalizado. `config.php` del entorno de
referencia define `$CFG->wwwroot = 'http://localhost/zajuna'`, y `localhost`
ya resuelve por defecto en `/etc/hosts` en cualquier máquina. No se
documenta un `/etc/hosts` adicional porque el proyecto real no depende de un
hostname propio.

Si el `wwwroot` local difiere (por ejemplo si se monta en otro subpath o
puerto), debe mantenerse consistente entre:
- `$CFG->wwwroot` en `config.php`,
- la ruta real donde Apache expone Moodle (ver sección 11),
- el valor de `alternateloginurl` en la configuración del sitio (ver
  Troubleshooting, punto crítico).

## 6. Variables de entorno / configuración

Este proyecto **no usa archivos `.env`** (no existe `.env`, `.env.example`
ni `.env.template` en el repo). La configuración se maneja por los dos
mecanismos propios de Moodle:

### 6.1. `config.php` de Moodle (raíz del host, fuera de este repo)

No versionado en este repositorio (vive en la raíz de Moodle, no en
`local/portafolio`). Debe crearse localmente. Campos verificados en el
entorno de referencia (valores de ejemplo, **no credenciales a reutilizar**):

| Variable | Propósito | Obligatoria | Origen |
|---|---|---|---|
| `$CFG->dbtype` | Motor de BD principal | Sí | `pgsql` en el entorno de referencia |
| `$CFG->dbhost` | Host de la BD principal | Sí | `localhost` |
| `$CFG->dbname` | Nombre de la BD principal | Sí | `moodle` |
| `$CFG->dbuser` / `$CFG->dbpass` | Credenciales de la BD principal | Sí | definir localmente, no reutilizar las de producción |
| `$CFG->dboptions['dbport']` | Puerto de PostgreSQL | Sí si no es el 5432 por defecto | `5433` en el entorno de referencia (cluster no estándar) |
| `$CFG->wwwroot` | URL pública del sitio | Sí | `http://localhost/zajuna` |
| `$CFG->dataroot` | Carpeta de datos de Moodle (fuera del webroot) | Sí | `/var/www/zajunadata` |
| `$CFG->admin` | Ruta del área de administración | Sí | `admin` (valor por defecto) |
| `$CFG->directorypermissions` | Permisos de directorios creados por Moodle | Sí | `0777` en el entorno de referencia |
| `$CFG->php_memory_limit` | Override de memoria PHP | No | presente en el entorno de referencia con un valor inusualmente alto; no es necesario replicarlo tal cual, basta con un límite razonable (p. ej. `256M`–`512M`) |

### 6.2. Configuración propia del plugin (vía UI de Moodle, persistida en BD)

`local_portafolio` no lee variables de entorno del sistema operativo. Su
única configuración es la BD externa de integración, definida en
`settings.php` y consumida en
`classes/infrastructure/IntegracionDbConnection.php`, editable en
**Site administration → Plugins → Local plugins → Portafolio**:

| Config (`local_portafolio/...`) | Propósito | Obligatoria | Default en código |
|---|---|---|---|
| `integracion_dbhost` | Host de la BD externa "integración" (Sofia Plus) | No — degrada con gracia si falla | `localhost` |
| `integracion_dbname` | Nombre de esa BD | No | `integracion` |
| `integracion_dbuser` | Usuario de esa BD | No | `postgres` |
| `integracion_dbpass` | Password de esa BD | No | placeholder de desarrollo en el propio `settings.php`, **no usar en un entorno con datos reales** |

**Hallazgo importante (verificado):** `IntegracionDbConnection::get()`
conecta siempre con `dbport => ''` (línea fija en el código, sin campo de
puerto en `settings.php`). Esto significa que la BD "integración" **solo
puede vivir en el puerto por defecto de PostgreSQL (5432)** — no hay forma,
desde la UI del plugin, de apuntarla al puerto 5433 usado por la BD
principal de Moodle en este entorno. Si se quiere reproducir esa BD
localmente en el mismo cluster PostgreSQL que Moodle, debe correr en un
cluster/instancia separada escuchando en 5432, o debe modificarse el código
— este documento no inventa una solución no presente en el repo.

En el entorno inspeccionado, **la base `integracion` no existe** (verificado
con `psql -l` contra el cluster local: solo existen `moodle`, `encuestados`,
`zajunadb`, `zajunadb22`, `postgres`, `template0/1`). El servicio que la
consume (`IntegracionResultadosService.php`, líneas ~125-138 y ~307-317)
envuelve las llamadas en `try { ... } catch (\dml_exception $e)`, así que su
ausencia no rompe el resto del plugin: solo deja vacíos los resultados RAP
("Resultados de aprendizaje") en la página `resultados.php`.

No se detectaron variables usadas por el código que falten en algún
`.env.example` (no aplica, no existe ese mecanismo), ni variables de
`.env.example` no usadas (no aplica, mismo motivo).

## 7. Dependencias

- **PHP**: no hay `composer.json` propio del plugin; no se instalan
  dependencias PHP adicionales para `local_portafolio`. El `composer.json`
  de la raíz de Moodle solo trae dependencias de *test* (PHPUnit, Behat,
  Mink) — necesarias solo si se van a correr pruebas automatizadas del core,
  no para desplegar el plugin.
- **JS/Node**: no aplica para este plugin (ver sección 2). El `.nvmrc`
  (`lts/iron`) y `package.json`/`Gruntfile.js` pertenecen al core de Moodle,
  para su propio pipeline de temas — no se documentan aquí por no ser parte
  de este repo ni requerirse para correr el plugin.
- **Autoload del plugin**: `bootstrap.php` implementa un autoloader PSR-4
  manual para el namespace `local_portafolio\` (no usa el autoload de
  Composer) — no requiere ningún paso de instalación, se activa con
  `require_once __DIR__ . '/bootstrap.php'`.

## 8. Base de datos

### 8.1. BD principal de Moodle

- Motor: **PostgreSQL 16** (`postgresql@16-main`, verificado con
  `pg_lsclusters`).
- Puerto: **5433** en el entorno de referencia (no el 5432 estándar —
  cluster configurado explícitamente así; confirmar el puerto real disponible
  en la máquina local con `pg_lsclusters`, puede variar).
- Base de datos: `moodle`.
- Usuario: definido localmente en `config.php`; no reutilizar credenciales
  de un entorno compartido.
- Prefijo de tablas: `mdl_`.

Levantarla localmente (Ubuntu/Debian, PostgreSQL 16 vía paquete de sistema —
esto es lo que corre en el entorno de referencia; **no aplica Docker
Compose porque el proyecto no trae uno**):

```bash
sudo systemctl start postgresql
sudo -u postgres psql -c "CREATE DATABASE moodle WITH ENCODING 'UTF8' LC_COLLATE 'es_CO.UTF-8' LC_CTYPE 'es_CO.UTF-8' TEMPLATE template0;"
sudo -u postgres psql -c "ALTER USER postgres PASSWORD '<definir localmente>';"
```

(Encoding/locale tomados de la BD `moodle` real, verificados con
`psql -l`: `UTF8` / `es_CO.UTF-8`.)

Comprobar que está arriba:

```bash
pg_lsclusters
psql -h localhost -p <puerto> -U postgres -l
```

Migraciones/instalación del esquema: **no las ejecuta el plugin.** El
esquema completo lo crea/actualiza el instalador de Moodle
(`admin/cli/install.php` para una instalación nueva, o
`admin/cli/upgrade.php` tras actualizar código — ver sección 14). El plugin
en sí no tiene `db/install.xml`, así que no aporta tablas ni migraciones
propias; solo se registra en `mdl_config_plugins` cuando Moodle detecta el
código nuevo bajo `local/portafolio` y se corre el upgrade.

Seeds: no hay seeds "oficiales" del plugin. Existen tres scripts CLI de
un solo uso en `cli/`, explícitamente marcados en su propio código como
herramientas de depuración, no parte del deploy estándar:

- `cli/seed_course73.php` y `cli/seed_rap.php` — siembran datos de prueba
  para un curso (`id=73`) y ficha (`2872729`) específicos contra la BD
  externa `integracion`. El propio `seed_rap.php` dice en su comentario:
  *"No es parte del plugin instalado - borrar tras usar."*
- `cli/verify_seed.php` — verificación de solo lectura de lo anterior.

No se documentan como paso obligatorio del deploy porque no lo son; se
mencionan para que QA sepa que existen y **no** los ejecute contra datos
reales sin entender lo que hacen.

### 8.2. BD externa "integración" (opcional)

Ver sección 6.2. Motor PostgreSQL, puerto fijo 5432 (limitación de código),
esquema no documentado en este repositorio — es una copia de la integración
SENA/Sofia Plus cuyo esquema no está definido aquí. **Información faltante:**
no hay en el repo un dump, `install.xml` ni definición de columnas de esta
BD externa; no se puede documentar cómo recrearla desde cero solo con este
repositorio.

## 9. Servicios auxiliares

No se encontró configuración de Redis, RabbitMQ, Kafka, Elasticsearch,
MongoDB, MinIO ni SMTP específica de este plugin, ni en el repo ni en el
entorno inspeccionado (`systemctl list-units --state=running` solo muestra
`apache2` y `postgresql@16-main` relacionados con este stack). No se
documentan estos servicios porque no son parte real del proyecto.

La única dependencia externa de red del plugin es un **fallback** a CDN
(`https://cdnjs.cloudflare.com/.../font-awesome/...`), usado por
`local_portafolio_add_iconpack()` en `lib.php` **solo si** el bundle local
`pix/icons/fontawesome/js/all.min.js` no existe. En el entorno de referencia
ese archivo sí existe, por lo que el plugin no depende de internet en
condiciones normales.

## 10. Build

No hay paso de build para este plugin (ver sección 2/7). El "build" completo
consiste en:

1. Tener un Moodle 4.3.x funcional (fuera de este repo).
2. Copiar/clonar este repositorio en `<moodle_root>/local/portafolio`.
3. Dejar que Moodle detecte e instale el plugin (sección 14).

No hay `npm run build`, `composer install` propio, ni artefactos a generar.

## 11. Reverse proxy / Web server

Como se documentó en la sección 2, no existe un reverse proxy independiente
en este proyecto — **Apache es el único servidor**, sirviendo PHP
directamente vía `mod_php` (confirmado con `apache2ctl -M`: no hay
`proxy_module`, `proxy_http_module` ni `ssl_module` cargados).

Configuración real usada (`/etc/apache2/sites-available/000-default.conf`
en el entorno de referencia):

```apache
<VirtualHost *:80>
    ServerAdmin webmaster@localhost
    DocumentRoot /var/www/html
    ErrorLog ${APACHE_LOG_DIR}/error.log
    CustomLog ${APACHE_LOG_DIR}/access.log combined
</VirtualHost>
```

- `DocumentRoot` apunta a `/var/www/html`, que en el entorno de referencia
  aloja un **portal institucional separado** (fuera de alcance de este
  repo/documento).
- Moodle se expone dentro de ese mismo vhost mediante un **symlink**:
  `/var/www/html/zajuna -> /var/www/zajuna`, de forma que la app queda
  accesible en `http://localhost/zajuna/...`.
- Para reproducir esto localmente sin necesitar el portal institucional,
  la opción más simple y honesta (sin inventar un vhost dedicado que no
  existe en el repo) es: crear un `DocumentRoot` propio para pruebas
  (p. ej. `/var/www/local-moodle`) y symlinkear/copiar la instalación de
  Moodle bajo un subpath `zajuna`, replicando la misma estructura de URL
  (`http://localhost/zajuna`) para que `wwwroot` coincida.
- No exponer directamente ningún "puerto interno de la aplicación" porque
  no existe tal puerto: PHP corre dentro del proceso de Apache
  (`mod_php`), no como servicio HTTP separado en otro puerto.

## 12. Frontend

Moodle renderiza HTML en servidor; no hay SPA ni frontend separado para
este plugin. Los únicos assets propios son:

- `css/styles.css` — CSS plano, cargado con
  `$PAGE->requires->css('/local/portafolio/css/styles.css')` (`lib.php:524`).
- `javascript/activity-grades.js` — JS plano, cargado con
  `$PAGE->requires->js('/local/portafolio/javascript/activity-grades.js', true)`
  (`lib.php:431`).
- `pix/icons/fontawesome/js/all.min.js` — bundle de iconos vendorizado, con
  fallback a CDN solo si falta (sección 9).

No hay paso de instalación/build/generación de artefactos para el
frontend: los archivos se sirven tal cual desde el repo.

## 13. Backend

- Runtime: **PHP 8.2** (verificado `php -v` → `8.2.32`).
- No hay comando de arranque propio: el "backend" es el código PHP del
  plugin, ejecutado por Apache/`mod_php` cada vez que Moodle enruta una
  petición hacia `local/portafolio/*.php`.
- No aplica el patrón "escuchar en `0.0.0.0`" porque no hay un puerto propio
  del backend — es código ejecutado dentro del proceso de Apache, no un
  servicio de red independiente.
- Puntos de entrada HTTP reales del plugin (cada uno hace
  `require_once __DIR__ . '/inc.php'`, que a su vez carga `config.php` de
  Moodle): `index.php`, `view.php`, `cursos.php`, `actividades.php`,
  `pendientes.php`, `resultados.php`, `participantes.php`, `foros.php`,
  `scorm.php`, `evidencias.php`, `quiz.php`, `wiki.php`, `blogs.php`,
  `logros.php`, `otros.php`, `voice.php`.
- Capacidades definidas (`db/access.php`): `local/portafolio:use`
  (CAP_ALLOW para el archetype `user`) y `local/portafolio:viewother`
  (CAP_ALLOW para `editingteacher`, `teacher`, `manager`).

## 14. Inicio del entorno

Con Moodle ya instalado (`config.php` presente) y este plugin copiado en
`local/portafolio`:

```bash
# 1. Levantar los servicios de sistema
sudo systemctl start postgresql
sudo systemctl start apache2

# 2. Verificar que ambos están activos
systemctl status postgresql apache2

# 3a. Instalación nueva de Moodle (solo la primera vez, sin config.php aún)
sudo -u www-data php admin/cli/install.php \
  --wwwroot="http://localhost/zajuna" \
  --dataroot="/var/www/zajunadata" \
  --dbtype=pgsql --dbhost=localhost --dbname=moodle \
  --dbuser=postgres --dbpass=<definir> --dbport=<puerto real> \
  --fullname="Zajuna (local)" --shortname="zajuna" \
  --adminuser=admin --adminpass=<definir> --adminemail=<definir> \
  --agree-license --non-interactive

# 3b. Si Moodle ya está instalado y solo se agregó/actualizó el código del
#     plugin, aplicar el upgrade para que lo registre:
sudo -u www-data php admin/cli/upgrade.php --non-interactive
```

(Flags de `install.php` verificados ejecutando
`php admin/cli/install.php --help` en el entorno de referencia; el mensaje
de ese mismo comando confirma además que, si `config.php` ya existe, hay que
usar `admin/cli/upgrade.php` en su lugar — texto real devuelto por el
script: *"El archivo de configuración config.php ya existe. Por favor,
utilice admin/cli/install_database.php para actualizar Moodle en este
sitio."*)

Ambos scripts deben ejecutarse **con el mismo usuario que corre Apache**
(`www-data` en el entorno de referencia) — así lo indica el propio `--help`
de esos comandos, para evitar problemas de permisos sobre `dataroot`.

## 15. Verificación

```bash
# Apache activo y sirviendo
systemctl is-active apache2

# PostgreSQL activo, cluster real levantado
pg_lsclusters
systemctl is-active postgresql

# Moodle responde
curl -sI http://localhost/zajuna/login/index.php

# El plugin está instalado y Moodle lo reconoce (debe listarlo como
# habilitado, sin errores de upgrade pendiente)
sudo -u www-data php admin/cli/checks.php 2>/dev/null || true
```

`admin/environment.php` es la verificación de entorno propia de Moodle
(requisitos de PHP/BD); responde con redirect (303) si no hay sesión, igual
que el resto del sitio — accederla autenticado como admin para ver el
resultado completo.

## 16. Smoke test

El punto de entrada real para un usuario externo es el mismo que usa el
navegador: `http://localhost/zajuna/...` (no un puerto interno, porque no
existe uno — sección 11).

1. **Sitio accesible**:
   ```bash
   curl -sI http://localhost/zajuna/login/index.php
   ```
   Debe responder `303 See Other` (Moodle siempre redirige desde
   `login/index.php`, ver punto crítico de autenticación abajo) con
   `Server: Apache/...` en la cabecera — confirma que Apache+PHP están
   sirviendo Moodle.

2. **Login funcional**: iniciar sesión con un usuario de prueba (método
   `email`, ver Troubleshooting — el método `oidc` no es reproducible
   localmente sin el IdP real de SENA).

3. **Portafolio accesible**: con sesión iniciada, navegar a
   `http://localhost/zajuna/local/portafolio/index.php` y confirmar que
   carga el mosaico de cursos matriculados (sin conmutador de vistas, según
   `CLAUDE.md`).

4. **Dashboard de un curso**: entrar a
   `http://localhost/zajuna/local/portafolio/view.php?courseid=<id>` de un
   curso donde el usuario de prueba esté matriculado, y confirmar que
   renderiza stats, accesos rápidos y actividades pendientes/presentadas
   sin errores PHP en pantalla ni en `error.log`.

5. **Conexión a BD principal**: implícita en los pasos 2-4 (todo el
   contenido viene de `$DB`, que usa la BD `moodle`).

6. **BD de integración (si está configurada)**: entrar a
   `resultados.php` de un curso con ficha asociada y confirmar que no hay
   `dml_exception` sin capturar en los logs; si la BD `integracion` no
   existe, la página debe mostrar el estado "sin resultados" en vez de un
   error 500 (comportamiento esperado según
   `IntegracionResultadosService.php`).

No se documentan endpoints de health check tipo `/health` porque **no
existen** en este proyecto ni en Moodle core; la verificación real de salud
es la combinación de los pasos 1-4.

## 17. Logs

| Componente | Ubicación | Cómo consultarlo |
|---|---|---|
| Apache (acceso) | `/var/log/apache2/access.log` (`${APACHE_LOG_DIR}` del vhost) | `tail -f /var/log/apache2/access.log` |
| Apache (errores) | `/var/log/apache2/error.log` | `tail -f /var/log/apache2/error.log` |
| PostgreSQL | `/var/log/postgresql/postgresql-16-main.log` (ruta real del cluster inspeccionado) | `tail -f /var/log/postgresql/postgresql-16-main.log` |
| Moodle (errores PHP en página) | depende de `$CFG->debug` / `$CFG->debugdisplay`, no seteados explícitamente en el `config.php` de referencia (usan el default de Moodle) | habilitar temporalmente vía Site administration → Development → Debugging, o revisar `error.log` de Apache, donde Moodle también escribe errores PHP no capturados |
| Servicios systemd | — | `journalctl -u apache2 -f`, `journalctl -u postgresql -f` |

## 18. Reinicio

```bash
# 1. Detener
sudo systemctl stop apache2
sudo systemctl stop postgresql

# 2. Iniciar de nuevo
sudo systemctl start postgresql
sudo systemctl start apache2

# 3. Verificar dependencias (sección 15)
pg_lsclusters
systemctl is-active apache2 postgresql

# 4. Verificar que no quedó un upgrade de Moodle/plugin pendiente
sudo -u www-data php admin/cli/upgrade.php --non-interactive

# 5. Repetir health checks (sección 15) y smoke test (sección 16)
```

## 19. Troubleshooting

- **`login/index.php` redirige a una URL externa (`http://lms.sena.edu.co`)
  y nunca muestra el formulario de login local.** Esto es real, no un bug:
  el sitio de referencia tiene configurado
  `$CFG->alternateloginurl = 'http://lms.sena.edu.co'` (verificado en
  `mdl_config`), y `login/index.php` (línea 317-318 del core) redirige
  incondicionalmente a esa URL si está definida — no hay parámetro que lo
  evite. Para probar el login localmente:
  ```bash
  sudo -u www-data php admin/cli/cfg.php --name=alternateloginurl --unset
  ```
  y, si se necesita restaurar el valor original después:
  ```bash
  sudo -u www-data php admin/cli/cfg.php --name=alternateloginurl --set="http://lms.sena.edu.co"
  ```
  **Esto modifica configuración compartida de Moodle** (tabla `mdl_config`)
  — hacerlo solo en una BD local de pruebas, nunca contra un `moodle` que
  se comparta con otros.
- **Métodos de autenticación habilitados (`mdl_config.auth = 'email,oidc'`,
  verificado):** `oidc` (SSO contra Azure AD/SENA vía `auth_oidc`, con ~70
  claves de configuración propias en `mdl_config_plugins`) **no es
  reproducible localmente** sin las credenciales reales del IdP — no se
  documentan porque no están en el repo y no deben estarlo (secreto). Para
  QA local, usar cuentas con método `email` (usuario/contraseña estándar de
  Moodle).
- **Puerto ocupado**: si `5433` ya está en uso por otro PostgreSQL local,
  ajustar `$CFG->dboptions['dbport']` en `config.php` para que coincida con
  el puerto real del cluster (`pg_lsclusters`).
- **`integracion` no existe / falla la conexión**: comportamiento esperado
  si no se creó esa BD (sección 6.2, 8.2) — el plugin degrada con gracia
  (try/catch), no debería producir error 500. Si sí lo produce, revisar que
  el error realmente venga de `IntegracionResultadosService` (buscar
  `dml_exception` en `error.log`) antes de asumir que es un problema del
  resto del plugin.
- **Migraciones/upgrade pendiente**: si tras copiar código nuevo del plugin
  Moodle muestra un aviso de "Existen actualizaciones disponibles" en el
  panel de administración, correr `admin/cli/upgrade.php` (sección 14/18).
- **Permisos de `dataroot`**: `/var/www/zajunadata` debe ser escribible por
  el usuario de Apache (`www-data` en el entorno de referencia,
  `directorypermissions = 0777` en `config.php`). Errores de "no se puede
  escribir en dataroot" apuntan a este directorio.
- **Certificados/HTTPS**: no aplica — el entorno real no usa TLS (sección 2,
  4). Si en un entorno distinto sí se requiere, no está cubierto por este
  documento porque no hay evidencia de ello en el repo.
- **Hostname**: no aplica un dominio propio (sección 5); si `wwwroot` local
  no coincide exactamente con la URL desde la que se accede (protocolo,
  host o subpath), Moodle puede fallar al generar enlaces o rechazar la
  sesión — mantenerlos idénticos.
- **CDN de FontAwesome inaccesible**: solo relevante si
  `pix/icons/fontawesome/js/all.min.js` falta del checkout — en condiciones
  normales el bundle está vendorizado y no se depende de internet
  (sección 9).

## 20. Limpieza

Limpieza segura (no destructiva de datos):

```bash
sudo systemctl stop apache2
sudo systemctl stop postgresql
```

Reconstrucción desde cero de la BD **es destructiva** — borra todos los
cursos, usuarios y datos de prueba de esa base. Confirmar antes de correr:

```bash
# ⚠️ DESTRUCTIVO: elimina todos los datos de la BD "moodle" local.
sudo -u postgres psql -c "DROP DATABASE moodle;"
sudo -u postgres psql -c "CREATE DATABASE moodle WITH ENCODING 'UTF8' LC_COLLATE 'es_CO.UTF-8' LC_CTYPE 'es_CO.UTF-8' TEMPLATE template0;"
# Reinstalar Moodle desde cero: sección 14, paso 3a.
```

```bash
# ⚠️ DESTRUCTIVO: elimina archivos subidos, cachés y sesiones de Moodle.
rm -rf /var/www/zajunadata/*
```

Eliminar solo el plugin (deja el resto de Moodle intacto):

```bash
rm -rf <moodle_root>/local/portafolio
# Luego correr admin/cli/upgrade.php para que Moodle detecte la desinstalación.
```

No aplica limpieza de contenedores/volúmenes Docker porque el proyecto no
usa Docker (sección 7).

## 21. Server parity checklist

- [ ] Máquina preparada (PHP 8.2, Apache + `mod_php`, PostgreSQL 16 o el
      motor real del equipo).
- [ ] Moodle 4.3.x instalado (fuera de este repo) o disponible.
- [ ] Plugin clonado en `<moodle_root>/local/portafolio`.
- [ ] `config.php` de Moodle configurado (dbtype/dbhost/dbname/dbport,
      wwwroot, dataroot).
- [ ] Hostname/URL local (`wwwroot`) coincide con la forma real de acceder
      al sitio.
- [ ] Apache sirviendo Moodle en el subpath/URL correcto (no aplica reverse
      proxy separado — es el propio Apache).
- [ ] HTTPS: no aplica en este proyecto (confirmar que no se está
      documentando por error algo que el servidor real no usa).
- [ ] Backend PHP funcionando bajo `mod_php` (no se requiere build).
- [ ] Frontend: no se requiere build (assets planos).
- [ ] PostgreSQL disponible en el puerto configurado en `config.php`.
- [ ] Esquema de Moodle instalado/actualizado
      (`admin/cli/install.php` / `admin/cli/upgrade.php`).
- [ ] Seeds: **no aplican** como paso obligatorio (scripts en `cli/` son
      herramientas de depuración de un solo uso, no parte del deploy).
- [ ] BD externa `integracion`: decidido explícitamente si se reproduce o
      se deja ausente (el plugin funciona sin ella, con RAP vacíos).
- [ ] Aplicación funcionando (`local/portafolio/index.php` carga sin
      errores tras login).
- [ ] Login local probado (con `alternateloginurl` neutralizado si aplica,
      y usando el método `email`, no `oidc`).
- [ ] Logs de Apache/PostgreSQL disponibles y consultables.
- [ ] Aplicación accesible desde la URL configurada
      (`http://localhost/zajuna/...` o el `wwwroot` local elegido).
- [ ] Smoke test (sección 16) completo y exitoso.
- [ ] Reinicio completo probado (sección 18), incluyendo verificación de
      upgrade pendiente tras el reinicio.
