# Deploy local — `mod_imagecarousel` (Zajuna)

> Documento operativo para QA / DevOps.
> Objetivo: levantar en una máquina limpia un entorno que se comporte como el servidor real, no un "modo desarrollo".

**Versión del plugin documentada:** `v0.3.3` — build `2026072300` (`imagecarousel/version.php`)
**Fecha de elaboración:** 2026-08-19
**Rama analizada:** `feature/imagecarousel_Carlos`

---

## 1. Objetivo

Este repositorio **no es una aplicación autónoma**. Es un **módulo de actividad de Moodle** (`mod_imagecarousel`) que se instala dentro de una instalación existente de Moodle, en la ruta `<moodleroot>/mod/imagecarousel`.

Esto está verificado en el código: todos los puntos de entrada arrancan con
`require('../../config.php')` (`view.php:3`, `manage.php:2`, `edit.php:2`, `delete.php:7`, `adding_image.php:12`, `carousel_content.php:9`, `webp-support.php:5`), es decir, dos niveles por encima del directorio del plugin.

Por lo tanto, "desplegar localmente" significa:

1. Provisionar el **host Moodle** con la misma pila que el servidor real (Apache + PHP + PostgreSQL).
2. Instalar Moodle 4.3.x con la misma configuración estructural (subruta `/zajuna`, prefijo `mdl_`).
3. Depositar el plugin en `mod/imagecarousel`.
4. Ejecutar el upgrade de Moodle, que dispara las migraciones y el sembrado de datos del plugin.
5. Verificar con health checks y smoke test **desde el punto de entrada público**, no desde puertos internos.

### 1.1 Sobre Docker (decisión explícita)

**El repositorio no contiene `Dockerfile`, `docker-compose.yml`, `compose.yml`, `package.json`, `composer.json`, ni pipelines de CI/CD** (`.github/workflows`, GitLab CI, Jenkins). Se verificó con una búsqueda exhaustiva del árbol completo.

El servidor real **no usa contenedores**: es Apache 2 ejecutando PHP en proceso, bajo el usuario `www-data` (evidencia: `REPORTE_QA_SEGURIDAD.md:10`, `REPORTE_QA_SEGURIDAD.md:393`).

Por eso **este documento usa la instalación nativa como camino principal**. Contenerizar aquí produciría *menos* paridad con el servidor (cambiaría el modelo de proceso, la propiedad de archivos y la resolución de rutas), y obligaría a inventar archivos que no existen en el repositorio. No se añade Docker.

---

## 2. Arquitectura local

### 2.1 Arquitectura real observada

```
Navegador (cliente)
   │  HTTP :80
   ▼
Apache 2.4  (mod_php 8.2, usuario www-data)   ← ES el servidor web, no un proxy inverso
   │  PHP ejecutado in-process (sin puerto de aplicación separado)
   ▼
Moodle 4.3.x   (docroot: /var/www/zajuna, servido en la subruta /zajuna)
   │
   ├── mod/imagecarousel        ← este repositorio
   │       ├── render embebido en el curso:  lib.php → imagecarousel_cm_info_view()
   │       │      → placeholder + fetch() → carousel_content.php
   │       │      → mod_imagecarousel_render_carousel_content()
   │       │      → templates/carousel.mustache
   │       └── vista individual:  view.php  (ruta de render separada)
   │
   ├── moodledata  (/var/www/zajunadata)   ← archivos, caché, sesiones
   │
   ▼
PostgreSQL 16   :5432 (solo localhost)
   ├── mdl_imagecarousel
   ├── mdl_imagecarousel_images
   └── mdl_config_plugins  ← toggle global de visibilidad del plugin
```

### 2.2 Punto crítico: **no hay proxy inverso separado**

Es importante para QA, porque cambia lo que hay que reproducir:

- Apache **es** el servidor web y **ejecuta PHP dentro de su propio proceso** (módulo `php8.2` cargado: `/etc/apache2/mods-enabled/php8.2.load`).
- **No existe un puerto interno de aplicación** (no hay Node, ni Gunicorn, ni PHP-FPM en puerto separado, ni upstream `proxy_pass`).
- Por lo tanto **no aplica** la sección "evitar que QA acceda al puerto interno": no hay tal puerto. El único punto de entrada es Apache en `:80`.

> ⚠️ **Ambigüedad detectada, sin resolver desde el repositorio.**
> `config.php` del Moodle local contiene `$CFG->sslproxy = false;` con el comentario `// TLS termina en el proxy`. El comentario sugiere que **en producción** podría existir un proxy TLS por delante de Apache, pero el valor está en `false` y no hay ningún archivo de configuración de proxy (Nginx/Traefik/Caddy/HAProxy) en el repositorio ni en la máquina. Ver Anexo A.2 *Información faltante*.

### 2.3 Paridad servidor ↔ local

| Componente | Servidor real | Local objetivo | Fuente |
|---|---|---|---|
| SO | Linux (`www-data`) | Ubuntu 22.04 LTS | `REPORTE_QA_SEGURIDAD.md:10` |
| Servidor web | Apache 2 | Apache 2.4.52 | `REPORTE_QA_SEGURIDAD.md:285,393` |
| Ejecución PHP | mod_php (in-process) | mod_php 8.2 | `mods-enabled/php8.2.load` |
| PHP | 8.2.28 | 8.2.x | `REPORTE_QA_SEGURIDAD.md:284` |
| Moodle | 4.3.x — `2023100903.06` | 4.3.3+ — `2023100903.06` | `REPORTE_QA_SEGURIDAD.md:283` |
| Base de datos | PostgreSQL | PostgreSQL 16 | `REPORTE_QA_SEGURIDAD.md:10` |
| Prefijo de tablas | `mdl_` | `mdl_` | `REPORTE_QA_SEGURIDAD.md:393` |
| Subruta web | `/zajuna` | `/zajuna` | `REPORTE_QA_SEGURIDAD.md:151,394` |
| Protocolo | HTTP (evidencia de prueba) | HTTP | `REPORTE_QA_SEGURIDAD.md:394` |
| Tema | Boost (Bootstrap) | Boost | `manage.php:37`, `adding_image.php:49` |

---

## 3. Requisitos previos

Versiones derivadas del servidor real y de `imagecarousel/version.php`.

| Requisito | Versión | Obligatorio | Motivo |
|---|---|---|---|
| Ubuntu / Debian | 22.04 LTS | Recomendado | Paridad con el servidor |
| Apache | 2.4.x | **Sí** | Servidor web del entorno real |
| PHP | **8.2.x** | **Sí** | Servidor: 8.2.28. Moodle 4.3 no soporta PHP 8.3 |
| PostgreSQL | 13+ (local: 16) | **Sí** | Motor del servidor real |
| Moodle | **4.3.x** | **Sí** | Servidor: `2023100903.06` |
| Git | cualquiera | Sí | Obtener el plugin |
| `unzip` / `rsync` | cualquiera | Sí | Copiar el plugin |

**Versión mínima de Moodle exigida por el plugin:**
```php
// imagecarousel/version.php
$plugin->requires = 2022112800;  // Moodle 4.1
```
El plugin declara compatibilidad desde Moodle 4.1, pero **el entorno de paridad es 4.3.x**. Despliega sobre 4.3.x.

### 3.1 Extensiones PHP

Moodle 4.3 exige: `pgsql`/`pdo_pgsql`, `gd`, `intl`, `mbstring`, `curl`, `zip`, `xml`, `soap`, `iconv`, `simplexml`, `fileinfo`, `tokenizer`, `sodium`, `exif`.

El plugin en sí solo añade una dependencia funcional: **`getimagesize()`** (5 usos, validación de dimensiones de imagen), incluida en el core de PHP.

> **Nota:** el plugin **no** requiere Composer, npm, Node ni ningún gestor de dependencias. No hay `composer.json` ni `package.json` en el repositorio.

---

## 4. Preparación de la máquina

Todos los comandos asumen Ubuntu 22.04 y una máquina limpia. Se ejecutan como usuario con `sudo`.

### 4.1 Instalar la pila

```bash
sudo apt update
sudo apt install -y \
  apache2 \
  php8.2 libapache2-mod-php8.2 \
  php8.2-pgsql php8.2-gd php8.2-intl php8.2-mbstring php8.2-curl \
  php8.2-zip php8.2-xml php8.2-soap \
  postgresql postgresql-contrib \
  git unzip rsync
```

> Si `php8.2` no está en los repositorios de tu Ubuntu, añade el PPA de Ondřej Surý:
> `sudo add-apt-repository ppa:ondrej/php && sudo apt update`

### 4.2 Habilitar módulos de Apache

```bash
sudo a2enmod php8.2 rewrite
sudo systemctl enable --now apache2 postgresql
```

Verificar:
```bash
apache2 -v                       # esperado: Apache/2.4.x
php -v                           # esperado: PHP 8.2.x
psql --version                   # esperado: psql (PostgreSQL) 13+
systemctl is-active apache2      # esperado: active
systemctl is-active postgresql   # esperado: active
apachectl -M | grep -E 'php|rewrite'
```

### 4.3 Ajustes de PHP requeridos por Moodle

Moodle 4.3 exige `max_input_vars >= 5000`. Los valores de referencia tomados del entorno funcionando (`/etc/php/8.2/apache2/php.ini`):

```ini
max_input_vars = 5000
memory_limit = 128M
post_max_size = 1G
upload_max_filesize = 2G
max_execution_time = 30
```

Aplicar:
```bash
sudo sed -i 's/^max_input_vars = .*/max_input_vars = 5000/' /etc/php/8.2/apache2/php.ini
sudo sed -i 's/^memory_limit = .*/memory_limit = 128M/' /etc/php/8.2/apache2/php.ini
sudo sed -i 's/^post_max_size = .*/post_max_size = 1G/' /etc/php/8.2/apache2/php.ini
sudo sed -i 's/^upload_max_filesize = .*/upload_max_filesize = 2G/' /etc/php/8.2/apache2/php.ini
sudo systemctl restart apache2
```

Verificar (los valores efectivos de Apache, no los de CLI):
```bash
php -i | grep -E '^(max_input_vars|upload_max_filesize|post_max_size)'
```

> ⚠️ **Por qué importa para este plugin:** las imágenes se guardan **en Base64 dentro de la base de datos**, no en el filesystem de Moodle. El límite propio del plugin es **5 MB por imagen** (`lib.php:620`, `adding_image.php:226,253`, `edit.php:220`). Un Base64 de 5 MB ocupa ~6.7 MB en el POST. Con `post_max_size = 8M` (default de Ubuntu) las cargas grandes fallan **silenciosamente**. Por eso los valores de arriba son más altos.

---

## 5. Configuración de hostname

### 5.1 Configuración usada por el entorno de referencia

El Moodle de referencia usa:

```php
$CFG->wwwroot = 'http://localhost/zajuna';
```

Es decir: **hostname `localhost`, puerto 80, subruta `/zajuna`**. **No se requiere ninguna entrada en `/etc/hosts`** para el despliegue estándar.

La subruta se resuelve mediante un **symlink** dentro del DocumentRoot:

```
/var/www/html/zajuna  ->  /var/www/zajuna     (propietario: www-data)
```

Y el vhost tiene `Options ... FollowSymLinks` activo desde el bloque global de `/etc/apache2/apache2.conf`:

```apache
<Directory /var/www/>
	Options Indexes FollowSymLinks
	AllowOverride None
	Require all granted
</Directory>
```

> ⛔ **Regla crítica de Moodle:** `$CFG->wwwroot` debe coincidir **exactamente** con la URL que escribes en el navegador (esquema, host, puerto y subruta). Si accedes por `http://127.0.0.1/zajuna` mientras `wwwroot` dice `http://localhost/zajuna`, Moodle te expulsará de la sesión en bucle.

### 5.2 (Opcional) Usar un hostname con nombre

Solo si QA necesita reproducir un acceso por nombre de host en vez de `localhost`. **No es requerido por el proyecto y el repositorio no define ningún dominio.** Si lo haces, hay que cambiar las dos cosas a la vez:

```bash
# 1) /etc/hosts  (elige tú el nombre; aquí un ejemplo)
echo "127.0.0.1  zajuna.local" | sudo tee -a /etc/hosts
```
```php
// 2) /var/www/zajuna/config.php  — debe coincidir con lo anterior
$CFG->wwwroot = 'http://zajuna.local/zajuna';
```
```bash
# 3) purgar cachés tras cambiar wwwroot
sudo -u www-data php /var/www/zajuna/admin/cli/purge_caches.php
```

---

## 6. Variables de entorno

### 6.1 Hallazgo: **este proyecto no usa variables de entorno**

Se buscaron en todo el árbol `.env`, `.env.example`, `.env.template` y **no existen**. El plugin no lee ninguna variable de entorno: no hay llamadas a `getenv()` ni a `$_ENV` en el código.

Toda la configuración vive en el `config.php` de **Moodle** (fuera de este repositorio) y en la tabla `mdl_config_plugins`.

### 6.2 Configuración real de Moodle (`config.php`)

Claves presentes en el entorno de referencia. **Nunca copies credenciales reales a un repositorio ni a este documento.**

| Clave `$CFG->` | Propósito | Obligatoria | Valor local seguro |
|---|---|---|---|
| `dbtype` | Motor de BD | **Sí** | `'pgsql'` |
| `dblibrary` | Driver | **Sí** | `'native'` |
| `dbhost` | Host de BD | **Sí** | `'localhost'` |
| `dbname` | Nombre de BD | **Sí** | `'zajunadb'` |
| `dbuser` | Usuario de BD | **Sí** | *elige uno local* |
| `dbpass` | Contraseña de BD | **Sí** | ⛔ **secreto — genera uno local, nunca reutilices el de producción** |
| `prefix` | Prefijo de tablas | **Sí** | `'mdl_'` (obligatorio para paridad) |
| `dboptions` | Opciones de conexión | Sí (array) | `array('dbpersist'=>0,'dbsocket'=>'','dbport'=>'')` |
| `wwwroot` | URL base | **Sí** | `'http://localhost/zajuna'` |
| `dataroot` | Directorio de datos | **Sí** | `'/var/www/zajunadata'` |
| `admin` | Slug del área admin | Sí | `'admin'` |
| `directorypermissions` | Permisos de dirs creados | No | `0777` (solo local; ver Anexo A.3 *Riesgos*) |
| `php_memory_limit` | Override de memoria | No | *omitir en local* |
| `sslproxy` | TLS termina en proxy externo | No | `false` |
| `slasharguments` | Rutas tipo `file.php/1/x.jpg` | No | `1` |
| `disableipcheck` | Desactiva chequeo de IP de sesión | No | `true` |
| `debug` / `debugdisplay` | Nivel de depuración | No | ver §6.3 |

### 6.3 Diferencia desarrollo vs. servidor

El `config.php` de referencia tiene la depuración **activada**:

```php
$CFG->debug = (E_ALL | E_STRICT);
$CFG->debugdisplay = 1;
```

Esto **no es configuración de producción**. Para un entorno de paridad tipo servidor, mantenlo desactivado y actívalo solo al depurar:

```bash
# activar depuración temporalmente
sudo -u www-data php /var/www/zajuna/admin/cli/cfg.php --name=debug --set=32767
sudo -u www-data php /var/www/zajuna/admin/cli/cfg.php --name=debugdisplay --set=1

# volver a comportamiento tipo servidor
sudo -u www-data php /var/www/zajuna/admin/cli/cfg.php --name=debug --set=0
sudo -u www-data php /var/www/zajuna/admin/cli/cfg.php --name=debugdisplay --set=0
```

### 6.4 Configuración propia del plugin (`mdl_config_plugins`)

El plugin **no tiene página de ajustes** (`settings.php` no existe). Sus dos únicos parámetros se escriben por código y se leen directamente de la BD:

| Nombre | Componente | Sembrado por | Propósito |
|---|---|---|---|
| `Slider_Informativo_Carrusel_Visible` | `mod_imagecarousel` | `db/install.php:32`, `db/upgrade.php:270` | Toggle global `1`/`0`. Con `0`, el carrusel se oculta a todos salvo `is_siteadmin()` |
| `Slider_Informativo_Carrusel_Version` | `mod_imagecarousel` | `db/install.php:31`, `db/upgrade.php:273` | Solo informativo; se sincroniza con `version.php` |

Leído en `lib.php:101`, `lib.php:374` y `carousel_content.php:26` — **con lectura directa a BD, sin caché**.

Gestión por CLI (comandos reales, verificados):
```bash
# leer todos los ajustes del plugin
sudo -u www-data php /var/www/zajuna/admin/cli/cfg.php --component=mod_imagecarousel

# ocultar el carrusel globalmente
sudo -u www-data php /var/www/zajuna/admin/cli/cfg.php \
  --component=mod_imagecarousel --name=Slider_Informativo_Carrusel_Visible --set=0

# volver a mostrarlo
sudo -u www-data php /var/www/zajuna/admin/cli/cfg.php \
  --component=mod_imagecarousel --name=Slider_Informativo_Carrusel_Visible --set=1
```

---

## 7. Dependencias

**No hay paso de instalación de dependencias para este plugin.** No existe `composer.json`, `package.json`, `requirements.txt` ni lockfile alguno.

Las únicas dependencias son de la plataforma anfitriona:

| Dependencia | Origen | Obligatoria | Verificación |
|---|---|---|---|
| Core de Moodle 4.3.x | Instalación anfitriona | **Sí** | `grep release /var/www/zajuna/version.php` |
| `theme_boost` (Bootstrap JS) | Core de Moodle | **Sí** | `ls -d /var/www/zajuna/theme/boost` |
| `core/form-colour` | Core de Moodle | **Sí** | Usado en `adding_image.php:48`, `edit.php:54` |

`$plugin->dependencies = [];` — el plugin **no depende de otros plugins** (`version.php`).

---

## 8. Base de datos

### 8.1 Motor y parámetros

| Parámetro | Valor | Fuente |
|---|---|---|
| Motor | PostgreSQL | `REPORTE_QA_SEGURIDAD.md:10` |
| Versión local | 16.x (mín. 13 para Moodle 4.3) | entorno |
| Host | `localhost` | `config.php` |
| Puerto | `5432` (default) | default PostgreSQL |
| Base de datos | `zajunadb` | `config.php` |
| Prefijo | `mdl_` | `config.php` |
| Usuario | definido en `$CFG->dbuser` | ⛔ no publicar |

### 8.2 Crear la base de datos

```bash
# Crear rol y base. Sustituye <USUARIO> y usa una contraseña local generada, NO la de producción.
sudo -u postgres psql -c "CREATE USER <USUARIO> WITH PASSWORD '<GENERA_UNA_LOCAL>';"
sudo -u postgres psql -c "CREATE DATABASE zajunadb OWNER <USUARIO> ENCODING 'UTF8';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE zajunadb TO <USUARIO>;"
```

Generar una contraseña local:
```bash
openssl rand -base64 24
```

### 8.3 Conectarse y comprobar que funciona

```bash
# conectividad básica
pg_isready -h localhost -p 5432
# esperado: localhost:5432 - accepting connections

# conexión con las credenciales de Moodle (pedirá contraseña)
psql -h localhost -U <USUARIO> -d zajunadb -c "SELECT version();"
```

### 8.4 Instalar Moodle (crea el esquema completo)

Solo en una instalación desde cero. Descarga Moodle **4.3.x** y colócalo en `/var/www/zajuna`.

```bash
sudo mkdir -p /var/www/zajunadata
sudo chown -R www-data:www-data /var/www/zajuna /var/www/zajunadata

sudo -u www-data php /var/www/zajuna/admin/cli/install_database.php \
  --agree-license \
  --adminuser=admin \
  --adminpass='<GENERA_UNA_LOCAL>' \
  --adminemail=admin@example.com \
  --fullname="Zajuna Local" \
  --shortname="ZajunaLocal"
```

> `install_database.php` requiere que `config.php` ya exista con los valores de §6.2.
> Alternativa web: navegar a `http://localhost/zajuna/` y seguir el instalador.

Publicar la subruta `/zajuna` (mecanismo real usado por el entorno de referencia):
```bash
sudo ln -sfn /var/www/zajuna /var/www/html/zajuna
sudo chown -h www-data:www-data /var/www/html/zajuna
```

### 8.5 Migraciones del plugin

**Las migraciones del plugin se ejecutan como parte del upgrade de Moodle** — ver §14.2. No hay comando de migración propio.

| Escenario | Archivo que actúa | Qué hace |
|---|---|---|
| Instalación nueva | `db/install.xml` | Crea `mdl_imagecarousel` (9 campos) y `mdl_imagecarousel_images` (26 campos) |
| Instalación nueva | `db/install.php` | Siembra el toggle de visibilidad en `mdl_config_plugins` |
| Instalación existente | `db/upgrade.php` | Aplica incrementalmente por `$oldversion` |

Pasos de upgrade definidos en `db/upgrade.php` (savepoints reales):

| Savepoint | Cambio |
|---|---|
| `2024040100` | Esquema inicial extendido |
| `2024040101` | Ajuste de campos |
| `2024040200` | Ajuste de campos |
| `2024040300` | Bloque grande de columnas de estilo de texto |
| `2025101503` | `availablefrom` / `availableuntil` (ventana de disponibilidad) |
| `2025121500` | Columna `visible` en `imagecarousel_images` + backfill a `1` |
| `2026072300` | Toggle global en `config_plugins` (fail-open: no pisa un valor ya cambiado) |

**El disparador es `$plugin->version`.** Si subes código sin incrementar `version.php`, **Moodle no ejecutará `upgrade.php`** — riesgo documentado en `REPORTE_QA_SEGURIDAD.md:312`.

### 8.6 Seeds / datos iniciales

No hay seeds de contenido (no se crean cursos ni imágenes de ejemplo). El único sembrado es el de `config_plugins` descrito en §6.4, ejecutado automáticamente por `install.php` / `upgrade.php`.

Los archivos bajo `imagecarousel/pix/banners_sena*/` **no son seeds**: son imágenes de prueba manual (incluyendo casos de error deliberados en `pix/banners_sena/Test Imagenes para error/`). Ver §10.2.

### 8.7 Verificar el esquema del plugin

```bash
# tablas creadas
psql -h localhost -U <USUARIO> -d zajunadb -c "\dt mdl_imagecarousel*"
# esperado: mdl_imagecarousel, mdl_imagecarousel_images

# columnas de la ventana de disponibilidad
psql -h localhost -U <USUARIO> -d zajunadb -c \
  "SELECT column_name FROM information_schema.columns
   WHERE table_name='mdl_imagecarousel'
     AND column_name IN ('availablefrom','availableuntil');"

# columna visible por imagen
psql -h localhost -U <USUARIO> -d zajunadb -c \
  "SELECT column_name FROM information_schema.columns
   WHERE table_name='mdl_imagecarousel_images' AND column_name='visible';"

# módulo registrado en Moodle
psql -h localhost -U <USUARIO> -d zajunadb -c \
  "SELECT id, name, visible FROM mdl_modules WHERE name='imagecarousel';"

# toggle global sembrado
psql -h localhost -U <USUARIO> -d zajunadb -c \
  "SELECT name, value FROM mdl_config_plugins WHERE plugin='mod_imagecarousel';"
```

---

## 9. Servicios auxiliares

**Ninguno es requerido.**

Se auditó el código en busca de Redis, RabbitMQ, Kafka, Elasticsearch, MongoDB, MinIO y SMTP. **El plugin no usa ninguno.** No hay clientes, ni configuración, ni referencias.

| Servicio | ¿Requerido? | Nota |
|---|---|---|
| Redis / Memcached | **No** | Moodle usa su caché de archivos por defecto, dentro de `$CFG->dataroot` |
| Colas (RabbitMQ / Kafka) | **No** | No hay procesamiento asíncrono |
| Almacenamiento de objetos | **No** | Las imágenes van en Base64 **dentro de PostgreSQL** |
| SMTP | **No** para el plugin | Moodle lo puede necesitar para correo, pero el plugin no envía correo |
| Cron de Moodle | **No** para el plugin | `$plugin->cron = 0;` — el plugin no declara tareas programadas. Moodle como plataforma sí requiere cron; ver §13.2 |

---

## 10. Build

### 10.1 No hay paso de build

Confirmado por inspección:

- **No hay compilación de backend.** PHP se interpreta directamente.
- **No hay compilación de frontend.** Las vistas son plantillas Mustache renderizadas en servidor (`templates/carousel.mustache`), y `styles.css` se sirve tal cual.
- **No hay build de AMD/Grunt necesario.** Existe `amd/src/load_styles.js`, pero:
  - **no existe `amd/build/`**, y
  - **ningún archivo lo carga**: no hay `js_call_amd('mod_imagecarousel/load_styles', ...)` en ninguna parte del plugin.

  Es decir, **`amd/src/load_styles.js` es código muerto**. No hace falta ejecutar Grunt. La inicialización real del carrusel viene de `theme_boost/bootstrap` (`manage.php:37`, `adding_image.php:49`, `edit.php:55`) y de JS inline generado en `lib.php:401`.

El único "artefacto" es el propio directorio del plugin copiado a su sitio.

### 10.2 Qué copiar (y qué NO copiar)

⚠️ **Hallazgo de QA.** El directorio `imagecarousel/` pesa ~31 MB, de los cuales solo una fracción es plugin. Copiarlo tal cual publica en el servidor web material que no debería estar ahí:

| Ruta | Tamaño | ¿Desplegar? | Motivo |
|---|---|---|---|
| `.scannerwork/` | 3.1 MB | ❌ **No** | Artefactos del análisis de SonarCloud |
| `pix/banners_sena*/` | 27 MB | ❌ **No** | Imágenes de prueba manual, incluidas imágenes de error deliberadas |
| `docs/` | 392 KB | ❌ **No** | Documentación interna (`.docx`, informes) |
| `*.md`, `*.doc` en raíz del plugin | — | ❌ **No** | Informes internos |
| `sonar-project.properties` | — | ❌ **No** | Configuración de análisis |
| Resto (`*.php`, `amd/`, `classes/`, `db/`, `lang/`, `templates/`, `styles.css`, `pix/*.svg`, `pix/*.png`) | — | ✅ **Sí** | Código del plugin y sus iconos |

> `pix/` **sí** debe existir: contiene los iconos del módulo (`icon.svg`, `monologo.svg`). Lo que se excluye son los subdirectorios `banners_sena*` de imágenes de prueba.

---

## 11. Reverse proxy / Web server

Como se explicó en §2.2, **Apache es el servidor web y no hay proxy inverso**. No hay `proxy_pass` que configurar ni upstream que apuntar.

### 11.1 Virtual host (configuración real del entorno de referencia)

`/etc/apache2/sites-enabled/000-default.conf`:

```apache
<VirtualHost *:80>
    ServerName localhost

    DocumentRoot /var/www/html
    <Directory /var/www/zajuna>
        AllowOverride FileInfo
        Require all granted
    </Directory>
    ErrorLog ${APACHE_LOG_DIR}/reposena_error.log
    CustomLog ${APACHE_LOG_DIR}/reposena_access.log combined
</VirtualHost>
```

Notas sobre esta configuración:

- **Puerto de entrada: 80.** Es el único puerto público.
- **DocumentRoot es `/var/www/html`**, no el directorio de Moodle. Moodle se alcanza en la subruta `/zajuna` a través del **symlink** `/var/www/html/zajuna -> /var/www/zajuna` (§5.1).
- El bloque `<Directory /var/www/zajuna>` concede acceso al destino real del symlink. `FollowSymLinks` viene heredado del bloque global `<Directory /var/www/>` de `apache2.conf`.
- `AllowOverride FileInfo` permite los `.htaccess` que Moodle coloca en algunas rutas.
- **Los nombres de log son personalizados**: `reposena_error.log` / `reposena_access.log`. Úsalos en §17.

### 11.2 Aplicar y validar

```bash
sudo apachectl configtest     # esperado: Syntax OK
sudo systemctl reload apache2
```

### 11.3 Archivos estáticos

No hay directorio de estáticos servido aparte. Todo (CSS, imágenes de iconos) se sirve desde el árbol de Moodle por Apache. `styles.css` se inyecta vía la API de Moodle:

```php
// manage.php:480
$PAGE->requires->css(new moodle_url('/mod/imagecarousel/styles.css'));
```

Las imágenes del carrusel **no se sirven como archivos**: se emiten inline como `data:image/...;base64,...` desde `lib.php` (~líneas 144-232). Existe además `mod_imagecarousel_pluginfile()` (`lib.php:437`) para el filearea `images`, que sí usa `send_stored_file()` con caché de 86400 s.

---

## 12. HTTP / HTTPS

**El entorno documentado usa HTTP, no HTTPS. No se configura TLS localmente.**

Justificación desde el repositorio y la configuración:

- `$CFG->wwwroot = 'http://localhost/zajuna';` — esquema `http`.
- `$CFG->sslproxy = false;`
- El vhost solo declara `<VirtualHost *:80>`; no hay `*:443`, ni `SSLEngine`, ni certificados.
- La evidencia de prueba contra el servidor real usa HTTP: `http://10.217.78.124/zajuna/login/index.php` (`REPORTE_QA_SEGURIDAD.md:394`).

> **Contradicción registrada.** `REPORTE_QA_SEGURIDAD.md:151` afirma *"El servidor usa HTTPS implícito mediante Apache"*, pero la propia prueba de ese mismo informe (línea 395) se ejecuta sobre HTTP, y `sslproxy` está en `false`. Aplicando la regla de "la configuración que realmente ejecuta el sistema manda", **este documento asume HTTP**. Ver Anexo A.2.

**No inventes certificados ni actives HTTPS local** sin confirmar antes con el equipo de infraestructura cuál es el terminador TLS real (ver Anexo A.2 *Información faltante*). Si se confirma que existe, el cambio local sería `$CFG->sslproxy = true` **más** un terminador TLS por delante — no un `SSLEngine` en este mismo vhost.

---

## 13. Frontend

### 13.1 Cómo se sirve realmente

No hay SPA, ni SSR de Node, ni bundle. El frontend es **HTML renderizado en servidor por PHP**, con dos rutas de render distintas — y **no son equivalentes** (`docs/CONTEXTO_TECNICO_IMAGECAROUSEL.md`):

**Ruta A — carrusel embebido en la página del curso (la ruta principal):**

1. `imagecarousel_cm_info_view()` (`lib.php:366`) emite un `<div>` placeholder + un `<script>` inline.
2. Ese script hace `fetch()` a `carousel_content.php?cmid=<id>&sesskey=<sesskey>` con `credentials: 'same-origin'`.
3. `carousel_content.php` valida sesskey, login y capacidad `mod/imagecarousel:view`, y responde HTML con cabeceras anti-caché:
   ```php
   header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
   ```
4. El HTML sale de `mod_imagecarousel_render_carousel_content()` → `templates/carousel.mustache`.

> Esta indirección por AJAX es deliberada: evita la caché de `coursemodinfo` de Moodle, para que cambios de orden/visibilidad se vean con un F5.

**Ruta B — vista individual del módulo:** `view.php` construye el HTML por su propio camino.

### 13.2 Comportamiento del carrusel

Lo aporta **Bootstrap del tema Boost**, cargado con `$PAGE->requires->js_call_amd('theme_boost/bootstrap', 'init')`. El plugin no incluye ninguna librería JS propia.

Intervalo de rotación fijado en el servidor: `'interval' => 5000` (`lib.php:347`).

### 13.3 Verificación

No hay comando de build que ejecutar. Para verificar el frontend:

```bash
# el CSS debe responder 200 desde el punto de entrada público
curl -sI http://localhost/zajuna/mod/imagecarousel/styles.css | head -1
# esperado: HTTP/1.1 200 OK
```

---

## 14. Backend

### 14.1 Runtime y modelo de proceso

| Aspecto | Valor |
|---|---|
| Runtime | PHP 8.2.x |
| Modelo | `mod_php` dentro de Apache (**no** hay proceso ni puerto separado) |
| Usuario | `www-data` |
| Host/interfaz | La de Apache: `*:80` |
| Comando de build | **Ninguno** |
| Comando de arranque | `sudo systemctl start apache2` |

> Sobre "escuchar en `0.0.0.0`": **no aplica**. No hay servidor de aplicación propio que enlazar. Quien escucha es Apache, y su enlace se define en `/etc/apache2/ports.conf` (`Listen 80`), que ya escucha en todas las interfaces.

### 14.2 Instalar el plugin y ejecutar el upgrade

Este es el paso central del despliegue. **Ejecutar en orden.**

```bash
# 0) Definir rutas
MOODLE_ROOT=/var/www/zajuna
REPO=/home/vboxuser/Documents/ZAJUNA/Anuncios/anuncios_del_curso

# 1) Modo mantenimiento (equivalente a lo que se hace en el servidor)
sudo -u www-data php $MOODLE_ROOT/admin/cli/maintenance.php --enable

# 2) Copiar el plugin, excluyendo lo que no debe publicarse (§10.2)
sudo rsync -a --delete \
  --exclude='.scannerwork/' \
  --exclude='docs/' \
  --exclude='pix/banners_sena*/' \
  --exclude='*.md' \
  --exclude='*.doc' \
  --exclude='sonar-project.properties' \
  "$REPO/imagecarousel/" "$MOODLE_ROOT/mod/imagecarousel/"

# 3) Propiedad y permisos (el servidor real corre como www-data)
sudo chown -R www-data:www-data $MOODLE_ROOT/mod/imagecarousel
sudo find $MOODLE_ROOT/mod/imagecarousel -type d -exec chmod 755 {} \;
sudo find $MOODLE_ROOT/mod/imagecarousel -type f -exec chmod 644 {} \;

# 4) Comprobar sintaxis antes de dejar que Moodle lo cargue
find $MOODLE_ROOT/mod/imagecarousel -name '*.php' -exec php -l {} \; | grep -v 'No syntax errors' || echo "PHP OK - 0 errores"

# 5) Ejecutar el upgrade: aquí corren install.xml / install.php / upgrade.php
sudo -u www-data php $MOODLE_ROOT/admin/cli/upgrade.php --non-interactive

# 6) Purgar cachés (obligatorio: cadenas de idioma y plantillas)
sudo -u www-data php $MOODLE_ROOT/admin/cli/purge_caches.php

# 7) Salir de mantenimiento
sudo -u www-data php $MOODLE_ROOT/admin/cli/maintenance.php --disable
```

> **Nota sobre permisos:** en la máquina de referencia el plugin quedó como `root:root`, lo que funciona en lectura pero se desvía del servidor (`www-data`). El paso 3 corrige esa desviación. Ver Anexo A.3 *Riesgos*.

### 14.3 Cron de Moodle (nivel plataforma)

El plugin declara `$plugin->cron = 0;` y no registra tareas programadas, así que **no necesita cron para funcionar**. Moodle como plataforma sí lo requiere para tareas generales:

```bash
sudo -u www-data php /var/www/zajuna/admin/cli/cron.php
```

---

## 15. Process manager

**No hay process manager de aplicación, ni en el servidor real ni localmente.** No existen unidades `systemd` propias, ni Supervisor, ni PM2, ni Gunicorn/uWSGI — nada de eso aplica a un plugin PHP servido por mod_php.

Los procesos administrados son los **servicios del sistema**, y esos ya cubren el requisito de "no depender de terminales abiertas":

```bash
sudo systemctl enable --now apache2      # servidor web + runtime PHP
sudo systemctl enable --now postgresql   # base de datos
```

Comprobar que arrancan solos tras un reinicio:
```bash
systemctl is-enabled apache2 postgresql
# esperado: enabled / enabled
```

Para el cron de Moodle, el mecanismo administrado estándar es una entrada de crontab del usuario del servidor web (opcional en QA):
```bash
# ver el crontab de www-data (no lo edites si no lo necesitas)
sudo crontab -u www-data -l
```

---

## 16. Inicio del entorno

Secuencia completa desde cero, en orden de dependencias:

```bash
# 1) Base de datos primero
sudo systemctl start postgresql
pg_isready -h localhost -p 5432

# 2) Servidor web + PHP
sudo systemctl start apache2
systemctl is-active apache2

# 3) Comprobar que Moodle responde en el punto de entrada público
curl -sI http://localhost/zajuna/ | head -1
# esperado: 2xx o 3xx (la raíz redirige al login; en la referencia: 302)
```

Si Moodle detecta un upgrade pendiente, el sitio quedará bloqueado hasta ejecutar §14.2 pasos 5-6.

---

## 17. Verificación (health checks)

> **El plugin no expone ningún endpoint de health check propio.** No se inventa ninguno. Lo que sigue son los chequeos reales de Moodle y del sistema, verificados como existentes en esta instalación.

### 17.1 Nivel servicio

```bash
systemctl is-active apache2       # esperado: active
systemctl is-active postgresql    # esperado: active
sudo apachectl configtest         # esperado: Syntax OK
pg_isready -h localhost -p 5432   # esperado: accepting connections
```

### 17.2 Nivel base de datos

```bash
# esquema de Moodle íntegro
sudo -u www-data php /var/www/zajuna/admin/cli/check_database_schema.php
# esperado: no reporta discrepancias

# esquema del plugin (ver §8.7 para las consultas completas)
psql -h localhost -U <USUARIO> -d zajunadb -c "\dt mdl_imagecarousel*"
```

### 17.3 Nivel aplicación (Moodle)

```bash
# chequeos de salud del núcleo de Moodle (script real: admin/cli/checks.php)
sudo -u www-data php /var/www/zajuna/admin/cli/checks.php

# el script acepta conjuntos de chequeos: status (default), security, performance
sudo -u www-data php /var/www/zajuna/admin/cli/checks.php --type=security
sudo -u www-data php /var/www/zajuna/admin/cli/checks.php --type=performance
```

Equivalente web: `http://localhost/zajuna/admin/environment.php` (requiere sesión de administrador).

> **Nota sobre la salida CLI.** Si el Moodle anfitrión tiene otros plugins locales instalados, éstos pueden imprimir líneas propias antes de la salida del script. En el entorno de referencia, por ejemplo, `blocks/portaapre` antepone `[Portaapre Bootstrap] Autoloader PSR-4 registrado` a **toda** ejecución CLI. Es ruido esperable, no un fallo. Ver Anexo A.3 *Riesgos*.

### 17.4 Nivel plugin

```bash
# versión instalada según la BD de Moodle
psql -h localhost -U <USUARIO> -d zajunadb -c \
  "SELECT name, value FROM mdl_config WHERE name LIKE '%imagecarousel%';"

# módulo registrado y activo
psql -h localhost -U <USUARIO> -d zajunadb -c \
  "SELECT id, name, visible FROM mdl_modules WHERE name='imagecarousel';"
# esperado: visible = 1

# toggle global del plugin
sudo -u www-data php /var/www/zajuna/admin/cli/cfg.php --component=mod_imagecarousel
# esperado: Slider_Informativo_Carrusel_Visible = 1
#           Slider_Informativo_Carrusel_Version = 2026072300
```

### 17.5 Nivel servidor web (entrada pública)

```bash
curl -sI http://localhost/zajuna/login/index.php | head -1
# esperado: una respuesta 2xx o 3xx (NO 000, 404 ni 5xx).
# En el entorno de referencia devuelve 303 (redirección de autenticación).

curl -sI http://localhost/zajuna/mod/imagecarousel/styles.css | head -1
# esperado: HTTP/1.1 200 OK
```

---

## 18. Smoke test

**Todo el smoke test se ejecuta desde el punto de entrada público `http://localhost/zajuna`.** No se accede a ningún puerto interno (no existe uno).

### 18.1 Automatizable (CLI)

```bash
BASE=http://localhost/zajuna

# 1) La aplicación responde
curl -s -o /dev/null -w "login: %{http_code}\n" $BASE/login/index.php     # 2xx o 3xx (referencia: 303)

# 2) Los estáticos del plugin se sirven
curl -s -o /dev/null -w "css:   %{http_code}\n" $BASE/mod/imagecarousel/styles.css  # 200

# 3) El backend habla con la base de datos
#    (checks.php falla si la BD no responde)
sudo -u www-data php /var/www/zajuna/admin/cli/checks.php >/dev/null && echo "db+app: OK"

# 4) Control de acceso activo: carousel_content.php exige sesskey.
#    Sin sesión ni sesskey NO debe devolver contenido del carrusel.
curl -s -o /dev/null -w "content sin sesskey: %{http_code}\n" "$BASE/mod/imagecarousel/carousel_content.php?cmid=1"
```

> Sobre el punto 4: `carousel_content.php:13` llama a `require_sesskey()` antes de cualquier otra cosa, y después `require_login()` y `require_capability('mod/imagecarousel:view', ...)`. Un usuario anónimo **no** debe recibir HTML de carrusel. Moodle 4.3 responde **404** (no 403) a fallos de `require_capability` — comportamiento estándar documentado en `REPORTE_QA_SEGURIDAD.md:61`.

### 18.2 Funcional (navegador) — funcionalidades que realmente existen

Ejecutar en `http://localhost/zajuna`, con un usuario con rol `editingteacher` o `manager` en un curso.

| # | Paso | Resultado esperado | Respaldo en código |
|---|---|---|---|
| 1 | Iniciar sesión | Redirige a `/zajuna/my/` | `REPORTE_QA_SEGURIDAD.md:302` |
| 2 | En un curso, *Añadir una actividad* → **Carrusel de imágenes** | El módulo aparece en el selector | `db/access.php` → `addinstance` |
| 3 | Guardar con nombre; dejar Disponibilidad vacía | Instancia creada; carrusel visible en la página del curso | `imagecarousel_add_instance()` `lib.php:11` |
| 4 | Abrir `manage.php?id=<cmid>` desde el botón *Gestionar imágenes* | Página de gestión visible | `manage.php:19` capacidad `manageitems` |
| 5 | Añadir imagen (`adding_image.php`) con un JPG/PNG/WebP **< 5 MB** | Se guarda y aparece en el carrusel | límite en `lib.php:620` |
| 6 | Subir un archivo **> 5 MB** | Error de validación, no se guarda | `lib.php:635` |
| 7 | Editar la imagen (`edit.php`): texto, color, posición, URL | Los cambios se reflejan al refrescar (F5) | `mod_imagecarousel_invalidate_caches()` `lib.php:78` |
| 8 | Cambiar orden / marcar `visible=0` en una imagen | El carrusel refleja el cambio con F5, sin purgar cachés a mano | ruta AJAX §13.1 |
| 9 | Poner `availablefrom` en el **futuro**, salir de modo edición, ver como estudiante | El carrusel **no** se muestra | `lib.php:107`, `lib.php:381` |
| 10 | Poner `availableuntil` en el **pasado** | El carrusel **no** se muestra | `lib.php:110`, `lib.php:385` |
| 11 | Con `availableuntil < availablefrom` | El formulario muestra error de validación | `REPORTE_QA_SEGURIDAD.md:48` |
| 12 | Apagar el toggle global (§6.4, `--set=0`) y recargar como no-admin | El carrusel desaparece; un `siteadmin` **sí** lo sigue viendo | `lib.php:101`, `carousel_content.php:26` |
| 13 | Volver a encender el toggle (`--set=1`) | El carrusel reaparece | idem |
| 14 | Como estudiante, abrir `manage.php?id=<cmid>` | **Bloqueado** (HTTP 404 con `nopermissions`) | `REPORTE_QA_SEGURIDAD.md:57` |
| 15 | Como estudiante, abrir `view.php?id=<cmid>` | Carrusel visible | `db/access.php` → `view` para `student` |
| 16 | `delete.php?id=<cmid>&imageid=<id>` | Pide confirmación antes de borrar | `delete.php:9` `$confirm` |

**Criterio de aprobación:** los 16 pasos con el resultado esperado, sin errores en `reposena_error.log` (§19).

---

## 19. Logs

Los nombres de archivo son los **realmente configurados** en el vhost (§11.1), no los de Apache por defecto.

| Origen | Comando |
|---|---|
| Apache — errores (incluye errores y `error_log()` de PHP) | `sudo tail -f /var/log/apache2/reposena_error.log` |
| Apache — accesos | `sudo tail -f /var/log/apache2/reposena_access.log` |
| PostgreSQL | `sudo tail -f /var/log/postgresql/postgresql-16-main.log` |
| Servicio Apache (systemd) | `sudo journalctl -u apache2 -f` |
| Servicio PostgreSQL (systemd) | `sudo journalctl -u postgresql -f` |
| Moodle — errores en pantalla | Requiere `$CFG->debugdisplay = 1` (§6.3) |
| Moodle — log de actividad | Web: *Administración del sitio → Informes → Registros* |

**Filtrar solo lo del plugin:**
```bash
sudo grep -i imagecarousel /var/log/apache2/reposena_error.log | tail -50
```

> ⚠️ **Advertencia de ruido.** El plugin escribe **mucho** con `error_log()` en la ruta normal, no solo en fallos: registra cada imagen procesada, incluyendo la longitud del Base64 (30 llamadas solo en `lib.php`, p. ej. `lib.php:258`, `lib.php:341`, y todo `mod_imagecarousel_pluginfile()`, `lib.php:437`). En un entorno con varios carruseles esto llena rápido `reposena_error.log`. Está señalado como riesgo en `REPORTE_QA_SEGURIDAD.md:242`. Vigila el espacio en disco durante sesiones largas de QA.

---

## 20. Reinicio del entorno

Simula un reinicio del servidor y revalida.

```bash
# 1) Detener (orden inverso a las dependencias)
sudo systemctl stop apache2
sudo systemctl stop postgresql

# 2) Arrancar (base de datos primero)
sudo systemctl start postgresql
sudo systemctl start apache2

# 3) Verificar dependencias
systemctl is-active postgresql apache2      # esperado: active / active
pg_isready -h localhost -p 5432

# 4) Verificar que no quedan migraciones pendientes
#    (en dry-run: si no hay nada pendiente, no aplica cambios)
sudo -u www-data php /var/www/zajuna/admin/cli/upgrade.php --non-interactive
sudo -u www-data php /var/www/zajuna/admin/cli/check_database_schema.php

# 5) Health checks (§17)
sudo -u www-data php /var/www/zajuna/admin/cli/checks.php

# 6) Smoke test (§18.1) y luego §18.2
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/zajuna/login/index.php   # 2xx o 3xx
```

Prueba de arranque real tras reinicio de la máquina:
```bash
systemctl is-enabled apache2 postgresql   # ambos deben decir: enabled
```

---

## 21. Troubleshooting

Problemas deducidos de la configuración y el código de este proyecto.

### El puerto 80 está ocupado
```bash
sudo ss -tlnp | grep ':80'
```
Otro servicio (Nginx, otro Apache) tiene el puerto. Deténlo o cámbialo. Si cambias el puerto de Apache debes actualizar `$CFG->wwwroot` **y** purgar cachés (§5.1).

### ⚠️ El login local redirige a un servidor EXTERNO (`lms.sena.edu.co`)

**Comportamiento observado en el entorno de referencia**, y una trampa seria para QA:

```bash
curl -sI http://localhost/zajuna/login/index.php | grep -iE '^(HTTP|location)'
# HTTP/1.1 303 See Other
# Location: http://lms.sena.edu.co
```

El login local **rebota al LMS de producción**. Si no lo detectas, acabarás autenticándote y probando **contra producción** creyendo que estás en local.

La causa no está en `login/index.php` (el archivo no contiene esa URL); lo más probable es el ajuste `alternateloginurl` guardado en `mdl_config`, o el mecanismo de autenticación externo cuyo residuo se ve en `admin/cli/upgrade.php.broken-bffauth-backup-20260722`. Comprobar y neutralizar en local:

```bash
# ver el valor actual
sudo -u www-data php /var/www/zajuna/admin/cli/cfg.php --name=alternateloginurl

# vaciarlo para que el login local sea el de Moodle
sudo -u www-data php /var/www/zajuna/admin/cli/cfg.php --name=alternateloginurl --set=''
sudo -u www-data php /var/www/zajuna/admin/cli/purge_caches.php
```

Tras el cambio, `login/index.php` debe devolver **200** y mostrar el formulario de Moodle. Si sigue redirigiendo, revisa los plugins de autenticación activos en *Administración del sitio → Plugins → Autenticación*.

> Confirma con el equipo antes de tocarlo si el entorno de referencia se comparte con alguien más.

### Bucle de login / sesión que se pierde
`$CFG->wwwroot` no coincide con la URL del navegador. Compara ambos exactamente (esquema, host, puerto, subruta `/zajuna`). Corrige `config.php` y purga cachés.

### `http://localhost/zajuna` da 404
El symlink falta o Apache no sigue symlinks.
```bash
ls -la /var/www/html/zajuna              # debe apuntar a /var/www/zajuna
grep -A3 "<Directory /var/www/>" /etc/apache2/apache2.conf   # debe incluir FollowSymLinks
```

### "Base de datos no disponible" / Moodle no arranca
```bash
pg_isready -h localhost -p 5432
sudo systemctl status postgresql
psql -h localhost -U <USUARIO> -d zajunadb -c "SELECT 1;"
```
Revisa `dbhost`, `dbname`, `dbuser`, `dbpass` y `prefix` en `config.php`.

### Migraciones pendientes / el sitio pide actualizar
```bash
sudo -u www-data php /var/www/zajuna/admin/cli/upgrade.php --non-interactive
sudo -u www-data php /var/www/zajuna/admin/cli/purge_caches.php
```

### Cambié código del plugin pero Moodle no ejecuta `upgrade.php`
Moodle solo dispara las migraciones si **`$plugin->version` aumenta**. Si cambiaste el esquema sin incrementar la versión, el upgrade no corre. Incrementa `version.php` y repite §14.2. (Riesgo documentado en `REPORTE_QA_SEGURIDAD.md:312`.)

### Aparecen marcadores `[[availability]]`, `[[manageimages]]` o similares
Falta una cadena de idioma o hay caché vieja.
```bash
sudo -u www-data php /var/www/zajuna/admin/cli/purge_caches.php
grep -c "manageimages" /var/www/zajuna/mod/imagecarousel/lang/es/imagecarousel.php
```
Si tu sitio usa una variante de idioma (`es_mx`), añade las claves en `lang/<variante>/` o usa Personalización de idioma.

### Las imágenes no aparecen en el carrusel
Recuerda que se guardan en **Base64 dentro de la BD**, no como archivos.
```bash
psql -h localhost -U <USUARIO> -d zajunadb -c \
  "SELECT id, carouselid, visible, sortorder,
          length(desktop_image) AS desktop_len,
          length(mobile_image)  AS mobile_len
   FROM mdl_imagecarousel_images ORDER BY id DESC LIMIT 10;"
```
Si `desktop_len` y `mobile_len` son `NULL` o `0`, la carga falló: revisa `post_max_size` / `upload_max_filesize` (§4.3) y el límite de 5 MB del plugin.

### Subir una imagen falla en silencio
Casi siempre son los límites de PHP. El POST lleva Base64 (~33% más grande que el archivo).
```bash
php -i | grep -E '^(post_max_size|upload_max_filesize|memory_limit|max_execution_time)'
```
Aplica los valores de §4.3 y reinicia Apache.

### Errores de permisos al guardar
```bash
ls -ld /var/www/zajunadata                     # debe ser propiedad de www-data
ls -ld /var/www/zajuna/mod/imagecarousel       # debe ser propiedad de www-data
sudo chown -R www-data:www-data /var/www/zajuna/mod/imagecarousel /var/www/zajunadata
```

### El carrusel no se muestra a nadie (pero sí al administrador)
Es el toggle global. Compruébalo:
```bash
sudo -u www-data php /var/www/zajuna/admin/cli/cfg.php --component=mod_imagecarousel
```
Si `Slider_Informativo_Carrusel_Visible` es `0`, solo `is_siteadmin()` ve el carrusel (`lib.php:101`). Ponlo a `1`.

### El carrusel no se muestra a nadie, incluido el admin, fuera de modo edición
Es la ventana de disponibilidad.
```bash
psql -h localhost -U <USUARIO> -d zajunadb -c \
  "SELECT id, name,
          to_timestamp(availablefrom)  AS desde,
          to_timestamp(availableuntil) AS hasta
   FROM mdl_imagecarousel;"
```
`0` significa "sin restricción". Verifica también la zona horaria del sitio: *Administración del sitio → Servidor → Ubicación*.

### El carrusel no rota / no responde a los controles
Bootstrap del tema no cargó. Abre la consola del navegador y busca `Bootstrap no disponible`. Confirma que el sitio usa el tema **Boost** (`ls -d /var/www/zajuna/theme/boost`).

### Los cambios de orden/visibilidad no se ven
La ruta AJAX ya evita la caché (`carousel_content.php` emite `Cache-Control: no-store`). Si aun así persiste, es caché del navegador o un proxy intermedio: recarga forzada (Ctrl+Shift+R) y, si hace falta:
```bash
sudo -u www-data php /var/www/zajuna/admin/cli/purge_caches.php
```

### El disco se llena durante QA
Ver la advertencia de §19: el plugin registra en `error_log()` en la ruta normal.
```bash
du -sh /var/log/apache2/reposena_error.log
sudo truncate -s 0 /var/log/apache2/reposena_error.log   # vacía el log (no borra el archivo)
```

---

## 22. Limpieza

### 22.1 Limpieza segura (no destruye datos)

```bash
# Detener servicios
sudo systemctl stop apache2
sudo systemctl stop postgresql

# Purgar cachés de Moodle (regenerables)
sudo -u www-data php /var/www/zajuna/admin/cli/purge_caches.php

# Vaciar logs
sudo truncate -s 0 /var/log/apache2/reposena_error.log
sudo truncate -s 0 /var/log/apache2/reposena_access.log
```

### 22.2 Desinstalar solo el plugin

`uninstall_plugins.php` corre en **dry-run** salvo que pases `--run`. Úsalo primero sin `--run`.

```bash
# Simulación: muestra qué haría, sin tocar nada
sudo -u www-data php /var/www/zajuna/admin/cli/uninstall_plugins.php --plugins=mod_imagecarousel
```

> ⚠️ **ADVERTENCIA — DESTRUCTIVO.** El comando siguiente **elimina permanentemente** las tablas `mdl_imagecarousel` y `mdl_imagecarousel_images`, con **todos los carruseles y todas las imágenes** (que viven dentro de la BD, no en disco). **No es reversible sin un backup.**
>
> Haz backup antes:
> ```bash
> pg_dump -h localhost -U <USUARIO> -d zajunadb \
>   -t mdl_imagecarousel -t mdl_imagecarousel_images \
>   > ~/backup_imagecarousel_$(date +%Y%m%d_%H%M).sql
> ```
> Y solo entonces:
> ```bash
> sudo -u www-data php /var/www/zajuna/admin/cli/uninstall_plugins.php \
>   --plugins=mod_imagecarousel --run
> sudo rm -rf /var/www/zajuna/mod/imagecarousel
> sudo -u www-data php /var/www/zajuna/admin/cli/purge_caches.php
> ```

### 22.3 Reconstruir desde cero

> ⚠️ **ADVERTENCIA — DESTRUCTIVO E IRREVERSIBLE.** Lo siguiente **borra la base de datos completa de Moodle y todos los archivos subidos al sitio** (cursos, usuarios, imágenes — todo). Solo para un entorno local desechable. **Nunca en un servidor compartido o de producción.** Haz backup completo primero:
> ```bash
> pg_dump -h localhost -U <USUARIO> -d zajunadb > ~/zajunadb_full_$(date +%Y%m%d_%H%M).sql
> sudo tar czf ~/zajunadata_$(date +%Y%m%d_%H%M).tar.gz /var/www/zajunadata
> ```

```bash
# Confirma que estás en la máquina local correcta antes de continuar
hostname; echo "BD objetivo: zajunadb"

sudo systemctl stop apache2

# Eliminar base de datos y datos del sitio
sudo -u postgres psql -c "DROP DATABASE IF EXISTS zajunadb;"
sudo rm -rf /var/www/zajunadata
sudo mkdir -p /var/www/zajunadata
sudo chown -R www-data:www-data /var/www/zajunadata

# Recrear la BD y reinstalar desde §8.2 → §8.4 → §14.2
```

### 22.4 Volúmenes / contenedores

**No aplica.** No hay Docker en este proyecto (§1.1), por tanto no hay contenedores ni volúmenes que limpiar.

---

## 23. Server parity checklist

Marca cada punto antes de dar por bueno el entorno.

- [ ] **Máquina preparada.** Ubuntu 22.04; `apache2 -v` → 2.4.x; `php -v` → 8.2.x; `psql --version` → 13+.
- [ ] **Dependencias instaladas.** Extensiones PHP de §3.1 presentes (`php -m`). *No hay dependencias de Composer/npm que instalar.*
- [ ] **Variables de entorno configuradas.** *No aplica: el proyecto no usa `.env`.* En su lugar: `config.php` con las claves de §6.2, y `prefix = 'mdl_'`.
- [ ] **Hostname local configurado.** `$CFG->wwwroot` coincide exactamente con la URL del navegador. Symlink `/var/www/html/zajuna` presente.
- [ ] **Reverse proxy configurado.** *No aplica: Apache es el servidor web, no hay proxy inverso.* En su lugar: `sudo apachectl configtest` → `Syntax OK` y el vhost de §11.1 activo.
- [ ] **HTTPS configurado si aplica.** *No aplica: el entorno es HTTP* (§12).
- [ ] **Frontend construido.** *No aplica: no hay build.* En su lugar: `curl -sI http://localhost/zajuna/mod/imagecarousel/styles.css` → 200.
- [ ] **Backend construido.** *No aplica: PHP interpretado.* En su lugar: `php -l` sin errores sobre todos los `.php` del plugin (§14.2 paso 4).
- [ ] **Base de datos disponible.** `pg_isready` → accepting connections; `psql ... -c "SELECT 1;"` funciona.
- [ ] **Migraciones ejecutadas.** `admin/cli/upgrade.php` terminó sin errores; `mdl_imagecarousel` y `mdl_imagecarousel_images` existen con `availablefrom`, `availableuntil` y `visible`.
- [ ] **Seeds ejecutados si aplican.** `mdl_config_plugins` contiene `Slider_Informativo_Carrusel_Visible=1` y `Slider_Informativo_Carrusel_Version=2026072300`.
- [ ] **Servicios auxiliares disponibles.** *No aplica: el plugin no requiere ninguno* (§9).
- [ ] **Aplicación funcionando.** `mdl_modules` tiene `imagecarousel` con `visible=1`.
- [ ] **Health check funcionando.** `admin/cli/checks.php` y `admin/cli/check_database_schema.php` sin errores.
- [ ] **Logs disponibles.** `reposena_error.log` y `reposena_access.log` escribiéndose; PostgreSQL logueando.
- [ ] **Aplicación accesible desde el hostname local.** `http://localhost/zajuna/login/index.php` → 2xx o 3xx (referencia: 303) y la página de login se renderiza en el navegador.
- [ ] **El login NO redirige a producción.** `curl -sI http://localhost/zajuna/login/index.php` no devuelve `Location: http://lms.sena.edu.co` (§21).
- [ ] **Smoke test exitoso.** §18.1 en verde y los 16 pasos de §18.2 con el resultado esperado.
- [ ] **Reinicio completo probado.** §20 ejecutado; `systemctl is-enabled apache2 postgresql` → `enabled`.
- [ ] **Propiedad de archivos correcta.** `/var/www/zajuna/mod/imagecarousel` es de `www-data` (paridad con el servidor).
- [ ] **Artefactos que no deben publicarse, excluidos.** `.scannerwork/`, `docs/`, `pix/banners_sena*/` **no** están en el árbol web (§10.2).

---

## Anexo A — Supuestos, información faltante y riesgos

### A.1 Supuestos

1. **El entorno de paridad es Moodle 4.3.x**, no el mínimo 4.1 que declara `version.php`, porque el servidor real corre `2023100903.06`.
2. **Los valores de `php.ini` de §4.3** se toman de la instalación local que funciona; el `php.ini` del servidor real no está en el repositorio y no pudo verificarse.
3. **El protocolo es HTTP** (§12), resolviendo a favor de la configuración ejecutable frente al texto de la documentación.
4. **La estructura de directorios** (`/var/www/zajuna`, `/var/www/zajunadata`, symlink en `/var/www/html/zajuna`) se toma del entorno local de referencia; el layout del servidor real no está en el repositorio, aunque la subruta `/zajuna` sí está confirmada.
5. **PostgreSQL 16** localmente; el informe de QA dice "PostgreSQL" sin número de versión para el servidor.
6. **`amd/src/load_styles.js` es código muerto**, concluido por ausencia de `amd/build/` y de cualquier `js_call_amd` que lo referencie.

### A.2 Información faltante (no determinable desde el repositorio)

1. **Versión exacta de PostgreSQL en el servidor real.**
2. **Si existe realmente un terminador TLS delante de Apache.** El comentario `// TLS termina en el proxy` junto a `sslproxy = false` es contradictorio. **Confirmar con infraestructura antes de asumir HTTPS.**
3. **Valores de `php.ini` del servidor real** (`post_max_size`, `upload_max_filesize`, `memory_limit`). Relevante porque condiciona el límite práctico de carga de imágenes.
4. **Proceso de despliegue oficial hacia el servidor.** No hay CI/CD en el repositorio; los manuales heredados (`DEPLOYMENT_imagecarousel_ES.md`, `docs/deploy_manual.md`) describen un flujo **Windows/WAMP con MySQL** que **no coincide** con el servidor real Linux/Apache/PostgreSQL. Se documentó el entorno real, no esos manuales.
5. **Política de backup y retención** del servidor.
6. **Configuración de correo (SMTP) de Moodle**: irrelevante para el plugin, pero necesaria si QA prueba flujos de notificación de la plataforma.
7. **Origen exacto del redirect de login hacia `lms.sena.edu.co`.** Se confirmó el comportamiento (303) pero no su causa: no está en `login/index.php`. La hipótesis es `alternateloginurl` en `mdl_config` o el mecanismo de autenticación externo ("bffauth"). No pudo verificarse sin credenciales de BD. Ver §21.

### A.3 Riesgos que QA puede cuestionar

| # | Riesgo | Detalle |
|---|---|---|
| 1 | **Documentación heredada contradictoria** | `DEPLOYMENT_imagecarousel_ES.md` y `docs/deploy_manual.md` documentan Windows/WAMP + MySQL (`C:\wamp64\www\zajuna`, `mysqldump`). El servidor real es Linux + Apache + **PostgreSQL**. Seguir esos manuales al pie de la letra en este entorno **no funciona**. |
| 2 | **Imágenes en Base64 dentro de la BD** | Infla la BD ~33%, no están cifradas en reposo, y un `pg_dump` expone el contenido binario. Señalado en `REPORTE_QA_SEGURIDAD.md:141-148`. Impacta el tamaño de los backups en QA. |
| 3 | **`error_log()` verboso en ruta normal** | El plugin registra cada imagen procesada con longitudes de datos. Llena `reposena_error.log` rápido (§19). |
| 4 | **`$CFG->directorypermissions = 0777`** | Permisos muy laxos en el entorno de referencia. Aceptable en una VM local aislada; **no** debe replicarse en un servidor compartido. |
| 5 | **`$CFG->debugdisplay = 1`** | El entorno de referencia muestra errores en pantalla — configuración de desarrollo, no de servidor. §6.3 explica cómo desactivarlo. |
| 6 | **`$CFG->disableipcheck = true`** | Desactiva la validación de IP de sesión. Debilita la protección contra secuestro de sesión; verificar si es intencional. |
| 7 | **Dos rutas de render no equivalentes** | El carrusel embebido en el curso y `view.php` renderizan por caminos distintos (`docs/CONTEXTO_TECNICO_IMAGECAROUSEL.md`). **Prueba ambas**; un fix en una no arregla la otra. |
| 8 | **XSS via `{{{text}}}` en Mustache** | `templates/carousel.mustache` usa triple llave (HTML sin escapar). Riesgo MEDIO abierto en `REPORTE_QA_SEGURIDAD.md:168-178`. Mitigado parcialmente porque `lib.php:124` pasa el texto por `format_text()`, pero el `text` del modal merece verificación. |
| 9 | **`mod/imagecarousel:view` permitida a `guest`** | `db/access.php` concede `view` al arquetipo `guest`. Confirmar que es intencional para contenido de tipo banner. |
| 10 | **Plugin en `MATURITY_ALPHA`** | `version.php` declara madurez ALPHA (`REPORTE_QA_SEGURIDAD.md:287-294`). |
| 11 | **Compatibilidad Bootstrap 4 vs 5** | El modal de "Ver más" usa `data-dismiss="modal"` (Bootstrap 4). Si el tema usa Bootstrap 5 (`data-bs-dismiss`), el cierre del modal falla (`REPORTE_QA_SEGURIDAD.md:411`). |
| 12 | **Propiedad de archivos desviada** | En la máquina de referencia, `/var/www/zajuna/mod/imagecarousel` es `root:root`, mientras que el servidor corre como `www-data`. §14.2 paso 3 corrige la desviación. |
| 13 | **Archivo residual en el core** | Existe `/var/www/zajuna/admin/cli/upgrade.php.broken-bffauth-backup-20260722` en la instalación local: evidencia de intervención manual sobre el core de Moodle. No afecta al plugin, pero indica que el Moodle local puede haber divergido del original. |
| 14 | **El Moodle de referencia NO es vanilla** | Además del residuo anterior, el anfitrión tiene otros plugins locales (p. ej. `blocks/portaapre`, que imprime en toda ejecución CLI). Un QA que instale un Moodle 4.3 limpio **no** los tendrá. Para probar `mod_imagecarousel` de forma aislada esto es preferible; pero si un bug solo reproduce en el entorno de referencia, sospecha de interacción con esos plugins antes que del carrusel. |
| 15 | **El login local redirige a producción** | `http://localhost/zajuna/login/index.php` responde `303 → http://lms.sena.edu.co`. QA puede acabar probando **contra producción** sin darse cuenta. Mitigación y diagnóstico en §21. **Verificar antes de dar por válido el entorno.** |
| 16 | **Moodle conecta a PostgreSQL como superusuario** | En el entorno de referencia `$CFG->dbuser` es `postgres`, el superusuario del motor. Si Moodle se ve comprometido, el atacante controla todo el clúster, no solo `zajunadb`. §8.2 de este documento indica crear un **rol dedicado** (`<USUARIO>`) precisamente para no replicar esa desviación en local. Plantear al equipo si debe corregirse también en el servidor. |
| 17 | **`imagecarousel.zip` sin versionar** | Hay un ZIP de 27 MB sin trackear en la raíz del repositorio. No se usa en este procedimiento; el despliegue parte del árbol de `imagecarousel/`. |
