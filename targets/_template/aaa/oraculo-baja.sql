-- Deshace oraculo-alta.sql: revoca los permisos y elimina el rol seclab_ro. No toca ninguna tabla.
--
--   docker exec -i <contenedor_postgres> psql -U <admin> -d <db> -v ON_ERROR_STOP=1 \
--     -v db=<db> -v tabla=<tabla_auditoria> -f - < targets/<perfil>/aaa/oraculo-baja.sql
REVOKE SELECT ON :"tabla" FROM seclab_ro;
REVOKE USAGE ON SCHEMA public FROM seclab_ro;
REVOKE CONNECT ON DATABASE :"db" FROM seclab_ro;
DROP ROLE IF EXISTS seclab_ro;
