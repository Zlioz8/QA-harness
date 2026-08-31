# `CENTRO DE ACTIVIDADES Y RESULTADOS ZAJUNA `

## Descripción General.

### Centro de Resultados

Este proyecto es un sistema de calificaciones diseñado para evaluar los resultados de aprendizaje de los aprendices a través de un perfil instructor. Permite a los instructores calificar y gestionar el progreso de los aprendices de ZAJUNA de una manera amigable y simple para el usuario.

### Centro de Actividades

Este proyecto es un sistema de calificaciones diseñado para evidencias, evaluar y hacer un seguimiento a las actividades de los aprendices en la plataforma de ZAJUNA, través de un perfil instructor. Permite a los instructores gestionar el progreso de los aprendices de ZAJUNA de una manera amigable y simple para el usuario, de igual forma los aprendices tendran la facilidad de hacer seguimiento a sus actividades realizadas.

### Arquitectura: tres repositorios trabajando juntos

Este manual cubre el despliegue de **dos** repositorios (`lmsActividad` y `lms-califica`), pero el ecosistema completo del Centro de Calificaciones se compone de **tres** repositorios:

| Repositorio remoto | Carpeta local | Rama | Rol | Funciones SQL requeridas |
|---|---|---|---|---|
| `centro_de_actividades` | `lmsActividad` | `lmsActividad` | Vista Centro de Actividades. Consume PostgreSQL **y** MongoDB. | `funcionesZajunaActi.sql`, `funcionesIntegracion.sql`, `comandos_conexion.sql` |
| `centro_de_resultados` | `lms-califica` | `centro_resultados` | Vista Centro de Resultados. Consume PostgreSQL únicamente. | `funcionesZajunaReas.sql`, `funcionesIntegracion.sql`, `comandos_conexion.sql` |
| `centro_de_calificaciones_sincronizacion` | `calificaciones` | `calificaciones` | Sincronizador PG → MongoDB. Alimenta los datos que consume `lmsActividad`. | Reutiliza `funcionesZajunaActi.sql` (ya cargado por `lmsActividad`). |

> **Importante:** los nombres de los repositorios remotos NO coinciden con los nombres de las carpetas locales. El renombrado al clonar es **obligatorio** porque la configuración de Apache (alias, symlinks) y las rutas internas asumen los nombres `lmsActividad`, `lms-califica` y `calificaciones`.
>
> **Ubicación de los archivos SQL:** todos los archivos `.sql` viven en **`lmsActividad/queries/`** y se cargan en la base PostgreSQL `DB_INTEGRACION`. `lms-califica` y `calificaciones` los consumen pero no los versionan. Por eso `lmsActividad` debe clonarse primero.
>
> **Orden de despliegue obligatorio:**
> 1. **`lmsActividad`** (este manual) — clona el repo, configura Apache, carga las funciones SQL desde `lmsActividad/queries/`.
> 2. **`lms-califica`** (este mismo manual) — clona el repo, configura Apache. Sus funciones SQL ya están cargadas en el paso 1.
> 3. **`calificaciones`** (sincronizador) — ver su [README propio](https://git.fsrisaralda.com/fabrica_zajuna/centro_de_calificaciones_sincronizacion). Depende de las funciones SQL cargadas en el paso 1.

## 1. Requisitos de Instalación (Ambos Centros)

- **Lenguaje**: PHP versión 8.2.
- **Extensiones PHP requeridas (desde Zajuna)**: PDO, cURL, fileinfo, gd, gettext, gmp, intl, imap, mbstring, exif, openssl, pdo_pgsql, pgsql, mongodb, soap, sockets, sodium, sqlite3, xsl, zip.
- **Base de Datos**: PostgreSQL versión 16, MongoDB 7.x (solo requerido para `lmsActividad`; `lms-califica` no usa MongoDB).
- **Gestor de Dependencias**: Composer 2.7.
- **Paquetes Composer**: `vlucas/phpdotenv`, `mongodb/mongodb`, `swiftmailer/swiftmailer` (versiones definidas en `composer.json` / `composer.lock` de cada proyecto).
- **Windows**: Instalar y configurar Wampserverx64 con las extensiones PHP mencionadas y el entorno de trabajo (`/wamp64/www`).
- **Linux (Ubuntu 24.04)**: Validar que el directorio de trabajo en Apache2 esté configurado a `/var/www/html/` para el acceso a los repositorios `lmsActividad` y `lms-califica`.

## 2. Instalación paso a paso para despliegue/instalación de los modulos de Centro de Resultados (`lms-califica`) y Centro de Actividades (`lmsActividad`)

### 2.1. Clonar Repositorios

**Prerrequisitos**
Antes de iniciar, asegúrate de tener instalado Git en tu máquina o servidor.Si no posees Git en tu servidor seguir los siguientes pasos:

- **Linux (Ubuntu 24.04)**: Instala Git `sudo apt-get install git`
- **Windows** desde [git-scm.com](https://git-scm.com/).

#### 1. Navega a tu directorio de trabajo (`cd /ruta/deseada`). Tener presente según el entorno de trabajo:

- **Windows**: Clona el repositorio en `/wamp64/www/`.
- **Linux**: Clona el repositorio en `/var/www/CARPETA-ESPECIFICADA-SEGUN-SERVIDOR/`. Se recomienda revisar la configuración del Apache2 para que el directorio de trabajo coincida con la ruta identificada por el servicio web.

**NOTA**: Recuerda que esta ruta puede cambiar según la necesidad de despliegue y la configuración del servidor.

#### 2. Clonar los repositorios:

> **Crítico:** clonar especificando el nombre de la carpeta destino. El nombre del repositorio remoto difiere del nombre que debe tener la carpeta local. Si se clona con el nombre por defecto, los alias de Apache y los enlaces simbólicos no funcionarán.

**Clonar `lms-califica` (Centro de Resultados):**

        git clone https://git.fsrisaralda.com/fabrica_zajuna/centro_de_resultados.git lms-califica
        cd lms-califica
        git fetch --all
        git switch centro_resultados
        cd ..

> Si ya clonaste con el nombre por defecto, renómbralo:
>
>     mv centro_de_resultados lms-califica

**Clonar `lmsActividad` (Centro de Actividades):**

        git clone https://git.fsrisaralda.com/fabrica_zajuna/centro_de_actividades.git lmsActividad
        cd lmsActividad
        git fetch --all
        git switch lmsActividad
        cd ..

> Si ya clonaste con el nombre por defecto, renómbralo:
>
>     mv centro_de_actividades lmsActividad

**(Opcional) Clonar `calificaciones` (Sincronizador PG → Mongo):**

Si vas a desplegar también el sincronizador (necesario para que `lmsActividad` reciba datos en MongoDB), clónalo en el mismo nivel:

        git clone https://git.fsrisaralda.com/fabrica_zajuna/centro_de_calificaciones_sincronizacion.git calificaciones
        cd calificaciones
        git fetch --all
        git switch calificaciones
        cd ..

Consulta el `README.md` y el `systemd.md` dentro de esa carpeta para su instalación y configuración del servicio de sincronización.

Para este proceso, se debe contar con el acceso a los repositorios otorgado por el equipo Centro de Calificaciones (token, llave SSH, o credenciales HTTPS).

**_NOTA_** : `Solicitar los tokens de acceso de cada repositorio al equipo "Centro de Calificaciones"`

### 2.2. Instalación de Dependencias:

**Habilitar extensiones PHP necesarias** (driver Mongo + PostgreSQL):

    sudo apt-get install -y php8.2-mongodb php8.2-pgsql php8.2-mbstring php8.2-curl
    sudo systemctl restart apache2

**Composer**: cada repositorio incluye su propio `composer.json` y `composer.lock`. El comando recomendado es `composer install` (respeta el lockfile e instala las versiones exactas usadas en producción):

    cd lmsActividad
    composer install
    cd ..

    cd lms-califica
    composer install
    cd ..

> **Nota:** evita usar `composer require <paquete>` para instalación inicial. `composer require` modifica `composer.json` y `composer.lock`, lo cual puede introducir versiones distintas a las validadas. Usa `composer install` para clonados nuevos.
>
> **Si `composer.json` aparece vacío o sin la sección `require`** (estado heredado de versiones antiguas), instalar manualmente las dependencias mínimas:
>
>     composer require vlucas/phpdotenv mongodb/mongodb swiftmailer/swiftmailer

> **Observación sobre `lms-califica`:** este proyecto actualmente **no usa MongoDB** en su código PHP (solo PostgreSQL directo). Aunque `composer.json` aún lista `mongodb/mongodb` como dependencia, no es estrictamente necesario para su operación. La extensión `php8.2-mongodb` solo es requerida por `lmsActividad`.

**_NOTA_** : Para màs informaciòn dirigirse al manual de desarrollador en la documentación ubicada en el repositorio de archivos **_Agata - LMS>DOCUMENTOS> EQUIPO CENTRO CALIFICACIONES > MANUALES > MANUAL VERSION CR-CA V4 > Manuales Centro Resultados V4 > MANUAL DE DESARROLLADOR CENTRO DE RESULTADOS VERSION 4.0 - NUMERAL 7 "Despliegue de Aplicativo" - PAG 60 "INSTALACIÓN COMPOSER (PARA LINUX)"._**

Asegúrate de tener instalado Composer en tu máquina. Si no lo tienes:

- **Windows**: descarga el instalador desde getcomposer.org y ejecútalo.
- **Linux**: https://getcomposer.org/download/

### 2.3. Configurar Variables de Entorno

1.  Crea un archivo `.env` (si aun no se ha creado).

        touch .env

2.  Abre el archivo `.env`

        vim .env

3.  Modifica las variables con las credenciales y configuraciones correctas para las bases de datos PostgreSQL (Zajuna y Sofia) y MongoDB.

        ZAJUNA_HOST=host
        ZAJUNA_PORT=port
        ZAJUNA_USER=user
        ZAJUNA_BD=name_bd
        ZAJUNA_PASSWORD=password

**Nota**: Para obtener el `MONGO_HOST` del servidor, ingresa a Mongo con el comando mongosh, donde se accede al servicio. Luego, busca la línea que indica `“Connecting to:”`, allí encontrarás el host de la base de datos instalada en el servidor.

### 2.4. Configuración del Servidor Web (Apache)

Pasos para implementar modificación en archivo .conf del servidor (Esta configuración es aplicable para ambos centros (CR y CA).)

1.  Edita el archivo de configuración de tu sitio, ejecutar en terminal de servidor (linux) el siguiente comando: `sudo vim /etc/apache2/apache2.conf`

2.  Se desplega la configuración de los host virtuales del servicio Apache2. Garantizar que la configuración contenga la siguiente configuración:

        <VirtualHost *:80>
        ...
        # ------------------------------------------------------------------------------
        # proyecto Centro Calificaciones
        Alias /lms-califica /var/www/CARPETA-ESPECIFICADA-SEGUN-SERVIDOR/lms-califica

        <Directory /var/www/CARPETA-ESPECIFICADA-SEGUN-SERVIDOR/lms-califica>
            Options Indexes
            AllowOverride All
            Require all granted

        </Directory>

        Alias /lmsActividad /var/www/CARPETA-ESPECIFICADA-SEGUN-SERVIDOR/lmsActividad

        <Directory /var/www/CARPETA-ESPECIFICADA-SEGUN-SERVIDOR/lmsActividad>
            Options Indexes
            AllowOverride All
            Require all granted
        </Directory>

        # proyecto Centro Calificaciones
        # ------------------------------------------------------------------------------
        ...
        </VirtualHost>

Al acceder aquí se puede editar la configuración según el puerto (port 80 para HTTP, port 443 para HTTPS).

**_NOTA 1_**: Es posible que no se requiera generar un alias, solo un enlace simbólico que redirija la configuración por defecto del servicio apache2 hacia la ruta del proyecto. Para este escenario ejecutaremos el siguiente comando:

        ln -s /var/www/lms-califica /var/www/html/lms-califica
        ln -s /var/www/lmsActividad /var/www/html/lmsActividad

**_Solo se debe generar el enlace simbólico cuando ambos repositorios ya se encuentren en el servidor._**

**_NOTA 2_**: Recuerda que esta configuración del servicio Apache2 puede cambiar según la necesidad de despliegue y la configuración del archivo .conf del servidor.

## 3. Instalaciòn Plugin Zajuna:

Instalacion plugin `calificaciones` en Zajuna (Moodle):

El plugin se distribuye **dentro de este mismo repositorio** en la carpeta:

        lmsActividad/moodle_plugin/calificaciones/

Estructura: es un plugin local de Moodle (incluye `version.php`, `lib.php`, `index.php`, `lang/`, `db/`). No requiere descarga externa.

### Opción A: Instalación vía interfaz web de Moodle (recomendado)

1. Comprimir la carpeta del plugin en un `.zip`:

        cd /var/www/lmsActividad/moodle_plugin
        zip -r calificaciones.zip calificaciones/

2. En el sitio Moodle/Zajuna, navegar a:
   - Administración del sitio → Plugins → Instalar plugins
3. Subir `calificaciones.zip` y seguir el asistente de instalación.

### Opción B: Instalación manual (copia de carpeta)

1. Copiar la carpeta del plugin al directorio de plugins locales de Moodle:

        sudo cp -r /var/www/lmsActividad/moodle_plugin/calificaciones /var/www/zajuna/local/calificaciones
        sudo chown -R www-data:www-data /var/www/zajuna/local/calificaciones

2. En el sitio Moodle/Zajuna, navegar a:
   - Administración del sitio → Notificaciones (Moodle detectará el plugin nuevo y pedirá ejecutar la instalación).
3. Confirmar la actualización de base de datos.

> **Nota:** la ruta `/var/www/zajuna/` es la instalación de Moodle/Zajuna; ajustar según la ruta real de tu despliegue de Moodle.

## 4. Configuración de Base de Datos

Antes de continuar, valide que el servidor cuente con:

- Las bases de datos mencionadas anteriormente.
- El usuario de PostgreSQL (postgres) configurado.
- Su respectiva contraseña para la conexión.

### 4.1. Creación de bases de datos (Base de datos Integración prueba para el centro de calificaciones):

Comandos para crear las bases de datos necesarias:

- Ingresar a PostgreSQL:

        psql -U postgres -h localhost -p 5432

- Crear la base de datos **DB_INTEGRACION** (Ajusta el nombre según tu preferencia):

        CREATE DATABASE "presencial_integracion";

- Acceder a la base de datos creada:

        \c presencial_integracion;

- Ejecutar el script de creación de tablas y estructuras necesarias para la base de datos **DB_INTEGRACION**. Solicita el backup de la Base de datos al equipo de centro de calificaciones.

        \i /www/esquemaIntegracion.sql

- Salir de PostgreSQL:

         \q

### 4.1.1. Creación de tablas y esquemas adicionales (DB_INTEGRACION / réplica)

Antes de continuar con la importación de esquemas foráneos (paso 4.2), se deben crear las siguientes tablas y esquema. **Todo este bloque se ejecuta conectado a la base `DB_INTEGRACION` (base de datos de Integración / réplica), NO a la Base de datos Zajuna**, ya que son requeridos por el `IMPORT FOREIGN SCHEMA` del paso siguiente.

**Tabla de relación para relacionar RAPs con Categorías de evaluación:**

```sql
-- "INTEGRACION"."RELACION_CA_CR" definition

-- Drop table

-- DROP TABLE "INTEGRACION"."RELACION_CA_CR";

CREATE TABLE "INTEGRACION"."RELACION_CA_CR" (
"ID" serial4 NOT NULL,
"COUSER_ID" int8 NULL,
"RELACION_JSON" jsonb NOT NULL,
"RESPONSABLE_RELACION" int8 NULL,
"FECHA_INSERT_DATA" timestamp DEFAULT CURRENT_TIMESTAMP NULL,
"FECHA_UPDATE_DATA" timestamp DEFAULT CURRENT_TIMESTAMP NULL,
"CONFIRMADO" bool DEFAULT false NOT NULL,
CONSTRAINT "RELACION_CA_CR_pkey" PRIMARY KEY ("ID")
);
```

**Esquema histórico para validar el historial de calificaciones de RAPs:**

```sql
-- DROP SCHEMA "HISTORICO_CR";

CREATE SCHEMA "HISTORICO_CR" AUTHORIZATION postgres;
```

**Tabla de histórico para validar el historial de calificaciones de RAPs:**

```sql
-- "HISTORICO_CR"."HISTORICO_RA_CC" definition

-- Drop table

-- DROP TABLE "HISTORICO_CR"."HISTORICO_RA_CC";

CREATE TABLE "HISTORICO_CR"."HISTORICO_RA_CC" (
"ID" serial4 NOT NULL,
"USR_NUM_DOC" varchar(20) NULL,
"INFO_CALIFICACION_JSON" jsonb NOT NULL,
"FECHA_INSERT_DATA" timestamp DEFAULT CURRENT_TIMESTAMP NULL,
CONSTRAINT "HISTORICO_RA_CC_pkey" PRIMARY KEY ("ID")
);
```

**Tabla pivot para visibilidad de REA por curso (ejecutar en la BD de integración/réplica, esquema `INTEGRACION`):**

```sql
-- Controla qué resultados de aprendizaje están ocultos en cada curso.
-- oculto=TRUE → instructor ve ojo-tachado; aprendiz no ve la fila.
CREATE TABLE IF NOT EXISTS "INTEGRACION"."rea_visible_curso" (
    rea_id   VARCHAR(50) NOT NULL,
    curso_id BIGINT      NOT NULL,
    oculto   BOOLEAN     NOT NULL DEFAULT FALSE,
    PRIMARY KEY (rea_id, curso_id)
);
```

> El toggle se hace vía POST a `/lmsActividad/controllers/toggle_rea_visible.php`.
> Instructor ve icono `fa-eye-slash` en cabecera de columna REA cuando está oculto.
> Aprendiz no ve la fila del REA si `oculto = TRUE`.

### 4.1.2. Creación de tablas y esquemas adicionales (DB Zajuna / zajuna_dash02)

**Todo este bloque se ejecuta conectado a la base de datos Zajuna (`zajuna_dash02`), NO a DB_INTEGRACION.**

**Esquema y tabla para envío de correos recordatorios** (usado por `controllers/enviar_recordatorio.php`):

```sql
-- Esquema
CREATE SCHEMA IF NOT EXISTS midb;

-- Tipo enum de estado de envío
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'env_estado' AND typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'midb')) THEN
        CREATE TYPE midb.env_estado AS ENUM ('pendiente', 'procesado', 'enviado', 'error');
    END IF;
END$$;

-- Tabla de envíos
CREATE TABLE IF NOT EXISTS midb.envios1 (
    id           SERIAL PRIMARY KEY,
    destinatario VARCHAR(255)      NOT NULL,
    asunto       VARCHAR(500)      NOT NULL,
    body         TEXT              NOT NULL,
    estado       midb.env_estado   NOT NULL DEFAULT 'pendiente',
    created_at   TIMESTAMPTZ       NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ       NOT NULL DEFAULT NOW()
);

-- Función y trigger para mantener updated_at
CREATE OR REPLACE FUNCTION midb.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_envios1_updated ON midb.envios1;
CREATE TRIGGER trg_envios1_updated
    BEFORE UPDATE ON midb.envios1
    FOR EACH ROW EXECUTE FUNCTION midb.set_updated_at();
```

> El INSERT solo requiere `destinatario`, `asunto`, `body` — el resto tiene valores por defecto.
> El campo `estado` es gestionado por el proceso de envío externo que consume la tabla.

### 4.2. Configuración de conexión entre bases de datos:

Una vez establecida la conexión con las bases de datos **Base de datos Zajuna** y **Base de datos Integración**, se debe crear una unión mediante un **servidor remoto en SQL**, el cual simula la conexión entre ambas bases de datos. Esto permitirá habilitar el despliegue de funciones clave en los siguientes pasos.

1. **_Paso 1:_** En ambas bases de datos se debe ejecutar la instalación de la siguiente extensión:

```sql

   CREATE EXTENSION IF NOT EXISTS postgres_fdw;

```

2. **_Paso 2:_** **Instalar extensión** :

```sql

    CREATE SERVER presencial_server
    FOREIGN DATA WRAPPER postgres_fdw
    OPTIONS (host '127.0.0.1', dbname 'DB_INTEGRACION', port '5432');

```

3. **_Paso 3:_** Crear el mapeo de usuario

```sql

    CREATE USER MAPPING FOR CURRENT_USER
    SERVER presencial_server
    OPTIONS (user 'postgres', password 'AQUI--DEBE--IR--CONTRASEÑA--USUARIO--DB');

```

4. **_Paso 4:_** Importamos los esquemas de **integración, resultados y resultados_p** hacia esquema **public Base de datos Zajuna**:

```sql

    IMPORT FOREIGN SCHEMA "INTEGRACION"
    LIMIT TO ("RESULTADO_APRENDIZAJE","COMPETENCIA", "RELACION_CA_CR")
    FROM SERVER presencial_server
    INTO public;

    -- Importar todas las tablas del esquema "RESULTADOS"
    IMPORT FOREIGN SCHEMA "RESULTADOS"
    FROM SERVER  presencial_server
    INTO public;

    -- Importar todas las tablas del esquema "RESULTADOS_P"
    IMPORT FOREIGN SCHEMA "RESULTADOS_P"
    FROM SERVER  presencial_server
    INTO public;

    -- Importar todas las tablas del esquema "HISTORICO_CR"
    IMPORT FOREIGN SCHEMA "HISTORICO_CR"
    FROM SERVER  presencial_server
    INTO public;

    -- Importar todas las tablas del esquema "PRESENCIAL"
    IMPORT FOREIGN SCHEMA "PRESENCIAL"
    FROM SERVER  presencial_server
    INTO public;

```

**_NOTA_**: Tenga en cuenta valores de esta nueva conexión para configurar variables de entorno con credenciales y contraseñas:

        SOFIA_HOST=host
        SOFIA_PORT=port
        SOFIA_USER=user
        SOFIA_BD=name_bd
        SOFIA_PASSWORD=password

        MONGO_HOST=mongodb://localhost:27017
        MONGO_DB=zajunaDB
        MONGO_COLLECTION=cursos
        MONGO_CONTENIDO_CURSO=contenido_cursos
        MONGO_CONTENIDO_GENERAL=contenido_general

**_NOTA_**: Tenga en cuenta que estas configuraciones pueden variar según el tipo de conexión que se desee realizar. Antes de ejecutar la conexión, verifique la siguiente información:

- Dirección IP del host (la creación del servidor no funciona o presenta algún error, utilice en el campo "host" la IP de la máquina.)
- Nombre de la base de datos objetivo
- Puerto de PostgreSQL
- Usuario de PostgreSQL a utilizar
- Contraseña correspondiente al usuario de la base de datos

**Estos comandos se pueden encontrar dentro de un archivo SQL llamado `comandos_conexion.sql` dentro del repositorio `lmsActividad/queries/`.**

### 4.3. Migración/creación de funciones SQL en bases de datos:

Para ejecutar la lógica del Centro de calificaciones, se debe realizar creación de funciones SQL definidas por el equipo de desarrollo. Entre estas se deben ejecutar los Scripts sql que se encuentran en los archivos:

Ruta dentro del repositorio `lmsActividad/queries/`:

**CENTRO DE CALIFICACIONES**

- `funcionesIntegracion.sql` en la base de datos `DB_INTEGRACION`.
- `funcionesZajunaReas.sql` en la base de datos `Base de datos Zajuna`.

**CENTRO DE ACTIVIDADES**

- `funcionesZajunaActi.sql` en la base de datos `Base de datos Zajuna`.

**_NOTA 1:_** Las funciones que se encuentran en el archivo **"funcionesIntegracion.sql"** deben ser ejecutadas en la base de datos **"DB_INTEGRACION"** y las funciones del archivo **"funcionesZajunaReas.sql"** y **"funcionesZajunaActi.sql"** deben ser ejecutadas en la base de datos **"Base de datos Zajuna"**. ESTO PUEDE CAMBIAR SEGUN EL NOMBRE DE LAS BASES DE DATOS EN EL SERVIDOR.

**_NOTA 2:_** Para conocer la funcionalidad de estas funciones SQL favor remitirse al manual desarrollador del centro de resultados, ubicado en el repositorio de archivos **_Agata - LMS>DOCUMENTOS>EQUIPO CENTRO CALIFICACIONES > MANUALES > MANUAL VERSION CR-CA V4 > Manuales Centro Resultados V4 > MANUAL DE DESARROLLADOR CENTRO DE RESULTADOS VERSION 4.0 - NUMERAL 4.1.1: Funciones SQL._**

## 5. CONFIGURACIONES DE LA PLATAFORMA PARA EL CENTRO DE ACTIVIDADES

### 5.1. Ajuste de archivo select_menu.mustache dentro del core de zajuna:

Para el óptimo funcionamiento del redireccionamiento entre el informe del calificador, en donde se puede ingresar a letras de calificación y configuración de calificaciones del curso, eliminamos el botón superior izquierdo que permite redireccionar a otras vistas de configuración del centro anterior.

Ingresamos al **mustache select_menu.mustache** que se encuentra en la ruta `zajuna/lib/templates/select_menu.mustache` y eliminamos de la línea de código **91** a la línea de código **125** (Aproximadamente, esto puede variar según la versión del LMS y si el archivo ha sufrido modificaciones personalizadas), así eliminamos esta fracción de código:

        <div
            class="btn dropdown-toggle"
            role="combobox"
            data-toggle="dropdown"
            {{#label}}aria-labelledby="{{baseid}}-label"{{/label}}
            aria-haspopup="listbox"
            aria-expanded="false"
            aria-controls="{{baseid}}-listbox"
            data-input-element="{{baseid}}-input"
            tabindex="0">
            {{selectedoption}}
        </div>
        <ul class="dropdown-menu" role="listbox" id="{{baseid}}-listbox" {{#label}}aria-labelledby="{{baseid}}-label"{{/label}}>
            {{#options}}
                {{#isgroup}}
                    <li role="none">
                        <ul role="group" aria-labelledby="{{id}}">
                            <li role="presentation" id="{{id}}">{{name}}</li>
                            {{#options}}
                                <li class="dropdown-item" role="option" id="{{id}}" data-value="{{value}}" {{#selected}}aria-selected="true"{{/selected}}>
                                    {{name}}
                                </li>
                            {{/options}}
                        </ul>
                    </li>
                {{/isgroup}}
                {{^isgroup}}
                    <li class="dropdown-item" role="option" id="{{id}}" data-value="{{value}}" {{#selected}}aria-selected="true"{{/selected}}>
                        {{name}}
                    </li>
                {{/isgroup}}
            {{/options}}
        </ul>
        <input type="hidden" name="{{name}}" value="{{value}}" id="{{baseid}}-input">

**_NOTA:_** (Si esta opción no funciona se recomienda modificar el tema de zajuna)

Se debe ingresar a `zajuna/theme/zajuna/templates/core/select_menu.mustache`

### 5.1.1 Ajuste de archivos overview_table.php y attempts_report_table.php dentro del core de zajuna:

Para visualizar la dirección IP de donde fue realizada las pruebas por los usuarios se debe realizar las siguientes modificaciones en los archivos mencionados.

Ingresamos inicialmente a \zajuna\mod\quiz\report\overview\overview_table.php, ubicamos la función constructor y validamos que se encuentre asi tal cual:

        public function __construct(
            $quiz,
            $context,
            $qmsubselect,
            quiz_overview_options $options,
            \core\dml\sql_join $groupstudentsjoins,
            \core\dml\sql_join $studentsjoins,
            $questions,
            $reporturl
        ) {
            parent::__construct(
                'mod-quiz-report-overview-report',
                $quiz,
                $context,
                $qmsubselect,
                $options,
                $groupstudentsjoins,
                $studentsjoins,
                $questions,
                $reporturl
            );
        }

Justo debajo de este costructor agregamos la siguiente función:

        public function setup()
        {
            parent::setup();
            // Agregar columna lastip con clave descriptiva (no índice numérico)
            $this->columns['lastip'] = count($this->columns);
            $this->headers[] = get_string('lastip');
        }

Posterior a esto buscamos en el archivo la funcion 'other_cols' y esta la reemplazamos por la siguiente funcion tal cual:

        public function other_cols($colname, $attempt)
            {

                // Manejar la columna lastip
                if ($colname === 'lastip') {
                    if (!empty($attempt->lastip)) {
                        return s($attempt->lastip);
                    }
                    return '-';
                }

                // Procesar columnas de preguntas (código original)
                if (!preg_match('/^qsgrade(\d+)$/', $colname, $matches)) {
                    return parent::other_cols($colname, $attempt);
                }
                $slot = $matches[1];

                $question = $this->questions[$slot];
                if (!isset($this->lateststeps[$attempt->usageid][$slot])) {
                    return '-';
                }

                $stepdata = $this->lateststeps[$attempt->usageid][$slot];
                $state = question_state::get($stepdata->state);

                if ($question->maxmark == 0) {
                    $grade = '-';
                } else if (is_null($stepdata->fraction)) {
                    if ($state == question_state::$needsgrading) {
                        $grade = get_string('requiresgrading', 'question');
                    } else {
                        $grade = '-';
                    }
                } else {
                    $grade = quiz_rescale_grade(
                        $stepdata->fraction * $question->maxmark,
                        $this->quiz,
                        'question'
                    );
                }

                if ($this->is_downloading()) {
                    return $grade;
                }

                if (isset($this->regradedqs[$attempt->usageid][$slot])) {
                    $gradefromdb = $grade;
                    $newgrade = quiz_rescale_grade(
                        $this->regradedqs[$attempt->usageid][$slot]->newfraction * $question->maxmark,
                        $this->quiz,
                        'question'
                    );
                    $oldgrade = quiz_rescale_grade(
                        $this->regradedqs[$attempt->usageid][$slot]->oldfraction * $question->maxmark,
                        $this->quiz,
                        'question'
                    );

                    $grade = html_writer::tag('del', $oldgrade) . '/' .
                        html_writer::empty_tag('br') . $newgrade;
                }

                return $this->make_review_link($grade, $attempt, $slot);
            }

Posterior a estos ajustes, ubicamos el archivo zajuna/mod/quiz/classes/local/reports/attempts_report_table.php y buscamos la función 'base_sql', validamos que se encuentre exactamente igual asi:

        public function base_sql(\core\dml\sql_join $allowedstudentsjoins)
        {
            global $DB;

            // Please note this uniqueid column is not the same as quiza.uniqueid.
            $fields = 'DISTINCT ' . $DB->sql_concat('u.id', "'#'", 'COALESCE(quiza.attempt, 0)') . ' AS uniqueid,';

            if ($this->qmsubselect) {
                $fields .= "\n(CASE WHEN $this->qmsubselect THEN 1 ELSE 0 END) AS gradedattempt,";
            }

            $userfieldsapi = \core_user\fields::for_identity($this->context)->with_name()
                ->excluding('id', 'idnumber', 'picture', 'imagealt', 'institution', 'department', 'email');
            $userfields = $userfieldsapi->get_sql('u', true, '', '', false);

            $fields .= '
            quiza.uniqueid AS usageid,
            quiza.id AS attempt,
            u.id AS userid,
            u.idnumber,
            u.picture,
            u.imagealt,
            u.institution,
            u.department,
            u.email,
            u.lastip,' . $userfields->selects . ',
            quiza.state,
            quiza.sumgrades,
            quiza.timefinish,
            quiza.timestart,
            CASE WHEN quiza.timefinish = 0 THEN null
                WHEN quiza.timefinish > quiza.timestart THEN quiza.timefinish - quiza.timestart
                ELSE 0 END AS duration';

            // El resto del código sigue igual...
            $from = " {user} u";
            $from .= "\n{$userfields->joins}";
            $from .= "\nLEFT JOIN {quiz_attempts} quiza ON
                                        quiza.userid = u.id AND quiza.quiz = :quizid";
            $params = array_merge($userfields->params, ['quizid' => $this->quiz->id]);

            if ($this->qmsubselect && $this->options->onlygraded) {
                $from .= " AND (quiza.state <> :finishedstate OR $this->qmsubselect)";
                $params['finishedstate'] = quiz_attempt::FINISHED;
            }

            switch ($this->options->attempts) {
                case attempts_report::ALL_WITH:
                    // Show all attempts, including students who are no longer in the course.
                    $where = 'quiza.id IS NOT NULL AND quiza.preview = 0';
                    break;
                case attempts_report::ENROLLED_WITH:
                    // Show only students with attempts.
                    $from .= "\n" . $allowedstudentsjoins->joins;
                    $where = "quiza.preview = 0 AND quiza.id IS NOT NULL AND " . $allowedstudentsjoins->wheres;
                    $params = array_merge($params, $allowedstudentsjoins->params);
                    break;
                case attempts_report::ENROLLED_WITHOUT:
                    // Show only students without attempts.
                    $from .= "\n" . $allowedstudentsjoins->joins;
                    $where = "quiza.id IS NULL AND " . $allowedstudentsjoins->wheres;
                    $params = array_merge($params, $allowedstudentsjoins->params);
                    break;
                case attempts_report::ENROLLED_ALL:
                    // Show all students with or without attempts.
                    $from .= "\n" . $allowedstudentsjoins->joins;
                    $where = "(quiza.preview = 0 OR quiza.preview IS NULL) AND " . $allowedstudentsjoins->wheres;
                    $params = array_merge($params, $allowedstudentsjoins->params);
                    break;
            }

            if ($this->options->states) {
                [$statesql, $stateparams] = $DB->get_in_or_equal(
                    $this->options->states,
                    SQL_PARAMS_NAMED,
                    'state'
                );
                $params += $stateparams;
                $where .= " AND (quiza.state $statesql OR quiza.state IS NULL)";
            }

            return [$fields, $from, $where, $params];
        }

### 5.1.2 Ajuste de archivo tablelog.php dentro del core de zajuna:

Se ubica el archivo en la ruta '\zajuna\grade\report\history\classes\output\tablelog.php', se busca la función 'define_table_columns.

Buscamos el arreglo de $cols y validamos que quede exactamente asi:

        $cols = array_merge(
            $cols,
            array(
                'lastip' => get_string('lastip'),
                'itemname' => get_string('gradeitem', 'grades'),
                'prevgrade' => get_string('gradeold', 'gradereport_history'),
                'finalgrade' => get_string('gradenew', 'gradereport_history'),
                'grader' => get_string('grader', 'gradereport_history'),
                'source' => get_string('source', 'gradereport_history'),
                'overridden' => get_string('overridden', 'grades'),
                'locked' => get_string('locked', 'grades'),
                'excluded' => get_string('excluded', 'gradereport_history'),
                'feedback' => get_string('feedbacktext', 'gradereport_history')
            )
        );

Posteriormente ubicamos la funcion 'get_sql_and_params' y en el parametro $fields validamos que este exactamente asi:

        $fields = 'ggh.id, ggh.timemodified, ggh.itemid, ggh.userid, ggh.finalgrade, ggh.usermodified,
                   ggh.source, ggh.overridden, ggh.locked, ggh.excluded, ggh.feedback, ggh.feedbackformat,
                   gi.itemtype, gi.itemmodule, gi.iteminstance, gi.itemnumber,
                    u.lastip, ';

Por ultimo, antes de que cierre la clase tablelog {}, agregamos la siguiente función:

        /**
        * Method to display column lastip.
        *
        * @param \stdClass $history
        * @return string HTML to display
        */
        public function col_lastip(\stdClass $history)
        {
            if (!empty($history->lastip)) {
                return s($history->lastip);
            }
            return '-';
        }

### 5.2. Generacion de redireccion al centro de actividades desde el menu desplegable de usuario (Rol Instructor).

En el archivo index.php que se encuentra en la ruta `zajuna/grade/report/singleview/index.php`, buscamos la linea de codigo **157** y se reemplaza la siguiente linea de código:

        $PAGE->set_url(new moodle_url('/grade/report/singleview/index.php', $pageparams));

Por el siguiente bloque de codigo:

        //INICIO MODIFICACION
        //SE OBTIENE EL ROL DEL USUARIO INGRESADO
        /* $context = context_course::instance($course->id);
        $roles = get_user_roles($context, $USER->id, true);
        $roleid = 2; // Valor por defecto
        sesskey();

        if (!empty($roles)) {
            $roleid = reset($roles)->roleid;
        }

        if (!empty($USER->access['rsw'])) {
            $temporal_roleid = reset($USER->access['rsw']);
            $new_url = new moodle_url('/../lmsActividad/config/login_config.php', array(
                'user' => $USER->id,
                'idnumber' => $course->id,
                'roleid' => $roleid,
                'rol_temp' => $temporal_roleid,
                'sesskey' => sesskey()
            ));
        } else {
            $temporal_roleid = null;
            $new_url = new moodle_url('/../lmsActividad/config/login_config.php', array(
                'user' => $USER->id,
                'idnumber' => $course->id,
                'roleid' => $roleid,
                'sesskey' => sesskey()
            ));
        }

        //NUEVA REDIRECCION AL CENTRO DE ACTIVIDADES
        $external_gradebook_url = new_url;

        // Redirige a la URL externa
        redirect($external_gradebook_url); */
        //FIN MODIFICACION

### 5.3. Generacion de redireccion al centro de actividades desde el menu desplegable de usuario (Rol Aprendiz).

En el archivo lib.php que se encuentra en la ruta `zajuna/grade/report/overview/lib.php`, buscamos la linea de código **321** y se reemplaza la siguiente linea de código:

        $coursenamelink = html_writer::link(new moodle_url('/course/user.php', [
            'mode' => 'grade',
            'id' => $course->id,
            'user' => $this->user->id,
        ]), $coursenamelink);

Por el siguiente bloque de código:

       $coursenamelink = html_writer::link($new_url, $coursenamelink;)

Debajo de la linea de codigo **313**:

        $coursenamelink = format_string(get_course_display_name_for_list($course), true, ['context' => $coursecontext]);

Se agrega el siguiente bloque de codigo:

        $context = context_course::instance($course->id);
        $roles = get_user_roles($context, $USER->id, true);
        $roleid = 2; // Valor por defecto
        sesskey();

        if (!empty($roles)) {
            $roleid = reset($roles)->roleid;
        }

        if (!empty($USER->access['rsw'])) {
            $temporal_roleid = reset($USER->access['rsw']);
            $new_url = new moodle_url('/../lmsActividad/config/login_config.php', array(
                'user' => $USER->id,
                'idnumber' => $course->id,
                'roleid' => $roleid,
                'rol_temp' => $temporal_roleid,
                'sesskey' => sesskey()
            ));
        } else {
            $temporal_roleid = null;
            $new_url = new moodle_url('/../lmsActividad/config/login_config.php', array(
                'user' => $USER->id,
                'idnumber' => $course->id,
                'roleid' => $roleid,
                'sesskey' => sesskey()
            ));
        }

### 5.4. Generacion de redireccion al centro de actividades desde el menu desplegable de usuario (Rol Administrador).

En el archivo index.php que se encuentra en la ruta `zajuna/grade/report/grader/index.php`, buscamos la linea de codigo **49** y se reemplaza la siguiente linea de codigo:

        $PAGE->set_url(new moodle_url('/grade/report/grader/index.php', array('id' => $courseid)));

Por el siguiente bloque de codigo:

        //INICIO MODIFICACION REDIRECCION ADMINISTRADOR
        //SE OBTIENE EL ROL DEL USUARIO INGRESADO
        /\* $context = context_course::instance($course->id);
        $roles = get_user_roles($context, $USER->id, true);
        $roleid = 2; // Valor por defecto
        sesskey();

            if (!empty($roles)) {
                $roleid = reset($roles)->roleid;
            }

            if (!empty($USER->access['rsw'])) {
                $temporal_roleid = reset($USER->access['rsw']);
                $new_url = new moodle_url('/../lmsActividad/config/login_config.php', array(
                    'user' => $USER->id,
                    'idnumber' => $course->id,
                    'roleid' => $roleid,
                    'rol_temp' => $temporal_roleid,
                    'sesskey' => sesskey()
                ));
            } else {
                $temporal_roleid = null;
                $new_url = new moodle_url('/../lmsActividad/config/login_config.php', array(
                    'user' => $USER->id,
                    'idnumber' => $course->id,
                    'roleid' => $roleid,
                    'sesskey' => sesskey()
                ));
            }

            //NUEVA REDIRECCION AL CENTRO DE ACTIVIDADES
            $external_gradebook_url = new_url;

            // Redirige a la URL externa
            redirect($external_gradebook_url); */

        //FIN MODIFICACION REDIRECCION ADMINISTRADOR

### 5.5. Generacion de redireccion al centro de actividades despues de editar una nota.

En el archivo grade.php que se encuentra en la ruta `zajuna/grade/edit/tree/grade.php`, buscamos la linea de codigo **60** y se reemplaza la siguiente linea de codigo:

Se ubica la linea de codigo:

        $context = context_course::instance($course->id);
        if (!has_capability('moodle/grade:manage', $context)) {
            require_capability('moodle/grade:edit', $context);
        }

Justo debajo se agrega el siguiente bloque de codigo:

        /////////////////////////////////////////////////////////////////////////////////////
        //AJUSTE REDIRECCION CENTRO DE ACTIVIDADES
        $roles = get_user_roles($context, $USER->id, true);
        $roleid = 2; // Valor por defecto
        sesskey();

        if (!empty($roles)) {
            $roleid = reset($roles)->roleid;
        }

        // Clave de sesión para este usuario/curso
        $session_key = 'lms_return_' . $USER->id . '_' . $course->id;
        $last_update_key = 'lms_last_update_' . $USER->id . '_' . $course->id;

        $return_url = null;

        // Verificar si venimos desde el sistema externo
        if (isset($_SERVER['HTTP_REFERER'])) {
            $referer = $_SERVER['HTTP_REFERER'];

            // Si venimos de nuestro sistema externo
            if (strpos($referer, 'lmsActividad') !== false) {
                // Verificar si es una URL diferente a la guardada anteriormente
                $current_saved = isset($_SESSION[$session_key]) ? $_SESSION[$session_key] : '';

                if ($current_saved !== $referer) {
                    // Es una URL diferente, actualizar
                    $_SESSION[$session_key] = $referer;
                    $_SESSION[$last_update_key] = time();
                    $return_url = $referer;
                } else {
                    // Es la misma URL, usar la guardada
                    $return_url = $referer;
                }
            }
        }

        // Si no hay referer válido, usar la URL guardada en sesión
        if (empty($return_url) && isset($_SESSION[$session_key])) {
            $return_url = $_SESSION[$session_key];
        }

        // Definir la URL de retorno
        if (!empty($return_url)) {
            // Para vistas que vienen del sistema externo, solo enviar el ID del curso
            $returnurl = new moodle_url($return_url, array('id' => $course->id));
        } else {
            // URL por defecto con todos los parámetros
            $returnurl = new moodle_url('/../lmsActividad/config/login_config.php', array(
                'user' => $USER->id,
                'courseid' => $course->id,
                'sesskey' => sesskey(),
                'idnumber' => $course->idnumber,
                'roleid' => $roleid
            ));
        }
        /////////////////////////////////////////////////////////////////////////////////////
        // default return url
        $gpr = new grade_plugin_return();
        $returnurl = $returnurl;
        /////////////////////////////////////////////////////////////////////////////////////
        // FIN AJUSTE REDIRECCION CENTRO DE ACTIVIDADES

### 5.6. Generacion de redireccion al centro de actividades despues de ocultar/mostrar una nota.

En el archivo grade.php que se encuentra en la ruta `zajuna/grade/edit/tree/action.php`, buscamos la linea de codigo **45** y se reemplaza la siguiente linea de codigo:

Se ubica la linea de codigo:

        $returnurl = $gpr->get_return_url($CFG->wwwroot.'/grade/edit/tree/index.php?id='.$course->id);

Justo debajo se agrega el siguiente bloque de codigo:

        /////////////////////////////////////////////////////////////////////////////////////
        //AJUSTE REDIRECCION CENTRO DE ACTIVIDADES
        $roles = get_user_roles($context, $USER->id, true);
        $roleid = 2; // Valor por defecto
        sesskey();

        if (!empty($roles)) {
            $roleid = reset($roles)->roleid;
        }

        // Clave de sesión para este usuario/curso
        $session_key = 'lms_return_' . $USER->id . '_' . $course->id;
        $last_update_key = 'lms_last_update_' . $USER->id . '_' . $course->id;

        $return_url = null;

        // Verificar si venimos desde el sistema externo
        if (isset($_SERVER['HTTP_REFERER'])) {
            $referer = $_SERVER['HTTP_REFERER'];

            // Si venimos de nuestro sistema externo
            if (strpos($referer, 'lmsActividad') !== false) {
                // Verificar si es una URL diferente a la guardada anteriormente
                $current_saved = isset($_SESSION[$session_key]) ? $_SESSION[$session_key] : '';

                if ($current_saved !== $referer) {
                    // Es una URL diferente, actualizar
                    $_SESSION[$session_key] = $referer;
                    $_SESSION[$last_update_key] = time();
                    $return_url = $referer;
                } else {
                    // Es la misma URL, usar la guardada
                    $return_url = $referer;
                }
            }
        }

        // Si no hay referer válido, usar la URL guardada en sesión
        if (empty($return_url) && isset($_SESSION[$session_key])) {
            $return_url = $_SESSION[$session_key];
        }

        // Definir la URL de retorno
        if (!empty($return_url)) {
            // Para vistas que vienen del sistema externo, solo enviar el ID del curso
            $returnurl = new moodle_url($return_url, array('id' => $course->id));
        } else {
            // URL por defecto con todos los parámetros
            $returnurl = new moodle_url('/../lmsActividad/config/login_config.php', array(
                'user' => $USER->id,
                'courseid' => $course->id,
                'sesskey' => sesskey(),
                'idnumber' => $course->idnumber,
                'roleid' => $roleid
            ));
        }
        /////////////////////////////////////////////////////////////////////////////////////
        // default return url
        $gpr = new grade_plugin_return();
        $returnurl = $returnurl;
        /////////////////////////////////////////////////////////////////////////////////////
        // FIN AJUSTE REDIRECCION CENTRO DE ACTIVIDADES

### 5.7. Generacion de redireccion al centro de actividades despues de editar una nota de un item manual.

En el archivo grade.php que se encuentra en la ruta `zajuna/grade/edit/tree/calculation.php`, buscamos la linea de codigo **55** y se reemplaza la siguiente linea de codigo:

Se ubica la linea de codigo:

        $returnurl = $gpr->get_return_url($CFG->wwwroot.'/grade/edit/tree/index.php?id='.$course->id);

Justo debajo se agrega el siguiente bloque de codigo:

        /////////////////////////////////////////////////////////////////////////////////////
        //AJUSTE REDIRECCION CENTRO DE ACTIVIDADES
        $roles = get_user_roles($context, $USER->id, true);
        $roleid = 2; // Valor por defecto
        sesskey();

        if (!empty($roles)) {
            $roleid = reset($roles)->roleid;
        }

        // Clave de sesión para este usuario/curso
        $session_key = 'lms_return_' . $USER->id . '_' . $course->id;
        $last_update_key = 'lms_last_update_' . $USER->id . '_' . $course->id;

        $return_url = null;

        // Verificar si venimos desde el sistema externo
        if (isset($_SERVER['HTTP_REFERER'])) {
            $referer = $_SERVER['HTTP_REFERER'];

            // Si venimos de nuestro sistema externo
            if (strpos($referer, 'lmsActividad') !== false) {
                // Verificar si es una URL diferente a la guardada anteriormente
                $current_saved = isset($_SESSION[$session_key]) ? $_SESSION[$session_key] : '';

                if ($current_saved !== $referer) {
                    // Es una URL diferente, actualizar
                    $_SESSION[$session_key] = $referer;
                    $_SESSION[$last_update_key] = time();
                    $return_url = $referer;
                } else {
                    // Es la misma URL, usar la guardada
                    $return_url = $referer;
                }
            }
        }

        // Si no hay referer válido, usar la URL guardada en sesión
        if (empty($return_url) && isset($_SESSION[$session_key])) {
            $return_url = $_SESSION[$session_key];
        }

        // Definir la URL de retorno
        if (!empty($return_url)) {
            // Para vistas que vienen del sistema externo, solo enviar el ID del curso
            $returnurl = new moodle_url($return_url, array('id' => $course->id));
        } else {
            // URL por defecto con todos los parámetros
            $returnurl = new moodle_url('/../lmsActividad/config/login_config.php', array(
                'user' => $USER->id,
                'courseid' => $course->id,
                'sesskey' => sesskey(),
                'idnumber' => $course->idnumber,
                'roleid' => $roleid
            ));
        }
        /////////////////////////////////////////////////////////////////////////////////////
        // default return url
        $gpr = new grade_plugin_return();
        $returnurl = $returnurl;
        /////////////////////////////////////////////////////////////////////////////////////
        // FIN AJUSTE REDIRECCION CENTRO DE ACTIVIDADES

### 5.8. Generación de botón para redirigir nuevamente al centro de actividades general.

Generamos un botón en el archivo index.php que se encuentra en la ruta `zajuna/grade/report/singleview/index.php`, se ubica la línea de código número **223** y se anexa el siguiente botón.

        echo '<a href="../../../../lmsActividad/views/actividades/actividades.php?id=' . $courseid . '"
            style="text-decoration: none; padding: 10px 20px; background-color: #4CAF50; color: white; border-radius: 5px; display: inline-block;">
            Regresar al Centro de Actividades
        </a>';

**_NOTA_**: para conocer la funcionalidad de estas funciones SQL favor remitirse al manual desarrollador del centro de resultados y actividades, ubicado en el repositorio de archivos: **_Agata - LMS>DOCUMENTOS> EQUIPO CENTRO CALIFICACIONES > MANUALES > MANUAL VERSION CR-CA V4 > MANUALES CENTRO DE ACTIVIDADES V4 > MANUAL DE DESARROLLADOR CENTRO DE ACTIVIDADES VERSION 4.0 - NUMERAL 4.3.1: Funciones SQL._**

## 6. Uso del Aplicativo Centro de Resultados:

### Perfil Instructor

#### 1. Acceso:

- Inicia sesión como instructor utilizando credenciales ZAJUNA.
- Ingresa a un curso/ficha en el que se encuentre matriculado, busca en el menú de navegación al lado izquierdo el botón llamado "Centro de Calificaciones".
- Podra visualizar el menu principal del centro de calificaciones , alli debera ingresar a la secciòn de **_Centro de Resultados_**.

#### 2. Visualización:

- Visualización de competencias activas: Permite consultar todas las competencias activas que estén asignadas a la ficha o curso correspondiente.
- Detalle de una competencia específica: Al ingresar en una competencia determinada, se muestran los resultados de aprendizaje asociados. Desde esta vista podrás:
  - Seleccionar los resultados que deseas visualizar mediante el filtro de vista previa.
  - Hacer clic en "Visualizar resultados" para cargar la información.
- Visualización de resultados de aprendizaje: En una vista general los REA seleccionados, asociados a la competencia junto con sus calificaciones, indicando:
  - Si ya fueron realizadas o aún están pendientes.
  - Si las calificaciones están guardadas de forma local.
  - Si se encuentran en proceso de sincronización con SOFIA Plus.

- Visualización de resultado de aprendizaje: Mediante los botones ubicados en la cabecera de cada tabla, podrás desplazarte entre los diferentes resultados de aprendizaje. Además, es posible ingresar a una vista más detallada de cada resultado individual, donde se muestra la información específica asociada a dicho resultado.

#### 3. Calificación:

- Tanto en la vista general de los resultados como en la vista individual, podrás realizar el proceso de calificación y guardar los avances de manera local, antes de proceder con el envío definitivo de las calificaciones a SOFIA Plus.
  **Calificación Local**: - Selecciona los aprendices con el checkbox. - Modifica la calificación (A/D). - Haz clic en "Guardar Calificaciones" y confirma.

**Envío a SOFIA Plus**: - Selecciona los aprendices con calificaciones modificadas. - Haz clic en "Enviar a Sofia". - Revalidar y confirmar una vez más los aprendices y su calificación - Confirma la acción y los datos a enviar.

#### 4. Herramientas:

- El proyecto cuenta con herramientas como filtros para visualizar competencias, resultados de aprendizaje y actividades específicas, permitiendo al usuario seleccionar y consultar información relevante de manera rápida. Además, dispone de historial de calificaciones y sincronización, lo que facilita el seguimiento del progreso y los cambios realizados por instructores y aprendices. También incluye exportación de reportes en formatos como Excel y CSV.

**_Nota:_** Se cuenta con botones de:

- **Regresar** : Regresa la navegación a la vista anterior dentro del centro de Resultados.
- **Guias de califiaciones**: Esta es una ventana emergente (modal) que aparece para orientar al instructor, especialmente para facilitar el proceso las primeras veces que usa la herramienta.
- **Código de colores**: A continuación, se describen los esquemas de colores del estado de la sincronización notas asignadas a los resultados de aprendizaje entre los sistemas LMS Zajuna y SOFIA plus.
  Por favor,tenga en cuenta los siguientes códigos de colores:

| COLOR         | NOTA  | ESTADO                                                                      |
| ------------- | ----- | --------------------------------------------------------------------------- |
| Verde azulado | A ó D | RESULTADO EVALUADO DESDE SOFIA Plus (APROBADO O NO APROBADO)                |
| Azul grisáceo | X     | POR EVALUAR                                                                 |
| Verde claro   | A     | APROBADO (PENDIENTE POR SINCRONIZAR)                                        |
| Rojo          | D     | NO APROBADO (PENDIENTE POR SINCRONIZAR)                                     |
| Celeste       | X     | PENDIENTE POR SINCRONIZAR                                                   |
| Azul oscuro   | A ó D | EN PROCESO DE SINCRONIZACIÓN DE LMS CON SOFIA Plus.                         |
| Verde medio   | A ó D | RESULTADO EVALUADO DESDE LMS Y SINCRONIZADO CON SOFIA Plus: PROCESO EXITOSO |
| Rosa          | A ó D | ERROR SINCRONIZACIÓN EN SOFIA Plus                                          |

### Perfil Aprendiz

#### 1. Acceso:

- Inicia sesión como aprendiz utilizando credenciales ZAJUNA.
- Ingresa a un curso en el que te encuentres matriculado, busca en el menú de navegación al lado izquierdo el botón llamado **"Centro de Resultados"**.

#### 2. Visualización:

- Visualiza la/las competencias de la ficha a la cual está matriculado.
- Continua navegando por las competencias, mediante el botón **"Resultados de aprendizaje"**.

#### 3. Herramientas:

- Cada una de las notas de tus resultados de aprendizaje se encuentran en esta ventana. Contienen el código del resultado, el nombre completo del mismo y su respectiva calificación. Así mismo la calificación se muestra según el código de colores, que también podrás encontrar en la parte superior izquierda de esta página.

6. Se cuenta con botón de **"Regresar"** y **"Código de colores"** los cuales cumplen las siguientes funciones:
   - Regresar: Regresa la navegación a la vista anterior dentro del centro de Resultados.
   - Código de colores: Informa al usuario aprendiz los colores correspondientes a cada calificación. Siendo estos así:

**Código de colores**
A continuación, se describen los esquemas de colores del estado de la sincronización notas asignadas a los resultados de aprendizaje entre los sistemas LMS Zajuna y SOFIA plus.
Por favor,tenga en cuenta los siguientes códigos de colores:

| COLOR         | NOTA  | ESTADO                                                                      |
| ------------- | ----- | --------------------------------------------------------------------------- |
| Verde azulado | A ó D | RESULTADO EVALUADO DESDE SOFIA Plus (APROBADO O NO APROBADO)                |
| Azul grisáceo | X     | POR EVALUAR                                                                 |
| Verde claro   | A     | APROBADO (PENDIENTE POR SINCRONIZAR)                                        |
| Rojo          | D     | NO APROBADO (PENDIENTE POR SINCRONIZAR)                                     |
| Celeste       | X     | PENDIENTE POR SINCRONIZAR                                                   |
| Azul oscuro   | A ó D | EN PROCESO DE SINCRONIZACIÓN DE LMS CON SOFIA Plus.                         |
| Verde medio   | A ó D | RESULTADO EVALUADO DESDE LMS Y SINCRONIZADO CON SOFIA Plus: PROCESO EXITOSO |
| Rosa          | A ó D | ERROR SINCRONIZACIÓN EN SOFIA Plus                                          |

## 7.Uso del Aplicativo Centro de Actividades:

## Perfil Instructor

#### 1. Acceso:

- Inicia sesión como instructor utilizando credenciales ZAJUNA.
- Ingresa a un curso/ficha en el que se encuentre matriculado, busca en el menú de navegación al lado izquierdo el botón llamado "Centro de Calificaciones".
- Podra visualizar el menu principal del centro de calificaciones , alli debera ingresar a la secciòn de **_Centro de Actividades_**.

#### 2. Visualización:

- Visualiza las actividades o pruebas de conocimiento de los aprendices matriculados a dicho curso en una vista general, junto con sus respectivas notas, si han sido realizadas o si están pendientes, discriminadas por fases (categorías) o resultados de aprendizaje, según el tipo de ficha.
- Continua navegando por las actividades, evidencias, foros o wikis, con los botones en la parte superior de la tabla.
- Cada nota de los aprendices contiene múltiples funciones que permiten al instructor redirigirse a la revisión de la actividad, evidencia, foro o wiki de cada aprendiz y siendo el caso esta redirección lo llevara al apartado donde puede calificar un foro o evidencia en cuestión.
- El indicativo de la categoría de las actividades funciona como un botón, el cual permite visualizar una vista con las únicas actividades relacionada a dicha categoría, esto con el fin de dar un filtro a las actividades, foros y evidencias. Tenemos en cuenta que wiki no son actividades evaluativas en ZAJUNA, por lo cual estas no tienen categorías.

#### 3. Herramientas:

- En la parte superior de la tabla encontrara unos botones los cuales permiten la accesibilidad a la tabla, una de estas permite restaurar columnas en caso de que el usuario haya ocultado alguna columna en especifica, a su vez dispone de exportaciones tipo **excel, csv, pdf**, con el fin de que el instructor tenga reportes de las actividades, evidencias, foros y wikis.
- En esta misma vista filtrada por categorías, el instructor tiene la opción de seleccionar múltiples aprendices para enviar correos recordatorios de realizar la actividad, evidencia, foro, evidencia o wiki si se encuentra pendiente de realizar.

**Código de colores:** Informa al usuario instructor los colores correspondientes a cada calificación. Siendo estos así:

Este código de colores está establecido para facilitar la lectura de las calificaciones del centro de calificaciones.
Por favor, tenga en cuenta los siguientes códigos de colores:

| Color            | Nota | Estado                               |
| ---------------- | ---- | ------------------------------------ |
| Color Verde agua | A    | APROBADO                             |
| Color Rojo       | D    | NO APROBADO                          |
| Color Gris claro | X    | PENDIENTE POR PRESENTAR              |
| Color Amarillo   |      | PENDIENTE POR EVALUAR DEL INSTRUCTOR |
| Color Morado     |      | NUEVO INTENTO PENDIENTE POR EVALUAR  |
| Color Azul cielo |      | NOTA ASIGNADA MANUALMENTE            |

## Perfil Aprendiz

#### 1. Acceso:

- Inicia sesión como instructor utilizando credenciales ZAJUNA.
- Ingresa a un curso/ficha en el que se encuentre matriculado, busca en el menú de navegación al lado izquierdo el botón llamado "Centro de Calificaciones".
- Podra visualizar el menu principal del centro de calificaciones , alli debera ingresar a la secciòn de **_Centro de Actividades_**.

#### 2. Visualización:

- Visualiza las actividades o pruebas de conocimiento del curso al que te encuentras matriculado en una vista general, junto con sus respectivas notas, si han sido realizadas o si están pendientes, discriminadas por fases (categorías) o resultados de aprendizaje, según el tipo de ficha.
- Continua navegando por las actividades, evidencias, foros o wikis, con los botones en la parte superior de la tabla.
- Cada una de tus notas contiene múltiples funciones que permiten al aprendiz redirigirse a la revisión de la actividad, evidencia, foro o wiki realizada o siendo el caso esta redirección lo llevara al apartado donde puede realizar dicha actividad.

#### 3. Herramientas:

En la parte superior de la tabla encontrará unos botones los cuales permiten la accesibilidad a la tabla, una de estas permite restaurar columnas en caso de que el usuario haya ocultado alguna columna en especifica, a su vez dispone de exportaciones tipo **excel y pdf**, con el fin de que el aprendiz tenga reportes de sus actividades, evidencias, foros y wikis.

**Código de colores:** Informa al usuario aprendiz los colores correspondientes a cada calificación. Siendo estos así:

Este código de colores está establecido para facilitar la lectura de las calificaciones del centro de calificaciones.
Por favor, tenga en cuenta los siguientes códigos de colores:

| Color            | Nota | Estado                               |
| ---------------- | ---- | ------------------------------------ |
| Color Verde agua | A    | APROBADO                             |
| Color Rojo       | D    | NO APROBADO                          |
| Color Gris claro | X    | PENDIENTE POR PRESENTAR              |
| Color Amarillo   |      | PENDIENTE POR EVALUAR DEL INSTRUCTOR |
| Color Morado     |      | NUEVO INTENTO PENDIENTE POR EVALUAR  |
| Color Azul cielo |      | NOTA ASIGNADA MANUALMENTE            |

## 8.Uso del Centro de Unificado:

#### 1. Acceso:

- Inicia sesión como instructor utilizando credenciales ZAJUNA.
- Ingresa a un curso/ficha en el que se encuentre matriculado, busca en el menú de navegación al lado izquierdo el botón llamado "Centro de Calificaciones".
- Podra visualizar el menu principal del centro de calificaciones , alli debera ingresar a la secciòn de **_Centro de General_**.

## Perfil Instructor

#### 2. Visualización:

- Al entrar, se encuentra con una vista general que consolida todas las actividades del curso (Pruebas de conocimiento, Evidencias, Foros, Wikis, Paquetes SCORM) y Resultados de aprendizaje . La información se presenta en una tabla que muestra a todos los aprendices matriculados y sus calificaciones para cada actividad y resultado de aprendizaje grupadas por categorías.

#### 3. Herramientas:

- Puede navegar fácilmente entre los diferentes tipos de actividades (Foros, Evidencias, etc.) usando los botones de acceso rápido.
- Dispone de filtros para acotar la información por grupo de aprendices, buscar una actividad específica por su nombre o filtrar por juicio evaluativo (A, D, Pendiente).
- Al hacer clic en el nombre de una categoría, la vista se filtra para mostrar únicamente las actividades o los resultados de aprendizaje que pertenencen a esa categoría.
- Calificación Local: Seleccionar aprendices, asignarles 'A' o 'D' y Guardar Calificaciones. Esto se puede con varios resultados de aprendizaje
- Puede generar reportes de las calificaciones en formatos como Excel y CSV.
- Para facilitar el uso, el sistema cuenta con una "Guía de calificación". Esta es una ventana emergente (modal) que aparece para orientar al instructor, especialmente las primeras veces que usa la herramienta.
- Un sistema de código de colores le informa visualmente el estado de cada calificación (Aprobado, No Aprobado, Pendiente por evaluar, Nuevo intento, etc.), facilitando la identificación rápida del progreso.

`Código de colores Actividades`
| Color | Nota | Estado |
| ---------------- | ---- | --------------------------------------------------------------- |
| Color Verde agua | A | APROBADO |
| Color Rojo | D | NO APROBADO |
| Color Gris claro | X | PENDIENTE POR PRESENTAR |
| Color Amarillo | | PENDIENTE POR EVALUAR DEL INSTRUCTOR |
| Color Morado | | NUEVO INTENTO PENDIENTE POR EVALUAR |
| Color Azul cielo | | NOTA ASIGNADA MANUALMENTE |

`Código de colores Resultados de aprendizaje`

| COLOR         | NOTA  | ESTADO                                                                      |
| ------------- | ----- | --------------------------------------------------------------------------- |
| Verde azulado | A ó D | RESULTADO EVALUADO DESDE SOFIA Plus (APROBADO O NO APROBADO)                |
| Azul grisáceo | X     | POR EVALUAR                                                                 |
| Verde claro   | A     | APROBADO (PENDIENTE POR SINCRONIZAR)                                        |
| Rojo          | D     | NO APROBADO (PENDIENTE POR SINCRONIZAR)                                     |
| Celeste       | X     | PENDIENTE POR SINCRONIZAR                                                   |
| Azul oscuro   | A ó D | EN PROCESO DE SINCRONIZACIÓN DE LMS CON SOFIA Plus.                         |
| Verde medio   | A ó D | RESULTADO EVALUADO DESDE LMS Y SINCRONIZADO CON SOFIA Plus: PROCESO EXITOSO |
| Rosa          | A ó D | ERROR SINCRONIZACIÓN EN SOFIA Plus                                          |

## Contacto SOPORTE APLICACION Centro de Calificaciones:

Si tienes alguna pregunta o sugerencia, no dudes en ponerte en contacto con nosotros a través de [dsalcedot@sena.edu.co](dsalcedot@sena.edu.co).
