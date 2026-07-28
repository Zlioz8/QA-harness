# SECURITY-LAB — laboratorio de auditoría/QA multiproyecto

Audita **cualquier** proyecto con herramientas estándar, cada una con su configuración nativa. La
orquestación es `docker compose` declarativo y un `Makefile` de objetivos 1:1.

> **Principio.** El proyecto auditado **nunca se modifica**: se monta *read-only*. Lo único
> escribible es `reports/` y las bases de datos efímeras. El laboratorio **observa**, no corrige.

**Requisito único en la máquina destino:** Docker + Docker Compose v2.
**Requisito de capacidad:** sistema de archivos **por debajo del 90% de uso** (SonarQube falla en
silencio por encima) y ~8 GB para imágenes de herramientas. `make doctor` lo comprueba.

---

## Estructura

```
SECURITY-LAB/
  docker-compose.yml     núcleo: SÓLO herramientas. Ningún nombre de proyecto aparece aquí.
  Makefile               objetivos; TARGET=<perfil> elige el proyecto
  tools/                 new · detect · doctor · gate · run-manifest · status
  recipes/               bloques de arranque reutilizables (postgres, moodle-plugin, fastapi-uvicorn, kafka-zk)
  lib/auth/              adaptadores de autenticación (sanctum, moodle-session, jwt-bearer, basic, none)
  lib/specs/             pruebas genéricas que hereda todo proyecto (cabeceras, matriz de autorización)
  targets/<nombre>/      el perfil de un proyecto: target.env, compose.runtime.yml, zap/, k6/, playwright/, db-init/
  reports/<nombre>/      salidas + RUN.md (qué se ejecutó y qué NO)
```

La línea de corte: el núcleo hace lo que se puede saber **leyendo un repositorio**; el perfil aporta
lo que sólo se sabe **conociendo la aplicación** (cómo arranca, cómo se inicia sesión, qué endpoints
existen, qué rol puede alcanzar qué).

---

## Dar de alta un proyecto

```bash
make new    TARGET=proyecto_x            # esqueleto desde targets/_template
$EDITOR targets/proyecto_x/target.env    # SRC_PATH (o REPO_URL+BRANCH)
make detect TARGET=proyecto_x            # propone LANGS, QODANA_IMAGE, AUTH_ADAPTER y recetas
make doctor TARGET=proyecto_x            # preflight: docker, disco, puertos, permisos, roles
make static TARGET=proyecto_x            # YA produce hallazgos, sin levantar nada
```

Para las dimensiones dinámicas hay que aportar además:

- `compose.runtime.yml` componiendo recetas (`include:` — rutas relativas al **directorio del
  proyecto**), que debe responder 200 en `HEALTH_PATH`.
- `AUTH_ADAPTER` y **dos cuentas de distinto privilegio** (`ROLE_A_*`, `ROLE_B_*`).
- `playwright/authz-matrix.json`: qué rol puede alcanzar qué. **Ninguna herramienta lo sabe.**
- Un escenario sembrado (los datos sobre los que la operación autorizada sí funciona).

```bash
make up TARGET=proyecto_x
make e2e dast perf TARGET=proyecto_x
make run-manifest TARGET=proyecto_x      # reports/proyecto_x/RUN.md: cobertura real
make gate         TARGET=proyecto_x      # veredicto: sale != 0 si se incumplen umbrales
make down         TARGET=proyecto_x      # sin residuos
```

`make help` lista todos los objetivos. `make list` los perfiles existentes.

---

## Dimensiones y herramientas

| Dimensión | Herramienta | Objetivo | Necesita runtime |
|---|---|---|---|
| Secretos en toda la historia git | gitleaks + trufflehog | `make secrets` | no |
| CVE de dependencias | Trivy (fs) | `make deps` | no |
| Configuración de contenedores | Trivy (config) | `make config-scan` | no |
| CVE de imágenes | Trivy (image) | `make image-scan IMAGE=...` | no |
| Inventario de componentes | Syft | `make sbom` | no |
| SAST poliglota con taint | semgrep | `make semgrep` | no |
| Calidad / mantenibilidad | SonarQube + Qodana | `make sonar` / `make qodana` | no |
| Superficie runtime | OWASP ZAP | `make dast` | **sí** |
| Autorización y flujos | Playwright | `make e2e` | **sí** |
| Carga | k6 | `make perf` | **sí** |

---

## Lo que el laboratorio NO hace

Está escrito aquí porque es el modo de fallo más probable de esta herramienta: leerla como un botón.

- **No conoce la política de autorización.** Un `200` sólo es hallazgo si la política decía `403`.
  Esa política la escribe una persona en `authz-matrix.json`.
- **No tría.** Un hallazgo de dependencia no es un riesgo hasta que alguien evalúa alcanzabilidad.
- **No inventa escenarios de abuso de negocio.** Esos guiones se escriben después de leer el código.
- **No calibra severidad** en contexto institucional.
- **No distingue un fallo del proyecto de uno del entorno.** Si SonarQube no corrió por falta de
  disco, eso no dice nada sobre el proyecto.
- **`skip` no es `PASS`.** `make gate` lo imprime y `RUN.md` lo registra. Una dimensión que no se
  ejecutó nunca debe leerse como aprobada.

Detalle completo, con la evidencia de la corrida que lo demostró, en
[`INFORME_MIGRACION_SECURITY_LAB.md`](INFORME_MIGRACION_SECURITY_LAB.md).

---

## Política de datos

El laboratorio puede llegar a concentrar datos personales reales, credenciales de prueba conocidas y
servicios sin endurecer: es un activo sensible, no una carpeta de trabajo.

- Todos los puertos publicados se atan a `127.0.0.1`. Es un invariante del núcleo — no lo cambies.
- Preferir semillas **sintéticas**. Un volcado de producción sólo se justifica para reproducir un
  comportamiento dependiente del volumen, y con fecha de caducidad.
- `make purge TARGET=<perfil>` borra los reportes de un perfil. Anonimiza antes de compartirlos.
- `make down TARGET=<perfil>` destruye contenedores y volúmenes.

## Perfiles actuales

| Perfil | Stack | Estado |
|---|---|---|
| `costos_web` | Laravel + Vue + PostgreSQL | extraído del núcleo; verificado sin regresión |
| `antiplagio` | Moodle + plugin PHP + FastAPI + Kafka + analyzers | estático y dinámico ejecutados; ver `reports/antiplagio/RUN.md` |
| `_template` | — | esqueleto para el siguiente proyecto |
