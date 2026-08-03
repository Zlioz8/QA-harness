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
  lib/specs/             pruebas genéricas que hereda todo proyecto (cabeceras, matriz de autorización,
                         presupuesto del hilo principal)
  lib/semgrep/           reglas SAST propias del laboratorio, por pila (laravel-vue.yml)
  targets/<nombre>/      el perfil de un proyecto: target.env, target.env.local, compose.runtime.yml,
                         zap/, k6/, playwright/, db-init/
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

### Dónde van las credenciales: `target.env` vs `target.env.local`

`target.env` **se versiona**: es el contrato del perfil — qué variables existen y qué significa cada
una. `target.env.local`, a su lado, **nunca** entra en git (`.gitignore`) y es el único sitio donde
van los valores que no pueden salir del equipo: la URL del despliegue interno y las contraseñas.

```bash
cp targets/proyecto_x/target.env.local.example targets/proyecto_x/target.env.local
$EDITOR targets/proyecto_x/target.env.local     # aquí sí, valores reales
```

El `.local` se carga **encima** del contrato y gana clave a clave: el `Makefile` pasa los dos
`--env-file` a compose, cada servicio lo declara como `env_file` opcional, y `tools/lib-env.sh` lo
consulta primero. Una clave vacía en el `.local` **no** anula: `QODANA_IMAGE=` en el contrato
significa «no aplica, salto documentado», y un `.local` a medio rellenar no debe convertir eso en
otra cosa. Para tapar una clave se le da valor; para heredarla, se omite.

Un perfil no nace con credenciales reales — se vuelve peligroso el día que deja de apuntar a
`localhost` con cuentas sembradas y se le apunta a un despliegue de validación. Ese es el momento
de mover los valores al `.local`; **publicar una credencial en un remoto alojado la escribe en el
historial para siempre.** Sin el `.local`, el perfil sigue siendo válido: las dimensiones `[code]`
corren igual y las `[live]` se detienen en `require-live` en vez de fingir que pasaron.

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
| Presupuesto del hilo principal | Playwright + CDP | `make budget` | **sí** |

`make static` corre todo lo `[code]`; `make live`, todo lo `[live]`.

### Reglas SAST propias (`lib/semgrep/`)

Los paquetes públicos de semgrep buscan vulnerabilidades **clásicas** — inyección, XSS, criptografía.
No conocen los modos de fallo del **framework**, que rompen un despliegue en producción sin ser
vulnerabilidades y por eso ninguna herramienta del laboratorio los veía. `lib/semgrep/laravel-vue.yml`
codifica dos defectos reales encontrados a mano (`env()` fuera de `config/`, que devuelve `null` en
cuanto corre `php artisan config:cache` — es decir, solo en producción; y las rutas absolutas a
`assets` que sobreviven al `build` de Vite). Un perfil las activa añadiendo
`--config=/seclab-lib/semgrep/laravel-vue.yml` a su `SEMGREP_CONFIG`.

### Presupuesto del hilo principal (`make budget`)

La dimensión que faltaba: **el navegador**. k6 mide el servidor, ZAP mide cabeceras, la matriz mide
permisos — y con los tres en verde la pestaña del usuario puede seguir congelándose, porque el
trabajo caro ocurre en su equipo, no en el tuyo. Esta prueba rastrea el bundle **entero** (no solo la
pantalla actual), cuenta **megapíxeles descodificados** en vez de bytes —que es lo que predice el
bloqueo, y lo que delata una «optimización» que recomprime sin redimensionar— y mide con la **CPU
frenada** ×4, que convierte «a mí me funciona» en un número. Umbrales y validación de la propia
herramienta: [`lib/specs/README-main-thread-budget.md`](lib/specs/README-main-thread-budget.md).

### Si la aplicación limita peticiones, decláralo (`E2E_PACE_MS`)

Una suite que inicia sesión en cada prueba se atropella a sí misma contra cualquier backend con
limitador: pasado el umbral el login devuelve `429`, la comprobación lo lee como «acceso denegado» y
el laboratorio reporta un falso positivo masivo **sobre la dimensión que existe para medir**. En
Costos Web fueron 59 fallos de autorización inexistentes. Tres medidas, ya en el núcleo:

- La sesión de cada rol se abre **una vez** y se reutiliza (`lib/auth`, memorizada por adaptador+rol).
- `workers: 1` en el perfil, porque cada worker es un proceso con su propia caché — N workers son N
  inicios de sesión por rol. Y `retries: 0`: un fallo intermitente de autorización es un hallazgo,
  no ruido que reintentar hasta que salga verde.
- `E2E_PACE_MS` en `target.env` espacia las comprobaciones de la matriz. Por defecto no hay espera;
  se declara solo en los perfiles cuya aplicación lo necesita.

**Y en la matriz, cuidado con las escrituras.** El motor ejecuta cada regla con **todos** los roles,
incluido el permitido — un endpoint que deniega a quien tiene derecho también es un hallazgo. Con un
`PUT` eso no es una comprobación: es la mutación real. Una regla `PUT {rol_id:1}` ascendió a la
cuenta de menor privilegio a administradora, y con ese privilegio otra spec borró la cuenta
administradora del entorno. Regla: en `authz-matrix.json`, escrituras **solo** contra objetivos
desechables o inexistentes; las que tocan datos del proyecto van en una spec del perfil, que puede
restaurar lo que toca.

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
- **Ninguna credencial real, ni ninguna dirección de infraestructura interna, en un archivo
  versionado.** Van en `targets/<perfil>/target.env.local` (ver arriba). Tampoco incrustadas como
  valor por defecto en una spec: un `process.env.BASE_URL || 'https://10.0.0.5'` sobrevive al
  despliegue que lo motivó y acaba midiendo el servidor equivocado, en verde. Sin objetivo, fallar.
- Cuando un perfil no puede tener cuentas sintéticas en absoluto, se excluye entero del repositorio
  (`targets/movil/`). El `.local` es la alternativa que conserva el contrato versionado.
- `make purge TARGET=<perfil>` borra los reportes de un perfil. Anonimiza antes de compartirlos.
- `make down TARGET=<perfil>` destruye contenedores y volúmenes.

## Perfiles actuales

| Perfil | Stack | Estado |
|---|---|---|
| `costos_web` | Laravel + Vue + PostgreSQL | peldaño 2 contra el despliegue de validación: matriz de 6 roles, flujos de negocio, recorrido de pantallas por rol y presupuesto del hilo principal. Credenciales en `target.env.local` |
| `antiplagio` | Moodle + plugin PHP + FastAPI + Kafka + analyzers | estático y dinámico ejecutados; ver `reports/antiplagio/RUN.md` |
| `_template` | — | esqueleto para el siguiente proyecto |
