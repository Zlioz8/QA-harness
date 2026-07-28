# Informe técnico — Migración de SECURITY-LAB a herramienta multiproyecto

**Objeto.** Determinar si el laboratorio de auditoría construido sobre **costos_web** funciona
realmente sobre *cualquier* proyecto, qué le falta para ser agnóstico, y qué debe asumir como
trabajo propio el equipo que lo reciba. La comprobación se hizo ejerciéndolo contra **Antiplagio
Zajuna**, el caso adverso (poliglota, sin SPA, con un plugin que no arranca solo, con broker).

| | |
|---|---|
| **Herramienta auditada** | `SECURITY-LAB` (laboratorio propio) |
| **Proyecto de prueba** | Antiplagio Zajuna — rama `dev`, commit `ce92fa1` |
| **Segundo proyecto (no-regresión)** | costos_web — rama `CostosWebDev` |
| **Fecha** | 27 de julio de 2026 |
| **Host de la corrida** | laptop de desarrollo · 16 CPU · Docker 29.6.2 / Compose 5.3.1 · FS raíz al 94-97% |
| **Componentes intervenidos** | `docker-compose.yml` (core), `Makefile`, `tools/`, `lib/`, `recipes/`, `targets/` |
| **Herramientas ejercidas** | gitleaks · trufflehog · Trivy (fs/config) · semgrep · syft · SonarQube · Playwright · OWASP ZAP |
| **Alcance — qué SÍ se tocó** | Separación core/perfiles, contrato de target, adaptadores de autenticación, recetas de runtime, compuerta de veredicto, manifiesto de cobertura, preflight |
| **Alcance — qué NO se tocó** | El código de Antiplagio y el de costos_web (montados **read-only**); los servidores 166 y preproducción; los datos de producción |
| **Reproducibilidad** | `make doctor|detect|static|up|e2e|dast|gate TARGET=<perfil>`; artefactos crudos en `reports/<perfil>/`, inventario de cobertura en `reports/<perfil>/RUN.md` |

**Veredicto en una línea:** el laboratorio era **agnóstico en su mitad estática y un target de
costos_web disfrazado de laboratorio en su mitad dinámica**. Tras la intervención corre sobre ambos
proyectos desde el mismo núcleo, y el costo de dar de alta el proyecto N+1 es un archivo de
configuración más, en el caso general, una receta de arranque.

---

## Resumen de hallazgos

Hallazgos **sobre la herramienta y su operación**. Los hallazgos sobre Antiplagio están en el
Anexo A: aquí sirven como evidencia de que el laboratorio efectivamente encuentra cosas.

| # | Hallazgo | Sev. | Estado | Responsable | Esfuerzo |
|---|---|---|---|---|---|
| M1 | El núcleo del lab contenía el runtime de un proyecto concreto (Laravel/Vue) | 🟠 Alto | ✅ Cerrado | Líder Técnico | 6 h |
| M2 | Ninguna corrida emitía veredicto: todas las herramientas con el código de salida neutralizado | 🟠 Alto | ✅ Cerrado | DevOps/Infra | 2 h |
| M3 | Sin inventario de cobertura: «no encontró nada» y «no se ejecutó» eran indistinguibles | 🟠 Alto | ✅ Cerrado | DevOps/Infra | 2 h |
| M4 | La matriz de autorización exige un escenario sembrado; sin él los resultados son inconclusos y se leen como fallos | 🟠 Alto | ⚠️ Abierto | Backend + operador del lab | 8 h |
| M5 | Un dato de prueba mal formado hace que el test «pase» sin haber probado nada | 🟠 Alto | ✅ Cerrado | Seguridad | 1 h |
| M6 | Semántica mixta de rutas en `include` de Compose → montajes vacíos silenciosos (la semilla de BD nunca se aplicaba) | 🟠 Alto | ✅ Cerrado | DevOps/Infra | 3 h |
| M7 | Dump real con datos personales de 20 368 personas versionado dentro del laboratorio | 🔴 Crítico | ⚠️ Abierto | Seguridad + Líder Técnico | 1 h |
| M8 | SonarQube falla de forma opaca cuando el sistema de archivos supera el 90% de uso | 🟡 Medio | ⚠️ Abierto | DevOps/Infra | — (capacidad) |
| M9 | `semgrep --config=auto` exige telemetría activada sobre el código auditado | 🟡 Medio | ✅ Cerrado | Seguridad | 30 min |
| M10 | Montar el laboratorio en `/lib` inutiliza el contenedor entero | 🟡 Medio | ✅ Cerrado | DevOps/Infra | 1 h |
| M11 | Los hooks de instalación corren como root y rompen los permisos del runtime | 🟡 Medio | ✅ Cerrado | DevOps/Infra | 1 h |
| M12 | Ninguna herramienta del lab analiza ficheros `docker-compose` | 🟡 Medio | ⚠️ Parcial | DevOps/Infra | 4 h |
| M13 | Qodana cubre un solo lenguaje por imagen: los proyectos poliglotas quedan a medias | 🟡 Medio | ⚠️ Parcial | Seguridad | 2 h |
| M14 | Imágenes de herramientas ancladas a `:latest` (mutables) | 🟠 Alto | ⚠️ Abierto | DevOps/Infra | 2 h |
| M15 | El servicio de clonado montaba `~/.ssh` completo | 🟠 Alto | ✅ Cerrado | DevOps/Infra | 1 h |
| M16 | Los directorios de reportes los crea el primer contenedor: si corre como root, las herramientas no privilegiadas no pueden escribir y la dimensión se pierde | 🟡 Medio | ✅ Cerrado | DevOps/Infra | 1 h |
| M17 | ZAP aborta la corrida por una *advertencia* del plan; sin eso, «ignorar su salida» ocultaría una corrida que no produjo nada | 🟡 Medio | ✅ Cerrado | DevOps/Infra | 1 h |

Severidad: 🔴 Crítico · 🟠 Alto · 🟡 Medio · 🟢 Bajo — Estado: Abierto / Parcial / Cerrado.

---

## M1 · 🟠 Alto · ✅ Cerrado — El núcleo contenía el runtime de un proyecto concreto
**Responsable: Líder Técnico**

### Qué está pasando
El `docker-compose.yml` del laboratorio declaraba los servicios `app` (`php artisan serve`),
`frontend` (Vite), `fpm` y `nginx-prod`; `docker/Dockerfile.app` instalaba PHP con extensiones de
Laravel; `docker/lab.env` hablaba de `SANCTUM_STATEFUL_DOMAINS`. La autenticación estaba cableada al
flujo Sanctum en `k6/lib/session.js` y `playwright/tests/_auth.ts`, y el plan de ZAP fijaba el
contexto `costos-api` con rutas `/api.*` y `/sanctum.*`.

Al apuntarlo a Antiplagio, la mitad estática (gitleaks, trufflehog, Trivy) funcionó **sin tocar
nada**; la mitad dinámica no tenía nada aprovechable: Antiplagio no tiene SPA, su interfaz son
páginas PHP dentro de Moodle, y su plugin `local_antiplagiarsena` **no tiene punto de entrada
propio** — sus archivos no significan nada fuera de una instalación de Moodle.

### Por qué es un error
Un laboratorio que promete portabilidad y sólo ha auditado un proyecto vende una capacidad que no
tiene. El equipo receptor descubriría el problema en su primer proyecto distinto, después de haber
planificado con el supuesto contrario.

### Recomendación de remediación
*Explicación.* La línea de corte real no es «estático vs dinámico», sino **lo que se puede saber
leyendo un repositorio** frente a **lo que sólo se sabe conociendo la aplicación**. Las herramientas
del primer grupo son agnósticas por naturaleza. Las del segundo necesitan tres datos que ningún
escáner deduce: cómo arranca la aplicación, cómo se inicia sesión y qué endpoints existen. Separar
el laboratorio por esa línea vuelve el núcleo reutilizable y concentra lo específico en un perfil.

*Orientación.* Implementado así:

```
SECURITY-LAB/
  docker-compose.yml     # sólo herramientas; ningún nombre de proyecto
  recipes/               # bloques de arranque reutilizables (postgres, moodle-plugin, fastapi-uvicorn, kafka-zk)
  lib/auth/              # adaptadores de autenticación (sanctum, moodle-session, jwt-bearer, basic, none)
  lib/specs/             # pruebas genéricas que hereda todo proyecto
  targets/<nombre>/      # target.env + compose.runtime.yml + zap/ + k6/ + playwright/ + db-init/
```
El perfil de costos_web se **extrajo** del núcleo (prueba de que quedó limpio) y el de antiplagio se
creó componiendo recetas:
```yaml
include:
  - path: ./recipes/postgres.yml
  - path: ./recipes/moodle-plugin.yml
  - path: ./recipes/fastapi-uvicorn.yml
```

### Verificación
```bash
grep -rniE 'costos|antiplag|zajuna' docker-compose.yml Makefile lib/ tools/ recipes/   # sin resultados
make doctor TARGET=costos_web    # el perfil antiguo sigue resolviendo
make doctor TARGET=antiplagio
```
Ejecutado: el núcleo no menciona ningún proyecto, y ambos perfiles resuelven origen, roles y
adaptador. `gitleaks` sobre costos_web sigue produciendo sus 9 hallazgos históricos
(2 × `laravel-app-key`, 5 × `env-db-password`).

### Prioridad y esfuerzo
Prioridad 1 · 6 h · **hecho**.

---

## M2 · 🟠 Alto · ✅ Cerrado — Ninguna corrida emitía veredicto
**Responsable: DevOps/Infra**

### Qué está pasando
Todas las herramientas estaban configuradas para **no fallar**: `gitleaks ... --exit-code=0`,
`php artisan migrate --force || true`, y semgrep con `--error=false`. Una corrida terminaba «bien»
tanto si el proyecto estaba impecable como si tenía 165 secretos en la historia.

### Por qué es un error
El equipo receptor no tiene el contexto para leer 300 páginas de SARIF. Sin un veredicto explícito,
la herramienta produce archivos, no decisiones; y en un pipeline, una corrida verde sobre un
proyecto vulnerable es peor que no correr nada, porque genera confianza injustificada.

### Recomendación de remediación
*Explicación.* Que cada herramienta no falle es **correcto**: una dimensión ruidosa no debe abortar
las demás. Lo que falta es un paso posterior que agregue los resultados y aplique el apetito de
riesgo **que declara cada proyecto**, no la herramienta.

*Orientación.* `tools/gate.sh` + umbrales en `target.env`:
```
ALLOW_SECRETS=0
MAX_DEP_FINDINGS=40
MAX_SAST_FINDINGS=60
K6_P95_MS=3000
K6_ERR_RATE=0.02
```
`make gate TARGET=<perfil>` sale distinto de cero. Distingue explícitamente `PASS`, `FAIL` y
`skip`, y recuerda al pie que **`skip` no es `PASS`**.

### Verificación
```bash
make gate TARGET=antiplagio; echo $?
```
Ejecutado — salida real:
```
FAIL  secrets: 165 found in git history (allowed 0)
FAIL  dependency findings: 90 (max 40)
PASS  SAST findings: 4 (max 60)
skip  k6 not run
FAIL  playwright: 13 failed specs
GATE FAILED   (exit 2)
```

### Prioridad y esfuerzo
Prioridad 1 · 2 h · **hecho**.

> **Nota de método.** La primera versión de esta compuerta buscaba `"status":"failed"` y el JSON de
> Playwright escribe `"status": "failed"`, con espacio: informó «sin fallos» sobre una suite con 13
> fallos. Es exactamente el modo de fallo que la compuerta debía impedir, dentro de la compuerta
> misma. Corregido con `grep -oE '"status":[[:space:]]*"failed"'`. **Toda compuerta debe probarse
> contra una corrida que se sabe que falla**, nunca sólo contra una que se sabe que pasa.

---

## M3 · 🟠 Alto · ✅ Cerrado — Sin inventario de cobertura
**Responsable: DevOps/Infra**

### Qué está pasando
El informe de la corrida anterior (`reports/costos_web/RESULTS.md`) anotaba en una celda de tabla
«SonarQube / Qodana — *wired, no ejecutado esta corrida*». Enterrado ahí, el documento se lee como
cobertura completa.

### Por qué es un error
En seguridad, la ausencia de hallazgo sólo significa algo si se puede distinguir de la ausencia de
análisis. Un directorio `reports/` con nueve carpetas parece exhaustivo aunque tres estén vacías.

### Recomendación de remediación
*Explicación.* La cobertura debe ser un **artefacto generado**, no una frase que alguien recuerde
escribir. Si se deriva de qué archivos existen y no están vacíos, no puede mentir.

*Orientación.* `tools/run-manifest.sh` → `reports/<perfil>/RUN.md` con: fecha, host, ruta y commit
del código auditado, sobre de recursos declarado, tabla de dimensiones con `yes`/**`NO`**, digests
de las imágenes usadas, y una sección fija de **lo que ninguna herramienta cubre**.

### Verificación
```bash
make run-manifest TARGET=antiplagio && sed -n '/## Coverage/,/^$/p' reports/antiplagio/RUN.md
```
En esta corrida marca `NO` en Image CVE, Quality (qodana) y Load (k6) — que es la verdad.

### Prioridad y esfuerzo
Prioridad 1 · 2 h · **hecho**.

---

## M4 · 🟠 Alto · ⚠️ Abierto — La matriz de autorización exige un escenario sembrado
**Responsable: Backend + operador del laboratorio**

### Qué está pasando
Se declaró la política esperada en `targets/antiplagio/playwright/authz-matrix.json` (10 endpoints
del plugin, con qué rol debe alcanzar cada uno) y se ejecutó con dos cuentas reales de Moodle,
`instructor_lab` (rol A) y `aprendiz_lab` (rol B). Resultado: **13 fallos de 27**. Al triarlos:

- Los fallos de **rol A** (`404`, `400`, `500`) no son hallazgos: el Moodle del laboratorio está
  recién instalado y **no existe el curso ni la actividad `cmid=1`**, ni hay entregas.
- Los fallos de **rol B** con `200` tampoco son bypass. Al inspeccionar el cuerpo:
  ```
  GET  get_student_results.php?userid=2&cmid=1 → HTTP 200  {"error":"A required parameter (id) was missing"}
  POST fix_criteria.php                        → HTTP 200  {"error":"A required parameter (id) was missing"}
  POST release_student.php                     → HTTP 200  {"error":"A required parameter (id) was missing"}
  ```
  La validación de parámetros ocurre **antes** de la comprobación de capacidades, así que la
  ejecución nunca llegó a la decisión de autorización.

**La dimensión de autorización quedó INCONCLUSA, no aprobada ni reprobada.**

### Por qué es un error
Es el riesgo más grave de todo el laboratorio: una matriz que falla por falta de escenario se parece
mucho a una matriz que falla por inseguridad, y una que «pasa» porque todo devuelve error se parece
a una aplicación bien protegida. Un equipo sin contexto puede cerrar la dimensión en cualquiera de
los dos sentidos, y ambos son falsos.

### Recomendación de remediación
*Explicación.* Probar autorización exige que la operación **pueda tener éxito** para quien sí tiene
derecho. Si nadie puede ejecutarla, el `403` del no autorizado no prueba nada. Por eso el escenario
—curso, actividad, matrículas por rol, una entrega analizada— es un **insumo obligatorio**, del
mismo rango que las credenciales.

*Orientación.*
1. Extender `targets/antiplagio/seed-users.sh` a `seed-scenario.sh`: crear curso, actividad
   `assign`, matricular rol A como `editingteacher` y rol B como `student`, subir un documento y
   ejecutar un análisis. El propio repositorio ya trae piezas reutilizables:
   `antiplagio/tests/generate_fake_data.py`, `helper/create_cohorte_test.php`, `helper/add_material.php`.
2. Sustituir los `cmid`/`userid` fijos de `authz-matrix.json` por los identificadores que emita ese
   sembrado (exportarlos a un `scenario.json` que la spec lea).
3. Añadir a `lib/specs/authz-matrix.spec.ts` una **precondición**: si el rol autorizado no obtiene
   un resultado legítimo, marcar la regla como *inconclusive* en vez de *failed*.

### Verificación
Con el escenario sembrado, para cada regla: el rol autorizado responde `<400` **con contenido real**
y el no autorizado responde `401/403/404`. Mientras alguna regla no cumpla la primera mitad, la
dimensión se declara inconclusa en `RUN.md`.

### Prioridad y esfuerzo
Prioridad 2 · 8 h.

---

## M5 · 🟠 Alto · ✅ Cerrado — Un dato de prueba mal formado hace que el test no pruebe nada
**Responsable: Seguridad**

### Qué está pasando
La prueba del secreto compartido entre analyzer y API enviaba
`{"id_process":..., "state_process":"finalizado"}`. La API respondía **422** y la prueba fallaba con
un mensaje de autenticación. El modelo real es otro
(`api_antiplagio/models_api/estatus_process.py`): `final_state_process` y `name_antpgl_report`.
FastAPI **valida el cuerpo antes de ejecutar el handler**, y la comprobación del secreto vive dentro
del handler; con un cuerpo inválido nunca se llega a autenticar.

### Por qué es un error
El fallo es indistinguible de un hallazgo real de autenticación. Con el signo contrario —una
aserción laxa— habría producido un «pasa» sobre un endpoint jamás ejercido.

### Recomendación de remediación
*Explicación.* Una prueba de autorización debe llegar hasta la comprobación de autorización. Eso
obliga a que la spec conozca el contrato de datos: el payload es parte del insumo, no un detalle.

*Orientación.* Payload correcto declarado como constante junto a su origen:
```ts
// Shape of models_api/estatus_process.py
const VALID_BODY = { id_process: 999999, final_state_process: 'finalizado', name_antpgl_report: 'lab-probe.pdf' };
```

### Verificación
```bash
make e2e TARGET=antiplagio     # las 2 pruebas del secreto compartido pasan
```
Ejecutado y comprobado además a mano:
```
sin secreto     -> 401
secreto erróneo -> 401
```

### Prioridad y esfuerzo
Prioridad 2 · 1 h · **hecho**.

> **Efecto lateral, que es un hallazgo del proyecto:** el orden «validar y después autenticar»
> permite a un no autenticado mapear el esquema esperado distinguiendo `422` de `401`. Ver A3.

---

## M6 · 🟠 Alto · ✅ Cerrado — Montajes vacíos silenciosos por la semántica de `include`
**Responsable: DevOps/Infra**

### Qué está pasando
Docker Compose resuelve la **ruta del `include`** contra el directorio del proyecto, pero las rutas
**dentro del archivo incluido** contra el directorio de ese archivo. Las recetas usaban
`./targets/${TARGET_NAME}/db-init`, que se resolvía como `recipes/targets/antiplagio/db-init`;
Docker **crea el directorio inexistente y lo monta vacío**. Consecuencia: la semilla de base de datos
no se aplicaba nunca y el contenedor arrancaba con una base vacía, sin un solo mensaje de error.

### Por qué es un error
Es el peor tipo de fallo de un laboratorio: silencioso y corriente abajo. Todo arranca, todo
responde, y los resultados son inválidos por una razón invisible. El mismo error dejó el script de
instalación del plugin montado como *directorio*, de modo que el hook nunca se ejecutó.

### Recomendación de remediación
*Explicación.* No hay opción de Compose que unifique ambas semánticas; la defensa es que las rutas
de las recetas sean relativas **a la carpeta de recetas**, y que exista una comprobación previa.

*Orientación.* Corregido a `../targets/${TARGET_NAME}/db-init` y `./moodle-plugin-install.sh`, con
la explicación escrita en `recipes/postgres.yml` para quien edite el archivo. Comprobación:
```bash
docker compose --env-file targets/<t>/target.env -f docker-compose.yml \
  -f targets/<t>/compose.runtime.yml --profile runtime config | grep -A1 'source:'
```
Toda ruta de origen debe existir en el host **antes** de levantar. Añadir esta comprobación a
`make doctor` es la mejora pendiente natural.

### Verificación
Ejecutado tras el arreglo: los orígenes resuelven a `SECURITY-LAB/targets/antiplagio/db-init` y a
`SECURITY-LAB/recipes/moodle-plugin-install.sh`, el hook corre y deja traza `[lab] plugin
installed...`, y las 11 tablas del plugin existen:
```
mdl_local_antiplag_actmap, ..._audit, ..._doc, ..._lsh, ..._matchdet, ..._parapair,
..._parasig, ..._progmap, ..._sig, ..._stud_report, mdl_local_antiplagiarsena
```

### Prioridad y esfuerzo
Prioridad 1 · 3 h · **hecho**.

---

## M7 · 🔴 Crítico · ⚠️ Abierto — Datos personales reales dentro del laboratorio
**Responsable: Seguridad + Líder Técnico**

### Qué está pasando
`targets/costos_web/db-init/01_data.sql` son 4,5 MB de volcado **real** con datos de 20 368
personas. Estaba en `db-init/` del laboratorio y se movió tal cual al perfil durante esta
intervención. Es el mismo dato cuya exposición fue el hallazgo L1 del informe de endurecimiento
anterior (puertos en `0.0.0.0` alcanzables desde la LAN institucional).

Además, `reports/` mantiene permisos `777` y no hay política de retención ni de purga.

### Por qué es un error
La herramienta de auditoría se convierte en el activo más sensible del entorno: concentra datos
personales, credenciales de prueba conocidas y servicios sin endurecer. Un incidente originado en la
herramienta de seguridad es, además de un problema de datos, un problema de credibilidad del área.

### Recomendación de remediación
*Explicación.* El laboratorio debe poder auditar **sin** datos reales. La única razón legítima para
un volcado real es reproducir un comportamiento dependiente del volumen (el `OOM` de
`/api/usuarios` en costos_web). Eso es una excepción acotada y con fecha, no el estado por defecto.

*Orientación.*
1. Retirar `01_data.sql` del árbol del laboratorio y conservarlo, si se necesita, cifrado y fuera
   del repositorio.
2. Sustituirlo por un generador sintético con volumetría equivalente (es el volumen lo que
   reproduce el hallazgo, no la identidad de las personas).
3. Declarar la política de datos en el README: quién puede correr con datos reales, en qué host, con
   qué retención; `make purge TARGET=<perfil>` ya existe para el borrado.
4. Anonimizar antes de compartir cualquier reporte.
5. Mantener **todos** los puertos publicados en `127.0.0.1` — ya es invariante del núcleo y se
   verificó en toda esta corrida.

### Verificación
```bash
ls targets/*/db-init/*.sql          # ningún volcado de producción
ss -ltn | grep -E '0\.0\.0\.0:(9000|8081|8030|8099|8100)'   # sin resultados
```
La segunda comprobación se ejecutó durante toda la corrida: ningún puerto del laboratorio escuchó
fuera de loopback.

### Prioridad y esfuerzo
Prioridad 1 · 1 h (más la decisión sobre el archivo).

---

## M8 · 🟡 Medio · ⚠️ Abierto — SonarQube falla de forma opaca con el disco al 90%
**Responsable: DevOps/Infra**

### Qué está pasando
`make sonar TARGET=antiplagio` falló dos veces. El error visible era
`dependency failed to start: container sonarqube exited (0)`. La causa real, en los registros del
contenedor:
```
flood stage disk watermark [95%] exceeded ... free: 9.8gb[2.7%], all indices will be marked read-only
high disk watermark [90%] exceeded ... free: 19.7gb[5.4%], shards will be relocated away from this node
Caused by: ResponseException: GET /_cluster/health?wait_for_status=yellow → 408 Request Timeout
```
El Elasticsearch embebido aplica sus umbrales en **porcentaje de uso**, no en espacio absoluto. Con
19,7 GB libres pero el 94% ocupado, no asigna shards, el índice nunca pasa a *yellow* y el escáner
muere con un 408. Liberar 10,7 GB de imágenes Docker no bastó.

### Por qué es un error
Cuesta media hora de trazas de Elasticsearch llegar a «falta disco», y el mensaje visible apunta al
contenedor equivocado. Para un equipo que no conoce la herramienta, es el tipo de fallo que hace
abandonar la dimensión.

### Recomendación de remediación
*Explicación.* No se arregla en el laboratorio: es un requisito de capacidad del host. Lo que sí
corresponde es **declararlo y detectarlo antes**, para que el fallo sea legible.

*Orientación.* `tools/doctor.sh` mide ahora las dos magnitudes y explica la consecuencia:
```
FAIL  disk used: 96% — SonarQube WILL fail: its Elasticsearch high watermark (90%) stops
      shard allocation, the index never turns yellow, and the scanner dies with an
      opaque '408 Request Timeout'. Free space until below 90%; extra GB do not help.
```
Requisito a documentar para el equipo receptor: **sistema de archivos por debajo del 90% de uso** y
~8 GB para imágenes de herramientas.

### Verificación
```bash
make doctor TARGET=antiplagio      # debe dar ok en «disk used»
make sonar  TARGET=antiplagio
```
En esta corrida, SonarQube y Qodana quedan marcados **`NO`** en `RUN.md`. Cobertura estática de esta
corrida: gitleaks, trufflehog, Trivy (fs y config), semgrep y syft.

### Prioridad y esfuerzo
Prioridad 3 · depende de capacidad del host.

---

## M9 · 🟡 Medio · ✅ Cerrado — `semgrep --config=auto` exige telemetría
**Responsable: Seguridad**

### Qué está pasando
Con `--metrics=off`, semgrep aborta: `Cannot create auto config when metrics are off`. Es decir,
`--config=auto` **requiere enviar telemetría** sobre el código analizado.

### Por qué es un error
El laboratorio analiza código institucional, en ocasiones junto a datos personales. Enviar
telemetría a un tercero como precio de una regla por defecto no es aceptable, y es la clase de
decisión que se toma sin darse cuenta al copiar el ejemplo de la documentación.

### Recomendación de remediación
*Explicación.* Los conjuntos de reglas explícitos se descargan igual pero no envían telemetría del
análisis, y además hacen **reproducible** la corrida: `auto` puede cambiar de reglas entre
ejecuciones y mover los resultados sin que cambie el código.

*Orientación.* En `target.env`:
```
SEMGREP_CONFIG=--config=p/security-audit --config=p/secrets --config=p/owasp-top-ten
```

### Verificación
```bash
make semgrep TARGET=antiplagio
```
Ejecutado: 376 reglas sobre 148 archivos, 4 hallazgos, sin telemetría.

### Prioridad y esfuerzo
Prioridad 2 · 30 min · **hecho**.

---

## M10 · 🟡 Medio · ✅ Cerrado — Montar el laboratorio en `/lib` inutiliza el contenedor
**Responsable: DevOps/Infra**

### Qué está pasando
Las bibliotecas compartidas del laboratorio se montaban como `- ./lib:/lib:ro`, encima del
**directorio de bibliotecas del sistema** del contenedor. Desaparece el cargador dinámico y ningún
binario ejecuta:
```
exec /usr/bin/sh: no such file or directory
```
El mensaje nombra al intérprete, nunca al montaje que lo rompió.

### Por qué es un error
Es un fallo total con un síntoma engañoso: parece una imagen corrupta. Cuesta horas si no se ha
visto antes, y `/lib` es un nombre que se elige con toda naturalidad.

### Recomendación de remediación
*Explicación.* Los puntos de montaje del laboratorio no deben colisionar con rutas del sistema
operativo (`/lib`, `/bin`, `/usr`, `/etc`, `/var`).

*Orientación.* Renombrado a `/seclab-lib`, con la advertencia escrita junto al montaje.

### Verificación
```bash
make e2e TARGET=antiplagio    # el contenedor arranca y ejecuta la suite
```
Ejecutado: 27 pruebas, 14 pasan, 13 fallan (ver M4 para el triaje).

### Prioridad y esfuerzo
Prioridad 2 · 1 h · **hecho**.

---

## M11 · 🟡 Medio · ✅ Cerrado — Hooks como root rompen los permisos del runtime
**Responsable: DevOps/Infra**

### Qué está pasando
El hook que instala el plugin corre como `root`; el servidor web no. Los directorios que el
`admin/cli/upgrade.php` creó bajo `moodledata` quedaron con propietario `root` y Moodle respondió
**HTTP 500** a toda petición:
> «Invalid permissions detected when trying to create a directory.»

El mensaje habla de permisos pero no de su causa. Antes de eso, otros dos intentos fallaron por
razones relacionadas: montar la fuente read-only dentro del árbol de Moodle impide que la imagen
reubique su propio código (`rm: cannot remove ...: Read-only file system`), y sobreescribir el
`command` de la imagen **salta la instalación completa** porque su entrypoint sólo la ejecuta cuando
el comando es el suyo propio.

### Por qué es un error
Tres fallos distintos con síntomas que apuntan a capas equivocadas (Apache, permisos, `config.php`).
Para el equipo receptor, cada uno es una sesión perdida.

### Recomendación de remediación
*Explicación.* El principio «la fuente auditada es de sólo lectura» y el hecho de que las imágenes
gestionen su propio árbol son incompatibles con un montaje directo. La solución es **copiar** desde
un montaje read-only externo al árbol, mediante el hook oficial de la imagen, y **devolver la
propiedad** de los directorios de datos.

*Orientación.* En `recipes/moodle-plugin-install.sh`:
```bash
OWNER="$(stat -c '%u:%g' /bitnami/moodledata)"
cp -a /plugin-src "$DEST"
php /bitnami/moodle/admin/cli/upgrade.php --non-interactive --allow-unstable
chown -R "$OWNER" /bitnami/moodledata "$DEST"
```
Regla general para nuevas recetas: **nunca sobreescribir el `command` de una imagen que instala
algo en su entrypoint**; usar su mecanismo de hooks.

### Verificación
```bash
curl -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8081/login/index.php     # 200
docker exec seclab_antiplagio-db-1 psql -U moodle -d moodle_lab -tAc \
  "select count(*) from pg_tables where tablename like '%antiplag%'"             # 11
```
Ambas ejecutadas y correctas. Es la prueba de que la receta `moodle-plugin` funciona: **Moodle mismo
creó el esquema del plugin**, no una versión escrita a mano.

### Prioridad y esfuerzo
Prioridad 2 · 1 h · **hecho**.

---

## M12 · 🟡 Medio · ⚠️ Parcial — Ninguna herramienta analiza ficheros `docker-compose`
**Responsable: DevOps/Infra**

### Qué está pasando
Se añadió `make config-scan` (Trivy en modo `config`) y detectó 3 problemas, **los tres en el
`Dockerfile`** del analyzer. El `docker-compose.yml` del propio proyecto declara
`ALLOW_ANONYMOUS_LOGIN=yes` en Zookeeper y `ALLOW_PLAINTEXT_LISTENER=yes` en Kafka, sobre imágenes
`bitnamilegacy` sin mantenimiento: **ninguna herramienta del laboratorio lo reporta** (Trivy cubre
Dockerfile, Kubernetes, Terraform y Helm, no Compose).

Quien lo detectó fue `tools/detect.sh`, por coincidencia de texto, y sólo como advertencia.

### Por qué es un error
Un broker sin autenticación es la clase de configuración que decide un compromiso, y queda fuera de
la cobertura de la herramienta justo cuando el informe declara «configuración analizada».

### Recomendación de remediación
*Explicación.* Se necesita un analizador que entienda Compose. La opción de menor fricción es un
conjunto de reglas propio de semgrep sobre YAML, que además queda versionado y revisable.

*Orientación.*
1. `configs/semgrep-compose/` con reglas para: `ALLOW_ANONYMOUS_LOGIN`, `ALLOW_PLAINTEXT_LISTENER`,
   puertos en `0.0.0.0`, `privileged: true`, montaje de `/var/run/docker.sock`, contenedores sin
   `user:`, imágenes por tag mutable.
2. Añadirlas a `SEMGREP_CONFIG` del perfil.
3. Mientras tanto, `RUN.md` debe declarar esta dimensión como no cubierta.

### Verificación
```bash
make semgrep TARGET=antiplagio   # debe reportar el Zookeeper anónimo y el Kafka en plaintext
```

### Prioridad y esfuerzo
Prioridad 3 · 4 h.

---

## M13 · 🟡 Medio · ⚠️ Parcial — Qodana cubre un solo lenguaje por imagen
**Responsable: Seguridad**

### Qué está pasando
La imagen de Qodana es específica por lenguaje. Antiplagio tiene 63 archivos Python y 38 PHP; con
`jetbrains/qodana-python` el plugin de Moodle queda fuera del análisis de calidad, y al revés con la
imagen de PHP.

### Por qué es un error
El proyecto poliglota es la norma, no la excepción, y la mitad no analizada no se nota en el
resultado.

### Recomendación de remediación
*Explicación.* Es una limitación del producto, no del laboratorio. Se compensa con la combinación
SonarQube (multi-lenguaje en la misma pasada) + semgrep (poliglota, con taint), y se declara.

*Orientación.* `LANGS` en `target.env` ya expresa los lenguajes; `make detect` propone la imagen y
**advierte** cuando hay más de uno:
```
# NOTE: polyglot project. One Qodana image covers ONE language; the others are
#       covered by SonarQube + semgrep. State that limit in the report.
```
Mejora pendiente: permitir varias pasadas de Qodana (`QODANA_IMAGES` como lista) escribiendo en
subcarpetas distintas de `reports/`.

### Verificación
`RUN.md` debe indicar qué lenguaje cubrió Qodana y cuáles quedaron sólo con SonarQube/semgrep.

### Prioridad y esfuerzo
Prioridad 3 · 2 h.

---

## M14 · 🟠 Alto · ⚠️ Abierto — Imágenes de herramientas en `:latest`
**Responsable: DevOps/Infra**

### Qué está pasando
`gitleaks`, `trufflehog`, `trivy`, `semgrep`, `syft`, `sonar-scanner`, `qodana`, `zap`, `k6` y
`alpine/git` se referencian por tag `latest`, que es mutable.

### Por qué es un error
Dos consecuencias. **Seguridad:** un tag republicado se ejecuta con los montajes del laboratorio —
incluido el código fuente del proyecto y, en el caso del clonado, material de credenciales.
**Reproducibilidad:** dos corridas del mismo commit pueden diferir sin que nadie sepa por qué, lo
que invalida cualquier comparación entre corridas.

### Recomendación de remediación
*Explicación.* Anclar por digest convierte la versión de la herramienta en parte del dato de la
corrida. La actualización pasa a ser un cambio deliberado y revisable.

*Orientación.*
1. `docker images --digests` (ya lo vuelca `RUN.md`) para tomar los digests actuales.
2. Fijar `imagen@sha256:...` en el núcleo, empezando por `alpine/git` (recibe material sensible) y
   por las que montan la fuente.
3. Revisión trimestral de digests.

### Verificación
```bash
grep -E 'image:.*:latest' docker-compose.yml     # sin resultados cuando esté cerrado
```

### Prioridad y esfuerzo
Prioridad 2 · 2 h.

---

## M15 · 🟠 Alto · ✅ Cerrado — El clonado montaba `~/.ssh` completo
**Responsable: DevOps/Infra**

### Qué está pasando
El servicio `clone` montaba `${HOME}/.ssh:/root/.ssh:ro` — **todas** las claves privadas del usuario
— dentro de un contenedor basado en una imagen con tag mutable (M14).

### Por qué es un error
Combina la peor exposición con el peor vector: una imagen comprometida obtiene todas las claves del
operador, no una de despliegue de sólo lectura.

### Recomendación de remediación
*Explicación.* En la práctica el código casi siempre ya está en el host. Hacer del checkout local el
camino por defecto elimina la necesidad de que una credencial entre en un contenedor.

*Orientación.* `SRC_PATH` (checkout local) es ahora el modo normal y el usado en toda esta corrida.
`make clone` permanece como alternativa y monta **un único archivo de clave dedicada**:
```yaml
- ${DEPLOY_KEY:-./configs/deploy_key}:/root/.ssh/id_ed25519:ro
```

### Verificación
```bash
grep -r 'HOME}/.ssh' docker-compose.yml recipes/    # sin resultados
```

### Prioridad y esfuerzo
Prioridad 1 · 1 h · **hecho**.

---

## M16 · 🟡 Medio · ✅ Cerrado — Los reportes los adueña el primer contenedor que escribe
**Responsable: DevOps/Infra**

### Qué está pasando
`make dast` completó el análisis y perdió el resultado:
```
Job report failed to generate report: AccessDeniedException /zap/wrk/reports/zap-report.html
```
La carpeta `reports/antiplagio/zap` la había creado antes otro contenedor **como root**; ZAP corre
sin privilegios y no pudo escribir. El escaneo se ejecutó entero y no dejó nada.

### Por qué es un error
Es la forma más cara de perder una dimensión: se paga el tiempo de cómputo y no queda evidencia. Y
si nadie revisa el registro, `RUN.md` marcará **NO** sin que se entienda por qué.

### Recomendación de remediación
*Explicación.* Quien crea el directorio primero decide su propietario. Si lo crea el usuario del
host antes de levantar nada, los contenedores root escriben igual (root escribe en todas partes) y
los no privilegiados también, porque el UID coincide.

*Orientación.* El objetivo `guard` del `Makefile` precrea **todos** los subdirectorios de salida
antes de cualquier contenedor. Es preferible al `chmod 777` del manual anterior: resuelve la causa
en vez del síntoma y no deja permisos abiertos sobre datos sensibles.

### Verificación
```bash
make dast TARGET=antiplagio && ls -l reports/antiplagio/zap/
```
Ejecutado: `zap-report.html` (115 KB) y `zap-report.json` (615 KB), propiedad del usuario del host.

### Prioridad y esfuerzo
Prioridad 2 · 1 h · **hecho**.

---

## M17 · 🟡 Medio · ✅ Cerrado — Una advertencia de ZAP abortaba la corrida
**Responsable: DevOps/Infra**

### Qué está pasando
ZAP devuelve un código distinto de cero cuando su plan produce **advertencias**, no sólo errores. La
advertencia era trivial —la URL semilla del contexto de la API responde 404 porque el servicio no
tiene manejador en `/`— y aun así detenía el `make`. Fijar `failOnError: false` y
`failOnWarning: false` en el plan no lo evita.

### Por qué es un error
Choca con el principio de M2: la herramienta no debe dictar el veredicto. Pero la solución perezosa
(`|| true`) es peor, porque habría ocultado exactamente el fallo de M16, donde ZAP terminó sin
escribir nada.

### Recomendación de remediación
*Explicación.* Hay que separar dos preguntas: **¿la herramienta corrió?** y **¿el resultado es
aceptable?**. La primera se responde con la existencia del artefacto; la segunda es de `make gate`.

*Orientación.* En el `Makefile`:
```make
-$(DC) --profile dast run --rm zap
@test -s $(REPORTS)/zap/zap-report.json || { echo "ZAP produced no report"; exit 1; }
```
Y un presupuesto de alertas en `target.env` (`MAX_DAST_FINDINGS`) para que la compuerta sí opine.

### Verificación
```bash
make dast TARGET=antiplagio; echo $?     # 0 con reporte presente, 1 si no lo hay
make gate TARGET=antiplagio              # ahora incluye la línea DAST
```
Ejecutado — salida real de la compuerta:
```
FAIL  secrets: 165 found in git history (allowed 0)
FAIL  dependency findings: 90 (max 40)
PASS  SAST findings: 4 (max 60)
FAIL  DAST alerts: 57 (max 40)
skip  k6 not run
FAIL  playwright: 13 failed specs
```

### Prioridad y esfuerzo
Prioridad 2 · 1 h · **hecho**.

---

# Los tres cubos de trabajo del controlador

La pregunta central de esta migración: **qué hace la herramienta, qué debe aportar la persona y qué
no se automatiza nunca.** Lo que sigue no es teoría: cada línea corresponde a algo que ocurrió en
esta corrida.

## 1. Automatizado — cero decisiones del operador

Funciona en cualquier proyecto sin saber qué hace el proyecto, porque sólo necesita **un
repositorio**:

| Dimensión | Comando | Resultado real sobre antiplagio |
|---|---|---|
| Secretos en toda la historia git | `make secrets` | 165 hallazgos |
| CVE de dependencias | `make deps` | 90 (1 crítico, 31 altos) |
| Configuración de contenedores | `make config-scan` | 3 (2 altos) |
| SAST poliglota | `make semgrep` | 4 (376 reglas, 148 archivos) |
| Inventario de componentes | `make sbom` | SPDX generado |
| DAST | `make dast` | 57 alertas (56 en Moodle, 1 en la API) |
| Calidad | `make sonar` / `make qodana` | **no ejecutado** (M8) |
| Reportes, manifiesto, desmontaje | `make run-manifest` / `make down` | — |

Coste de puesta en marcha para este proyecto: **editar un archivo**. `make detect` dedujo solo el
censo de lenguajes, el linter aplicable, el adaptador de autenticación (`moodle-session`, a partir
de `version.php`) y las recetas necesarias (`fastapi-uvicorn`, `moodle-plugin`, `kafka-zk`).

## 2. Requiere insumos — la herramienta no los adivina

Formato «insumo → qué se rompe si falta», con lo observado:

| Insumo | Si falta |
|---|---|
| `SRC_PATH` / repositorio y rama | No hay nada que analizar |
| **Receta de arranque** (`compose.runtime.yml`) | No hay DAST, ni carga, ni autorización. Es el insumo más caro: un plugin de Moodle **no arranca solo** |
| **Adaptador de autenticación** | Todo se prueba sin sesión; el informe dirá «DAST hecho» sobre superficie pública |
| **Dos cuentas de distinto privilegio** | La autorización no se puede probar en absoluto |
| **Escenario sembrado** (curso, actividad, entrega) | La matriz devuelve resultados inconclusos que parecen fallos (M4) |
| **`authz-matrix.json`**: qué rol puede alcanzar qué | Ninguna herramienta conoce la política institucional |
| **Contrato de datos** de los endpoints probados | El test no llega a la comprobación que pretende probar (M5) |
| `HEALTH_PATH` | No se distingue «no hay hallazgos» de «no había nada corriendo» |
| Matriz de lenguajes (`LANGS`) | Se analiza medio proyecto sin que se note |
| **Sobre de recursos declarado** (`PERF_CPUS`, `PERF_MEM`) | Los números de carga no son comparables entre corridas ni entre máquinas |
| Umbrales del gate | La corrida no emite veredicto |

## 3. Requiere análisis humano — no automatizable

- **Decidir qué *debería* hacer un endpoint.** Un `200` sólo es hallazgo si la política decía `403`.
  Ninguna herramienta conoce los roles de Zajuna.
- **Triaje.** De 13 fallos de la suite, **cero** eran bypass de autorización: unos por escenario
  ausente y otros porque el `200` traía un cuerpo de error. Un informe automático habría reportado
  diez vulnerabilidades críticas inexistentes.
- **Triaje al revés.** semgrep marcó `echoed-request` en `get_data.php:132` y `get_reports.php:75`.
  Leyendo el código: el primero es **falso positivo** (`get_data.php:3` fija
  `Content-Type: application/json`); el segundo es **parcialmente real** (no fija cabecera). Y
  `get_lines.php` tiene el mismo defecto y **semgrep no lo marcó**. La herramienta acertó una de
  tres; la lectura del código cerró las otras dos.
- **Alcanzabilidad.** 90 hallazgos de dependencias no son 90 riesgos. `PyJWT 2.3.0`
  (CVE-2022-29217, confusión de algoritmos) importa porque la API firma tokens con PyJWT; varios
  CVE de `pillow` pesan distinto según si se procesan imágenes de terceros.
- **Abuso de lógica de negocio.** Los guiones `abuse_per_page.js`, `abuse_search.js` y
  `seguimiento_write.js` de costos_web se escribieron **después de leer el código**. Son la salida
  de un análisis, no su entrada.
- **Modelo de amenazas entre servicios.** El patrón «autenticación opcional si la variable está
  vacía» (A3) no lo encuentra ningún escáner: el rastreador no adivina el nombre de la cabecera y el
  SAST ve una decisión de compatibilidad deliberada y comentada.
- **Calibración de severidad** en contexto institucional (documentos de aprendices del SENA).
- **Distinguir hallazgo de problema de entorno.** SonarQube no corrió por el disco del host, no por
  el proyecto. Confundirlos contamina el informe en ambas direcciones.

---

# ¿Es viable como herramienta escalable e intuitiva?

Sí, y la corrida lo acota con números en lugar de opiniones.

**Lo que ya es intuitivo.** Dar de alta antiplagio requirió: `make new`, `make detect`, editar
`target.env`, `make doctor`, `make static`. La parte estática produjo hallazgos reales **sin
runtime**, en minutos y sin conocer el proyecto. Ese es el 80% de los casos y el 100% del primer día
de cualquier equipo.

**Lo que cuesta una vez por stack.** El runtime. Aquí fueron ~4 horas y cinco fallos sucesivos
(M6, M10, M11 ×3). Pero el resultado quedó en `recipes/moodle-plugin.yml`: **el siguiente plugin de
Moodle se levanta con tres líneas de `include`**. Ese es el modelo de escala — el catálogo de recetas
crece y el coste del proyecto N+1 baja. Hoy: `postgres`, `moodle-plugin`, `fastapi-uvicorn`,
`kafka-zk`, más los de costos_web.

**Lo que no será intuitivo nunca.** El cubo 3. Un equipo que reciba el laboratorio como «un botón»
producirá informes con diez falsos críticos —lo vimos— o cerrará como segura una dimensión que nunca
se ejecutó. **El modo de fallo más probable de esta migración no es técnico, es de expectativa.**

Por eso el laboratorio incluye ahora tres piezas cuyo único propósito es hacer visible lo que no
sabe: `make gate` (veredicto explícito), `RUN.md` (qué NO se ejecutó) y `skip ≠ PASS` impreso en la
propia salida.

---

# Orden recomendado de ejecución

Por riesgo y esfuerzo, para el equipo receptor:

1. **M7** — retirar el volcado con datos personales del árbol del laboratorio *(1 h, crítico)*.
2. **M14** — anclar por digest las imágenes que reciben montajes sensibles *(2 h)*.
3. **M8** — disponer de un host con el sistema de archivos por debajo del 90% y volver a correr
   SonarQube/Qodana *(capacidad)*.
4. **M4** — sembrar el escenario de Antiplagio y volver a ejecutar la matriz de autorización, que
   hoy es la única dimensión **inconclusa** *(8 h)*.
5. **M12** — reglas de semgrep para `docker-compose` *(4 h)*.
6. **M13** — pasadas múltiples de Qodana en proyectos poliglotas *(2 h)*.

Todo lo marcado ✅ está aplicado y verificado en esta corrida.

---

# Reproducción

```bash
cd "SECURITY-LAB"

# 1. alta de un proyecto
make new    TARGET=<nombre> && $EDITOR targets/<nombre>/target.env
make detect TARGET=<nombre>          # propone LANGS / QODANA_IMAGE / AUTH_ADAPTER / recetas
make doctor TARGET=<nombre>          # preflight: docker, disco (dos unidades), puertos, permisos

# 2. dimensiones sin runtime (ya producen hallazgos)
make secrets deps config-scan sbom semgrep TARGET=<nombre>

# 3. runtime + dimensiones dinámicas
make up TARGET=<nombre>
./targets/<nombre>/seed-users.sh     # las dos cuentas; sin ellas no hay autorización
make e2e dast perf TARGET=<nombre>

# 4. veredicto y cobertura
make run-manifest TARGET=<nombre>
make gate         TARGET=<nombre>    # sale != 0 si se incumplen los umbrales

# 5. sin residuos
make down TARGET=<nombre>
```

Artefactos de esta corrida en `reports/antiplagio/`: `gitleaks.sarif`, `trivy/trivy-fs.sarif`,
`trivy/trivy-config.sarif`, `semgrep/semgrep.sarif`, `sbom/`, `playwright/results.json`, `RUN.md`.

---

# Anexo A — Hallazgos sobre Antiplagio detectados en la corrida

No son el objeto de este informe (requieren su propio informe técnico), pero constituyen la prueba
de que el laboratorio funciona sobre este proyecto. **Sin triar salvo donde se indica.**

| # | Hallazgo | Evidencia | Sev. estimada |
|---|---|---|---|
| A1 | 165 secretos recuperables de la historia git: `.env` versionados en `antiplagio/api_antiplagio/`, `antiplagio_web_backend/docker_config/`, `antiplagio/helper/`; `.env.example` con credenciales reales; además `.venv/` completo y registros de `tmux` en el árbol | `reports/antiplagio/gitleaks.sarif` | 🔴 Crítico |
| A2 | 90 hallazgos de dependencias (1 crítico, 31 altos): `nltk 3.9.1` (CVE-2025-14009), `PyJWT 2.3.0` (CVE-2022-29217, confusión de algoritmos), `pillow 11.3.0`, `urllib3 2.5.0`, `pypdf 5.9.0` | `reports/antiplagio/trivy/trivy-fs.sarif` | 🟠 Alto |
| A3 | `/api/process/status` **queda sin autenticación** si `PROCESS_STATUS_SECRET` está vacío. Comprobado en vivo: con la variable vacía la petición se procesa (400 desde la capa de datos); configurada, responde 401 | `api_antiplagio/main.py:47`; contraste ejecutado en el laboratorio | 🟠 Alto |
| A4 | La comprobación del secreto ocurre **después** de la validación del cuerpo, de modo que un no autenticado distingue `422` de `401` y mapea el esquema esperado | `api_antiplagio/main.py:111-118` | 🟡 Medio |
| A5 | `/openapi.json` responde 200 (contrato completo de la API) aunque `/docs` esté deshabilitado; y `Access-Control-Allow-Origin: *` en la API | verificado con `curl` | 🟡 Medio |
| A6 | Endpoints que devuelven **errores con HTTP 200**: `get_student_results.php`, `fix_criteria.php`, `release_student.php`, `download_historico.php`. Este último envía cuerpo JSON con `Content-Type: text/html` | ejecutado con sesión de aprendiz | 🟡 Medio |
| A7 | `get_reports.php` responde **500** con `{"error":"Can't find data record in database."}` — código incorrecto y filtración de estado interno | ejecutado con ambos roles | 🟡 Medio |
| A8 | `analyzer_plagiarism/Dockerfile`: se ejecuta como **root** (las líneas de usuario no root están comentadas) y `apt-get install` sin `--no-install-recommends` | `trivy-config.sarif` (DS-0002, DS-0029) | 🟠 Alto |
| A9 | `docker_config/docker-compose.yml`: Zookeeper con `ALLOW_ANONYMOUS_LOGIN=yes` y Kafka con `ALLOW_PLAINTEXT_LISTENER=yes`, sobre imágenes `bitnamilegacy` sin mantenimiento. **Ninguna herramienta del laboratorio lo reporta** (M12) | lectura del archivo | 🟠 Alto |
| A10 | Falta `Content-Security-Policy` y `X-Content-Type-Options: nosniff`. Confirmado por dos vías independientes | `lib/specs/security-headers.spec.ts` y ZAP | 🟡 Medio |
| A12 | ZAP: 57 alertas, **56 sobre la superficie de Moodle y 1 sobre la API**. Las diez de mayor volumen (`User Controllable HTML Element Attribute`, `Absence of Anti-CSRF Tokens`, `Sub Resource Integrity`, `Cross-Domain JavaScript`) corresponden a páginas del **núcleo de Moodle**, no al plugin. **Atribuir antes de reportar**: sin separar núcleo de plugin, el informe carga al equipo de Antiplagio con deuda ajena | `reports/antiplagio/zap/zap-report.html` | 🟡 Medio |
| A11 | Autorización del plugin: **INCONCLUSA**. Ver M4 — requiere escenario sembrado antes de emitir juicio | `reports/antiplagio/playwright/results.json` | — |

*Fin del informe técnico. El resumen ejecutivo, si se requiere, va en formato institucional SENA
(PDF) aparte; este documento está dirigido a quien implementa los cambios.*
