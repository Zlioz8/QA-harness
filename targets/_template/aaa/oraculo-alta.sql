-- Alta del rol de SOLO LECTURA que usa el oráculo de auditoría (tools/aaa-oracle.sh).
-- Reversible con oraculo-baja.sql. La contraseña NO va en este archivo: se pasa como variable.
--
--   docker exec -i <contenedor_postgres> psql -U <admin> -d <db> -v ON_ERROR_STOP=1 \
--     -v db=<db> -v tabla=<tabla_auditoria> -v seclab_pass='<contraseña>' -f - < targets/<perfil>/aaa/oraculo-alta.sql
--
-- y en targets/<perfil>/target.env.local:  AAA_DB_URL=postgresql://seclab_ro:<contraseña>@127.0.0.1:<puerto>/<db>
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'seclab_ro') THEN CREATE ROLE seclab_ro LOGIN; END IF;
END $$;
ALTER ROLE seclab_ro WITH PASSWORD :'seclab_pass';
GRANT CONNECT ON DATABASE :"db" TO seclab_ro;
GRANT USAGE ON SCHEMA public TO seclab_ro;
GRANT SELECT ON :"tabla" TO seclab_ro;
