-- ============================================================================
--  APORTADO POR EL LABORATORIO — datos SINTÉTICOS. NO son RAP reales de nadie.
-- ============================================================================
--
-- Semilla mínima para que la pantalla Resultados de local_portafolio renderice contra el esquema
-- reconstruido (01-integracion-schema.sql). Los VALORES son inventados: nombres de RAP y
-- competencias genéricos, un resultado aprobado y otro desaprobado. Por eso la dimensión Resultados
-- es NO AUTORITATIVA — mide que el despliegue conecta y pinta, no los resultados reales del
-- aprendiz (esos se vieron con la cuenta REAL en zajunavideo.com, evidencia remoto-03).
--
-- ENCAJE CON EL CORE LOCAL (lo que hace que el match funcione, sin inventar comportamiento):
--   · FIC_ID 9990001  <-> mdl_course.idnumber del curso 23535 (se fija en 03-core-hooks.sql).
--   · USR_NUM_DOC '01' <-> username 'demo_apr_01' tras regexp_replace(...,'\D','') = '01'.
--   · modalidad 'V' + fecha 2025-08-15 -> RESULTADOS.RA_V_2025_02 (resolveResultsTable()).

-- Ficha (Virtual). Un solo registro: el curso demo del aprendiz.
INSERT INTO "INTEGRACION"."V_FICHA_CARACTERIZACION_B"
    ("FIC_ID","FIC_MOD_FORMACION","FIC_FCH_INICIALIZACION","PRF_DENOMINACION","PRA_NOMBRE")
VALUES
    (9990001, 'V', '2025-08-15', 'TECNÓLOGO EN ANÁLISIS Y DESARROLLO DE SOFTWARE (DEMO LAB)',
     'PROYECTO FORMATIVO DEMO — RECONSTRUCCIÓN DEL LABORATORIO')
ON CONFLICT ("FIC_ID") DO NOTHING;

-- Competencias (dos, genéricas).
INSERT INTO "INTEGRACION"."COMPETENCIA" ("CMP_ID","CMP_NOMBRE") VALUES
    (5001, 'ANALIZAR REQUISITOS DEL SISTEMA SEGÚN METODOLOGÍA (DEMO)'),
    (5002, 'DESARROLLAR EL SOFTWARE SEGÚN DISEÑO (DEMO)')
ON CONFLICT ("CMP_ID") DO NOTHING;

-- Resultados de aprendizaje (tres, genéricos).
INSERT INTO "INTEGRACION"."RESULTADO_APRENDIZAJE" ("REA_ID","REA_NOMBRE") VALUES
    (7001, 'IDENTIFICAR LOS REQUISITOS FUNCIONALES DE ACUERDO CON EL PROBLEMA (DEMO)'),
    (7002, 'CONSTRUIR EL MODELO DE DATOS SEGÚN LOS REQUISITOS (DEMO)'),
    (7003, 'CODIFICAR LOS MÓDULOS SEGÚN EL DISEÑO (DEMO)')
ON CONFLICT ("REA_ID") DO NOTHING;

-- Resultados por-aprendiz para demo_apr_01 (USR_NUM_DOC '01'): uno aprobado, uno desaprobado,
-- uno pendiente (resultado no en LETTER_MAP -> se muestra 'X'/pendiente).
INSERT INTO "RESULTADOS"."RA_V_2025_02"
    ("USR_NUM_DOC","FIC_ID","REA_ID","CMP_ID","ADR_EVALUACION_RESULTADO","FECHA_UPDATE_CALIF","RESPONSABLE_DE_EVALUAR")
VALUES
    ('01', 9990001, 7001, 5001, 'A', '2025-10-30 14:00:00', 'DEMO-INSTRUCTOR-01'),
    ('01', 9990001, 7002, 5001, 'D', '2025-10-30 14:05:00', 'DEMO-INSTRUCTOR-01'),
    ('01', 9990001, 7003, 5002, 'P', '2025-11-02 09:00:00', 'DEMO-INSTRUCTOR-01');
