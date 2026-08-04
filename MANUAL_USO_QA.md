# Manual de uso — QA Harness (SECURITY-LAB)

Guía operativa para el **analista de QA / calidad y seguridad** que recibe esta herramienta y tiene
que auditar un proyecto de principio a fin: desde `git clone` del laboratorio hasta un informe con
veredicto, cobertura declarada y triaje registrado.

No es el documento de diseño (eso es [`README.md`](README.md)) ni el historial de decisiones
(eso es [`INFORME_MIGRACION_SECURITY_LAB.md`](INFORME_MIGRACION_SECURITY_LAB.md)). Aquí solo está
**qué hace una persona, en qué orden, y cómo sabe que lo hizo bien**.

---

## 0. Lo que el QA debe tener claro antes de tocar nada

Tres reglas que determinan si el trabajo sirve o no sirve:

1. **El laboratorio no despliega la aplicación auditada.** Analiza el código que le señales y, si
   le dices dónde responde *tu* despliegue, lo mide en vivo. Si esperas que «levante el proyecto»,
   vas a concluir que la herramienta está rota.
2. **`skip` no es `PASS`.** Una dimensión que no corrió no es una dimensión sin hallazgos. Toda la
   herramienta está construida alrededor de esta distinción: `make gate` la imprime, `RUN.md` la
   registra y el informe HTML la pinta como `NO EJECUTADO`.
3. **La política de autorización la escribe una persona.** Ninguna herramienta sabe si un `200` es
   correcto. Si el QA no redacta `authz-matrix.json`, la dimensión más importante de la auditoría
   sencillamente no se prueba.

### La escalera: cuánto puedes medir según lo que traigas

| Peldaño | Qué aportas | Qué se desbloquea |
|---|---|---|
| **1** | un checkout del código | secretos · CVE · configuración · SAST · SBOM · calidad · contrato de API |
| **2** | + tu despliegue vivo (URL + 2 cuentas) | + DAST · autorización · flujos · carga · presupuesto de navegador |
| **3** | + una receta de arranque (`compose.runtime.yml`) | lo mismo que 2, pero efímero y reproducible |

El peldaño **2 es el caso normal**. El 3 solo se escribe si necesitas repetibilidad exacta o no
quieres depender de que alguien mantenga un despliegue vivo.

`make doctor TARGET=<perfil>` te dice en qué peldaño estás y qué te queda bloqueado.

---

## 1. Preparar el equipo (una vez)

**Requisito único:** Docker + Docker Compose v2. Ninguna herramienta se instala en el anfitrión;
todas corren como imágenes.

```bash
docker --version && docker compose version
```

**Requisitos de capacidad**, que no son opcionales:

- Sistema de archivos raíz **por debajo del 90 % de uso**. Por encima, el Elasticsearch embebido de
  SonarQube marca sus índices como solo-lectura y el análisis muere con un `408` opaco. Añadir GB
  no ayuda: lo que importa es el **porcentaje**.
- ~8 GB libres para las imágenes de herramientas.

```bash
git clone <URL-del-laboratorio> && cd SECURITY-LAB
```

El laboratorio no requiere `make install` ni dependencias de Python en el host: `docker`, `make`,
`bash`, `curl`, `git` y `python3` (ya presente en cualquier distro) es todo.

---

## 2. Las dos rutas de trabajo

Ambas hacen exactamente lo mismo — la interfaz web invoca el mismo `Makefile` y los mismos scripts,
para que el navegador y el terminal no puedan contar historias distintas.

### Ruta A · Interfaz web (recomendada para el QA que no vive en el terminal)

```bash
make ui        # http://127.0.0.1:7777
```

Ofrece: alta de proyectos, formulario de configuración del perfil, botones de ejecución agrupados
por `[code] / [live] / [admin]`, log en vivo de cada corrida, lista plana y filtrable de hallazgos,
captura de triaje y acceso al informe.

> **Solo para el operador, en `127.0.0.1`.** La interfaz tiene el socket de Docker: quien alcance
> ese puerto ejecuta contenedores arbitrarios, es decir, es root en este equipo. `make ui` verifica
> el confinamiento al arrancar (`tools/ui-check-bind.sh`) y **apaga la interfaz** si alguna vez
> queda publicada fuera de loopback. No la expongas por red ni la pongas detrás de un túnel
> compartido.

Si el código a auditar vive fuera del directorio padre del laboratorio, indícalo al arrancar:
`make ui SRC_MOUNT=/home/dev/repos`.

Para apagarla: `make ui-stop`. Para ver su propio log: `make ui-logs`.

### Ruta B · Terminal

Todo objetivo se invoca con `make <objetivo> TARGET=<perfil>`. `make help` los lista agrupados por
lo que cada uno necesita; `make list` muestra los perfiles existentes.

---

## 3. Dar de alta el proyecto a auditar

### 3.1 Crear el perfil

```bash
make new TARGET=proyecto_x
```

Copia `targets/_template/` a `targets/proyecto_x/`. Un **perfil** es todo el contrato entre el
laboratorio y un proyecto: qué código, dónde responde, cómo se inicia sesión, qué umbrales aplican.

### 3.2 Rellenar `target.env` — lo mínimo

```bash
$EDITOR targets/proyecto_x/target.env
```

| Variable | Qué es | Nota |
|---|---|---|
| `SRC_PATH` | ruta **absoluta** al checkout ya existente | preferido: ninguna llave SSH entra en un contenedor |
| `REPO_URL` + `BRANCH` | alternativa: que el lab clone (`make clone`) | usa una **deploy key dedicada de solo lectura**, nunca tu `~/.ssh` |
| `SOURCE_DIRS` | qué subdirectorios son código propio | mantiene `vendor/` y `node_modules/` fuera de Sonar |
| `LANGS` | `py,php,js,go` | decide qué linters aplican |

> **Ojo con los comentarios en línea.** `QODANA_IMAGE=  # no aplica` es *vacío* para las
> herramientas del lab y un *nombre de imagen literal* para docker compose, que muere con
> «invalid reference format». Los comentarios van en su propia línea, encima de la variable.
> `make doctor` avisa de esto explícitamente.

### 3.3 Dejar que la herramienta proponga el resto

```bash
make detect TARGET=proyecto_x
```

Hace un censo de archivos y **propone** (nunca escribe): `LANGS`, `AUTH_ADAPTER`, `QODANA_IMAGE` y
qué recetas de `recipes/` aplicarían. También marca banderas rojas que ya son hallazgo: un compose
del proyecto publicando en `0.0.0.0`, un broker con login anónimo. Confirma tú y pega lo que
corresponda: adivinar en silencio es como una auditoría acaba midiendo otra cosa.

### 3.4 Preflight

```bash
make doctor TARGET=proyecto_x
```

Comprueba docker, `SRC_PATH`, presencia de historia git, las dos cuentas de rol, disco (en GB **y**
en porcentaje), puertos ocupados —consultando tanto los sockets locales como los contenedores
publicados—, permisos de escritura en `reports/`, comentarios en línea en `target.env`, y termina
diciéndote **en qué peldaño estás y qué queda bloqueado**.

Un `warn` no impide trabajar; un `FAIL` sí.

### 3.5 Primer resultado real, sin desplegar nada

```bash
make static TARGET=proyecto_x
```

Corre `secrets · deps · config-scan · sbom · semgrep · qodana · sonar`. A partir de aquí ya hay
hallazgos que triar. Todo lo demás de este manual es ampliar cobertura.

---

## 4. Desbloquear las dimensiones en vivo (peldaño 2)

Aquí está el 80 % del trabajo intelectual del QA. Sin esto, la auditoría es un escaneo estático.

### 4.1 Dónde responde la aplicación

```ini
BASE_URL=https://mi-despliegue.interno       # visto desde ESTE host (curl, Playwright)
APP_INTERNAL_URL=https://mi-despliegue.interno  # visto desde OTRO contenedor (ZAP, k6)
HEALTH_PATH=/health                          # devuelve 200 SOLO si de verdad está sirviendo
```

Dos URLs porque son dos puntos de vista distintos: Playwright corre con `network_mode: host` y ve
lo mismo que tú; ZAP y k6 corren dentro de la red del compose, donde «localhost» es el contenedor
de la propia herramienta. **Si la aplicación corre en este mismo equipo:**
`APP_INTERNAL_URL=http://host.docker.internal:<puerto>`.

`HEALTH_PATH` no es decorativo: es lo único que distingue «no hay hallazgos» de «no había nada
corriendo». Que apunte a un *health check* de verdad, no a una redirección ni a una pantalla de
login — un `302` perpetuo no te dice nada.

Si el despliegue usa certificado autofirmado (lo normal en preproducción), declara
`K6_INSECURE_SKIP_TLS_VERIFY=true`: sin eso k6 aborta el 100 % de las peticiones con un error x509
y el resultado se lee como aplicación caída. La validez del TLS la reporta ZAP, que sabe tratarla
como hallazgo.

Verifica antes de gastar una corrida:

```bash
tools/require-live.sh proyecto_x     # o simplemente lanza un objetivo [live]: lo llama solo
```

### 4.2 Las dos cuentas

```ini
AUTH_ADAPTER=sanctum        # sanctum | moodle-session | jwt-bearer | basic | zajuna | none
ROLE_A_USER=...             # máximo privilegio (admin / instructor / gestor)
ROLE_A_PASS=...
ROLE_B_USER=...             # mínimo privilegio (usuario normal / aprendiz)
ROLE_B_PASS=...
```

**Dos cuentas de distinto privilegio no son opcionales.** La autorización es la única dimensión que
ningún escáner puede probar por ti, y para probarla hace falta una cuenta de bajo privilegio que
intente lo que solo la de alto privilegio debería poder.

Si tu aplicación inicia sesión de una forma que no cubre ningún adaptador de `lib/auth/`, se
escribe un adaptador nuevo — y ese adaptador queda disponible para todos los proyectos futuros.

### 4.3 Dónde van las credenciales: `target.env` vs `target.env.local`

`target.env` **se versiona**: es el contrato, dice qué variables existen. `target.env.local`
**nunca** entra en git y es el único sitio donde van los valores que no pueden salir del equipo:
la dirección del despliegue interno y las contraseñas reales.

```bash
cp targets/proyecto_x/target.env.local.example targets/proyecto_x/target.env.local
$EDITOR targets/proyecto_x/target.env.local
```

El `.local` se carga encima del contrato y gana clave a clave. Una clave **vacía** en el `.local`
no anula: para tapar una clave se le da valor; para heredarla, se omite.

Regla operativa: mientras las cuentas sean sembradas y sintéticas, pueden vivir en `target.env`.
El día que el perfil apunta a un despliegue de validación con cuentas reales, los valores se mueven
al `.local`. **Publicar una credencial en un remoto alojado la escribe en el historial para
siempre.**

### 4.4 La matriz de autorización — el entregable propio del QA

`targets/proyecto_x/playwright/authz-matrix.json`:

```json
[
  { "path": "/api/users", "method": "GET", "allow": ["A"] },
  { "path": "/download.php?id=999", "method": "GET", "allow": [],
    "note": "documento de otro usuario: nadie puede leerlo adivinando el id" }
]
```

`allow` lista los roles que **deberían** poder. Cualquier otro rol debe recibir `401/403/404`. El
motor genérico (`lib/specs/authz-matrix.spec.ts`) la ejecuta; el archivo ausente se reporta como
dimensión **no probada**, jamás como aprobada.

> **⚠️ Cuidado con las escrituras.** El motor ejecuta cada regla con **todos** los roles, incluido
> el permitido —porque un endpoint que deniega a quien tiene derecho también es un hallazgo—. Con
> un `PUT` eso deja de ser una comprobación y pasa a ser la mutación real. En un proyecto, una
> regla `PUT {rol_id:1}` ascendió la cuenta de menor privilegio a administradora y, con ese
> privilegio, otra spec borró la cuenta administradora del entorno.
>
> **Regla: en la matriz, escrituras solo contra objetivos desechables o inexistentes.** Las que
> tocan datos del proyecto van en una spec propia del perfil, que puede restaurar lo que toca.

### 4.5 Escenario sembrado

La matriz necesita datos sobre los que la operación autorizada **sí** funcione. Sin ellos, un
`404` es ambiguo: ¿denegó o no existía? Siembra usuarios y datos sintéticos (ver
`targets/*/seed-users.sh`, `scenarios/`) y anota en el informe qué escenario usaste.

### 4.6 Si la aplicación limita peticiones

Una suite que inicia sesión en cada prueba se atropella contra cualquier backend con limitador:
pasado el umbral el login devuelve `429`, la comprobación lo lee como «acceso denegado» y el
laboratorio reporta un falso positivo masivo **sobre la dimensión que existe para medir**. En un
proyecto real fueron 59 fallos de autorización inexistentes.

El núcleo ya reutiliza la sesión por rol y fuerza `workers: 1` / `retries: 0`. Lo que aporta el
QA es declarar el ritmo cuando su aplicación lo necesita:

```ini
E2E_PACE_MS=1200
```

### 4.7 Artefactos que aporta el perfil, por dimensión

| Dimensión | Archivo que debe existir en `targets/<perfil>/` | Si falta |
|---|---|---|
| DAST | `zap/automation.yaml` (usa `${ZAP_TARGET_URL}`, nunca URL incrustada) | ZAP no corre |
| Carga | `k6/<script>.js`; el perfil elige cuál con `K6_SCRIPT=` | usa `smoke.js` |
| E2E / authz | `playwright/playwright.config.ts` + `playwright/authz-matrix.json` (+ `playwright/tests/`) | dimensión no probada |
| Carga con plan propio | `jmeter/plan.jmx` (o `JMETER_PLAN=`) | `NO DISPONIBLE` |
| Contrato de API | `OPENAPI_SPEC=` / `OPENAPI_SPEC_URL=` en `target.env` | `NO DISPONIBLE` |
| Build de producción | servicio `front-build` (o `BUILD_SERVICE=`) en `compose.runtime.yml` | `NO DISPONIBLE` |

`NO DISPONIBLE` (este perfil aún no puede medirlo) y `NO EJECUTADO` (podía y no se hizo) son cosas
distintas y el manifiesto las registra distinto. No las mezcles en el informe.

---

## 5. Ejecutar la auditoría

```bash
# peldaño 3 únicamente: el laboratorio levanta la aplicación
make up TARGET=proyecto_x

make static TARGET=proyecto_x       # todo lo que no necesita la app corriendo
make live   TARGET=proyecto_x       # dast + perf + e2e
```

Y las dimensiones que dependen de un artefacto del perfil, aparte:

```bash
make api-lint    TARGET=proyecto_x
make api-fuzz    TARGET=proyecto_x
make budget      TARGET=proyecto_x
make perf-jmeter TARGET=proyecto_x
make build       TARGET=proyecto_x
make image-scan  TARGET=proyecto_x IMAGE=mi-repo:tag
```

`make all TARGET=proyecto_x` es `static` + `live`.

### Mapa completo: comando → qué mide → artefacto

| Comando | Herramienta | Qué evalúa | Artefacto |
|---|---|---|---|
| `secrets` | gitleaks + trufflehog | secretos en **toda** la historia git | `gitleaks.sarif`, `trufflehog.txt` |
| `deps` | Trivy (fs) | CVE de dependencias | `trivy/trivy-fs.sarif` |
| `config-scan` | Trivy (config) | Dockerfiles / compose / k8s del proyecto | `trivy/trivy-config.sarif` |
| `image-scan` | Trivy (image) | CVE de una imagen construida | `trivy/trivy-image.sarif` |
| `sbom` | Syft | inventario de componentes y licencias | `sbom/sbom.spdx.json` |
| `semgrep` | semgrep | SAST poliglota con taint | `semgrep/semgrep.sarif` |
| `sonar` | SonarQube | calidad y mantenibilidad | `sonar/sonar.sarif`, `sonar/issues.json` |
| `qodana` | JetBrains Qodana | calidad, un lenguaje por imagen | `qodana/qodana.sarif`, `qodana/report/` |
| `api-lint` | Spectral | ¿la descripción OpenAPI es sólida? | `api/spectral.sarif` |
| `dast` | OWASP ZAP | superficie runtime, cabeceras, alertas | `zap/zap-report.html`, `zap/zap.sarif` |
| `e2e` | Playwright | autorización y flujos funcionales | `playwright/results.json`, `playwright/html/` |
| `perf` | k6 | latencia / throughput bajo carga | `k6/summary.json` |
| `perf-jmeter` | JMeter | carga con el plan `.jmx` del equipo | `jmeter/html/index.html` |
| `api-fuzz` | Schemathesis | ¿la API cumple su propio contrato? | `api/schemathesis.xml` |
| `budget` | Playwright + CDP | presupuesto del hilo principal del navegador | en el log de la corrida |

**Qué NO cubre `dast`:** ZAP recorre la aplicación **sin sesión**. Un reporte de ZAP limpio no dice
nada sobre autorización — nunca inició sesión. Esa es la dimensión de `e2e`.

**Qué mide `budget` y por qué existe:** k6 mide el servidor, ZAP mide cabeceras, la matriz mide
permisos — y con los tres en verde la pestaña del usuario puede seguir congelándose, porque el
trabajo caro ocurre en el equipo del usuario. Rastrea el bundle entero, cuenta **megapíxeles
descodificados** en vez de bytes y mide con la CPU frenada ×4. Umbrales en
[`lib/specs/README-main-thread-budget.md`](lib/specs/README-main-thread-budget.md).

---

## 6. Veredicto y cobertura

```bash
make run-manifest TARGET=proyecto_x   # reports/proyecto_x/RUN.md
make gate         TARGET=proyecto_x   # sale != 0 si se incumple un umbral
make dashboard    TARGET=proyecto_x   # reports/proyecto_x/index.html
make status       TARGET=proyecto_x   # qué está arriba, qué corrió, qué falta
```

### `make gate` — el único sitio donde una corrida recibe veredicto

Todas las herramientas están configuradas deliberadamente para **no** fallar su propia ejecución
(`gitleaks --exit-code=0`, `semgrep --error=false`), de modo que una dimensión ruidosa no aborte
las demás. La consecuencia es que una corrida siempre sale «verde» y no significa nada. El gate es
lo que le da significado, contra los umbrales declarados en `target.env`:

| Umbral | Qué acota |
|---|---|
| `ALLOW_SECRETS` | secretos admitidos en la historia git (normalmente `0`) |
| `MAX_DEP_FINDINGS` | hallazgos de dependencias |
| `MAX_SAST_FINDINGS` | hallazgos de semgrep |
| `MAX_QUALITY_FINDINGS` | hallazgos de calidad: SonarQube **+** Qodana sumados |
| `MAX_DAST_FINDINGS` | alertas de ZAP |
| `K6_P95_MS` / `K6_ERR_RATE` | SLO de latencia p95 y tasa de error |

Playwright no tiene umbral: **cualquier spec fallida es FAIL**.

Lee la salida entera, no solo la última línea: `GATE PASSED` con cinco `skip` encima es una corrida
que no midió casi nada.

### `RUN.md` — qué se auditó y, sobre todo, qué **no**

Registra fecha, host, commit exacto y rama del código auditado, el envelope de recursos declarado
(sin él los números de carga no son comparables), una tabla de cobertura dimensión por dimensión
(`yes` / **`NO`**), los digests de las imágenes de herramientas usadas, y la lista explícita de lo
que ninguna herramienta cubre y exige análisis humano.

Este archivo es lo que impide que un informe se lea como cobertura completa cuando no lo fue.

### El informe HTML

```bash
make dashboard TARGET=proyecto_x && xdg-open reports/proyecto_x/index.html
```

Consolida cinco dialectos de SARIF más los JSON de Playwright y k6 en una página autocontenida:
sin servidor, sin dependencias, sin red. Tres propiedades a tener presentes al usarla:

- **No recalcula el veredicto**: invoca `tools/gate.sh` y muestra su salida, para que el informe y
  el pipeline no puedan discrepar.
- **Una dimensión sin ejecutar se pinta `NO EJECUTADO`, nunca como cero hallazgos.**
- **Es un archivo**, no un servicio: se abre con doble clic y se adjunta a un correo.

---

## 7. Triaje — la parte que solo hace el QA

Un hallazgo de herramienta no es un riesgo hasta que alguien evalúa alcanzabilidad e impacto. La
interfaz web guarda ese juicio para que no se pierda al cerrar la sesión:

1. `make ui` → el proyecto → **Hallazgos**.
2. Lista plana y filtrable de todo lo que produjo toda herramienta. Un filtro **oculta, no
   descarta**: el total crudo está siempre en pantalla junto al filtrado.
3. Marca cada hallazgo como **Confirmado / Falso positivo / Inconcluso**, con su razón.
4. Al guardar, el informe se regenera y el triaje viaja con él.

Lo que el laboratorio **no** hace por ti, y por tanto va en el informe escrito a mano:

- Decidir si un `200` es un hallazgo: eso depende de la política que tú escribiste.
- Calibrar severidad en contexto institucional (datos personales, procesos regulados).
- Inventar escenarios de abuso de negocio: se escriben después de leer el código.
- Distinguir un fallo del proyecto de uno del entorno. Si SonarQube no corrió por falta de disco,
  eso no dice nada sobre el proyecto.

---

## 8. Entrega

Entregables sugeridos, en este orden:

1. `reports/<perfil>/index.html` — el informe consolidado con veredicto y triaje.
2. `reports/<perfil>/RUN.md` — cobertura declarada. **Adjúntalo siempre**: es lo que hace honesto
   al primero.
3. Informe técnico en Markdown con hallazgos, evidencia `archivo:línea` y comandos de reproducción
   (estructura estándar de informe técnico institucional).
4. Informe ejecutivo en PDF si el destinatario lo requiere.

**Antes de compartir cualquier reporte, anonimízalo.** Los artefactos pueden contener rutas
internas, direcciones de infraestructura, fragmentos de código y datos de escenario.

---

## 9. Cierre

```bash
make down  TARGET=proyecto_x    # destruye contenedores y volúmenes; sin residuos
make purge TARGET=proyecto_x    # borra los reportes del perfil (pide confirmación por nombre)
make ui-stop                    # apaga la interfaz web
docker ps                       # verifica que no quedó nada
```

**Política de datos**, resumida: el laboratorio puede llegar a concentrar datos personales reales,
credenciales de prueba conocidas y servicios sin endurecer. Es un activo sensible, no una carpeta
de trabajo.

- Todos los puertos publicados se atan a `127.0.0.1`. Es un invariante del núcleo; no lo cambies.
- Semillas **sintéticas** por defecto. Un volcado de producción solo se justifica para reproducir
  un comportamiento dependiente del volumen, y con fecha de caducidad.
- Ninguna credencial real ni dirección de infraestructura interna en un archivo versionado — ni
  siquiera como valor por defecto en una spec: un `process.env.BASE_URL || 'https://10.0.0.5'`
  sobrevive al despliegue que lo motivó y acaba midiendo el servidor equivocado, en verde.
  **Sin objetivo, fallar.**

---

## 10. Diagnóstico de fallos frecuentes

| Síntoma | Causa / arreglo |
|---|---|
| `ERROR: set TARGET=<name>` | todo objetivo salvo `help/new/list/ui` exige `TARGET=` |
| `ABORTED: <url> -> 000` en un objetivo `[live]` | la app no está arriba, **o** las herramientas no la alcanzan desde su red: usa `APP_INTERNAL_URL=http://host.docker.internal:<puerto>` |
| `ABORTED: ... -> 302/401` | `HEALTH_PATH` apunta a una redirección o a un login, no a un health check |
| SonarQube muere con `408` | disco por encima del 90 % de uso: libera espacio, no añadas GB |
| `qodana: NO DISPONIBLE para este perfil` | el linter se resuelve desde `LANGS`. Si tu lenguaje solo tiene imagen de pago (PHP, JS, Go, .NET), hace falta `QODANA_TOKEN`; sin él la dimensión es **NO DISPONIBLE**, nunca un pass. La calidad la cubren `sonar` y `semgrep` |
| `qodana: LANGS vacío` | corre `make detect` y copia el `LANGS` que propone |
| `invalid reference format` al arrancar compose | comentario en línea en `target.env`: muévelo a su propia línea |
| ZAP no genera reporte | permisos de `reports/<perfil>/zap` (ZAP corre sin privilegios); el `guard` del Makefile pre-crea los directorios como usuario del host |
| k6 marca 100 % de error contra un https sano | certificado autofirmado: `K6_INSECURE_SKIP_TLS_VERIFY=true` |
| Decenas de fallos de autorización de golpe | limitador de peticiones devolviendo `429`: declara `E2E_PACE_MS` |
| JMeter no arranca («is not empty») | el objetivo ya borra `results.jtl` y `html/` antes de correr; si lo invocas a mano, bórralos tú |
| `port N already in use by container ...` | otro perfil dejó residuos: `make down TARGET=<el-otro>` |
| `build: no existe el servicio 'front-build'` | el perfil no trae `compose.runtime.yml`: es `NO DISPONIBLE`, no un error |
| La interfaz web se apagó sola al arrancar | quedó publicada fuera de loopback y `ui-check-bind.sh` la bajó. Es el comportamiento correcto |

---

## 11. Checklist del QA

**Alta del proyecto**

- [ ] `make new` y `SRC_PATH` apuntando a un checkout real de este equipo
- [ ] `make detect` revisado y sus propuestas confirmadas (no pegadas a ciegas)
- [ ] `make doctor` sin `FAIL`, y peldaño identificado
- [ ] `make static` con artefactos en `reports/<perfil>/`

**Para medir en vivo**

- [ ] `BASE_URL`, `APP_INTERNAL_URL` y `HEALTH_PATH` verificados (`require-live` en verde)
- [ ] `AUTH_ADAPTER` correcto y dos cuentas de distinto privilegio que **inician sesión de verdad**
- [ ] Credenciales y host interno en `target.env.local`, no en `target.env`
- [ ] `authz-matrix.json` escrita, con las escrituras acotadas a objetivos desechables
- [ ] Escenario sembrado documentado
- [ ] `zap/automation.yaml` sin URL incrustada; script de k6 elegido

**Cierre de la auditoría**

- [ ] `make run-manifest` y `RUN.md` revisado dimensión por dimensión
- [ ] `make gate` leído entero: ¿cuántos `skip` hay y por qué?
- [ ] Triaje registrado en la interfaz, con razón por hallazgo
- [ ] `make dashboard` y el informe anonimizado antes de compartirlo
- [ ] `make down` y `docker ps` limpio

---

*Diseño y decisiones: [`README.md`](README.md). Historial de hallazgos sobre la propia herramienta:
[`INFORME_MIGRACION_SECURITY_LAB.md`](INFORME_MIGRACION_SECURITY_LAB.md) y
[`INFORME_HARDENING_SECURITY_LAB.md`](INFORME_HARDENING_SECURITY_LAB.md).*
