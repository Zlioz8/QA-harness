-- newintegracion: SYNTHETIC, and that word has to survive all the way into the report.
--
-- This is one of the four databases DEPLOY.md section 8 says cannot be built from the
-- repository: they hold real integration data and exist only as backups. The lab has no
-- backup, and the lab's data policy would refuse a production dump anyway — the previous
-- incident (finding L1) was exactly a real dump becoming reachable from the LAN, with 20,368
-- real people in it.
--
-- So the structure is reconstructed from what the application QUERIES — the object and column
-- names below come from dashboard/Consultas/*.sql and database/queries-*.json, not from a
-- schema anyone handed over — and the rows are invented.
--
-- WHAT THIS BUYS, AND WHAT IT DOES NOT:
--
--   * The application boots, the integration screens render, and every AUTHORIZATION and
--     runtime question becomes measurable — which is what the audit is for. A screen that
--     500s because a table is missing tests nothing.
--
--   * It does NOT make the reports correct. Anything that depends on the SHAPE of the real
--     data — row counts, aggregate totals, performance under real volume, an N+1 that only
--     hurts at 20k rows — is NOT COVERED, and must be reported as NOT COVERED rather than as
--     "no findings". Those two are not the same sentence and the difference is the whole
--     point of this lab.
--
-- If the team supplies a sanitised backup, drop it in place of this file and delete these
-- caveats from the report.

\connect newintegracion

CREATE SCHEMA IF NOT EXISTS "INTEGRACION";

-- Replicated SOFIA views. Real ones are views over Oracle; here they are plain tables, which
-- is indistinguishable to a SELECT and is what every query in the repository issues.
CREATE TABLE IF NOT EXISTS "INTEGRACION"."V_PROGRAMA_FORMACION_B" (
    "PRF_ID"             BIGINT PRIMARY KEY,
    "PRF_TIPO_PROGRAMA"  VARCHAR(40),
    "PRF_CODIGO"         VARCHAR(40),
    "PRF_DENOMINACION"   VARCHAR(200)
);

CREATE TABLE IF NOT EXISTS "INTEGRACION"."V_FICHA_CARACTERIZACION_B" (
    "FIC_ID"                  BIGINT PRIMARY KEY,
    "PRF_ID"                  BIGINT,
    "RGN_ID"                  BIGINT,
    "SED_ID"                  BIGINT,
    "PRA_ID"                  BIGINT,
    "FIC_FCH_INICIALIZACION"  TIMESTAMP,
    "FIC_MOD_FORMACION"       VARCHAR(60),
    "PRF_CODIGO"              VARCHAR(40),
    "PRF_DENOMINACION"        VARCHAR(200),
    "LMS_ID"                  BIGINT,
    "LMS_ESTADO"              VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS "INTEGRACION"."V_PERSONA_B" (
    "PER_ID"        BIGINT PRIMARY KEY,
    "PER_NOMBRE"    VARCHAR(120),
    "PER_APELLIDO"  VARCHAR(120),
    "PER_CORREO"    VARCHAR(160),
    "PER_NUM_DOC"   VARCHAR(30)
);

CREATE TABLE IF NOT EXISTS "INTEGRACION"."V_REGISTRO_ACADEMICO_B" (
    "REG_ID"   BIGINT PRIMARY KEY,
    "FIC_ID"   BIGINT,
    "PER_ID"   BIGINT,
    "REG_ESTADO" VARCHAR(40)
);

CREATE TABLE IF NOT EXISTS "INTEGRACION"."V_INSTRUCTORXFICHA_B" (
    "ID"      BIGINT PRIMARY KEY,
    "FIC_ID"  BIGINT,
    "PER_ID"  BIGINT
);

CREATE TABLE IF NOT EXISTS "INTEGRACION"."V_FUNCIONARIO_B" (
    "FUN_ID"  BIGINT PRIMARY KEY,
    "PER_ID"  BIGINT,
    "FUN_CARGO" VARCHAR(120)
);

-- Integration working tables.
CREATE TABLE IF NOT EXISTS "INTEGRACION"."USUARIO_LMS" (
    "ID_USUARIO_LMS"  BIGINT PRIMARY KEY,
    "PER_ID"          BIGINT,
    "USERNAME"        VARCHAR(100),
    "CORREO"          VARCHAR(160),
    "LMS_ESTADO"      VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS "INTEGRACION"."USUARIO_LMS_ENROLL_C" (
    "ID_USUARIO_LMS_ENROLL" BIGINT PRIMARY KEY,
    "ID_USUARIO_LMS"        BIGINT,
    "FIC_ID"                BIGINT,
    "LMS_ESTADO"            VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS "INTEGRACION"."USUARIO_LMS_ENROLL_T" (
    LIKE "INTEGRACION"."USUARIO_LMS_ENROLL_C" INCLUDING ALL
);

CREATE TABLE IF NOT EXISTS "INTEGRACION"."NOVEDAD_ENROLL_C" (
    "ID_NOVEDAD_ENROLL" BIGINT PRIMARY KEY,
    "FIC_ID"            BIGINT,
    "PER_ID"            BIGINT,
    "TIPO_NOVEDAD"      VARCHAR(60),
    "LMS_ESTADO"        VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS "INTEGRACION"."NOVEDAD_ENROLL_T" (
    LIKE "INTEGRACION"."NOVEDAD_ENROLL_C" INCLUDING ALL
);

CREATE TABLE IF NOT EXISTS "INTEGRACION"."NOVEDAD_FICHA_C" (
    "ID_NOVEDAD_FICHA" BIGINT PRIMARY KEY,
    "FIC_ID"           BIGINT,
    "TIPO_NOVEDAD"     VARCHAR(60),
    "LMS_ESTADO"       VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS "INTEGRACION"."NOVEDAD_FICHA_T" (
    LIKE "INTEGRACION"."NOVEDAD_FICHA_C" INCLUDING ALL
);

-- ---------------------------------------------------------------------------------------
-- Invented rows. Enough for a screen to render a table, a chart and a non-empty export.
-- Deliberately tiny: pretending to reproduce production volume would invite exactly the
-- performance conclusions this fixture cannot support.
-- ---------------------------------------------------------------------------------------
INSERT INTO "INTEGRACION"."V_PROGRAMA_FORMACION_B" VALUES
  (1, 'TECNOLOGO',    'PRG-001', 'Programa sintetico de laboratorio A'),
  (2, 'TECNICO',      'PRG-002', 'Programa sintetico de laboratorio B'),
  (3, 'COMPLEMENTARIA','PRG-003','Programa sintetico de laboratorio C')
ON CONFLICT DO NOTHING;

INSERT INTO "INTEGRACION"."V_FICHA_CARACTERIZACION_B" VALUES
  (1001, 1, 63, 9001, 5001, '2026-02-01 08:00:00', 'PRESENCIAL', 'PRG-001', 'Programa sintetico de laboratorio A', 70001, 'ACTIVO'),
  (1002, 2, 63, 9002, 5002, '2026-03-15 08:00:00', 'VIRTUAL',    'PRG-002', 'Programa sintetico de laboratorio B', NULL,  NULL),
  (1003, 3, 11, 9003, 5003, '2026-04-20 08:00:00', 'PRESENCIAL', 'PRG-003', 'Programa sintetico de laboratorio C', 70003, 'ACTIVO')
ON CONFLICT DO NOTHING;

INSERT INTO "INTEGRACION"."V_PERSONA_B" VALUES
  (5001, 'Persona', 'Sintetica Uno', 'sintetica1@lab.test', '900000101'),
  (5002, 'Persona', 'Sintetica Dos', 'sintetica2@lab.test', '900000102'),
  (5003, 'Persona', 'Sintetica Tres','sintetica3@lab.test', '900000103')
ON CONFLICT DO NOTHING;

INSERT INTO "INTEGRACION"."V_REGISTRO_ACADEMICO_B" VALUES
  (6001, 1001, 5001, 'EN FORMACION'),
  (6002, 1002, 5002, 'EN FORMACION'),
  (6003, 1003, 5003, 'RETIRO VOLUNTARIO')
ON CONFLICT DO NOTHING;

INSERT INTO "INTEGRACION"."V_INSTRUCTORXFICHA_B" VALUES
  (7001, 1001, 5003), (7002, 1003, 5001)
ON CONFLICT DO NOTHING;

INSERT INTO "INTEGRACION"."V_FUNCIONARIO_B" VALUES
  (8001, 5003, 'Instructor de laboratorio')
ON CONFLICT DO NOTHING;

INSERT INTO "INTEGRACION"."USUARIO_LMS" VALUES
  (70001, 5001, 'sintetica1', 'sintetica1@lab.test', 'ACTIVO'),
  (70002, 5002, 'sintetica2', 'sintetica2@lab.test', NULL),
  (70003, 5003, 'sintetica3', 'sintetica3@lab.test', 'ACTIVO')
ON CONFLICT DO NOTHING;

INSERT INTO "INTEGRACION"."USUARIO_LMS_ENROLL_C" VALUES
  (80001, 70001, 1001, 'ACTIVO'),
  (80002, 70002, 1002, NULL)
ON CONFLICT DO NOTHING;

INSERT INTO "INTEGRACION"."NOVEDAD_ENROLL_C" VALUES
  (90001, 1001, 5001, 'TRASLADO', 'ACTIVO'),
  (90002, 1003, 5003, 'RETIRO',   NULL)
ON CONFLICT DO NOTHING;

INSERT INTO "INTEGRACION"."NOVEDAD_FICHA_C" VALUES
  (95001, 1002, 'APERTURA', NULL)
ON CONFLICT DO NOTHING;

