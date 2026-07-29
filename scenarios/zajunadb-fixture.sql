-- Escenario: el esquema `midb` que local_slider_form consulta fuera de Moodle.
--
-- Descubrimiento del propio código, no supuesto: classes/external/ZajunaDbConnection.php abre un
-- PDO con las MISMAS credenciales de Moodle ($CFG->dbhost/dbname/dbuser/dbpass) y sólo cambia de
-- esquema. No hay servidor externo: `midb` vive en la misma base. El PDO aparte existe porque
-- $DB de Moodle no hace SQL cross-schema.
--
-- Sin este esquema, tres endpoints responden 500 y quedan SIN MEDIR — entre ellos los dos que
-- manejan datos personales (filtros de destinatarios e historial de envíos). Un 500 no es un
-- hallazgo de seguridad ni una ausencia de hallazgos: es una dimensión que no se pudo evaluar.
--
-- Los datos son SINTÉTICOS y deliberadamente pocos. Su trabajo no es parecerse a producción, es
-- permitir que el código llegue hasta el final de sus consultas para poder juzgar su
-- autorización. Las regionales y centros llevan nombres reconocibles del SENA porque el plugin
-- los muestra en pantalla y un nombre inventado haría ilegible la evidencia.
--
-- Estructura derivada de las consultas del plugin: no existe DDL en el repositorio, así que las
-- columnas son las que el código pide. Si una consulta futura pide una columna que falta, el
-- fallo será un 500 explícito aquí y no un silencio.

CREATE SCHEMA IF NOT EXISTS midb;

-- SELECT rgn_id, nombre FROM midb.regionales WHERE rgn_id IN (...)
-- SELECT DISTINCT r.rgn_id AS id, r.nombre AS name ...
CREATE TABLE IF NOT EXISTS midb.regionales (
    rgn_id  integer PRIMARY KEY,
    nombre  text NOT NULL
);

-- SELECT sed_id, nombre FROM midb.centros WHERE sed_id IN (...)
-- rgn_id no aparece en las consultas leídas, pero un centro sin regional no es representable;
-- se incluye para que la semilla sea coherente y para que un JOIN futuro no rompa.
CREATE TABLE IF NOT EXISTS midb.centros (
    sed_id  integer PRIMARY KEY,
    rgn_id  integer REFERENCES midb.regionales(rgn_id),
    nombre  text NOT NULL
);

-- Filtros de destinatarios guardados. El propio archivo documenta el alcance: cada
-- administrador ve y borra SÓLO los suyos (created_by = $USER->id). Probar esa frase necesita
-- dos administradores sembrados; con uno solo la consulta se ejecuta pero no demuestra nada.
CREATE TABLE IF NOT EXISTS midb.saved_filters (
    id           serial PRIMARY KEY,
    nombre       text,
    modalidad    text,
    regional_id  text,      -- listas separadas por coma, no enteros: implode(',', $ids)
    centro_id    text,
    programa_id  text,
    fecha_desde  bigint,
    fecha_hasta  bigint,
    roles        text,
    estado       integer DEFAULT 1,
    created_by   bigint,
    created_at   timestamptz DEFAULT now()
);

-- Historial de correo enviado. `envios2`, con el 2, tal como lo nombra el INSERT del plugin.
CREATE TABLE IF NOT EXISTS midb.envios2 (
    id            serial PRIMARY KEY,
    destinatario  text,
    asunto        text,
    body          text,
    cursos        jsonb,
    created_at    timestamptz DEFAULT now()
);

INSERT INTO midb.regionales (rgn_id, nombre) VALUES
    (1, 'RISARALDA'), (2, 'ANTIOQUIA'), (3, 'DISTRITO CAPITAL')
ON CONFLICT (rgn_id) DO NOTHING;

INSERT INTO midb.centros (sed_id, rgn_id, nombre) VALUES
    (11, 1, 'CENTRO DE COMERCIO Y SERVICIOS'),
    (12, 1, 'CENTRO ATENCION SECTOR AGROPECUARIO'),
    (21, 2, 'CENTRO DE SERVICIOS Y GESTION EMPRESARIAL'),
    (31, 3, 'CENTRO DE GESTION INDUSTRIAL')
ON CONFLICT (sed_id) DO NOTHING;

-- Un filtro guardado de ejemplo, atribuido al administrador del sitio (id 2). Existe para que
-- `?action=list` devuelva una fila en vez de un conjunto vacío: un endpoint que responde 200 con
-- una lista vacía no prueba que la autorización funcione, sólo que no falló al conectarse.
INSERT INTO midb.saved_filters
    (nombre, modalidad, regional_id, centro_id, programa_id, fecha_desde, fecha_hasta, roles, estado, created_by)
SELECT 'Filtro de laboratorio', 'titulada', '1', '11', '', 0, 0, 'student', 1, 2
WHERE NOT EXISTS (SELECT 1 FROM midb.saved_filters WHERE nombre = 'Filtro de laboratorio');

-- Los permisos van al usuario que Moodle usa; el nombre lo pone la receta al restaurar.
GRANT USAGE ON SCHEMA midb TO CURRENT_USER;
GRANT ALL ON ALL TABLES IN SCHEMA midb TO CURRENT_USER;
GRANT ALL ON ALL SEQUENCES IN SCHEMA midb TO CURRENT_USER;

-- Y uno del ROL A de la auditoría, resuelto por username porque su id lo asigna Moodle al
-- sembrarlo. Con esto `?action=list` devuelve una fila para A y ninguna para B, que es
-- exactamente la afirmación que el archivo hace sobre sí mismo — comprobable en vez de creída.
INSERT INTO midb.saved_filters
    (nombre, modalidad, regional_id, centro_id, programa_id, fecha_desde, fecha_hasta, roles, estado, created_by)
SELECT 'Filtro del rol A', 'complementaria', '2', '21', '', 0, 0, 'student', 1, u.id
FROM mdl_user u
WHERE u.username = 'gestor_lab'
  AND NOT EXISTS (SELECT 1 FROM midb.saved_filters WHERE nombre = 'Filtro del rol A');
