Todo el código es de **Anderson Rincón** (los dos repos). El orden es por impacto, no por persona:

**1. Desbloquear el despliegue (D1) — una línea, Alta.** Añadir `CREATE SCHEMA IF NOT EXISTS
"Produc" AUTHORIZATION encuestas;` a `deploy/postgres/10-search-path.sql`. Sin esto, cualquiera que
despliegue desde cero siguiendo el README se encuentra la API caída con un error de schema que no
menciona la causa.

**2. Cerrar el origen en claro (Alta, infraestructura).** El puerto 8000 de zajunavideo5 sirve la
API entera sin TLS (`http://zajunavideo5.com:8000/api/...`). Cerrarlo al exterior (que solo el
proxy hable con Apache) o forzar HTTPS. El HSTS que hoy manda por ese puerto es inútil sobre HTTP.

**3. Rotar los secretos de la historia (Media).** `DB_PASSWORD` en `FASE_0_COMPLETADA.md` y la
`APP_KEY` en `.env.backup_20251210_153643`. Rotar ambos y purgar la historia. Ninguno está vivo
hoy, pero la historia de git es permanente.

**4. Documentar y proteger PgBouncer (D2, D3, Media).** Añadir al README el orden real de arranque
para generar `userlist.txt` (levantar postgres → leer el hash SCRAM → escribir el fichero → levantar
el resto), y añadir `deploy/pgbouncer/userlist.txt` al `.gitignore` (el README ya pide no
versionarlo, pero nada lo impide).

**5. Añadir CI (D4, Media).** Ningún repo tiene integración continua. Nada verifica el proyecto
salvo esta auditoría.

**6. Higiene de cabeceras (Baja).** `server_tokens off` en nginx (hoy anuncia `nginx/1.24.0`), y
completar las directivas de CSP de la API (ZAP marcó directivas sin fallback explícito).

**7. Triar la señal de calidad.** 1475 hallazgos de SonarQube y ~56 CVE de dependencias (el bruto
de 87 tiene doble conteo: el repo lleva `package-lock.json` Y `yarn.lock` con los mismos 31 CVE).
No son bloqueantes por sí solos, pero conviene una pasada.
