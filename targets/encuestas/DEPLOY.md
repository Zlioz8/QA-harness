# Despliegue a producción — Encuestas

Cierra los 4 puntos de infraestructura que son el cuello de botella real (no el refactor).

| # | Punto | Estado | Cómo se resuelve aquí |
|---|-------|--------|----------------------|
| 1 | Pooling de conexiones (PgBouncer) | Provisto | servicio `pgbouncer` + `pgbouncer/pgbouncer.ini` |
| 2 | Worker de cola | Provisto | servicio `worker` (o `supervisor/encuestas-worker.conf`) |
| 3 | Servidor web real | Ya existía | Apache vía `docker/Dockerfile` (NO `php artisan serve`) |
| 4 | Endurecimiento frontend (CSP / token) | Parcial | CSP API ya está; SPA y token: ver abajo |
| 5 | Scheduler (tareas agendadas) | Provisto | servicio `scheduler` (`php artisan schedule:work`) |
| 6 | Índices/contadores pesados (`migrations_manual`) | Provisto | servicio `indexer` — paridad con el `docker-compose.yml` raíz |

## 0. Antes de nada — `.env` de producción
```
APP_ENV=production
APP_DEBUG=false                # NUNCA true en prod (filtra trazas/errores)
APP_URL=https://tu-dominio
FRONTEND_URL=https://tu-front
CORS_ALLOWED_ORIGINS=https://tu-front
SANCTUM_STATEFUL_DOMAINS=tu-front
SANCTUM_EXPIRATION=240

DB_CONNECTION=pgsql
DB_HOST=pgbouncer              # <-- apunta al POOLER, no a Postgres
DB_PORT=6432
DB_DATABASE=encuestas
DB_USERNAME=encuestas
DB_PASSWORD=<fuerte>
DB_SCHEMA=Produc

QUEUE_CONNECTION=database      # requiere el worker corriendo
CACHE_STORE=redis             # opcional pero recomendado (hay redis)
SESSION_DRIVER=redis

API_RATE_LIMIT=500            # se queda en 500 en prod
# LOGIN_RATE_LIMIT: NO definir en prod (default de codigo = 5/min, anti fuerza-bruta)
```

## 1. PgBouncer (pooling)
1. Generar `pgbouncer/userlist.txt` desde `userlist.txt.example` (hash SCRAM real del rol).
2. El `search_path` del schema `Produc` se fija a NIVEL DE ROL (`postgres/10-search-path.sql`), porque
   en `pool_mode=transaction` un `SET search_path` por sesión NO persiste. Si la DB ya existe (no es
   primer arranque), correr manualmente:
   ```sql
   ALTER ROLE encuestas SET search_path TO "Produc", public;
   ```
3. `default_pool_size` (20) debe ser < `max_connections` de Postgres (aquí 200) con margen.
4. Si aparece `prepared statement "..." already exists`: añadir a `config/database.php` en la conexión
   `pgsql` -> `'options' => [PDO::ATTR_EMULATE_PREPARES => true]` (Laravel/PDO no suele necesitarlo,
   pero es el escape si el pooling de transacciones choca con prepared statements del servidor).

## 2. Worker de cola
- Con docker-compose: el servicio `worker` ya corre `queue:work --tries=3 --max-time=3600`.
- Sin docker: usar `supervisor/encuestas-worker.conf`.
- CRÍTICO tras cada deploy de código: reiniciar el worker (`docker compose ... restart worker` o
  `supervisorctl restart encuestas-worker:*`) — es un proceso largo y si no, ejecuta el código viejo.
  - **En un solo comando** (sin `restart` aparte): añadir `--force-recreate` al `up` (ver §5) recrea
    worker/scheduler/export_worker en la misma subida. Imprescindible en el stack **LOCAL**
    (`docker-compose.yml`, código por **bind-mount** → `up --build` por sí solo NO recrea los procesos
    largos, que siguen con el código y el `.env` viejos). En el stack docker de **PROD** el código va
    **COPIADO** en la imagen, así que `up -d --build` ya recrea los servicios cuya imagen cambió; ahí el
    `restart`/`--force-recreate` solo hace falta para el path **sin-docker/supervisor**.
- Sin worker, `SendSurveyEmailJob` y `InvalidateSurveyCacheListener` se encolan y NUNCA se procesan.

## 2.1 Scheduler (tareas agendadas)
- Las tareas agendadas en `bootstrap/app.php` (`withSchedule`) son: `surveys:update-states` (migración de
  estados de encuesta), `surveys:send-reminders` y `surveys:send-assignment-reminders` (recordatorio
  automático por asignación N días antes del cierre — ficha 3.7). Todas `hourly()`.
- Con docker-compose: el servicio `scheduler` corre `php artisan schedule:work` (proceso de larga vida que
  ejecuta las tareas vencidas cada minuto; NO necesita crontab dentro del contenedor).
- Sin docker: un cron del sistema con `* * * * * cd /ruta && php artisan schedule:run >> /dev/null 2>&1`.
- SIN scheduler, los recordatorios automáticos por asignación NUNCA se disparan (la lógica existe pero
  nada la ejecuta). El `scheduler` ENCOLA correos; el `worker` los procesa: se necesitan ambos.
- Tras cada deploy de código: reiniciar también el `scheduler` (`docker compose ... restart scheduler`).

## 3. Servidor web
- Ya es real (Apache en el contenedor `app`). No usar `php artisan serve` en prod.
- Optimización de prod (build de imagen): cambiar `composer install` a `--no-dev --optimize-autoloader`
  y cachear config/rutas/vistas en el entrypoint de prod:
  ```
  php artisan config:cache && php artisan route:cache && php artisan view:cache
  ```
  (OJO: con config:cache, `env()` fuera de config/ devuelve null — el código ya usa config(); revisar.)

## 4. Endurecimiento de frontend
- **CSP de la API**: ya la envía `app/Http/Middleware/SecurityHeaders.php` (restrictiva para no-HTML).
- **CSP de la SPA**: configurarla donde se sirve el frontend compilado (nginx/Apache/CDN del front), p.ej.:
  ```
  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
    img-src 'self' data:; connect-src 'self' https://tu-api; object-src 'none'; frame-ancestors 'none';
    base-uri 'self'
  ```
- **Token en HttpOnly cookie** (mitiga robo por XSS): es un cambio de CÓDIGO (Sanctum SPA cookie-based +
  quitar el token de localStorage en el front). Requiere probar el flujo de login con la SPA corriendo;
  NO incluido aquí. Mientras tanto está mitigado con TTL corto (4h) + CSP + sanitización.

## 5. Migraciones y arranque
Las migraciones corren SOLAS al levantar: el servicio `migrate` (de un solo uso) ejecuta
`migrate --force` conectado DIRECTO a Postgres, y `app` + `worker` esperan a que termine OK
(`depends_on: condition: service_completed_successfully`). No hay que correr nada a mano.

**Índices/contadores pesados — servicio `indexer` (¡presente en AMBOS composes!).** Aparte del `migrate`
bloqueante, un servicio `indexer` (de un solo uso, EN SEGUNDO PLANO) corre las migraciones de
`database/migrations_manual/` — los ~14 `CREATE INDEX CONCURRENTLY` sobre tablas de millones — más
`counters:rebuild --if-empty` y `respondent-counters:rebuild --if-empty`. NO bloquea el arranque:
`app`/`worker`/`scheduler` **NO** dependen de él, así que un CONCURRENTLY que tarda minutos nunca cuelga el
`up`. Es idempotente (en los `up` siguientes sale en segundos). Se conecta DIRECTO a Postgres (no a
PgBouncer), igual que `migrate`. **Está en el `docker-compose.yml` de la raíz Y en
`deploy/docker-compose.prod.yml`**, así que —uses el compose que uses— el resultado final es el MISMO
(mismas migraciones normales + manuales + contadores). Antes faltaba en el de `deploy/`; ya se agregó a
paridad.
```
docker compose -f deploy/docker-compose.prod.yml up -d --build
# El servicio 'migrate' aplica las migraciones PENDIENTES una vez y sale; luego suben app y worker.
# (jobs/failed_jobs ya existen; si no: php artisan queue:table && php artisan queue:failed-table)
#
# Stack LOCAL (dev, bind-mount) — TODO en un comando, sin 'restart' aparte:
#   docker compose -f docker-compose.yml up -d --build --force-recreate
#   --force-recreate recrea worker/scheduler/export_worker (procesos 'queue:work' de larga vida) para que
#   tomen el CÓDIGO y el .env (Redis) nuevos; en LOCAL 'up --build' por sí solo NO los recrea.
#   NO borra volúmenes: los datos de Postgres persisten (no es un 'down --volumes').
```
- Se conecta directo a Postgres (no a PgBouncer) porque el DDL y los advisory locks de las
  migraciones no juegan bien con el pooling en modo transaccion.
- `migrate --force` solo aplica lo PENDIENTE (idempotente); reejecutarlo no toca lo ya migrado.
- Si una migracion falla, el servicio `migrate` sale con codigo != 0 y app/worker NO arrancan
  (fallo visible en `docker compose logs migrate`), en vez de arrancar con un schema a medias.

## 6. Checklist final de prod
- [ ] `APP_DEBUG=false`, `APP_ENV=production`
- [ ] DB apunta a PgBouncer (6432); `ALTER ROLE ... search_path` aplicado
- [ ] worker corriendo y reiniciado tras el deploy
- [ ] HTTPS + CSP en el host de la SPA
- [ ] backups de Postgres + monitoreo de `failed_jobs`
- [ ] `API_RATE_LIMIT=500`, sin `LOGIN_RATE_LIMIT` en prod
- [ ] mail real configurado (no mailpit) y probado
