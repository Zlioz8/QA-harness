-- ============================================================================
--  APORTADO POR EL LABORATORIO — NO es un artefacto del proyecto.
-- ============================================================================
--
-- QUÉ ES. La reconstrucción del ESQUEMA de la BD externa "integracion" (copia local de la
-- integración SENA/Sofia Plus) que local_portafolio consulta para la pantalla Resultados (RAP).
-- El repositorio NO trae esta BD ni su definición, y el propio DEPLOY.md §8.2 lo declara como
-- «Información faltante: no hay en el repo un dump, install.xml ni definición de columnas… no se
-- puede documentar cómo recrearla desde cero solo con este repositorio». Esa ausencia ES el
-- hallazgo (candidato P3); esto solo permite MEDIR que el despliegue conecta y la pantalla
-- renderiza sin 500 en este ambiente.
--
-- DE DÓNDE SALE CADA COLUMNA. NINGUNA se inventó: todas están nombradas literalmente en
-- classes/application/services/IntegracionResultadosService.php (queries get_records_sql). El
-- esquema es fiel a lo que el código EXIGE. Lo que sí es sintético son los VALORES de la semilla
-- (02-integracion-seed.sql), y por eso la dimensión Resultados se declara NO AUTORITATIVA en el
-- informe: mide una reconstrucción del laboratorio, no los RAP reales del aprendiz.
--
-- CONTRASTE QUE LA RESPALDA. La pantalla RAP se recorrió con la cuenta REAL en zajunavideo.com
-- (evidencia mcp-evidencia/remoto-03-resultados-RAP-aprendiz.png: 83 resultados reales, con
-- competencias e instructores resueltos). Allí funciona contra la BD real. Aquí se reconstruye
-- solo para cerrar «¿el despliegue en ESTE ambiente puede servir esa pantalla?».
--
-- LÍMITE (METODOLOGIA §3). Se reconstruye lo que el código NOMBRA. Las vistas PRESENCIAL.* se
-- crean vacías con su estructura (el código las prueba en orden tras la Virtual): su ausencia de
-- filas no es un hueco, es que este aprendiz demo es de modalidad Virtual. No se dedujo ni una
-- columna que el código no pida.

-- ---------------------------------------------------------------------------
--  Esquemas. Los nombres van entre comillas: el código los escribe en MAYÚSCULAS
--  entrecomilladas ("INTEGRACION"."RESULTADO_APRENDIZAJE"), así que en PostgreSQL son
--  identificadores sensibles a mayúsculas y deben crearse igual.
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS "INTEGRACION";
CREATE SCHEMA IF NOT EXISTS "PRESENCIAL";
CREATE SCHEMA IF NOT EXISTS "RESULTADOS";
CREATE SCHEMA IF NOT EXISTS "RESULTADOS_P";

-- ---------------------------------------------------------------------------
--  INTEGRACION.RESULTADO_APRENDIZAJE  (ra):  REA_ID, REA_NOMBRE
--  Usada en el JOIN de fetchResults() y getDetailedResultsForUser().
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "INTEGRACION"."RESULTADO_APRENDIZAJE" (
    "REA_ID"     integer PRIMARY KEY,
    "REA_NOMBRE" text NOT NULL
);

-- ---------------------------------------------------------------------------
--  INTEGRACION.COMPETENCIA  (cmp):  CMP_ID, CMP_NOMBRE
--  Usada en el JOIN de getDetailedResultsForUser().
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "INTEGRACION"."COMPETENCIA" (
    "CMP_ID"     integer PRIMARY KEY,
    "CMP_NOMBRE" text NOT NULL
);

-- ---------------------------------------------------------------------------
--  INTEGRACION.V_FICHA_CARACTERIZACION_B  (modalidad Virtual):
--    FIC_ID, FIC_MOD_FORMACION, FIC_FCH_INICIALIZACION, PRF_DENOMINACION, PRA_NOMBRE
--  resolveModalidad() la prueba PRIMERO. FIC_MOD_FORMACION debe ser 'V' o 'P' (RA_SCHEMA_MAP);
--  FIC_FCH_INICIALIZACION la parsea strtotime() para armar el año/semestre de la tabla RA_*.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "INTEGRACION"."V_FICHA_CARACTERIZACION_B" (
    "FIC_ID"                integer PRIMARY KEY,
    "FIC_MOD_FORMACION"     varchar(2)  NOT NULL,   -- 'V' Virtual | 'P' Presencial
    "FIC_FCH_INICIALIZACION" varchar(32) NOT NULL,  -- fecha parseable por strtotime()
    "PRF_DENOMINACION"      text,
    "PRA_NOMBRE"            text
);

-- ---------------------------------------------------------------------------
--  PRESENCIAL.V_FICHA_CARACTERIZACION_F y _I: misma forma. resolveModalidad() las prueba
--  DESPUÉS de la Virtual. Se crean con estructura y VACÍAS: el aprendiz demo es Virtual, así que
--  el código nunca cae aquí. Vacío ≠ hueco: es que este caso no las usa.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "PRESENCIAL"."V_FICHA_CARACTERIZACION_F" (
    "FIC_ID"                integer PRIMARY KEY,
    "FIC_MOD_FORMACION"     varchar(2)  NOT NULL,
    "FIC_FCH_INICIALIZACION" varchar(32) NOT NULL,
    "PRF_DENOMINACION"      text,
    "PRA_NOMBRE"            text
);
CREATE TABLE IF NOT EXISTS "PRESENCIAL"."V_FICHA_CARACTERIZACION_I" (
    "FIC_ID"                integer PRIMARY KEY,
    "FIC_MOD_FORMACION"     varchar(2)  NOT NULL,
    "FIC_FCH_INICIALIZACION" varchar(32) NOT NULL,
    "PRF_DENOMINACION"      text,
    "PRA_NOMBRE"            text
);

-- ---------------------------------------------------------------------------
--  RESULTADOS.RA_V_<anio>_<sem>  (r): la tabla de resultados por-aprendiz. El nombre lo compone
--  resolveResultsTable() a partir de la modalidad ('V'->esquema RESULTADOS) y la fecha de la
--  ficha. La semilla usa FIC_FCH_INICIALIZACION = 2025-08-15 -> año 2025, mes 8 > 6 -> semestre
--  '02' -> RESULTADOS.RA_V_2025_02. Columnas exactas del SELECT:
--    USR_NUM_DOC, FIC_ID, REA_ID, CMP_ID, ADR_EVALUACION_RESULTADO, FECHA_UPDATE_CALIF,
--    RESPONSABLE_DE_EVALUAR
--  El match del aprendiz es regexp_replace(USR_NUM_DOC,'\D','') = regexp_replace(username,...):
--  el username demo 'demo_apr_01' se reduce a '01', así que USR_NUM_DOC de la semilla es '01'.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "RESULTADOS"."RA_V_2025_02" (
    "USR_NUM_DOC"               varchar(32) NOT NULL,
    "FIC_ID"                    integer     NOT NULL,
    "REA_ID"                    integer     NOT NULL,
    "CMP_ID"                    integer     NOT NULL,
    "ADR_EVALUACION_RESULTADO" varchar(2),           -- 'A' aprobado | 'D' desaprobado (LETTER_MAP)
    "FECHA_UPDATE_CALIF"        varchar(32),
    "RESPONSABLE_DE_EVALUAR"    varchar(32)           -- idnumber de un mdl_user (se resuelve en $DB)
);
