# QA-harness — laboratorio de auditoría/QA multiproyecto

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

## Qué tienes que traer (la escalera)

**El laboratorio no instala tu aplicación.** Hay tres peldaños y cada uno desbloquea más:

| Peldaño | Qué aportas | Qué se desbloquea |
|---|---|---|
| **1** | un checkout del código | secretos · CVE · configuración · SAST · SBOM · calidad |
| **2** | + **tu** despliegue (URL + 2 cuentas) | + DAST · autorización · flujos · carga |
| **3** | + una receta de arranque | lo mismo, pero efímero y reproducible |

El peldaño 1 no necesita desplegar nada: con la ruta al código ya produce hallazgos. El **2 es el
caso normal**: tu aplicación corre donde sea que la despliegues y el laboratorio le apunta — no la
levanta ni la administra, y no hace falta escribir ningún `compose.runtime.yml`. El 3 solo se usa
cuando quieres repetibilidad exacta o no depender de que alguien mantenga un despliegue vivo.

`make doctor TARGET=<perfil>` te dice en qué peldaño estás y qué queda bloqueado.

Los objetivos están etiquetados según lo que necesitan, y `make help` los agrupa:

- **`[code]`** — solo el checkout.
- **`[live]`** — la aplicación respondiendo. Abortan con una explicación si no lo está: un reporte
  de ZAP limpio contra una aplicación caída es idéntico a uno contra una aplicación segura.
- **`[admin]`** — mantenimiento.

## Interfaz web

```bash
make ui        # http://127.0.0.1:7777
```

Alta de proyectos, ejecución con log en vivo, configuración por formulario y captura de triaje.

> **Solo para el operador, en `127.0.0.1`.** Tiene el socket de Docker: quien alcance ese puerto
> ejecuta contenedores arbitrarios, es decir, root en este equipo. `make ui` verifica el
> confinamiento al arrancar y **apaga la interfaz** si alguna vez queda publicada más allá de
> loopback. Compartirla por red exigiría autenticación, permisos por rol, auditoría y custodia de
> credenciales — deliberadamente no construidos.

Si tu código vive fuera del directorio padre del laboratorio, indícalo:
`make ui SRC_MOUNT=/home/dev/repos`.

## Dar de alta un proyecto

```bash
make new    TARGET=proyecto_x            # esqueleto desde targets/_template
$EDITOR targets/proyecto_x/target.env    # SRC_PATH (o REPO_URL+BRANCH)
make detect TARGET=proyecto_x            # propone LANGS, QODANA_IMAGE, AUTH_ADAPTER y recetas
make doctor TARGET=proyecto_x            # preflight: docker, disco, puertos, permisos, roles
make static TARGET=proyecto_x            # YA produce hallazgos, sin levantar nada
```

Para las dimensiones dinámicas (peldaño 2) hay que aportar además:

- `BASE_URL` y `HEALTH_PATH`: dónde responde **tu** despliegue y cómo saber que está vivo. Si
  corre en este mismo equipo, `APP_INTERNAL_URL=http://host.docker.internal:<puerto>` — dentro de
  la red del compose, «localhost» es el contenedor de la herramienta, no tu máquina.
- `AUTH_ADAPTER` y **dos cuentas de distinto privilegio** (`ROLE_A_*`, `ROLE_B_*`).
- `playwright/authz-matrix.json`: qué rol puede alcanzar qué. **Ninguna herramienta lo sabe.**
- Un escenario sembrado (los datos sobre los que la operación autorizada sí funciona).

Solo si quieres el peldaño 3 escribes `compose.runtime.yml`, componiendo `recipes/` con `include:`
(rutas relativas al **directorio del proyecto**).

```bash
make up TARGET=proyecto_x                # solo en el peldaño 3
make e2e dast perf TARGET=proyecto_x
make run-manifest TARGET=proyecto_x      # reports/proyecto_x/RUN.md: cobertura real
make gate         TARGET=proyecto_x      # veredicto: sale != 0 si se incumplen umbrales
make dashboard    TARGET=proyecto_x      # reports/proyecto_x/index.html: todo en una página
make down         TARGET=proyecto_x      # sin residuos
```

## Leer los resultados

```bash
make dashboard TARGET=proyecto_x && xdg-open reports/proyecto_x/index.html
```

Cada herramienta escribe en su propio dialecto: cinco SARIF que no se ponen de acuerdo en dónde
va la severidad, más JSON de Playwright y de k6. `make dashboard` los consolida en un HTML
autocontenido — sin servidor, sin dependencias, sin red — con el veredicto de la compuerta, la
cobertura real y la evidencia `archivo:línea`.

Tres decisiones deliberadas de esa página:

- **No recalcula el veredicto**: invoca `tools/gate.sh` y muestra su salida, de modo que el
  dashboard y el pipeline no puedan discrepar sobre si la corrida pasó.
- **Una dimensión sin ejecutar se pinta `NO EJECUTADO`, jamás como cero hallazgos.** Un gráfico
  tranquilizador sobre un análisis que nadie corrió es peor que no tener gráfico.
- **Es un archivo**, no un servicio. Se abre con doble clic y se adjunta a un correo. Un tablero
  de seguridad que necesita un servidor para leerse es un servidor que alguien acabará exponiendo.

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

`make static` corre todo lo `[code]`; `make live`, todo lo `[live]`.

---

## Lo que el laboratorio NO hace

Está escrito aquí porque es el modo de fallo más probable de esta herramienta: leerla como un botón.

- **No instala tu aplicación.** Ver la escalera arriba: con el código solo ya analiza; para medir
  en vivo le apuntas a tu despliegue.
- **No conoce la política de autorización.** Un `200` sólo es hallazgo si la política decía `403`.
  Esa política la escribe una persona en `authz-matrix.json`.
- **No tría.** Un hallazgo de dependencia no es un riesgo hasta que alguien evalúa alcanzabilidad.
- **No inventa escenarios de abuso de negocio.** Esos guiones se escriben después de leer el código.
- **No calibra severidad** en contexto institucional.
- **No distingue un fallo del proyecto de uno del entorno.** Si SonarQube no corrió por falta de
  disco, eso no dice nada sobre el proyecto.
- **`skip` no es `PASS`.** `make gate` lo imprime y `RUN.md` lo registra. Una dimensión que no se
  ejecutó nunca debe leerse como aprobada. Y **`NO DISPONIBLE` no es `NO EJECUTADO`**: lo primero
  es que este perfil aún no puede medirlo; lo segundo, que podía y no se hizo.
- **No tría por ti, pero sí guarda tu triaje.** En la interfaz marcas cada hallazgo como
  confirmado / falso positivo / inconcluso con su razón, y eso viaja al informe. Sin ese paso, el
  razonamiento se pierde en cuanto cierras la sesión.

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
