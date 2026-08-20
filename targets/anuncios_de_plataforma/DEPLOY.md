# Deploy local — `local_slider_form` (Anuncios de Plataforma)

> **Componente 2 de 2.** «Anuncios de Plataforma» es un único proyecto compuesto por dos plugins
> Moodle de tipo `local` que se despliegan por separado pero se ejecutan acoplados:
>
> | Plugin | Carpeta del repositorio | Destino en Moodle | Rol funcional |
> |---|---|---|---|
> | `local_slider` | `slider/` | `{dirroot}/local/slider` | Renderiza el banner en el front. Ver `slider/DEPLOY.md`. |
> | `local_slider_form` | `slider_form/` | `{dirroot}/local/slider_form` | **Este documento.** Back-office: gestión de imágenes del banner + envío segmentado de correos. |
>
> ⚠️ **`local_slider` debe instalarse ANTES que este plugin.** `local_slider_form` escribe en la
> tabla `local_slider` (`slider_form/config.php:7`) e invalida la caché
> `cache::make('local_slider','imagecache')` (`slider_form/lib/utilsFunctions.php:219`), ambas
> declaradas por el plugin hermano. Sin él, este plugin falla en tiempo de ejecución.
> Ver sección 7.3 — y ojo, `slider_form/docs/DESPLIEGUE_PREPROD.md` afirma lo contrario y está
> desactualizado (sección 22.6).

---

## 1. Objetivo

Levantar en una máquina local limpia un entorno que reproduzca el comportamiento del servidor
real para `local_slider_form`: un Moodle servido por **Apache** sobre **PHP**, con **PostgreSQL**
como motor, en el que un administrador con las *capabilities* adecuadas puede (a) publicar
imágenes en el carrusel de la plataforma y (b) encolar envíos de correo segmentados por
modalidad, regional, centro, programa, fechas y rol.

Este plugin tiene **dos particularidades que definen todo el despliegue** y que no se deducen de
un `README` genérico:

1. **Dos caminos de acceso a datos sobre la misma base**: el `$DB` de Moodle **y** una conexión
   PDO cruda (`ZajunaDbConnection`) que ejecuta SQL cross-schema contra `midb.*`.
2. **Un conjunto de tablas fuera del control de Moodle** (`midb.saved_filters`, `midb.envios2`,
   `midb.centros`, `midb.regionales`) que se crean **manualmente con `psql`** a partir de
   `db/migrations/*.sql`. `db/upgrade.php` **no** las ejecuta. Sin ellas, la mitad del plugin no
   arranca.

Este documento **no** describe un modo de desarrollo alternativo: el plugin no tiene build, ni
servidor de desarrollo, ni proceso propio. Su único modo de ejecución —en local y en el
servidor— es «PHP ejecutado por Apache dentro del árbol de Moodle».

**Fuente de verdad:** el código del repositorio y la configuración real de la máquina de
desarrollo (`/var/www/zajuna/config.php`, `/etc/apache2/sites-enabled/000-default.conf`). Lo que
no pudo determinarse desde el repositorio está declarado en la sección 22.5.

---

## 2. Arquitectura local

### 2.1 Cadena de ejecución

```
Navegador (administrador / QA)
   │  HTTP :80
   ▼
Apache 2.4  ──  VirtualHost *:80  ServerName localhost
   │           DocumentRoot /var/www/html
   │           /var/www/html/zajuna ──symlink──> /var/www/zajuna
   ▼
mod_php (PHP 8.2)  →  Moodle 4.3.3+  (dirroot /var/www/zajuna)
   │
   ├─ settings.php:16  admin_externalpage 'local_slider_form_manage'
   │        └─> /local/slider_form/menu.php   (hub)
   │                ├─ index.php · manage_images.php · show_order.php  → CRUD del carrusel
   │                ├─ segmented.php                                   → envío segmentado
   │                └─ send_logs.php · table_logs.php                  → historial
   │
   ├─ Endpoints POST/AJAX
   │        insertRecord.php · updateRecord.php · deleteRecord.php · order.php
   │        active_role_users.php
   │        ajax/categories.php · ajax/send_segmented.php
   │        ajax/preview_correo.php · ajax/saved_filters.php · ajax/export_envios.php
   │
   ├── CAMINO A ──  $DB de Moodle  (driver nativo pgsql)
   │        tablas mdl_*  +  mdl_local_slider (propiedad de local_slider)
   │
   └── CAMINO B ──  PDO crudo  (classes/external/ZajunaDbConnection.php)
            reutiliza $CFG->dbhost/dbname/dbuser/dbpass
            SQL cross-schema + regex Postgres  →  midb.*
                       │
                       ▼
        PostgreSQL 16  :5432   base zajunadb
            ├─ public.mdl_*            (Moodle, prefijo mdl_)
            └─ midb.saved_filters      (filtros e historial de envíos)
               midb.envios2            ← COLA DE CORREOS (se escribe aquí)
               midb.regionales         (catálogo SENA)
               midb.centros            (catálogo SENA)
                       │
                       ▼
        ┌──────────────────────────────────────────────┐
        │  PROCESO DE ENVÍO DE CORREO — EXTERNO        │
        │  NO forma parte de este repositorio.         │
        │  Consume midb.envios2 y actualiza sus        │
        │  columnas `estado` y `sent_at`.              │
        │  Ver secciones 9.2 y 22.5.                   │
        └──────────────────────────────────────────────┘
```

### 2.2 Por qué existen dos caminos de acceso a datos

Documentado en `slider_form/classes/external/ZajunaDbConnection.php:3-7`: el `$DB` de Moodle no
puede expresar SQL cross-schema contra `midb.*` ni las expresiones regulares de PostgreSQL que
usa la resolución de cursos. La conexión PDO es un **singleton** que reutiliza exactamente las
credenciales de Moodle (`ZajunaDbConnection.php:21-25`) — **no hay credenciales propias, ni
fichero de configuración aparte, ni contraseña embebida**.

Consecuencia crítica para el despliegue: **el SQL crudo escribe el prefijo `mdl_` literal**. Se
usa en 6 tablas (`mdl_course`, `mdl_course_categories`, `mdl_user`, `mdl_role`,
`mdl_role_assignments`, `mdl_config_plugins`). Con un `$CFG->prefix` distinto de `mdl_`, la
cascada de filtros y el historial fallan.

### 2.3 Decisiones de arquitectura y dónde están en el código

| Aspecto | Implementación real | Referencia |
|---|---|---|
| **Entrada en el menú de administración** | Un `admin_externalpage` añadido al nodo `root`, **gateado por las *capabilities* del plugin y no por `moodle/site:config`**, para que roles limitados vean solo esta opción. El array de dos capabilities tiene semántica *CUALQUIERA*. | `slider_form/settings.php:16-21` |
| **Modelo de permisos** | Dos *capabilities* en `CONTEXT_SYSTEM` con **arquetipos vacíos**: ningún rol las obtiene por defecto, deben concederse explícitamente. `:edit` implica `:view`. | `slider_form/db/access.php:5-17`, `slider_form/lib/usersValidations.php:76-77` |
| **Interruptor global** | Fila en `mdl_config_plugins` (`plugin='local_slider_form'`, `name='Anuncios_Plataforma_Admin_Banner_Visible'`). Se lee **directo de la tabla, sin caché MUC**. `'0'` ⇒ oculto para todos salvo superadministrador. Ausencia de fila ⇒ visible (*fail-open*). | `slider_form/settings.php:13-15`, `slider_form/lib/usersValidations.php:46-60` |
| **Guardas de cada página/endpoint** | `checkSession()` + `checkUserRole()` (+ `checkCsrfToken()` en escritura). `$action` es `'redirect'` en páginas y `'exception'` en AJAX. | `slider_form/lib/usersValidations.php:26`, `:68`, `:93` |
| **CSRF** | `confirm_sesskey()` de Moodle envuelto con validación de tipo y presencia. | `slider_form/lib/usersValidations.php:93-107` |
| **Anti-CSRF adicional en el envío** | `ajax/send_segmented.php` exige `Content-Type: application/json`, lo que bloquea el envío desde un formulario HTML plano (que no dispara *preflight* CORS). | `slider_form/ajax/send_segmented.php:44-48` |
| **Imágenes del carrusel** | Se guardan como **base64 en columnas `text` de `mdl_local_slider`**. No se usa la File API de Moodle. | `slider_form/config.php:7`; esquema en `slider/db/install.xml:11-12` |
| **Invalidación de la caché del banner** | Tras cada `INSERT`/`UPDATE`/`DELETE`/reordenación se llama a `deleteSliderCache()`, que borra `images_site` e `images_course` de la MUC de `local_slider`. | `slider_form/lib/utilsFunctions.php:217-222`; llamadas en `insertRecord.php:147`, `updateRecord.php:133`, `deleteRecord.php:52`, `order.php:73` |
| **Resolución de cursos del envío** | Todo se deriva de `public.mdl_course` (`visible`, `shortname`, `fullname`). **El esquema `INTEGRACION` ya no se consulta** (solo aparece en comentarios). | `slider_form/lib/modalidades.php:1-40`, `:259` |
| **El plugin NO envía correo** | No hay `email_to_user()`, ni `message_send()`, ni `mail()`, ni configuración SMTP en todo el repositorio. `send_segmented.php` hace `INSERT` en `midb.envios2` y termina. **La entrega la hace un proceso externo.** | `slider_form/ajax/send_segmented.php:316-346`; búsqueda sin resultados de `email_to_user\|message_send\|mail(` |
| **Plantilla del correo** | Fichero **obligatorio en tiempo de ejecución**: `docs/Cuerpo_Correo.html`, validado contra escape de ruta antes de leerse. | `slider_form/ajax/send_segmented.php:298-303` |

### 2.4 Diferencias entre desarrollo y servidor

No hay ramas de código ni ficheros de configuración que distingan entornos. Las diferencias
reales son **tres**, y las tres son de datos o configuración:

1. **`config.php` de Moodle** (`wwwroot`, credenciales, `dataroot`).
2. **Los IDs de categoría de curso, que están hardcodeados** en
   `slider_form/lib/modalidades.php:62` y `:65`. Hoy valen `10` y `200`; **deben coincidir con
   `mdl_course_categories` de la base destino**. Ver sección 6.3 — es la causa clásica del error
   500 al cargar modalidades.
3. **La presencia y el contenido de las tablas `midb.*`**, que se crean a mano (sección 8.4).

---

## 3. Requisitos previos

### 3.1 Versiones verificadas

| Componente | Versión verificada | Cómo se comprobó |
|---|---|---|
| Moodle | `4.3.3+ (Build: 20240308)` | `grep '$release' /var/www/zajuna/version.php` |
| PHP | 8.2.33 | `php -v` |
| Apache | 2.4.52 (Ubuntu) | `apache2 -v` |
| PostgreSQL | 16.15 | `psql --version` |
| Sistema | Ubuntu 22.04 (kernel 6.8) | `uname -a` |

**Mínimo declarado por el plugin:** `$plugin->requires = 2022112800`
(`slider_form/version.php:30`) = **Moodle 4.1**. Release actual: `0.4.1`, `version = 2026072800`
(`slider_form/version.php:28-29`).

> **PostgreSQL es obligatorio, no intercambiable.** El plugin usa sintaxis exclusiva de
> PostgreSQL: `STRING_AGG(... ORDER BY ...)`, `COUNT(*) FILTER (WHERE ...)`, el operador de regex
> `~`, `SUBSTRING(... FROM 'patrón')`, casts `::jsonb`, `to_regclass`. No funciona sobre MySQL ni
> MariaDB.

### 3.2 Extensiones PHP

| Extensión | Para qué | Dónde se usa | Verificación |
|---|---|---|---|
| `pgsql` | Driver nativo de Moodle (`$DB`) | Todo el plugin | `php -m \| grep -x pgsql` |
| **`pdo_pgsql`** | **Camino B: la conexión PDO cruda a `midb.*`** | `classes/external/ZajunaDbConnection.php:30` | `php -m \| grep -x pdo_pgsql` |
| **`gd` con soporte WebP** | Validar la imagen del correo (`imagecreatefromstring`, `getimagesize`) y las del carrusel | `ajax/send_segmented.php:104`, `lib/fieldsValidations.php:112` | ver más abajo |
| **`fileinfo`** | Detección real de MIME (`finfo_open`/`finfo_file`), que no se fía de la extensión | `ajax/send_segmented.php:101-103`, `lib/fieldsValidations.php:96-98` | `php -m \| grep -x fileinfo` |
| **`zip`** | Generación del XLSX del reporte (`MoodleExcelWorkbook`, formato `Xlsx`) | `ajax/export_envios.php:18`, `:127` | `php -m \| grep -x zip` |
| `mbstring`, `intl`, `curl`, `xml`, `soap`, `exif` | Requisitos de **Moodle core** | — | `php -m` |

Comprobación específica de WebP en GD — **es la que más falla en máquinas nuevas**, y sin ella el
envío segmentado rechaza toda imagen:

```bash
php -r 'var_dump(gd_info()["WebP Support"]);'
# → bool(true)   ← obligatorio
```

Si devuelve `false` o la clave no existe, instala/recompila GD con WebP
(`sudo apt install php8.2-gd` en Ubuntu 22.04 ya lo trae).

### 3.3 Lo que este proyecto NO usa

Verificado por búsqueda explícita en todo el repositorio:

- **No hay Docker ni Compose** (`Dockerfile`, `docker-compose.yml`, `compose.yml`: inexistentes).
- **No hay Node, npm ni build de frontend** (`package.json`: inexistente). El JS va inline en
  `segmented.php`/`send_logs.php` o suelto en `js/script.js`.
- **No hay Composer** (`composer.json`: inexistente). No hay `vendor/`.
- **No hay CI/CD** (`.github/workflows`, `.gitlab-ci.yml`, `Jenkinsfile`: inexistentes).
- **No hay tests ni linter.** Ambos `.vscode/settings.json` están vacíos. La validación es
  manual (sección 16) y por los informes de QA/pentest en `docs/`.
- **No hay reverse proxy adicional** (Nginx, Caddy, Traefik). Apache es servidor web y punto de
  entrada.
- **No hay Redis, RabbitMQ, Kafka, Elasticsearch, MongoDB ni MinIO.**
- **No hay SMTP configurado por el plugin** — porque el plugin no envía correo (sección 9.2).
- **No hay process manager propio** (systemd unit, Supervisor, PM2, Gunicorn, uWSGI). El único
  servicio gestionado es `apache2`.
- **No hay variables de entorno** (`.env*`: inexistentes; sin `getenv()` en el código).
- **No hay endpoint de health check propio.** Se usan los de Moodle core (sección 15.6).

---

## 4. Preparación de la máquina

Rutas de la máquina de referencia: `DIRROOT=/var/www/zajuna`, `DATAROOT=/var/www/zajunadata`.

### 4.1 Instalar la pila

```bash
sudo apt update
sudo apt install -y apache2 postgresql postgresql-client \
    php php-pgsql php-gd php-intl php-mbstring php-curl php-xml php-zip php-soap
sudo a2enmod php8.2 rewrite
sudo systemctl enable --now apache2 postgresql
```

Comprobación inmediata de las extensiones críticas de **este** plugin:

```bash
php -m | grep -E '^(pdo_pgsql|pgsql|gd|zip|fileinfo)$'
php -r 'var_dump(gd_info()["WebP Support"]);'   # → bool(true)
```

### 4.2 Moodle base y `local_slider`

Este repositorio contiene **solo los dos plugins**, no Moodle. Necesitas previamente:

1. Un Moodle 4.1+ (referencia: 4.3.3+) instalado y funcionando sobre PostgreSQL.
2. **`local_slider` ya desplegado** siguiendo `slider/DEPLOY.md` — es el propietario de la tabla
   `local_slider` y de la definición de caché `imagecache` que este plugin usa.

```bash
grep -E '^\$CFG->(dbtype|dbhost|dbname|dbuser|prefix|wwwroot|dataroot)' /var/www/zajuna/config.php
```

Salida esperada (la contraseña **no** se muestra ni se documenta):

```
$CFG->dbtype    = 'pgsql';
$CFG->dbhost    = 'localhost';
$CFG->dbname    = 'zajunadb';
$CFG->dbuser    = 'postgres';
$CFG->prefix    = 'mdl_';
$CFG->wwwroot   = 'http://localhost/zajuna';
$CFG->dataroot  = '/var/www/zajunadata';
```

> ⚠️ **`$CFG->prefix` DEBE ser `mdl_`.** El SQL crudo del camino PDO lo escribe literalmente
> (sección 2.2). Con otro prefijo, `ajax/categories.php`, `ajax/send_segmented.php`,
> `send_logs.php`, `table_logs.php` y `ajax/export_envios.php` fallan con
> `SQLSTATE[42P01] relation ... does not exist`.

### 4.3 Publicar Moodle bajo el `DocumentRoot`

Configuración real de la máquina de referencia — `wwwroot` es un **subdirectorio** resuelto con
un enlace simbólico:

```bash
sudo ln -sfn /var/www/zajuna /var/www/html/zajuna
```

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

El bloque `<Directory /var/www/>` de `/etc/apache2/apache2.conf` ya trae
`Options Indexes FollowSymLinks`, necesario para seguir el enlace. Sin él, **403**.

```bash
sudo apachectl configtest && sudo systemctl reload apache2
```

### 4.4 Límites de PHP

Relevantes porque el formulario del carrusel acepta **dos imágenes de hasta 5 MB cada una**
(`slider_form/lib/fieldsValidations.php:92`) y las convierte a base64 (~1,33× de tamaño).

```bash
grep -hE "^(upload_max_filesize|post_max_size|memory_limit|max_execution_time|max_input_vars)" \
     /etc/php/8.2/apache2/php.ini
```

Valores de la máquina de referencia:

```
upload_max_filesize = 2G
post_max_size = 1G
memory_limit = 128M
max_execution_time = 30
max_input_vars = 5000
```

> **`max_execution_time = 30` es un riesgo real en el envío segmentado**, no una nota teórica:
> `send_segmented.php` inserta **una fila por destinatario** dentro de una única transacción
> (`ajax/send_segmented.php:321-348`). Con decenas de miles de destinatarios puede agotar el
> tiempo y hacer `rollBack()`, dejando el envío sin registrar. Ver sección 19.7.

---

## 5. Configuración de hostname

**Este plugin no depende de ningún hostname ni dominio propio.** No hay comprobación de `Host`,
ni cookies de dominio propio, ni CORS en el código.

El único hostname en juego es el de `$CFG->wwwroot` — en la máquina de referencia, `localhost`,
resoluble sin tocar `/etc/hosts`. **No añadas entradas a `/etc/hosts` para este proyecto:** no
hay ningún dominio que registrar.

Matiz relevante para QA: todas las URLs del plugin se construyen con `new moodle_url(...)`
(por ejemplo `slider_form/segmented.php:22-26`), de modo que heredan `$CFG->wwwroot`. Las
llamadas `fetch()` del navegador usan `credentials: 'include'`
(`slider_form/segmented.php:1521`, `:2148`, `:2186`, `:2280`, `:2355`): si accedes por una URL
distinta de `$CFG->wwwroot`, la cookie de sesión no viaja y **todos los AJAX devuelven 401**.
Entra siempre por la URL exacta configurada.

---

## 6. Variables de entorno

**No aplica: este plugin no usa variables de entorno.** Verificado:

```bash
grep -rn "getenv\|\$_ENV" slider_form/ --include=*.php   # → sin resultados
find . -name '.env*'                                     # → sin resultados
```

La configuración vive en tres sitios, y los tres hay que revisarlos al desplegar.

### 6.1 Configuración de Moodle (`config.php`)

| Ajuste | Propósito para `local_slider_form` | Obligatorio | Valor de referencia |
|---|---|---|---|
| `$CFG->dbtype` | Debe ser `pgsql` (sección 3.1). | Sí | `pgsql` |
| `$CFG->dbhost` | **Doble uso**: `$DB` de Moodle **y** DSN del PDO (`ZajunaDbConnection.php:21`). | Sí | `localhost` |
| `$CFG->dbname` | Ídem (`ZajunaDbConnection.php:23`). | Sí | `zajunadb` |
| `$CFG->dbuser` / `$CFG->dbpass` | Ídem (`ZajunaDbConnection.php:24-25`). **El usuario necesita permisos sobre el esquema `midb`** (sección 8.3). | Sí | `postgres` / **no documentar** |
| `$CFG->dboptions['dbport']` | Puerto del DSN PDO; **si no está definido, se usa `'5432'` por defecto** (`ZajunaDbConnection.php:22`). | No | sin definir ⇒ 5432 |
| `$CFG->prefix` | **Debe ser `mdl_`** (sección 2.2). | Sí | `mdl_` |
| `$CFG->wwwroot` | Base de todas las `moodle_url` y de los `fetch()` con cookie. | Sí | `http://localhost/zajuna` |
| `$CFG->dirroot` | Ruta de la plantilla de correo (`ajax/send_segmented.php:298`). | Sí | `/var/www/zajuna` |
| `$CFG->dataroot` | Caché MUC y ficheros temporales de Moodle. | Sí | `/var/www/zajunadata` |
| `$CFG->libdir` | Carga de `excellib.class.php` para el XLSX (`ajax/export_envios.php:18`). | Sí | derivado de `dirroot` |

> 🔒 **Nunca copies `$CFG->dbpass` a un documento, ticket o captura.** Para verificar la conexión
> usa `PGPASSWORD` en una variable de shell efímera (sección 8.5).

### 6.2 Configuración del plugin (tabla `mdl_config_plugins`)

Se siembran en la instalación (`slider_form/db/install.php:9-10`) y se resincronizan en la
actualización (`slider_form/db/upgrade.php:41-56`):

| Clave (`name`) | `plugin` | Propósito | Obligatoria | Defecto |
|---|---|---|---|---|
| `Anuncios_Plataforma_Admin_Banner_Visible` | `local_slider_form` | **Interruptor real.** `'0'` ⇒ el enlace del menú de administración se oculta y **todas** las páginas y endpoints devuelven 403, salvo para superadministrador. | No (*fail-open*) | `'1'` |
| `Anuncios_Plataforma_Admin_Banner_Version` | `local_slider_form` | Solo informativa; refleja `$plugin->version`. | No | `2026072800` |

```sql
-- Ver estado
SELECT plugin, name, value FROM mdl_config_plugins WHERE plugin = 'local_slider_form';

-- Apagar el back-office para todos salvo superadministrador (mantenimiento en caliente)
UPDATE mdl_config_plugins SET value = '0'
 WHERE plugin = 'local_slider_form' AND name = 'Anuncios_Plataforma_Admin_Banner_Visible';

-- Volver a encenderlo
UPDATE mdl_config_plugins SET value = '1'
 WHERE plugin = 'local_slider_form' AND name = 'Anuncios_Plataforma_Admin_Banner_Visible';
```

Aplican **al instante**, sin purgar cachés, por diseño (`slider_form/lib/usersValidations.php:51-56`).
El estándar completo está en `docs/Estandar_Componente_Para_Visibilizacion_del_Plugin.html`
(reglas R1–R5).

### 6.3 ⚠️ Constantes hardcodeadas que dependen de la base destino

**Este es el ajuste por entorno más importante del plugin.** No es una variable de entorno: es
código, y hay que editarlo por entorno.

`slider_form/lib/modalidades.php:62` y `:65`:

```php
/* Categorías mdl_course_categories que componen "Complementaria", en orden de despliegue. */
const TIPO_CATEGORIAS = ['complementaria' => [10, 200]];

/* Etiquetas para claves cat_N (sin necesidad de consultar la BD). */
const MODALIDAD_CATEGORIA_LABELS = [
    10 => 'Complementaria presencial',
    200 => 'Complementaria virtual',
];
```

Los IDs `10` y `200` son `mdl_course_categories.id` **de la base de desarrollo**. Si en la base
destino esas categorías tienen otros IDs, el nivel de formación «Complementaria» devuelve una
lista vacía.

Cómo determinar los IDs correctos en tu base:

```sql
SELECT cc.id, cc.name, count(c.id) AS cursos_visibles
  FROM mdl_course_categories cc
  LEFT JOIN mdl_course c ON c.category = cc.id AND c.visible = 1
 GROUP BY cc.id, cc.name
 ORDER BY cursos_visibles DESC;
```

Identifica las categorías que corresponden a formación complementaria y sustituye ambos valores
en `modalidades.php:62` y `:65`. Es el **único** punto donde viven hoy (verificado:
`grep -rn "TIPO_CATEGORIAS" slider_form/` solo devuelve `lib/modalidades.php` y dos usos en
`ajax/export_envios.php:103-104`).

> `slider_form/docs/cambio-categorias-despliegue.md` documenta este mismo ajuste pero apunta a
> constantes que **ya no existen** (`CATEGORIAS` en `ajax/categories.php`, `CATEGORIAS_VALIDAS`
> en `ajax/send_segmented.php`). Ese documento está obsoleto — ver sección 22.6.

Además, la resolución de cursos depende del **formato del `shortname`**
`P_<código>_<V|A|P|PI>_<ficha>_R_<regional>_C_<centro>` (`slider_form/lib/modalidades.php:14-35`).
Si los cursos de tu base no siguen ese formato, la cascada devuelve listas vacías **sin error**.
Comprobación:

```sql
SELECT count(*) FILTER (WHERE shortname ~ '^P_\d+_.*_R_\d+_C_\d+') AS con_formato,
       count(*)                                                    AS visibles_total
  FROM mdl_course WHERE visible = 1;
```

---

## 7. Dependencias

### 7.1 Dependencias de código

**Ninguna gestionada por un gestor de paquetes.** No hay `composer.json`, `package.json` ni
equivalente; no hay `vendor/` ni `node_modules/`. Todo el PHP y el JS está versionado tal cual.

### 7.2 Dependencias de Moodle core

| Librería | Uso | Referencia |
|---|---|---|
| `excellib.class.php` (`MoodleExcelWorkbook`) | Genera el XLSX del reporte de envíos. Requiere la extensión `zip`. | `slider_form/ajax/export_envios.php:18`, `:127` |
| `cache/lib.php` | Invalidación de la caché del banner. | `insertRecord.php:23`, `updateRecord.php:21`, `deleteRecord.php:19`, `order.php:20` |
| `moodleform` (`classes/forms/`) | Formularios de alta y edición del carrusel. | `slider_form/classes/forms/Insert.php`, `Update.php` |

### 7.3 Dependencia del plugin hermano `local_slider` — **obligatoria**

`slider_form/version.php` **no declara `$plugin->dependencies`**, pero el acoplamiento es real y
bloqueante:

| Qué necesita | De dónde viene | Si falta |
|---|---|---|
| Tabla `mdl_local_slider` | `slider/db/install.xml:7` | Todo el CRUD del carrusel falla: `dml_missing_record_exception` / tabla inexistente |
| Definición de caché `imagecache` | `slider/db/caches.php:7` | `cache::make('local_slider','imagecache')` lanza excepción en cada guardado (`slider_form/lib/utilsFunctions.php:219`) |
| Render del banner | `slider/lib.php:35` | Las imágenes se guardan pero **no se muestran en ninguna parte** |

**Instala `local_slider` primero.** Ver `slider/DEPLOY.md`.

### 7.4 Dependencia externa en tiempo de ejecución

**Ninguna para este plugin.** No carga CDNs: el JS de `segmented.php` y `send_logs.php` es
inline y sin librerías externas.

> El plugin hermano **sí** depende de `https://unpkg.com` para Swiper
> (`slider/lib/showSlider.php:224-228`). Si la máquina de QA está aislada, el back-office
> funcionará pero el banner no se animará. Ver `slider/DEPLOY.md`, sección 19.3.

### 7.5 Fichero de datos obligatorio en tiempo de ejecución

`slider_form/docs/Cuerpo_Correo.html` (~41 KB) **no es documentación**: es la plantilla HTML del
correo, leída en cada envío y en cada vista previa
(`ajax/send_segmented.php:298-303`, `ajax/preview_correo.php`). Si falta, el endpoint lanza
`Plantilla de correo no encontrada.` con HTTP 500.

**Debe copiarse al servidor**, aunque esté dentro de `docs/`. Ver sección 10.1.

---

## 8. Base de datos

### 8.1 Motor y conexión

| Dato | Valor | Origen |
|---|---|---|
| Motor | PostgreSQL 16.15 | `psql --version` |
| Base | `zajunadb` | `$CFG->dbname` |
| Host / Puerto | `localhost` / 5432 | `$CFG->dbhost`; puerto por defecto del PDO (`ZajunaDbConnection.php:22`) |
| Usuario | `postgres` | `$CFG->dbuser` |
| Contraseña | **Solo en `config.php`.** No documentar, no versionar. | `$CFG->dbpass` |
| Prefijo Moodle | `mdl_` | `$CFG->prefix` |
| Esquemas usados | `public` (Moodle) y **`midb`** (tablas del plugin) | `grep -o "midb\.\w*"` |
| Modo PDO | `ERRMODE_EXCEPTION`, `FETCH_ASSOC` | `ZajunaDbConnection.php:31-32` |

**Una sola base de datos, dos esquemas.** No hay una segunda base ni credenciales aparte.

### 8.2 Tablas que usa el plugin

**Del esquema `public` (Moodle, prefijo `mdl_`) — creadas por Moodle:**

| Tabla | Acceso | Uso |
|---|---|---|
| `mdl_local_slider` | Lectura/escritura vía `$DB` | CRUD del carrusel. **Propiedad de `local_slider`.** |
| `mdl_course` | Lectura vía PDO crudo | Universo de cursos: `visible`, `shortname`, `fullname`, `startdate`, `category` |
| `mdl_course_categories` | Lectura vía PDO crudo | Categorías de «Complementaria» |
| `mdl_user`, `mdl_user_enrolments`, `mdl_enrol`, `mdl_role`, `mdl_role_assignments`, `mdl_context` | Lectura vía `$DB` | Destinatarios con matrícula activa (`ue.status = 0`) |
| `mdl_config_plugins` | Lectura/escritura | Interruptor y versión |
| `mdl_role_capabilities` | Lectura/escritura en upgrade | Migración de `:manage` a `:view`/`:edit` |

**Del esquema `midb` — NO gestionadas por Moodle, se crean a mano (sección 8.4):**

| Tabla | Creada por | Uso | Escritura |
|---|---|---|---|
| `midb.saved_filters` | `001`…`012` | Filtros guardados e historial de envíos. `estado`: `0` = envió sin guardar, `1` = guardado activo, `3` = eliminado. | `ajax/send_segmented.php:355`, `ajax/saved_filters.php` |
| `midb.envios2` | `007`, `013` | **Cola de correos**, una fila por destinatario. | `ajax/send_segmented.php:316-318` |
| `midb.regionales` | `003` / `004` | Catálogo de nombres de regionales SENA por `rgn_id` | Solo lectura desde el plugin |
| `midb.centros` | `003` / `005` | Catálogo de nombres de centros SENA por `sed_id` | Solo lectura desde el plugin |

### 8.3 Preparación del esquema `midb` — paso previo obligatorio

> ⚠️ **Ninguna migración crea el esquema `midb`.** Verificado:
> `grep -ril 'create schema' slider_form/db/migrations/` no devuelve resultados. Si el esquema no
> existe, la **primera** migración falla con
> `ERROR: schema "midb" does not exist`.

```bash
psql -h localhost -U postgres -d zajunadb -c 'CREATE SCHEMA IF NOT EXISTS midb;'
```

Si el usuario de Moodle no es el propietario de la base, además hace falta:

```sql
GRANT USAGE, CREATE ON SCHEMA midb TO postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA midb TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA midb
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO postgres;
```

(Sustituye `postgres` por el valor real de `$CFG->dbuser`.)

### 8.4 Migraciones — **manuales, con `psql`, en orden**

`slider_form/db/upgrade.php` **NO ejecuta estos ficheros**: solo gestiona cambios de
*capabilities* y de configuración del lado Moodle. Las tablas `midb.*` son responsabilidad del
operador.

```bash
cd /var/www/zajuna/local/slider_form/db/migrations

for f in 001_saved_filters.sql \
         002_saved_filters_fecha_hasta.sql \
         003_centros_regionales.sql \
         004_regionales.sql \
         005_centros.sql \
         006_saved_filters_jsonb.sql \
         007_envios2_verify.sql \
         008_saved_filters_align.sql \
         009_saved_filters_estado.sql \
         010_saved_filters_csv.sql \
         011_saved_filters_regional_csv.sql \
         012_saved_filters_all_text.sql \
         013_envios2_cursos.sql
do
  echo "── $f ──"
  psql -h localhost -U postgres -d zajunadb -v ON_ERROR_STOP=1 -f "$f" || break
done
```

`ON_ERROR_STOP=1` es deliberado: **detiene la cadena en el primer fallo** en lugar de dejar el
esquema a medias.

Qué hace cada una (resumen; el encabezado de cada fichero lo detalla):

| # | Fichero | Efecto |
|---|---|---|
| 001 | `001_saved_filters.sql` | Crea `midb.saved_filters` (esquema original: `roles text[]`, IDs `bigint`) |
| 002 | `002_saved_filters_fecha_hasta.sql` | Añade `fecha_hasta date` |
| 003 | `003_centros_regionales.sql` | Crea `midb.regionales` (PK `rgn_id`) y `midb.centros`, con datos |
| 004 | `004_regionales.sql` | Recrea `midb.regionales` con `id SERIAL` PK + `rgn_id UNIQUE`, 34 regionales. **`CREATE TABLE IF NOT EXISTS` ⇒ es no-op si 003 ya corrió** (ver 22.6) |
| 005 | `005_centros.sql` | **`DROP TABLE IF EXISTS midb.centros`** y la recrea con `id SERIAL` PK + `sed_id UNIQUE`, 118 centros |
| 006 | `006_saved_filters_jsonb.sql` | Migra `centro_id`/`programa_id`/`roles` a `jsonb`; añade `asunto`, `descripcion`, `imagen`, `imagen_mime` |
| 007 | `007_envios2_verify.sql` | Crea `midb.envios2` (`destinatario`, `asunto`, `body`, `created_at`) + índice sobre `created_at` |
| 008 | `008_saved_filters_align.sql` | Alinea tipos a `jsonb` de forma tolerante al esquema previo |
| 009 | `009_saved_filters_estado.sql` | Añade `estado smallint NOT NULL DEFAULT 1` con `CHECK (estado IN (0,1,3))`; blinda `NOT NULL` |
| 010 | `010_saved_filters_csv.sql` | Convierte `centro_id`/`programa_id`/`roles` de `jsonb` a **`text` CSV** |
| 011 | `011_saved_filters_regional_csv.sql` | Convierte `regional_id` de `bigint` a `text` CSV |
| 012 | `012_saved_filters_all_text.sql` | **Normaliza a `text` CSV todas las columnas multivalor**, idempotente y tolerante al tipo actual. Arregla `22001` y `22P02` en despliegues atrasados |
| 013 | `013_envios2_cursos.sql` | Añade `envios2.cursos jsonb NOT NULL DEFAULT '[]'` con el detalle por ficha de cada destinatario |

> **La secuencia 001→012 reescribe varias veces las mismas columnas** (de `bigint`/`text[]` a
> `jsonb` y de vuelta a `text` CSV). Es historia real del proyecto, no un error. En una base
> **limpia**, ejecutarlas todas en orden deja el estado correcto; la 012 es idempotente y
> converge sea cual sea el punto de partida.

**Verificación tras las migraciones:**

```bash
psql -h localhost -U postgres -d zajunadb <<'SQL'
-- 1. ¿Existen las 4 tablas?
SELECT table_name FROM information_schema.tables
 WHERE table_schema = 'midb' ORDER BY table_name;
-- esperado: centros, envios2, regionales, saved_filters

-- 2. ¿saved_filters quedó con todas las columnas multivalor en text? (efecto de la 012)
SELECT column_name, data_type FROM information_schema.columns
 WHERE table_schema='midb' AND table_name='saved_filters'
   AND column_name IN ('modalidad','regional_id','centro_id','programa_id','roles')
 ORDER BY column_name;
-- esperado: las 5 con data_type = 'text'

-- 3. ¿envios2 tiene la columna cursos? (efecto de la 013)
SELECT column_name, data_type FROM information_schema.columns
 WHERE table_schema='midb' AND table_name='envios2' ORDER BY ordinal_position;

-- 4. ¿Los catálogos tienen datos?
SELECT 'regionales' AS tabla, count(*) FROM midb.regionales
UNION ALL
SELECT 'centros', count(*) FROM midb.centros;
-- esperado aproximado: regionales 33-34, centros 118
SQL
```

### 8.5 ⚠️ Columnas de `midb.envios2` que las migraciones NO crean

El historial de envíos lee **dos columnas que ninguna migración del repositorio define**:

| Columna leída | Dónde se lee | Dónde se crea |
|---|---|---|
| `envios2.estado` | `send_logs.php:34-35`, `table_logs.php:41`, `ajax/export_envios.php:44` | **En ninguna migración** |
| `envios2.sent_at` | `table_logs.php:42`, `ajax/export_envios.php:45` | **En ninguna migración** |

Verificado: `grep -rn "sent_at\|estado" slider_form/db/migrations/*.sql | grep -i envios` no
devuelve ninguna definición.

**Interpretación:** son columnas de las que se apropia el **proceso externo de envío** (sección
9.2), que marca cada fila como `'pendiente'` o `'enviado'` y estampa la fecha de entrega. El
repositorio no incluye ese proceso ni su DDL.

**Consecuencia para QA:** tras aplicar solo las migraciones del repositorio, `segmented.php`
funciona y encola correos, pero **`send_logs.php` falla** con:

```
SQLSTATE[42703]: Undefined column: 7 ERROR:  column "estado" does not exist
```

Para desbloquear el historial en un entorno local **hasta que se confirme el DDL real con el
equipo responsable del proceso de envío**, añade las columnas de forma compatible con lo que el
código espera (`'pendiente'` / `'enviado'`, `send_logs.php:34-35`):

```sql
-- SUPUESTO LOCAL, no verificado contra el proceso de envío real.
-- Confirmar tipos y valores con quien mantiene el consumidor de midb.envios2.
ALTER TABLE midb.envios2
    ADD COLUMN IF NOT EXISTS estado  text        NOT NULL DEFAULT 'pendiente',
    ADD COLUMN IF NOT EXISTS sent_at timestamptz;

CREATE INDEX IF NOT EXISTS envios2_estado_idx ON midb.envios2 (estado);
```

Está declarado como **supuesto** en la sección 22.4 y como **información faltante** en la 22.5.

### 8.6 Cómo conectarse y comprobar

```bash
# Toma la contraseña del config.php de Moodle sin imprimirla:
read -rs PGPASSWORD < <(php -r "require '/var/www/zajuna/config.php'; echo \$CFG->dbpass;")
export PGPASSWORD

psql -h localhost -p 5432 -U postgres -d zajunadb -c '\conninfo'
# → You are connected to database "zajunadb" as user "postgres" ...

# ¿El usuario puede escribir en midb?
psql -h localhost -U postgres -d zajunadb -Atc \
  "SELECT has_schema_privilege(current_user, 'midb', 'USAGE, CREATE');"
# → t

# Tabla del carrusel (propiedad de local_slider)
psql -h localhost -U postgres -d zajunadb -Atc \
  "SELECT to_regclass('public.mdl_local_slider');"
# → mdl_local_slider

unset PGPASSWORD
```

### 8.7 Datos iniciales (*seeds*)

| Conjunto | ¿Hay seed en el repositorio? | Cómo se obtiene |
|---|---|---|
| `midb.regionales` (33-34 filas) | **Sí**, embebido en `003_centros_regionales.sql` y `004_regionales.sql` | Se cargan al aplicar las migraciones |
| `midb.centros` (118 filas) | **Sí**, embebido en `003_centros_regionales.sql` y `005_centros.sql` | Ídem |
| `mdl_course` con `shortname` en formato SENA | **No** | Debe existir en la base de Moodle. Sin cursos con ese formato, la cascada devuelve listas vacías (sección 6.3) |
| `mdl_local_slider` (imágenes del carrusel) | **No** | Se crean desde la interfaz, o por SQL (ver `slider/DEPLOY.md`, sección 8.5) |
| `midb.saved_filters` / `midb.envios2` | **No** (arrancan vacías) | Se llenan al usar el plugin |

Los nombres de los catálogos son corregibles directamente en base, tal como documenta
`ajax/categories.php:38-40`:

```sql
UPDATE midb.regionales SET nombre = 'RISARALDA'        WHERE rgn_id = 66;
UPDATE midb.centros    SET nombre = 'CENTRO ...'       WHERE sed_id = 9308;
```

---

## 9. Servicios auxiliares

### 9.1 Servicios que sí hacen falta

| Servicio | Unidad systemd | Obligatorio | Verificación |
|---|---|---|---|
| Apache | `apache2` | Sí | `systemctl is-active apache2` |
| PostgreSQL | `postgresql` | Sí | `systemctl is-active postgresql` |

**No hay Redis, RabbitMQ, Kafka, Elasticsearch, MongoDB ni MinIO.** La caché MUC usa el *store*
por defecto de Moodle (sistema de archivos bajo `$CFG->dataroot`) y no requiere ningún demonio.

### 9.2 El servicio de correo — **externo y fuera de este repositorio**

Es el punto que más confusión genera en QA, así que se declara sin rodeos:

> **`local_slider_form` NO envía correo.** No hay `email_to_user()`, ni `message_send()`, ni
> `mail()`, ni configuración SMTP en ninguna parte del repositorio (búsqueda explícita: cero
> resultados). `ajax/send_segmented.php` hace `INSERT` en `midb.envios2` y responde
> `"Se programó el envío a N destinatario(s) correctamente."` (`ajax/send_segmented.php:376-380`).
> **Programar ≠ enviar.**

| Aspecto | Estado |
|---|---|
| Quién consume `midb.envios2` | Un proceso externo, **no versionado en este repositorio** |
| Cómo se despliega ese proceso | **Desconocido desde el repositorio.** Confirmar con el equipo responsable |
| Qué actualiza | `envios2.estado` (`'pendiente'` → `'enviado'`) y `envios2.sent_at` (sección 8.5) |
| Servidor SMTP | No configurado por este plugin. Si el proceso externo usa el SMTP de Moodle, se configura en *Administración del sitio → Servidor → Correo electrónico → Configuración SMTP* |

**Qué significa para el entorno local:** puedes desplegar, probar y validar `local_slider_form`
**completo** sin ningún servicio de correo. El resultado observable de un envío es **filas nuevas
en `midb.envios2`**, no correos en una bandeja. El smoke test (sección 16) está construido sobre
esa premisa.

```sql
-- Comprobar el resultado real de un envío:
SELECT asunto, count(*) AS destinatarios, min(created_at) AS lote
  FROM midb.envios2 GROUP BY asunto, created_at ORDER BY lote DESC LIMIT 5;
```

---

## 10. Build

**No hay build.** No existe `package.json`, `composer.json`, `Makefile` ni artefacto de
empaquetado. El «build» equivale a copiar ficheros y ejecutar el upgrade de Moodle.

```bash
DIRROOT=/var/www/zajuna
REPO=/ruta/al/repositorio/anuncios_de_plataforma

# 0. PRERREQUISITO: local_slider ya desplegado (ver slider/DEPLOY.md)

# 1. Copiar el plugin
sudo rsync -a --delete \
  --exclude '.git*' --exclude '.vscode/' --exclude '.claude/' \
  --exclude '*.zip' --exclude 'DEPLOY.md' --exclude 'CLAUDE.md' \
  --exclude 'prueba.html' \
  --exclude 'classes/forms/Insert.php10122025' \
  --exclude 'docs/*.puml' --exclude 'docs/*.mmd' \
  "$REPO/slider_form/" "$DIRROOT/local/slider_form/"

# 2. Propietario y permisos
sudo chown -R www-data:www-data "$DIRROOT/local/slider_form"
sudo find "$DIRROOT/local/slider_form" -type d -exec chmod 755 {} \;
sudo find "$DIRROOT/local/slider_form" -type f -exec chmod 644 {} \;

# 3. Registrar/actualizar el plugin (capabilities + config; NO ejecuta db/migrations/)
sudo -u www-data php "$DIRROOT/admin/cli/upgrade.php" --non-interactive

# 4. Migraciones midb.* — MANUALES (sección 8.4). NO se ejecutan solas.

# 5. Purgar cachés
sudo -u www-data php "$DIRROOT/admin/cli/purge_caches.php"
```

### 10.1 Qué copiar y qué NO copiar

**Obligatorio copiar aunque parezca documentación:**

| Ruta | Motivo |
|---|---|
| **`docs/Cuerpo_Correo.html`** | **Plantilla del correo leída en tiempo de ejecución** (`ajax/send_segmented.php:298`). Sin ella, el envío devuelve 500. |
| `db/migrations/*.sql` | Los necesitas en el servidor para aplicarlos con `psql` (sección 8.4). |
| `lang/es/`, `lang/en/` | Cadenas de interfaz, incluida `manage_slider` del menú de administración (`lang/es/local_slider_form.php:62`). |
| `css/formUpdate.css`, `js/script.js` | Estáticos del formulario. |

**No copiar:**

| Ruta | Motivo |
|---|---|
| `classes/forms/Insert.php10122025` | Respaldo de desarrollo. Extensión no-PHP, pero servible por Apache como texto plano: **expondría código fuente**. |
| `prueba.html` | Fichero de pruebas suelto bajo el `DocumentRoot`. |
| `docs/*.puml`, `docs/*.mmd` | Diagramas fuente; solo documentación. |
| `DEPLOY.md`, `CLAUDE.md`, `README.md`, `LICENSE.md`, resto de `docs/*.md` | Documentación. |
| `.git/`, `.gitignore`, `.vscode/`, `.claude/` | Metadatos de desarrollo. `.git/` bajo el `DocumentRoot` es un riesgo de seguridad. |
| `*.zip` de la raíz del repositorio | Paquetes históricos. |

> **Verificación tras copiar** — que no quede nada indebido servible por HTTP:
> ```bash
> curl -s -o /dev/null -w '%{http_code}\n' http://localhost/zajuna/local/slider_form/prueba.html
> # esperado: 404
> curl -s -o /dev/null -w '%{http_code}\n' \
>   http://localhost/zajuna/local/slider_form/classes/forms/Insert.php10122025
> # esperado: 404
> ```

### 10.2 Cuándo hay que subir la versión

Cualquier cambio de código que deba llegar al servidor exige incrementar `$plugin->version` en
`slider_form/version.php:29` (formato entero `AAAAMMDDXX`) **antes** de ejecutar
`admin/cli/upgrade.php`. Si no se incrementa, Moodle no ejecuta el upgrade y —con OPcache
activo— puede seguir sirviendo el código anterior.

### 10.3 Concesión de *capabilities* — paso obligatorio post-instalación

Las dos *capabilities* tienen **arquetipos vacíos** (`slider_form/db/access.php:9`, `:15`):
**ningún rol las recibe automáticamente, ni siquiera el de administrador del sitio**. Tras
instalar, nadie salvo el superadministrador (que las tiene por *bypass*) verá el plugin.

Por interfaz — *Administración del sitio → Usuarios → Permisos → Definir roles* → editar el rol
→ marcar:

- `local/slider_form:view` — acceso de solo lectura (menú, historial, exportar reportes).
- `local/slider_form:edit` — acceso de escritura (CRUD del carrusel, envío segmentado). Implica
  `:view` (`slider_form/lib/usersValidations.php:76-77`). Marcada con
  `RISK_SPAM | RISK_XSS` (`db/access.php:12`) por razones evidentes: permite enviar correo masivo.

Verificación:

```sql
SELECT r.shortname, rc.capability, rc.permission
  FROM mdl_role_capabilities rc
  JOIN mdl_role r ON r.id = rc.roleid
 WHERE rc.capability LIKE 'local/slider_form:%'
 ORDER BY r.shortname, rc.capability;
```

> **Nota histórica:** en la versión 0.4.0 la *capability* única `:manage` se dividió en
> `:view`/`:edit`. El bloque `2026070200` de `slider_form/db/upgrade.php:17-39` migra las
> concesiones existentes automáticamente. **No reintroduzcas `:manage`.**

---

## 11. Reverse proxy / Web server

### 11.1 Situación real

**El proyecto no usa un reverse proxy.** No hay Nginx, Caddy ni Traefik en el repositorio ni en
la máquina de referencia. **Apache es simultáneamente el servidor web y el punto de entrada
público**, y ejecuta PHP en proceso vía `mod_php`.

La instrucción de «evitar que QA acceda al puerto interno de la aplicación» **se cumple por
construcción**: no existe un puerto interno de aplicación distinto del 80. QA entra por
`http://localhost/zajuna`, que es exactamente el punto de entrada del servidor real.

### 11.2 Configuración de Apache

Ver el bloque de la sección 4.3 — se reproduce tal cual el del servidor. Puntos a entender:

- **`DocumentRoot` es `/var/www/html`, no Moodle.** Moodle cuelga por el symlink
  `/var/www/html/zajuna → /var/www/zajuna`, de ahí que `wwwroot` sea `http://localhost/zajuna`.
- **`Options FollowSymLinks`** viene del bloque `<Directory /var/www/>` de `apache2.conf`. Sin
  él, **403**.
- **`AllowOverride FileInfo`** permite `.htaccess` para cabeceras/reescrituras; Moodle no lo
  requiere.

### 11.3 Routing

No hay reglas de reescritura ni *proxy pass*: cada `.php` del plugin se resuelve por ruta física
bajo `local/slider_form/`. La tabla completa de rutas está en la sección 13.3.

### 11.4 Cabeceras

- **No se necesita ninguna cabecera de proxy.** El plugin no lee `X-Forwarded-For`,
  `X-Forwarded-Proto` ni equivalentes (grep sin resultados).
- **Cabeceras que el plugin sí emite**: `Content-Type: application/json; charset=utf-8` en los
  endpoints AJAX (`ajax/send_segmented.php:25`, `ajax/categories.php:48`) y las de descarga que
  genera `MoodleExcelWorkbook` en `ajax/export_envios.php:127`.
- **Cabecera que el plugin sí exige del cliente**: `ajax/send_segmented.php` **rechaza** con 415
  cualquier petición cuyo `Content-Type` no empiece por `application/json`
  (`ajax/send_segmented.php:44-48`). Es una defensa anti-CSRF deliberada: **si un proxy
  reescribiera esa cabecera, el envío dejaría de funcionar.**

### 11.5 Archivos estáticos

Apache los sirve directamente desde `local/slider_form/`: `css/formUpdate.css` y `js/script.js`
(registrados en `index.php:31-32`). El resto del CSS y el JS va **inline** dentro de
`segmented.php`, `send_logs.php` y `table_logs.php`.

### 11.6 Si tu instalación sí tiene un proxy delante

Fuera del alcance del repositorio. Si Apache quedara detrás de otro proxy, `$CFG->wwwroot` debe
seguir siendo la URL **pública** y habría que configurar `$CFG->reverseproxy` / `$CFG->sslproxy`
en `config.php` (ajustes de Moodle core). **En el repositorio no hay nada que lo indique ni lo
requiera**, y habría que verificar que el proxy no altera el `Content-Type` de los POST JSON
(sección 11.4).

---

## 12. Frontend

### 12.1 Cómo se sirve realmente

No hay frontend compilado, ni SSR, ni framework. Todo es **HTML generado por PHP dentro del tema
de Moodle**, con CSS y JavaScript escritos a mano.

| Página | Qué renderiza | Estáticos |
|---|---|---|
| `menu.php` | Hub con tres botones. Los de escritura solo si `has_capability(':edit')` (`menu.php:18`, `:96`) | CSS inline |
| `index.php` | Formulario de alta (`classes/forms/Insert.php`) | `css/formUpdate.css`, `js/script.js` (`index.php:31-32`) |
| `manage_images.php` | Tabla de gestión con paginación (`classes/table/Table_manage.php`) | Ídem |
| `show_order.php` | Reordenación de despliegue (`classes/table/Table_order.php`) | Ídem |
| `segmented.php` | **La página compleja**: cascada de filtros, vista previa, envío. ~2 400 líneas con CSS y JS inline | Sin estáticos externos |
| `send_logs.php` | Listado de lotes de envío con filtros y ordenación en cliente | CSS y JS inline |
| `table_logs.php` | Detalle de un lote («Ver más») | CSS y JS inline |

Los formularios son clases PHP con un método `display()` capturado mediante `ob_start()`; ver
`renderForm()` en `index.php:81-89`.

### 12.2 La cascada de `segmented.php`

Encadena cinco llamadas AJAX a `ajax/categories.php`, cada una filtrada por la selección anterior
(`ajax/categories.php:88-245`):

```
Nivel de formación (?action=modalidades&tipo=…)
        ↓
Regionales        (?action=regionales&categorias=[…])
        ↓
Centros           (?action=centros&categorias=[…]&regional_ids=[…])
        ↓
Programas         (?action=programas&…&centro_ids=[…])
        ↓
Fechas            (?action=fechas&…&programa_codes=[…])
        ↓
Roles             (?action=roles)
```

Todas usan `fetch(url, { credentials: 'include' })` (`segmented.php:1521`), por lo que dependen
de la cookie de sesión de Moodle — de ahí la advertencia de la sección 5.

**Si un nivel devuelve una lista vacía, la cascada se detiene ahí sin mensaje de error.** Casi
siempre significa datos, no código: IDs de categoría incorrectos (sección 6.3) o `shortname` que
no siguen el formato SENA.

### 12.3 Restricciones de imagen — dos conjuntos distintos

Fáciles de confundir; son requisitos diferentes para funciones diferentes:

| Función | Formatos | Dimensiones | Peso máximo | Validado en |
|---|---|---|---|---|
| **Imagen del carrusel** | JPEG, PNG, WebP | **exactamente 1920×720 px** | 5 MB (5 242 880 B) | `lib/fieldsValidations.php:91-94`, `:121` |
| **Imagen del correo segmentado** | **solo WebP** | **exactamente 622×233 px** | **50 KB** (51 200 B) | `ajax/send_segmented.php:95`, `:112`, `:115` |

En ambos casos el MIME se comprueba con `finfo` sobre el contenido real, no por la extensión
(`fieldsValidations.php:96-98`, `send_segmented.php:101-103`), y la imagen se abre con GD para
confirmar que es válida.

---

## 13. Backend

| Aspecto | Valor real | Referencia |
|---|---|---|
| Runtime | PHP 8.2.33 ejecutado por Apache (`mod_php`) | `php -v` |
| Comando de build | Ninguno | Sección 10 |
| Comando de ejecución | Ninguno propio: el ciclo de vida lo controla Apache | — |
| Host/interfaz de escucha | Apache en `*:80`; **el plugin no escucha en ningún socket** | `000-default.conf:1` |
| Necesidad de escuchar en `0.0.0.0` | **No aplica**: no hay proceso de aplicación separado ni contenedor | — |
| Punto de entrada de administración | `admin_externalpage` `local_slider_form_manage` → `menu.php` | `slider_form/settings.php:16-21` |
| Conexiones salientes | Una: el PDO a PostgreSQL (`localhost:5432`) | `ZajunaDbConnection.php:27-30` |

### 13.1 Modelo de autorización

Cada página y cada endpoint aplica la misma secuencia de guardas
(`slider_form/lib/usersValidations.php`):

1. `require_login()` — sesión de Moodle.
2. `checkSession($action, $params)` — `isloggedin()` (`:26-34`).
3. `checkUserRole($action, $params, $level)` — que a su vez llama a `checkBannerVisible()`
   (interruptor global, `:46-60`) y luego comprueba la *capability* (`:68-90`).
4. En escritura: `checkCsrfToken($sesskey)` → `confirm_sesskey()` (`:93-107`).

`$action` es `'redirect'` en páginas (envía a `/login/index.php`) y `'exception'` en AJAX
(devuelve JSON con código HTTP).

### 13.2 Nivel de permiso exigido por endpoint

| Recurso | Nivel | Referencia |
|---|---|---|
| `menu.php` | `view` | `menu.php:18` |
| `index.php`, `manage_images.php`, `show_order.php`, `segmented.php` | `edit` (valor por defecto) | `index.php:37`, `segmented.php:17` |
| `insertRecord.php`, `updateRecord.php`, `deleteRecord.php`, `order.php` | `edit` + CSRF | `insertRecord.php:77`, `updateRecord.php:60`, `deleteRecord.php:32`, `order.php:35` |
| `send_logs.php`, `table_logs.php` | `view` | `send_logs.php:25`, `table_logs.php:25` |
| `ajax/export_envios.php` | `view` | `ajax/export_envios.php:22` |
| `ajax/send_segmented.php` | `edit` + CSRF + `Content-Type: application/json` | `ajax/send_segmented.php:41-48` |
| `ajax/categories.php` | `edit` (comprobación propia con `has_capability`) | `ajax/categories.php:64-70` |
| `ajax/saved_filters.php`, `ajax/preview_correo.php` | `edit` | `ajax/saved_filters.php:38`, `ajax/preview_correo.php:64` |
| `active_role_users.php` | `edit` (con `require_capability`, no `checkUserRole`) + interruptor global | `active_role_users.php:21-33` |

### 13.3 Rutas HTTP del plugin

Base: `http://localhost/zajuna/local/slider_form/`

| Ruta | Método | Función |
|---|---|---|
| `menu.php` | GET | Hub |
| `index.php` | GET | Alta de imagen |
| `insertRecord.php` | POST | Crear registro (JSON) |
| `manage_images.php` | GET | Gestión de imágenes |
| `updateRecord.php` | POST | Editar registro (JSON) |
| `deleteRecord.php` | POST | Eliminar registro (JSON) |
| `show_order.php` | GET | Orden de despliegue |
| `order.php` | POST | Guardar orden (JSON) |
| `segmented.php` | GET | Formulario de envío segmentado |
| `send_logs.php` | GET | Historial de lotes |
| `table_logs.php` | GET | Detalle de lote (`?asunto=&created_at=`) |
| `active_role_users.php` | POST | Usuarios activos por rol (JSON) |
| `ajax/categories.php` | GET | Cascada de filtros (`?action=…`) |
| `ajax/send_segmented.php` | POST JSON | **Encola el envío en `midb.envios2`** |
| `ajax/preview_correo.php` | POST JSON / GET | Vista previa con destinatario aleatorio (token de sesión, TTL 1 h) |
| `ajax/saved_filters.php` | GET / POST JSON | Listar y eliminar filtros propios |
| `ajax/export_envios.php` | GET | Descarga XLSX (`?asunto=&created_at=&scope=`) |

Entrada por el menú de administración:
`http://localhost/zajuna/admin/settings.php?section=local_slider_form_manage`

### 13.4 Configuración de producción vs. local

No hay ninguna en el código. Las únicas diferencias son `config.php`, los IDs de categoría
(sección 6.3) y los datos. Para paridad de rendimiento conviene igualar `opcache.enable=1`,
`memory_limit` y `max_execution_time` con los del servidor.

---

## 14. Inicio del entorno

### 14.1 Arranque de servicios

No hay unidades systemd propias del proyecto ni Supervisor/PM2/Gunicorn:

```bash
sudo systemctl enable --now postgresql
sudo systemctl enable --now apache2
systemctl is-active postgresql apache2   # → active / active
```

El orden importa: con PostgreSQL caído, Moodle devuelve error de conexión en cada petición.

### 14.2 Secuencia completa desde cero

```bash
DIRROOT=/var/www/zajuna

sudo systemctl start postgresql
sudo systemctl start apache2

# 1. Verificar que Moodle ve la base
sudo -u www-data php "$DIRROOT/admin/cli/cfg.php" --name=wwwroot

# 2. PRERREQUISITO: local_slider instalado (slider/DEPLOY.md)
psql -h localhost -U postgres -d zajunadb -Atc "SELECT to_regclass('public.mdl_local_slider');"
# → mdl_local_slider

# 3. Esquema midb + migraciones manuales (secciones 8.3 y 8.4)
psql -h localhost -U postgres -d zajunadb -c 'CREATE SCHEMA IF NOT EXISTS midb;'
# … aplicar db/migrations/001 … 013 en orden …

# 4. Upgrade de Moodle (capabilities + config del plugin)
sudo -u www-data php "$DIRROOT/admin/cli/upgrade.php" --non-interactive

# 5. Purgar cachés
sudo -u www-data php "$DIRROOT/admin/cli/purge_caches.php"

# 6. Confirmar registro del plugin
sudo -u www-data php "$DIRROOT/admin/cli/cfg.php" --component=local_slider_form

# 7. Conceder capabilities a un rol (sección 10.3) — si no, nadie salvo el
#    superadministrador verá el plugin.
```

### 14.3 Invalidar la caché del banner

Necesario tras cambios de datos hechos **por fuera de la interfaz**. La interfaz lo hace sola
(`slider_form/lib/utilsFunctions.php:217-222`):

```bash
sudo -u www-data php -r '
define("CLI_SCRIPT", true);
require "/var/www/zajuna/config.php";
$c = cache::make("local_slider", "imagecache");
$c->delete("images_site");
$c->delete("images_course");
echo "imagecache invalidada\n";'
```

---

## 15. Verificación

### 15.1 Servicios

```bash
systemctl is-active apache2 postgresql   # → active / active
sudo apachectl configtest                # → Syntax OK
ss -ltnp | grep -E ':80|:5432'
```

### 15.2 Extensiones PHP críticas

```bash
php -m | grep -E '^(pdo_pgsql|pgsql|gd|zip|fileinfo)$'
# → los 5

php -r 'var_dump(gd_info()["WebP Support"]);'
# → bool(true)   ← sin esto, el envío segmentado rechaza toda imagen
```

### 15.3 Base de datos y esquema `midb`

```bash
psql -h localhost -U postgres -d zajunadb -c '\conninfo'

psql -h localhost -U postgres -d zajunadb <<'SQL'
SELECT nspname FROM pg_namespace WHERE nspname = 'midb';
SELECT table_name FROM information_schema.tables
 WHERE table_schema = 'midb' ORDER BY table_name;
SELECT 'regionales' AS t, count(*) FROM midb.regionales
UNION ALL SELECT 'centros', count(*) FROM midb.centros;
SQL
```

Esperado: el esquema existe; cuatro tablas (`centros`, `envios2`, `regionales`,
`saved_filters`); catálogos con ~33 y ~118 filas.

### 15.4 Dependencia del plugin hermano

```bash
psql -h localhost -U postgres -d zajunadb -Atc "SELECT to_regclass('public.mdl_local_slider');"
# → mdl_local_slider (si está vacío: falta desplegar local_slider)

sudo -u www-data php -r '
define("CLI_SCRIPT", true);
require "/var/www/zajuna/config.php";
try { cache::make("local_slider", "imagecache"); echo "imagecache OK\n"; }
catch (Throwable $e) { echo "FALLA: " . $e->getMessage() . "\n"; }'
```

### 15.5 Registro del plugin y capabilities

```bash
sudo -u www-data php /var/www/zajuna/admin/cli/cfg.php --component=local_slider_form
# → Anuncios_Plataforma_Admin_Banner_Version = 2026072800
# → Anuncios_Plataforma_Admin_Banner_Visible = 1
```

Coteja con `$plugin->version` de `slider_form/version.php:29`.

```sql
-- ¿Las capabilities están registradas?
SELECT name FROM mdl_capabilities WHERE name LIKE 'local/slider_form:%';
-- esperado: local/slider_form:edit, local/slider_form:view
-- (si aún aparece local/slider_form:manage, el upgrade 2026070200 no corrió)

-- ¿Algún rol las tiene concedidas?
SELECT r.shortname, rc.capability
  FROM mdl_role_capabilities rc JOIN mdl_role r ON r.id = rc.roleid
 WHERE rc.capability LIKE 'local/slider_form:%' AND rc.permission = 1;
```

### 15.6 Health checks de la plataforma

`local_slider_form` **no expone ningún endpoint de health check propio** — no hay `/health` ni
`/status` en el repositorio. Los disponibles son los de **Moodle core**:

| Health check | Cómo se ejecuta | Qué cubre |
|---|---|---|
| Comprobaciones del sitio (CLI) | `sudo -u www-data php /var/www/zajuna/admin/cli/checks.php` | Base de datos, cachés, `dataroot`, tareas, seguridad. Código de salida ≠ 0 si hay fallos. |
| Comprobaciones del sitio (web) | `http://localhost/zajuna/report/status/index.php` (requiere administrador) | Lo mismo, en interfaz. |
| Camino B (PDO a `midb`) | El propio `ajax/categories.php?action=modalidades`: si responde 200, la conexión PDO y el esquema funcionan. | Ver smoke test paso 5. |
| Base de datos | `psql ... -c '\conninfo'` | Capa de datos. |
| Servidor web | `sudo apachectl configtest` + `curl -I http://localhost/zajuna/` | Capa web. |

---

## 16. Smoke test

Se ejecuta **desde el mismo punto de entrada que usaría un usuario externo**:
`http://localhost/zajuna`. No hay ningún puerto interno que evitar (sección 11.1).

### 16.1 Precondiciones

- Verificación de la sección 15 superada.
- `local_slider` desplegado.
- Un usuario con `local/slider_form:edit` concedida (sección 10.3), o superadministrador.
- Cursos en `mdl_course` con `visible = 1` y `shortname` en formato SENA (sección 6.3), y
  usuarios matriculados activos, para que la cascada devuelva resultados.
- Dos imágenes de prueba: una de **1920×720** (carrusel) y otra **WebP de 622×233 y < 50 KB**
  (correo).

### 16.2 Bloque A — acceso y gestión del carrusel

| # | Acción | Resultado esperado |
|---|---|---|
| 1 | `curl -I http://localhost/zajuna/` | `200` o `303`. Un `403` apunta a `FollowSymLinks`; un `500`, al `error_log`. |
| 2 | Iniciar sesión en `http://localhost/zajuna/login/index.php` | Sesión establecida. |
| 3 | Abrir *Administración del sitio* | Aparece **«Administrar Banner Plataforma»** (`lang/es/local_slider_form.php:62`) en el menú raíz. |
| 4 | Pulsarlo (`admin/settings.php?section=local_slider_form_manage`) | Carga `menu.php` con «Publicar anuncio a todos», «Envío segmentado» e «Historial de envíos». |
| 5 | *Publicar anuncio a todos* → subir la imagen de **1920×720**, estado activo, guardar | Mensaje «El registro se creó de manera correcta.» |
| 6 | Verificar en base | `SELECT id, name, state, length(desktop_image) FROM mdl_local_slider ORDER BY id DESC LIMIT 1;` devuelve la fila con base64 no vacío. |
| 7 | Abrir `http://localhost/zajuna/my/courses.php` | **La imagen aparece en el banner sin purgar cachés** — confirma que `deleteSliderCache()` funcionó (`lib/utilsFunctions.php:217-222`) y que la integración con `local_slider` es correcta. |
| 8 | *Gestionar imágenes* → editar y eliminar el registro | Los cambios se reflejan en `/my/courses.php` tras recargar. |
| 9 | Subir una imagen con dimensiones incorrectas | Se rechaza con error de dimensiones (`lib/fieldsValidations.php:121`). **Un rechazo es el resultado correcto.** |

### 16.3 Bloque B — envío segmentado

| # | Acción | Resultado esperado |
|---|---|---|
| 10 | Abrir `segmented.php` | El desplegable **«Nivel de formación»** se llena. En *Network*, `ajax/categories.php?action=modalidades` responde **200**. **Un 500 aquí es el síntoma clásico**: ver sección 19.2. |
| 11 | Elegir un nivel | Cargan las **regionales** (200 en `?action=regionales`). Confirma que el camino PDO y `midb.regionales` funcionan. |
| 12 | Recorrer la cascada: regional → centro → programa → fechas | Cada nivel se llena. Una lista vacía indica datos, no código (sección 6.3). |
| 13 | Seleccionar roles, asunto y la imagen **WebP 622×233 < 50 KB** | El formulario los acepta. |
| 14 | *Vista previa* | Se abre el HTML del correo con un destinatario real aleatorio, la imagen y el asunto. Confirma que `docs/Cuerpo_Correo.html` está desplegado (sección 7.5). |
| 15 | Probar una imagen JPEG o de otro tamaño | Rechazo con «Formato inválido: solo se permite WebP» o «Dimensiones inválidas» (`ajax/send_segmented.php:112`, `:116`). **El rechazo es el resultado correcto.** |
| 16 | Confirmar el envío | Respuesta JSON `{"success":true,"count":N,...}` con `N > 0` y mensaje «Se programó el envío a N destinatario(s) correctamente.» |
| 17 | **Verificar el resultado real en base** | Ver consulta más abajo. **Este es el criterio de éxito**, no una bandeja de correo (sección 9.2). |
| 18 | Marcar «guardar filtro», enviar de nuevo, y recargar `segmented.php` | El filtro aparece en la lista de filtros guardados (`ajax/saved_filters.php?action=list`). |

```sql
-- Paso 17: el envío quedó encolado
SELECT asunto, created_at, count(*) AS destinatarios
  FROM midb.envios2 GROUP BY asunto, created_at ORDER BY created_at DESC LIMIT 3;

-- El detalle por ficha se persistió (efecto de la migración 013)
SELECT destinatario, jsonb_array_length(cursos) AS fichas
  FROM midb.envios2 ORDER BY id DESC LIMIT 5;

-- El filtro quedó registrado (estado 0 = envió sin guardar, 1 = guardado)
SELECT id, nombre, modalidad, regional_id, centro_id, programa_id, roles, estado, created_at
  FROM midb.saved_filters ORDER BY id DESC LIMIT 3;
```

> **`count = 0` con la cascada llena** es un caso conocido y documentado: significa que la
> resolución encontró cursos pero ningún usuario con matrícula activa (`ue.status = 0`) y el rol
> seleccionado. Ver sección 19.5.

### 16.4 Bloque C — historial y reportes

| # | Acción | Resultado esperado |
|---|---|---|
| 19 | Abrir `send_logs.php` | Lista de lotes con totales de enviados y pendientes. **Si falla con `column "estado" does not exist`, aplica la sección 8.5.** |
| 20 | *Ver más* en un lote (`table_logs.php`) | Detalle por destinatario con estado y fecha. |
| 21 | Descargar un reporte (*Pendientes* / *Enviados*) | Se descarga un `.xlsx` que abre correctamente. Confirma la extensión `zip` y `excellib`. |

### 16.5 Bloque D — permisos e interruptor

| # | Acción | Resultado esperado |
|---|---|---|
| 22 | Como usuario con **solo** `:view` | En `menu.php` **solo** se ve «Historial de envíos» (`menu.php:96`). `index.php` y `segmented.php` redirigen a login. |
| 23 | Como usuario **sin ninguna** capability | El nodo del menú de administración no aparece; el acceso directo a `menu.php` redirige. |
| 24 | Apagar el interruptor (sección 6.2) y recargar como no superadministrador | El nodo desaparece y todas las páginas y AJAX devuelven 403 **sin purgar cachés**. Como superadministrador **sí** sigue accesible. |
| 25 | Volver a encenderlo | El acceso se restablece de inmediato. |

### 16.6 Qué cubre cada bloque

| Capa del enunciado | Bloque / paso |
|---|---|
| Aplicación accesible desde el punto de entrada | A: 1–4 |
| Frontend funcionando | A: 5, 8 · B: 10–14 |
| Backend funcionando | A: 5–9 · B: 15–18 · C: 19–21 |
| Conexión con base de datos — **camino A (`$DB`)** | A: 6, 7 |
| Conexión con base de datos — **camino B (PDO a `midb`)** | B: 11, 17 · C: 19 |
| Health check | Sección 15.6 |
| Funcionalidad básica disponible | Todos los bloques; D cubre permisos e interruptor |

---

## 17. Logs

`local_slider_form` **no escribe logs propios**. No emite eventos de Moodle ni usa la tabla
`mdl_local_slider_errors` (que existe en el esquema de `local_slider` pero nadie usa). Todo el
diagnóstico sale de las capas inferiores.

| Capa | Comando | Notas |
|---|---|---|
| **Apache — errores** | `sudo tail -f /var/log/apache2/reposena_error.log` | Definido en `000-default.conf:11`. **Aquí aparecen los errores fatales de PHP y las excepciones PDO no capturadas.** |
| **Apache — accesos** | `sudo tail -f /var/log/apache2/reposena_access.log` | Formato `combined`. Útil para ver los códigos de los AJAX. |
| **Apache — servicio** | `sudo journalctl -u apache2 -f` | Arranques, recargas, `configtest`. |
| **PHP** | Sin `error_log` propio ⇒ va al `ErrorLog` de Apache. Comprobar: `php -i \| grep -E '^error_log'`. | |
| **PostgreSQL** | `sudo tail -f /var/log/postgresql/postgresql-16-main.log` | **La fuente clave del camino B**: errores de sintaxis SQL, columnas inexistentes, permisos sobre `midb`. |
| **PostgreSQL — servicio** | `sudo journalctl -u postgresql -f` | |
| **Respuestas de error del plugin** | Pestaña *Network* del navegador: los endpoints devuelven JSON `{"error":"…"}` con el código HTTP correspondiente (`ajax/send_segmented.php:382-389`) | **El diagnóstico más directo del envío segmentado.** |
| **Moodle — depuración** | *Administración del sitio → Desarrollo → Modo de depuración*: `DEVELOPER` + «Mostrar mensajes de depuración» | ⚠️ **Solo en local.** Expone rutas, credenciales en trazas y consultas. |
| **Moodle — log de eventos** | *Administración del sitio → Informes → Registros* | El plugin **no emite eventos propios**; no encontrarás entradas suyas. |
| **Contenedores** | No aplica: no hay Docker. | |

Filtros útiles:

```bash
sudo grep -i "slider_form" /var/log/apache2/reposena_error.log | tail -50
sudo grep -iE "midb\.|zajunadb" /var/log/postgresql/postgresql-16-main.log | tail -50
```

Para ver consultas lentas del camino B (útil con `count` alto), activa temporalmente en
`postgresql.conf`:

```
log_min_duration_statement = 1000   # milisegundos
```
y recarga con `sudo systemctl reload postgresql`.

---

## 18. Reinicio

```bash
DIRROOT=/var/www/zajuna

# ── 1. Detener (orden inverso al de arranque) ──
sudo systemctl stop apache2
sudo systemctl stop postgresql

# ── 2. Reiniciar ──
sudo systemctl start postgresql
sudo systemctl start apache2

# ── 3. Verificar dependencias ──
systemctl is-active postgresql apache2
psql -h localhost -U postgres -d zajunadb -c '\conninfo'

# ── 4. Verificar migraciones ──
#    4a. Lado Moodle (idempotente)
sudo -u www-data php "$DIRROOT/admin/cli/upgrade.php" --non-interactive
#    Esperado si está al día: "No upgrade needed for the installed version"

#    4b. Lado midb (NO se ejecutan solas; solo se comprueba que persisten)
psql -h localhost -U postgres -d zajunadb -Atc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='midb';"
# → 4

# ── 5. Health checks ──
sudo -u www-data php "$DIRROOT/admin/cli/checks.php"

# ── 6. Smoke test ──
# Repetir la sección 16 completa. Presta atención a los pasos 10-11:
# confirman que la conexión PDO se reestableció tras el reinicio.
```

Prueba de resistencia al reinicio de la máquina:

```bash
sudo systemctl enable postgresql apache2
sudo reboot
# Al volver: repetir pasos 3-6.
```

Comprobación de que los datos persistieron (nada vive solo en memoria de proceso):

```sql
SELECT count(*) FROM midb.envios2;
SELECT count(*) FROM midb.saved_filters;
SELECT count(*) FROM mdl_local_slider;
```

> **El PDO es un singleton por petición** (`ZajunaDbConnection.php:12`), no un *pool*
> persistente: no hay conexiones que «recuperar» tras el reinicio. La primera petición tras
> reiniciar PostgreSQL abre una conexión nueva.

---

## 19. Troubleshooting

### 19.1 El plugin no aparece en el menú de administración

| Causa | Cómo confirmarla | Solución |
|---|---|---|
| **Capabilities sin conceder** (la causa más frecuente) | La consulta de la sección 15.5 no devuelve filas | Conceder `:view` y/o `:edit` a un rol (sección 10.3) |
| Interruptor apagado | `SELECT value FROM mdl_config_plugins WHERE plugin='local_slider_form' AND name='Anuncios_Plataforma_Admin_Banner_Visible';` = `0` | `UPDATE ... SET value='1'` (sección 6.2) |
| Plugin no registrado | `admin/cli/cfg.php --component=local_slider_form` no devuelve nada | Ejecutar sección 10 completa |
| `version.php` no se incrementó | La versión registrada es menor que `slider_form/version.php:29` | Subir `$plugin->version` y reejecutar `upgrade.php` |
| Caché de administración | Todo lo anterior correcto pero el nodo no aparece | `sudo -u www-data php admin/cli/purge_caches.php` |
| OPcache | El código en disco es correcto pero el comportamiento no cambia | `sudo systemctl reload apache2` |

### 19.2 «Error al cargar modalidades: Error al obtener datos (500)»

Es **el error más reportado** de este plugin. Abre *Network*, mira la respuesta de
`ajax/categories.php?action=modalidades` y compara con esta tabla:

| Respuesta / síntoma | Causa | Solución |
|---|---|---|
| `SQLSTATE[08006] ... password authentication failed` | Credenciales de `config.php` inválidas para PostgreSQL | Corregir `$CFG->dbpass`; verificar con `psql` (sección 8.6). **No** edites `ZajunaDbConnection.php`: hoy toma todo de `$CFG` (`:21-25`) |
| `could not find driver` | Falta `pdo_pgsql` | `sudo apt install php8.2-pgsql && sudo systemctl restart apache2` |
| `SQLSTATE[3F000] schema "midb" does not exist` | El esquema nunca se creó | Sección 8.3 |
| `SQLSTATE[42P01] relation "midb.regionales" does not exist` | Migraciones no aplicadas | Sección 8.4 |
| `SQLSTATE[42P01] relation "mdl_course" does not exist` | `$CFG->prefix` ≠ `mdl_` | Sección 2.2. **El SQL crudo no puede adaptarse al prefijo** |
| `permission denied for schema midb` | El usuario de Moodle no tiene privilegios sobre `midb` | Sección 8.3, bloque `GRANT` |
| **200 pero lista vacía** | IDs de categoría hardcodeados que no existen en tu base | **Sección 6.3** |
| `401` | Sesión perdida o acceso por una URL distinta de `$CFG->wwwroot` | Sección 5 |
| `403` | Falta `:edit` (`ajax/categories.php:64-70`) o interruptor apagado | Secciones 10.3 y 6.2 |

### 19.3 La cascada se detiene en un nivel (lista vacía, sin error)

No es un fallo del entorno: significa que la consulta no devolvió filas. Diagnostica de dentro
hacia fuera:

```sql
-- (a) ¿Hay cursos visibles con el formato de shortname esperado?
SELECT count(*) FROM mdl_course
 WHERE visible = 1 AND shortname ~ '^P_\d+_.*_R_\d+_C_\d+';

-- (b) ¿Y para la familia 'presencial' (letras P / PI)?
SELECT count(*) FROM mdl_course
 WHERE visible = 1 AND shortname ~ '^P_\d+_PI?_\d+_R_\d+_C_\d+';

-- (c) ¿Qué regionales y centros aparecen realmente en los shortname?
SELECT DISTINCT substring(shortname from '_R_(\d+)') AS rgn,
                substring(shortname from '_C_(\d+)') AS sed
  FROM mdl_course WHERE visible = 1 AND shortname ~ '_R_\d+_C_\d+'
 ORDER BY 1, 2 LIMIT 20;

-- (d) ¿Esos rgn/sed tienen nombre en los catálogos?
SELECT rgn_id, nombre FROM midb.regionales ORDER BY rgn_id;
SELECT sed_id, nombre FROM midb.centros    ORDER BY sed_id LIMIT 20;

-- (e) ¿El código de programa se extrae del fullname?
SELECT id, fullname, substring(fullname from '\(([0-9]+)(?:_PRY_[0-9]+)?\)\s*$') AS codigo
  FROM mdl_course WHERE visible = 1 LIMIT 10;
```

Si (a) o (b) devuelven `0`, los datos de tu Moodle no siguen la convención SENA que el plugin
espera (`slider_form/lib/modalidades.php:14-35`) y la cascada **no puede** funcionar. Si (d)
devuelve nombres faltantes, la interfaz mostrará «Regional N» / «Centro N» en su lugar
(`ajax/send_segmented.php:332-333`), lo cual es degradación, no fallo.

### 19.4 El envío rechaza la imagen

| Mensaje | Requisito real | Referencia |
|---|---|---|
| `Formato inválido: solo se permite WebP.` | Solo WebP, comprobado con `getimagesize` **y** `finfo` | `ajax/send_segmented.php:112` |
| `Dimensiones inválidas (W×H). Requerido: 622×233 px.` | Exactamente 622×233 px | `:115-116` |
| `Imagen excede 50 KB.` | Máximo 51 200 bytes | `:95` |
| `No se pudo leer la imagen.` | GD no pudo abrirla | `:106-108` |

Si **toda** imagen WebP válida es rechazada con «No se pudo leer la imagen», es que GD no tiene
soporte WebP:

```bash
php -r 'var_dump(gd_info()["WebP Support"]);'   # debe ser bool(true)
sudo apt install --reinstall php8.2-gd && sudo systemctl restart apache2
```

> Ojo, no confundas con las restricciones del **carrusel**, que son distintas: JPEG/PNG/WebP,
> 1920×720, 5 MB (sección 12.3).

### 19.5 El envío responde `count = 0`

La cascada resolvió cursos pero ningún destinatario. Los tres mensajes posibles distinguen dónde
se detuvo (`ajax/send_segmented.php:160-162`, `:175-177`, `:208-210`):

| Mensaje | Significado |
|---|---|
| «No se encontraron cursos activos para el filtro indicado.» | La resolución no devolvió ningún `mdl_course.id` |
| «No se encontraron contextos de los cursos.» | Los cursos existen pero no tienen contexto (base inconsistente) |
| «No se encontraron usuarios con los roles seleccionados en los cursos filtrados.» | Hay cursos y contextos, pero ningún usuario cumple **todas** las condiciones |

Las condiciones del último caso, todas simultáneas (`ajax/send_segmented.php:190-205`):

```sql
-- ue.status = 0 (matrícula activa), u.deleted = 0, u.suspended = 0, u.email <> ''
SELECT r.shortname AS rol, count(DISTINCT u.id) AS usuarios
  FROM mdl_user u
  JOIN mdl_user_enrolments ue  ON ue.userid = u.id AND ue.status = 0
  JOIN mdl_enrol e             ON e.id = ue.enrolid
  JOIN mdl_context ctx         ON ctx.contextlevel = 50 AND ctx.instanceid = e.courseid
  JOIN mdl_role_assignments ra ON ra.userid = u.id AND ra.contextid = ctx.id
  JOIN mdl_role r              ON r.id = ra.roleid
 WHERE u.deleted = 0 AND u.suspended = 0 AND u.email <> ''
   AND e.courseid IN ( /* los ids que resolvió la cascada */ )
 GROUP BY r.shortname;
```

Sospechosos habituales: matrículas suspendidas (`ue.status = 1`), usuarios sin correo, o el rol
seleccionado asignado en un contexto distinto del de curso.

### 19.6 `send_logs.php` falla con `column "estado" does not exist`

Es el hueco documentado en la **sección 8.5**: las columnas `estado` y `sent_at` de
`midb.envios2` las crea el proceso externo de envío, no las migraciones del repositorio. Aplica
el `ALTER TABLE` de esa sección **como supuesto local** y confirma el DDL real con el equipo
responsable.

### 19.7 El envío tarda mucho o se corta a medias

`send_segmented.php` inserta una fila por destinatario dentro de una **única transacción**
(`ajax/send_segmented.php:321-348`). Con muchos destinatarios puede chocar con
`max_execution_time` (30 s en la máquina de referencia).

Síntomas: la petición muere sin respuesta JSON, o el navegador muestra un error de red; en el
`error_log` aparece `Maximum execution time of 30 seconds exceeded`.

Diagnóstico y mitigación:

```bash
# ¿Cuántos destinatarios resolvería el filtro? (ejecutar la consulta de 19.5)
grep -E "^max_execution_time" /etc/php/8.2/apache2/php.ini
```

- Segmentar más el envío (menos centros o programas por lote).
- Subir `max_execution_time` en `/etc/php/8.2/apache2/php.ini` y `systemctl reload apache2`.
  **Iguala el valor al del servidor real**, no lo subas solo en local: si no, QA validará algo
  que en producción se corta.
- Al ser transaccional, un corte hace `rollBack()` (`ajax/send_segmented.php:383-385`): no
  quedan envíos parciales. Verifícalo con la consulta del paso 17 del smoke test.

### 19.8 Los AJAX devuelven 401 aunque la sesión esté iniciada

Estás accediendo por una URL distinta de `$CFG->wwwroot`. Los `fetch()` usan
`credentials: 'include'` (`segmented.php:1521`), y la cookie de sesión está ligada al host y
ruta configurados. Entra exactamente por `http://localhost/zajuna`.

### 19.9 `Plantilla de correo no encontrada.` (500)

No se copió `docs/Cuerpo_Correo.html` al servidor (sección 7.5).

```bash
ls -l /var/www/zajuna/local/slider_form/docs/Cuerpo_Correo.html
# debe existir, ~41 KB, legible por www-data
```

El endpoint también valida que la ruta resuelta esté dentro del directorio del plugin
(`ajax/send_segmented.php:299-301`): un enlace simbólico que apunte fuera también provoca este
error.

### 19.10 Error 403 al abrir `http://localhost/zajuna/`

```bash
grep -A4 "<Directory /var/www/>" /etc/apache2/apache2.conf   # FollowSymLinks
grep -A3 "<Directory /var/www/zajuna>" /etc/apache2/sites-enabled/000-default.conf
ls -ld /var/www/html/zajuna
sudo apachectl configtest && sudo systemctl reload apache2
```

### 19.11 Error 500 en cualquier página de Moodle

```bash
sudo tail -50 /var/log/apache2/reposena_error.log
```

Causas típicas: PostgreSQL caído; ficheros no legibles por `www-data`
(`sudo chown -R www-data:www-data /var/www/zajuna/local/slider_form`); `$CFG->dataroot` no
escribible; error de sintaxis PHP (`php -l <archivo>`).

### 19.12 Puerto 80 ocupado

```bash
sudo ss -ltnp | grep ':80'
```

Detén el proceso que lo ocupa o cambia el puerto del `VirtualHost`. **Si cambias el puerto, debes
actualizar `$CFG->wwwroot`** para incluirlo; si no, Moodle redirigirá en bucle y **todos los
AJAX perderán la cookie** (sección 5).

### 19.13 Certificados locales / HTTPS

**No aplica en la configuración actual.** El entorno de referencia sirve **HTTP en el puerto 80**
(`$CFG->wwwroot = 'http://localhost/zajuna'`, `<VirtualHost *:80>`). No hay `mod_ssl` habilitado,
ni `<VirtualHost *:443>`, ni certificados en el repositorio, ni `$CFG->sslproxy`.

Por eso **este documento no incluye pasos de HTTPS**: inventarlos rompería la paridad con el
servidor tal como está configurado. Si el entorno real migra a HTTPS, habrá que (a) habilitar
`mod_ssl` y un `VirtualHost *:443`, (b) cambiar `$CFG->wwwroot` a `https://…`, y (c) revisar que
los `fetch()` sigan enviando la cookie (`Secure` + `SameSite`). Ver sección 22.5.

---

## 20. Limpieza

### 20.1 Limpieza segura (no destruye datos)

```bash
DIRROOT=/var/www/zajuna

sudo systemctl stop apache2
sudo -u www-data php "$DIRROOT/admin/cli/purge_caches.php"
sudo logrotate -f /etc/logrotate.d/apache2
sudo systemctl start apache2
```

Limpieza de datos transitorios en sesión (tokens de vista previa, TTL 1 h, se purgan solos en
`ajax/preview_correo.php:48-60`): no requiere acción.

### 20.2 Reconstruir el plugin desde cero (conserva los datos)

```bash
DIRROOT=/var/www/zajuna
REPO=/ruta/al/repositorio/anuncios_de_plataforma

sudo rm -rf "$DIRROOT/local/slider_form"
sudo rsync -a \
  --exclude '.git*' --exclude '.vscode/' --exclude '.claude/' \
  --exclude '*.zip' --exclude 'DEPLOY.md' --exclude 'CLAUDE.md' \
  --exclude 'prueba.html' --exclude 'classes/forms/Insert.php10122025' \
  --exclude 'docs/*.puml' --exclude 'docs/*.mmd' \
  "$REPO/slider_form/" "$DIRROOT/local/slider_form/"
sudo chown -R www-data:www-data "$DIRROOT/local/slider_form"
sudo -u www-data php "$DIRROOT/admin/cli/upgrade.php" --non-interactive
sudo -u www-data php "$DIRROOT/admin/cli/purge_caches.php"
```

**Las tablas `midb.*` y `mdl_local_slider` no se tocan.** Las migraciones ya aplicadas siguen
válidas; no hay que reejecutarlas.

> Borrar la carpeta sin volver a copiarla deja el plugin «huérfano»: Moodle lo detectará como
> desinstalable en *Notificaciones* y ofrecerá borrar sus datos. **Ese flujo no borra las tablas
> `midb.*`**, porque Moodle no las conoce — quedarían huérfanas en la base.

### 20.3 ⚠️ Comandos destructivos — BORRAN DATOS DE FORMA IRREVERSIBLE

> **ADVERTENCIA**
>
> Lo que sigue **elimina permanentemente** el historial de envíos, los filtros guardados y/o las
> imágenes del carrusel. **`midb.envios2` es la única evidencia de qué se envió y a quién**: no
> hay copia en ninguna otra parte, y el proceso externo de envío puede estar consumiéndola en ese
> momento.
>
> **Antes de ejecutar cualquiera de estos comandos, respalda y verifica que el respaldo existe:**
>
> ```bash
> pg_dump -h localhost -U postgres -d zajunadb \
>   -n midb -t public.mdl_local_slider \
>   -f ~/backup_anuncios_$(date +%F_%H%M).sql
> ls -lh ~/backup_anuncios_*.sql   # debe existir y no estar vacío
> ```
>
> **Coordina con quien opera el proceso de envío antes de tocar `midb.envios2`.** Ejecuta solo en
> una máquina local sin datos reales.

**a) Vaciar historial de envíos y filtros guardados:**

```sql
-- DESTRUCTIVO: borra toda la cola/historial de correos y los filtros.
TRUNCATE TABLE midb.envios2      RESTART IDENTITY;
TRUNCATE TABLE midb.saved_filters RESTART IDENTITY;
```

**b) Eliminar por completo el esquema `midb`** (incluye los catálogos de centros y regionales;
habría que reaplicar las migraciones desde cero):

```sql
-- DESTRUCTIVO: elimina las 4 tablas del plugin y sus datos.
DROP SCHEMA midb CASCADE;
```

**c) Desinstalar el plugin de Moodle** (elimina sus *capabilities* y su configuración; **no**
toca `midb.*` ni `mdl_local_slider`):

```bash
sudo -u www-data php /var/www/zajuna/admin/cli/uninstall_plugins.php \
     --plugins=local_slider_form --run
```

> Si vas a desinstalar también `local_slider`, **desinstala primero `local_slider_form`**: es el
> que depende del otro (sección 7.3).

**d) Eliminar la base de datos completa:** fuera del alcance de este documento. Destruiría todo
Moodle. **No lo hagas** siguiendo esta guía.

### 20.4 Contenedores y volúmenes

**No aplica: el proyecto no usa Docker ni volúmenes.**

---

## 21. Server parity checklist

Los ítems marcados **N/A** lo están por una razón concreta del proyecto, indicada al lado — no
son omisiones.

- [ ] **Máquina preparada.** Ubuntu 22.04 con Apache 2.4, PHP 8.2, PostgreSQL 16 (sección 4.1).
- [ ] **Dependencias instaladas.** `pdo_pgsql`, `pgsql`, `gd` **con WebP**, `zip`, `fileinfo` presentes (sección 15.2). Sin gestores de paquetes que ejecutar.
- [ ] **Variables de entorno configuradas.** **N/A** — el plugin no usa variables de entorno. En su lugar: `config.php` correcto, las 2 claves de `mdl_config_plugins` sembradas, y **los IDs de categoría de `modalidades.php:62` ajustados a la base destino** (secciones 6.1–6.3).
- [ ] **Hostname local configurado.** **N/A** — no hay dominio propio; `$CFG->wwwroot` es `http://localhost/zajuna`. **Verificado en su lugar:** se accede por esa URL exacta, para que los `fetch()` conserven la cookie (sección 5).
- [ ] **Reverse proxy configurado.** **N/A como proxy separado** — Apache es el punto de entrada. Verificado: `VirtualHost *:80`, symlink `html/zajuna`, `FollowSymLinks`, `apachectl configtest` = `Syntax OK` (sección 11).
- [ ] **HTTPS configurado si aplica.** **N/A** — el entorno real sirve HTTP en el puerto 80; no hay `mod_ssl` ni certificados en el repositorio (sección 19.13).
- [ ] **Frontend construido.** **N/A como build** — no hay compilación. Verificado en su lugar: `css/formUpdate.css` y `js/script.js` responden 200; la cascada de `segmented.php` se llena (smoke test 10–12).
- [ ] **Backend construido.** **N/A como build** — verificado en su lugar: plugin copiado **con `docs/Cuerpo_Correo.html`**, `chown www-data`, `upgrade.php` ejecutado, versión registrada = `2026072800` (secciones 10 y 15.5).
- [ ] **Base de datos disponible.** `\conninfo` conecta a `zajunadb` en `localhost:5432` (sección 15.3).
- [ ] **Migraciones ejecutadas.** **Dos frentes:** (a) upgrade de Moodle aplicado — `:view`/`:edit` registradas y `:manage` ausente; (b) **esquema `midb` creado a mano** y las 13 migraciones aplicadas en orden, con las 4 tablas presentes (secciones 8.3, 8.4, 15.3, 15.5).
- [ ] **Columnas `envios2.estado` y `envios2.sent_at` presentes.** No las crea ninguna migración del repositorio; sin ellas `send_logs.php` falla (sección 8.5). Confirmar el DDL real con el equipo del proceso de envío.
- [ ] **Seeds ejecutados si aplican.** Catálogos `midb.regionales` (~33) y `midb.centros` (~118) poblados por las migraciones 003–005 (sección 8.7).
- [ ] **Servicios auxiliares disponibles.** **N/A** — no hay Redis/RabbitMQ/Kafka. **El proceso de envío de correo es externo y no forma parte de este despliegue** (sección 9.2).
- [ ] **Aplicación funcionando.** El nodo «Administrar Banner Plataforma» aparece y `menu.php` carga (smoke test 3–4).
- [ ] **Capabilities concedidas a un rol.** Sin esto nadie salvo el superadministrador ve el plugin (sección 10.3).
- [ ] **`local_slider` desplegado.** Tabla `mdl_local_slider` y caché `imagecache` disponibles (sección 15.4).
- [ ] **Health check funcionando.** `admin/cli/checks.php` sin fallos; `ajax/categories.php?action=modalidades` responde 200 (sección 15.6).
- [ ] **Logs disponibles.** `reposena_error.log`, `reposena_access.log` y el log de PostgreSQL existen y crecen (sección 17).
- [ ] **Aplicación accesible desde el hostname local.** `http://localhost/zajuna/admin/settings.php?section=local_slider_form_manage` responde (smoke test 4).
- [ ] **Smoke test exitoso.** Bloques A (carrusel), B (envío segmentado), C (historial y XLSX) y D (permisos e interruptor) superados (sección 16).
- [ ] **Reinicio completo probado.** Secuencia de la sección 18 ejecutada; tras `reboot` la cascada vuelve a cargar sin intervención manual.

---

## 22. Auditoría y notas finales

Segunda pasada con el criterio del enunciado: «¿podría alguien que nunca ha trabajado en este
proyecto, con solo el repositorio, una máquina limpia y este documento, obtener un entorno que se
comporte como el servidor?».

### 22.1 Archivos analizados

**Configuración y ciclo de vida del plugin:**
`slider_form/version.php`, `config.php`, `settings.php`, `lib.php`, `db/access.php`,
`db/install.php`, `db/upgrade.php`, `db/migrations/001…013_*.sql` (los 13).

**Páginas y endpoints:**
`menu.php`, `index.php`, `insertRecord.php`, `updateRecord.php`, `deleteRecord.php`,
`manage_images.php`, `order.php`, `show_order.php`, `segmented.php`, `send_logs.php`,
`table_logs.php`, `active_role_users.php`, `ajax/categories.php`, `ajax/send_segmented.php`,
`ajax/preview_correo.php`, `ajax/saved_filters.php`, `ajax/export_envios.php`.

**Librerías y clases:**
`classes/external/ZajunaDbConnection.php`, `classes/forms/Insert.php`, `classes/forms/Update.php`,
`classes/table/*.php`, `classes/modal/Modal.php`, `classes/tabs/Tabs.php`,
`lib/usersValidations.php`, `lib/fieldsValidations.php`, `lib/utilsFunctions.php`,
`lib/modalidades.php`, `lib/helpers.php`.

**Recursos:** `docs/Cuerpo_Correo.html`, `css/formUpdate.css`, `js/script.js`,
`lang/es/local_slider_form.php`, `lang/en/local_slider_form.php`.

**Documentación del proyecto:** `slider_form/README.md`, `slider_form/CLAUDE.md`,
`slider_form/docs/DESPLIEGUE_PREPROD.md`, `slider_form/docs/cambio-categorias-despliegue.md`,
`slider_form/docs/LOGIC_SEGMENTED.md`, `docs/nuevo_relacionamiento_BD.md`,
`docs/Estandar_Componente_Para_Visibilizacion_del_Plugin.html`, ambos `.gitignore`.

**Del plugin hermano (para determinar el acoplamiento):** `slider/version.php`, `slider/lib.php`,
`slider/lib/showSlider.php`, `slider/db/install.xml`, `slider/db/caches.php`.

**Del entorno real (referencia de paridad):** `/var/www/zajuna/config.php`,
`/var/www/zajuna/version.php`, `/etc/apache2/sites-enabled/000-default.conf`,
`/etc/apache2/apache2.conf`, `/etc/php/8.2/apache2/php.ini`, salidas de `php -v`, `php -m`,
`psql --version`, `apache2 -v`, `ls -la /var/www/html/`, `ls /var/www/zajuna/admin/cli/`.

**Ausencias verificadas** (búsqueda explícita, sin resultados): `Dockerfile`,
`docker-compose.yml`, `compose.yml`, `package.json`, `composer.json`, `requirements.txt`,
`pyproject.toml`, `pom.xml`, `build.gradle`, `go.mod`, `.env*`, `.github/workflows`,
`.gitlab-ci.yml`, `Jenkinsfile`, `*.tf`, manifiestos de Kubernetes, charts de Helm, unidades
`systemd` propias, configuración de Supervisor/PM2, configuración de Nginx/Caddy/Traefik,
`email_to_user`/`message_send`/`mail(`, `getenv`, `CREATE SCHEMA` en las migraciones.

### 22.2 Arquitectura identificada

Pila de tres capas sin servicios intermedios — **navegador → Apache 2.4 (`mod_php`, puerto 80,
punto de entrada único) → Moodle 4.3.3+ → PostgreSQL 16 (`zajunadb`)** — con **dos caminos de
acceso a datos sobre la misma base**: el `$DB` de Moodle sobre `public.mdl_*` y un PDO crudo
sobre `midb.*`.

`local_slider_form` no es un servicio: es una **extensión en proceso** de Moodle, montada como
`admin_externalpage`. Su salida de negocio no es un correo enviado, sino **filas encoladas en
`midb.envios2`**, que un proceso externo —fuera de este repositorio— consume y entrega.

### 22.3 Paridad servidor/local

| Aspecto del servidor | ¿Se reproduce en local? | Cómo |
|---|---|---|
| Punto de entrada HTTP :80 vía Apache | **Sí, idéntico** | Mismo `VirtualHost`, `DocumentRoot` y symlink (sección 4.3) |
| URL pública de acceso | **Sí** | QA entra por `http://localhost/zajuna`, no por un puerto interno (secciones 11.1 y 16) |
| Ejecución PHP en proceso de Apache | **Sí** | `mod_php`, sin PHP-FPM |
| Motor y esquemas de datos | **Sí** | PostgreSQL 16, `zajunadb`, `public` + `midb`, prefijo `mdl_` |
| **Los dos caminos de acceso a datos** | **Sí** | `$DB` y el PDO crudo con las mismas credenciales de `$CFG` |
| Proceso de despliegue | **Sí** | Copiar ficheros + `upgrade.php` + `psql` para `midb`, igual que en el servidor |
| Modelo de permisos | **Sí** | Mismas *capabilities* con arquetipos vacíos; concesión manual (sección 10.3) |
| Interruptor de visibilidad | **Sí** | Mismas filas en `mdl_config_plugins`, mismo comportamiento sin caché |
| Restricciones de imagen | **Sí** | Mismas validaciones de formato, dimensiones y peso |
| **Proceso de envío de correo** | **No — es externo y no está en el repositorio** | El entorno local llega hasta el encolado en `midb.envios2` (sección 9.2) |
| **IDs de categoría** | **Solo si se ajustan a mano** | Están hardcodeados y difieren por entorno (sección 6.3) |
| **Columnas `envios2.estado` / `sent_at`** | **Bajo supuesto** | No hay DDL en el repositorio (secciones 8.5 y 22.5) |
| **HTTPS** | **No, porque el servidor de referencia tampoco lo usa** | Sección 19.13 |
| **Datos de producción** | **No** | Cursos, matrículas e imágenes hay que sembrarlos |

### 22.4 Supuestos declarados

1. **Se asume que ya existe un Moodle instalado y funcional sobre PostgreSQL**, y que
   **`local_slider` está desplegado**. Instalar Moodle queda fuera de alcance (sección 4.2).
2. **Se asume Ubuntu 22.04 con paquetes de la distribución**, por ser lo verificado. En otra
   distribución cambian rutas de configuración y de logs, no la arquitectura.
3. **Se asume que la máquina de referencia (`/var/www/zajuna`) refleja la configuración del
   servidor real.** Es la mejor fuente disponible: el repositorio no contiene configuración de
   infraestructura.
4. **Se asume el DDL de `envios2.estado` y `envios2.sent_at`** propuesto en la sección 8.5
   (`text` con valores `'pendiente'`/`'enviado'`, y `timestamptz`). Se dedujo de cómo los lee el
   código (`send_logs.php:34-35`, `table_logs.php:41-42`), **no de una definición existente**.
   **Debe confirmarse con el equipo que mantiene el proceso de envío.**
5. **Se asume que los IDs de categoría `10` y `200`** de `lib/modalidades.php:62` corresponden a
   la base de desarrollo y **deben revisarse en cada entorno** (sección 6.3).
6. **Se asume que el usuario `$CFG->dbuser` tiene o puede recibir privilegios sobre el esquema
   `midb`.** El repositorio no documenta ningún usuario distinto.
7. **Se asume que los datos de `mdl_course` siguen la convención de `shortname` de SENA**
   (`lib/modalidades.php:14-35`). Sin ella la cascada no puede funcionar, aunque el entorno esté
   perfectamente desplegado.

### 22.5 Información faltante (no determinable desde el repositorio)

1. **El proceso externo que consume `midb.envios2`.** Ni su código, ni su despliegue, ni su
   cadencia, ni su configuración SMTP están en este repositorio. **Es el eslabón que convierte un
   envío «programado» en un correo entregado.** Debe documentarlo quien lo mantenga.
2. **El DDL real de `envios2.estado` y `envios2.sent_at`** (sección 8.5). Se leen pero no se
   crean. El `ALTER TABLE` propuesto es un supuesto para desbloquear QA en local.
3. **La configuración real del servidor de producción.** El repositorio no incluye ficheros de
   infraestructura; todo lo de Apache, puertos y rutas procede de la máquina de desarrollo.
4. **Si producción usa HTTPS.** El entorno de referencia es HTTP en el puerto 80; no hay
   certificados, `mod_ssl`, `$CFG->sslproxy` ni `$CFG->reverseproxy` en ninguna parte. Este
   documento **no inventa** una sección de HTTPS (sección 19.13).
5. **Los IDs de categoría correctos de cada entorno destino** (sección 6.3). Solo se pueden
   determinar consultando la base destino.
6. **La contraseña de PostgreSQL de cada entorno.** Por diseño, no se documenta: se lee de
   `$CFG->dbpass`.
7. **La política de retención y respaldo de `midb.envios2`.** La tabla crece una fila por
   destinatario y por envío, sin purga automática ni particionado. No hay política documentada.
8. **Varios documentos internos están en `.gitignore` y no existen en un clon limpio**:
   `slider_form/CLAUDE.md`, `slider_form/docs/Relacionamiento_segmented.md` (mapa autoritativo
   cascada→columnas), `docs/Capability_slider_form.md` (guía de *scoping* de roles),
   `docs/Rol_Comunidades_Acceso_Banner.md` y los informes de seguridad/pentest. **Quien reciba
   solo el repositorio no los tendrá.**

### 22.6 Inconsistencias detectadas entre documentación y código

**En todos los casos, la fuente válida es el código.**

| # | Inconsistencia | Dónde | Realidad verificada |
|---|---|---|---|
| 1 | `docs/DESPLIEGUE_PREPROD.md` dice que hay que editar a mano la contraseña de PostgreSQL en `ZajunaDbConnection.php:20`, y que ahí vive una clave en texto plano. | `slider_form/docs/DESPLIEGUE_PREPROD.md`, sección 3 | **Obsoleto y ya corregido.** `ZajunaDbConnection.php:21-25` toma host, puerto, base, usuario y contraseña de `$CFG`. **No hay ninguna credencial embebida** en el archivo. **No lo edites.** |
| 2 | El mismo documento afirma que `local_slider_form` «no depende del plugin hermano `local/slider`». | `slider_form/docs/DESPLIEGUE_PREPROD.md`, sección 1 | **Falso.** `config.php:7` apunta a la tabla `local_slider` y `lib/utilsFunctions.php:219` invoca su caché. Dependencia real y bloqueante (sección 7.3). |
| 3 | El mismo documento exige que existan `"INTEGRACION"."SEEDS"` en la base destino. | `slider_form/docs/DESPLIEGUE_PREPROD.md`, sección 5 | **El esquema `INTEGRACION` ya no se consulta.** Solo aparece en comentarios (`lib/modalidades.php:6`, `ajax/categories.php:6`, `ZajunaDbConnection.php:5`). Verificado: cero consultas SQL contra él. |
| 4 | El mismo documento menciona `classes/external/foreing_db_connection.php` como código muerto. | `slider_form/docs/DESPLIEGUE_PREPROD.md`, sección 8 | **Ese archivo ya no existe** en el repositorio. |
| 5 | El mismo documento lista las migraciones hasta la `010` y declara release `0.3.2`. | `slider_form/docs/DESPLIEGUE_PREPROD.md`, secciones 1 y 5 | Hoy hay **13** migraciones y el release es **`0.4.1`** (`version.php:28`). Usa la lista de la sección 8.4 de este documento. |
| 6 | `docs/cambio-categorias-despliegue.md` indica cambiar los IDs de categoría en 4 archivos y 8 puntos: `CATEGORIAS` en `ajax/categories.php:42`, `CATEGORIAS_VALIDAS` en `ajax/send_segmented.php:35`, etc. | `slider_form/docs/cambio-categorias-despliegue.md` | **Ninguna de esas constantes existe ya.** Hoy los IDs viven **solo** en `lib/modalidades.php:62` y `:65`. Ver sección 6.3. |
| 7 | `send_segmented.php` y `preview_correo.php` sustituyen los marcadores `{{ASUNTO}}` y `{{DESCRIPCION}}` en la plantilla. | `ajax/send_segmented.php:309-310`, `ajax/preview_correo.php:256-257` | **La plantilla `docs/Cuerpo_Correo.html` no contiene esos marcadores** (solo `{{IMAGEN}}` y el literal `NOMBRE DE LA PERSONA`). Las dos sustituciones son *no-ops*: **el asunto no se inyecta en el cuerpo del correo**. Funcionalmente inocuo hoy, pero engañoso al leer el código. |
| 8 | Las migraciones `003` y `004` crean ambas `midb.regionales` con **esquemas distintos** (`003`: PK `rgn_id`; `004`: PK `id SERIAL` + `rgn_id UNIQUE`), usando `CREATE TABLE IF NOT EXISTS`. | `db/migrations/003_centros_regionales.sql:5`, `004_regionales.sql:6` | En una base limpia, **la `004` es un no-op**: la tabla queda con el esquema de la `003`. Además los nombres difieren (`'Regional Antioquia'` vs. `'ANTIOQUIA'`). El código solo lee `rgn_id` y `nombre`, así que **funciona igual**, pero los nombres mostrados dependen de cuál se aplicó. |
| 9 | La migración `005` hace **`DROP TABLE IF EXISTS midb.centros`** antes de recrearla. | `db/migrations/005_centros.sql:6` | **Reejecutarla en un entorno con datos borra la tabla y la repuebla con el catálogo del fichero.** Si alguien corrigió nombres con `UPDATE`, esos cambios se pierden. |
| 10 | El repositorio contiene `classes/forms/Insert.php10122025` y `prueba.html` dentro del árbol del plugin. | Árbol de `slider_form/` | Restos de desarrollo. `Insert.php10122025` tiene extensión no reconocida como PHP: **si se copia al servidor, Apache lo sirve como texto plano y expone el código fuente.** Excluidos en la sección 10.1. |
| 11 | `slider_form/README.md` y `slider_form/CLAUDE.md` figuran en `.gitignore` de la raíz. | `.gitignore` | `README.md` sí está versionado (se ignoró después de comitearlo); **`CLAUDE.md` no lo está** y no existirá en un clon limpio. |
| 12 | La tabla `mdl_local_slider_errors` existe en el esquema del plugin hermano. | `slider/db/install.xml:31` | **Ningún archivo de ninguno de los dos plugins la lee ni la escribe.** No busques ahí al diagnosticar: usa los logs de Apache (sección 17). |

### 22.7 Riesgos que QA puede cuestionar legítimamente

1. **«Envío programado» no es «correo enviado».** El plugin responde «Se programó el envío a N
   destinatario(s) correctamente» tras un `INSERT`, sin ninguna garantía de entrega. Si el proceso
   externo está caído, el usuario no recibe ninguna señal. **Es el riesgo funcional más
   importante del proyecto.**
2. **Dos columnas de `midb.envios2` sin DDL en el repositorio** (`estado`, `sent_at`). Un
   despliegue que siga solo las migraciones versionadas deja el historial roto (sección 8.5).
3. **Migraciones manuales, sin registro de cuáles se aplicaron.** No hay tabla de control ni
   herramienta: el operador debe llevar la cuenta. Reejecutar la `005` **borra `midb.centros`**
   (inconsistencia 9).
4. **IDs de categoría hardcodeados en el código.** Cambiar de entorno exige editar
   `lib/modalidades.php` y volver a desplegar. No es configuración, es código.
5. **Dependencia estricta del formato de `shortname`.** Si un curso no sigue
   `P_<n>_<letra>_<ficha>_R_<rgn>_C_<sed>`, queda invisible para el envío **sin ningún aviso**.
   Un cambio de convención de nombres en Moodle rompería la segmentación en silencio.
6. **Envío transaccional de una fila por destinatario, sin lotes ni tarea en segundo plano.** Con
   volúmenes grandes puede agotar `max_execution_time` y hacer `rollBack()` (sección 19.7). El
   propio código comenta que la plataforma está pensada para 3 000 000+ de usuarios
   (`db/migrations/012_saved_filters_all_text.sql:4-5`), lo que hace este punto especialmente
   relevante.
7. **`local/slider_form:edit` está marcada `RISK_SPAM | RISK_XSS`** (`db/access.php:12`) y permite
   correo masivo a toda la plataforma. La concesión de esa *capability* merece control estricto —
   y por eso los arquetipos están vacíos, que es la decisión correcta.
8. **Los filtros guardados son por usuario** (`saved_filters.created_by = $USER->id`,
   `ajax/saved_filters.php:9-10`), pero **el historial de envíos es global**: cualquiera con
   `:view` ve todos los envíos de todos. Puede ser intencionado; conviene confirmarlo.
9. **SQL crudo con prefijo `mdl_` literal.** Impide desplegar sobre una instalación con otro
   prefijo, algo habitual en instalaciones compartidas (sección 2.2).
10. **No hay tests automatizados, ni linter, ni CI.** Cualquier regresión solo se detecta con el
    smoke test manual. QA debería ejecutar la sección 16 **completa** en cada despliegue.
11. **El entorno de referencia es HTTP plano.** Las sesiones de Moodle —y los `sesskey` de los
    POST— viajan sin cifrar. Observación sobre la infraestructura, no sobre este plugin.
12. **Restos de desarrollo dentro del árbol del plugin** (`Insert.php10122025`, `prueba.html`). Si
    se copian al servidor quedan accesibles bajo el `DocumentRoot`. La sección 10.1 los excluye;
    verifica la exclusión tras cada despliegue con los `curl` de esa sección.

---

*Documento generado a partir del análisis del repositorio en la rama `feature_test/slider-form_Carlos`
y de la configuración verificada de la máquina de desarrollo. Componente complementario:
`slider/DEPLOY.md`.*
