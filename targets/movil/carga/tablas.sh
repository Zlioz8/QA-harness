#!/usr/bin/env bash
# Filas exactas y bytes de cada tabla de la base de la API, en CSV: tabla,filas,bytes.
docker exec -i movil_api-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F","' <<'SQL'
select format('select %L, count(*), pg_total_relation_size(%L::regclass) from %I', relname, quote_ident(relname), relname)
  from pg_stat_user_tables order by 1 \gexec
SQL
