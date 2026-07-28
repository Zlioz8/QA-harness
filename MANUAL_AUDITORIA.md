# Manual — Laboratorio de Auditoría/QA reproducible (SECURITY-LAB)

Guía para auditar **cualquier proyecto** con este laboratorio. Está pensado para proyectos
**Laravel + Vue + PostgreSQL**, pero el patrón (contenedores + herramientas dedicadas +
parametrización por `.env`) sirve para adaptarlo a otros stacks.

Principio rector: **se audita, no se modifica.** El repositorio objetivo se monta *read-only*; lo
único escribible es `reports/` y la base de datos efímera.

---

## 1. Requisito único
- **Docker + Docker Compose v2.** Nada más. Todas las herramientas (PHP, Node, SonarQube, Qodana,
  gitleaks, trufflehog, Trivy, OWASP ZAP, k6, Playwright) corren como imágenes; no se instala nada
  en la máquina anfitriona.

Verificar:
```bash
docker --version && docker compose version
```

---

## 2. Estructura del laboratorio
```
SECURITY-LAB/
  .env                     # <-- lo ÚNICO que editas por proyecto
  docker-compose.yml       # orquestación (perfiles)
  Makefile                 # targets 1:1 a cada herramienta
  docker/
    Dockerfile.app         # backend (PHP + extensiones) — ajusta versión por proyecto
    lab.env                # .env de RUNTIME del backend (DB/sesión del lab)
  db-init/                 # esquema+seed que se cargan al primer arranque de la BD
  sonar/  qodana/  zap/  k6/  playwright/  configs/   # config nativa de cada herramienta
  work/repo/               # clon del proyecto (montado read-only)   [gitignored]
  reports/                 # salidas de cada herramienta             [gitignored]
```

---

## 3. Poner el lab a apuntar a un proyecto nuevo

### 3.1 Editar `.env`
```bash
REPO_URL=ssh://git@tu-git:2222/grupo/proyecto.git
BRANCH=develop
BACKEND_SUBDIR=Backend            # subcarpeta del backend Laravel dentro del repo
FRONTEND_SUBDIR=Frontend          # subcarpeta del SPA Vue
PHP_VERSION=8.4                   # la que exija el composer.json del proyecto
APP_PORT=8099                     # puerto host del backend (curl/ZAP/k6)
FRONTEND_PORT=5173                # puerto host del SPA
DB_NAME=audit  DB_USER=postgres  DB_PASSWORD=admin01
ADMIN_EMAIL=admin@test.local  ADMIN_PASS=secret123     # cuentas de prueba (ver 3.3)
REP_EMAIL=rep@test.local      REP_PASS=secret123
ALLOWED_ORIGIN=http://localhost:5173
```

### 3.2 Ajustar el runtime del backend (`docker/lab.env`)
Es el `.env` que usa el backend **dentro del lab** (no el del proyecto). Debe apuntar a la BD del
lab y usar sesión/cache que no dependan del esquema del proyecto:
```
DB_CONNECTION=pgsql  DB_HOST=db  DB_PORT=5432  DB_DATABASE=audit  DB_USERNAME=postgres  DB_PASSWORD=admin01
SESSION_DRIVER=file  CACHE_STORE=file  QUEUE_CONNECTION=sync
SANCTUM_STATEFUL_DOMAINS=localhost:8099,localhost:8000,localhost:5173
```
> Por qué existe: `php artisan serve` **reenvía a sus workers los valores del archivo `.env`**, así
> que la config de BD/sesión debe estar correcta en ese archivo, no solo en variables de entorno.

### 3.3 Datos: dos escenarios

**A) El proyecto tiene migraciones completas** → no necesitas `db-init/`. El backend hará
`php artisan migrate` y creará el esquema. Añade solo un seed de usuarios de prueba
(`db-init/02_seed.sql`) con contraseña conocida (bcrypt) que coincida con `ADMIN_PASS`/`REP_PASS`.

**B) El proyecto NO reproduce su esquema por migraciones** (o te dan un dump) → coloca en
`db-init/`:
- `01_data.sql` — el esquema+datos. Si el dump es **formato custom** de PostgreSQL, conviértelo
  primero:
  ```bash
  docker run --rm -v "$PWD/work/repo/DUMP.sql:/in.dump:ro" postgres:17 \
    pg_restore --no-owner --no-privileges -f /dev/stdout /in.dump > db-init/01_data.sql
  ```
- `02_seed.sql` — inserta tus 2 usuarios de prueba (rol admin y rol no-admin) con hash bcrypt
  conocido, referenciando IDs válidos del propio dump. Genera el hash:
  ```bash
  php -r 'echo password_hash("secret123", PASSWORD_BCRYPT, ["cost"=>10]),"\n";'
  ```
Postgres ejecuta todo `db-init/*.sql` en orden alfabético al primer arranque.

### 3.4 Versión de PHP y extensiones
`docker/Dockerfile.app` instala `pdo_pgsql pgsql gd intl zip bcmath`. Si el proyecto usa otras
(p. ej. `redis`, `gmp`), agrégalas ahí. Cambia `PHP_VERSION` en `.env`.

### 3.5 Rutas de análisis
- `sonar/sonar-project.properties`: ajusta `sonar.sources` a tus subdirs.
- `playwright/tests/*.spec.ts` y `k6/*.js`: adapta los endpoints/flujos a tu API.

---

## 4. Traer el código y levantar
```bash
make clone     # clona REPO_URL@BRANCH en work/repo  (requiere acceso SSH)
#   alternativa manual:  git clone -b <rama> <REPO_URL> work/repo

make up         # db(+seed) + backend + frontend
#   valida:     curl -fsS http://localhost:$APP_PORT/up   -> 200
```

---

## 5. Ejecutar los análisis (una dimensión por comando)

| Comando | Herramienta | Qué evalúa | Salida |
|---|---|---|---|
| `make static` | SonarQube + Qodana + gitleaks + Trivy | calidad, seguridad estática, secretos, CVEs | dashboard + `reports/` |
| `make secrets` | gitleaks + trufflehog | secretos en **todo** el historial git | `reports/gitleaks.sarif` |
| `make deps` | Trivy | dependencias vulnerables | `reports/trivy/` |
| `make sonar` / `make qodana` | SonarQube / Qodana | code smells, duplicación, complejidad | dashboard `:9000` / `reports/qodana/` |
| `make build` | Vite (node) | build de producción en Linux | `reports/build/vite-build.log` |
| `make dast` | OWASP ZAP | headers, superficie, alertas runtime | `reports/zap/zap-report.html` |
| `make perf` | k6 | latencia/throughput bajo carga | consola + `reports/k6/` |
| `make e2e` | Playwright | authz, XSS, flujos funcionales (API) | `reports/playwright/html/` |

Ver reporte visual de Playwright:
```bash
xdg-open reports/playwright/html/index.html
```

---

## 6. Pruebas por navegador (UI real)
El backend suele estar publicado en `:APP_PORT` (curl/ZAP/k6). Si el **SPA tiene la URL de API
hardcodeada** (ej. `localhost:8000`), publica el backend también en ese puerto para que el navegador
lo resuelva como en la máquina del desarrollador (añade `- "8000:8000"` al servicio `app`).

Abre `http://localhost:5173`, entra con las cuentas de prueba y valida:
- separación de roles (una cuenta de bajo privilegio no debe alcanzar rutas admin),
- pantallas que dependen de datos reales (listados grandes, reportes),
- render de contenido de usuario (XSS),
- en DevTools → Network, a qué origen llama el SPA (detecta URLs hardcodeadas).

> Si el SPA no monta por assets con capitalización incorrecta (case-sensitivity en Linux), es un
> **hallazgo**. Para poder testear la UI puedes crear copias con el nombre correcto **solo en la
> copia de runtime del contenedor** (ver el comentario `LAB-ONLY WORKAROUND` en el servicio
> `frontend`), dejándolo documentado como anotación; **nunca** edites el repo auditado.

### Con Chrome DevTools MCP (opcional)
Si tu entorno tiene el MCP de Chrome DevTools, puedes automatizar el flujo UI (navegar, llenar
login, click, screenshot, listar red/consola) y capturar evidencias sin escribir Selenium.

---

## 7. Interpretar y reportar
- Cada herramienta deja su formato estándar en `reports/` (dashboard, SARIF, HTML, JSON).
- Consolida en un índice (`reports/RESULTS.md`) que enlace los reportes y traduzca a hallazgos.
- Entregables sugeridos:
  - **Informe técnico** (`.md`): hallazgos con evidencia por herramienta, `archivo:línea`, comandos.
  - **Informe ejecutivo** (PDF formato institucional): síntesis por severidad y decisiones.

---

## 8. Apagar
```bash
make down       # elimina contenedores + volúmenes; sin residuos
```
Verifica que no quedó nada: `docker ps` y los puertos liberados.

---

## 9. Adaptar a otros stacks
El patrón es agnóstico. Para un stack distinto:
- **Backend no-PHP** (Node/FastAPI/Go): reemplaza `Dockerfile.app` y el `command` del servicio
  `app` por el arranque de ese runtime; el resto (ZAP, k6, Playwright, gitleaks, Trivy) no cambia.
- **Sin frontend**: usa solo perfiles `runtime/static/dast/perf` y las specs de Playwright en modo
  API (request context).
- **Otra BD**: cambia `DB_IMAGE` y el healthcheck; ajusta `lab.env`.
- **Herramientas**: cada una es un servicio independiente en `docker-compose.yml`; agrega o quita
  según el proyecto (p. ej. `bandit`/`semgrep` para Python, `gosec` para Go).

---

## 10. Solución de problemas
| Síntoma | Causa / arreglo |
|---|---|
| `composer` falla por versión de PHP | ajusta `PHP_VERSION`; el `command` ya usa `--ignore-platform-req=php` como respaldo |
| Login del backend da 500 con `sqlite`/BD equivocada | revisa `docker/lab.env` (serve reenvía sus valores); usa `SESSION_DRIVER=file` |
| `pg_restore: unsupported version` | convierte el dump con una imagen `postgres:<versión-del-dump>` (ver 3.3.B) |
| Herramienta no puede escribir en `reports/` | permisos por UID; `docker run --rm -v "$PWD/reports:/r" alpine chmod -R 777 /r` |
| El SPA no carga en Linux (assets) | case-sensitivity → hallazgo; workaround solo en runtime (ver 6) |
| ZAP no genera reporte | carpeta `reports/zap` de otro UID; recréala con permisos abiertos |

---

*El laboratorio es reproducible: los mismos comandos producen los mismos resultados en cualquier
máquina con Docker. El detalle de la última corrida está en `reports/RESULTS.md`.*
