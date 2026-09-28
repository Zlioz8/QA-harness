# Bitácora del laboratorio — defectos del instrumento

> Documento **interno**. No va al informe del proyecto: los defectos del laboratorio no son
> accionables por el equipo auditado. Se registran con el mismo rigor que un hallazgo porque una
> medición vale lo que valga su instrumento.

---

## L-R2-01 · ZAP muere por OOM y el pipeline recicla el informe de la ronda anterior

**Gravedad: CRÍTICA.** Es el modo de fallo que este laboratorio existe para impedir.

**Qué pasó.** Con `ZAP_MEM` en su valor por defecto (2g), `make dast` sobre
`anuncios_de_plataforma` murió con `Error 137` (SIGKILL) a mitad del `activeScan`. A pesar de eso
la corrida terminó imprimiendo:

```
zap: 122 findings (21 rules) -> reports/anuncios_de_plataforma/zap/zap.sarif
```

Ese `zap.sarif` llevaba fecha de hoy. Los 122 hallazgos venían de `zap-report.json` **del 29 de
julio**, de la ronda 1, medido contra el Moodle efímero en `http://localhost:8083`. Comprobado:
las 122 ubicaciones del SARIF apuntaban a `http://localhost:8083`, no al blanco de esta ronda.

**Por qué es grave.** El gate cuenta lo que haya en `zap.sarif`. Sin mirar la procedencia, esta
ronda habría reportado 122 alertas de **otro sistema** como cobertura propia. Es peor que un
informe vacío: es un informe lleno de datos ajenos con fecha de hoy.

**Cómo se detectó.** No por el código de salida (`make` imprimió `Error 137 (no tiene efecto)` y
el objetivo continuó), sino al comparar la fecha de `zap-report.json` con la de `zap.sarif`, y
después al mirar qué host aparecía en las ubicaciones.

**Arreglo aplicado en el perfil, no en el núcleo.** `ZAP_MEM=8g` en
`targets/anuncios_de_plataforma/target.env`, con la misma justificación medida que ya llevaba
`adi`: el contenedor levanta un Firefox además de la JVM y lo que se agota es el cgroup entero.

**Arreglo pendiente en el núcleo.** El conversor a SARIF debería negarse a producir un artefacto
cuando el informe de origen es más antiguo que el arranque de la corrida, igual que
`tools/secrets.sh` se niega a escribir un `gitleaks.sarif` vacío. Hoy la única defensa es
`MAX_ARTIFACT_AGE_H` en el gate, que no cubre este caso porque el SARIF sí es reciente: lo viejo
es su contenido.

---

## L-R2-02 · `DEPLOY_BRANCHES` declarado en el perfil se ignoraba en silencio

**Qué pasó.** `tools/ingest-deploy.sh` hacía `BRANCHES="${DEPLOY_BRANCHES:-dev dev2}"`, leyendo la
variable de **shell**. Pero el perfil se lee con `envget`, que lee el fichero: la variable de
entorno nunca se rellenaba desde `target.env`, así que declararla ahí no tenía efecto.

**Por qué no se había notado.** El único perfil que la declaraba (`adi`) le puso exactamente el
valor por defecto. En `anuncios_de_plataforma` el remoto no tiene `dev` ni `dev2`, así que la
búsqueda fallaba y la ausencia del documento **parecía del equipo** cuando era del laboratorio.

**Arreglo.** `BRANCHES="${DEPLOY_BRANCHES:-$(envget DEPLOY_BRANCHES)}"` con el valor por defecto
detrás. Verificado sin regresión sobre `adi` (sigue encontrando `origin/dev`, 2 hallazgos, 1
crítico).

---

## L-R2-03 · El contraste del contrato asumía el documento en la raíz

**Qué pasó.** `ingest-deploy.sh` buscaba `DEPLOY.md` en la raíz del repositorio. Este proyecto
tiene **dos componentes desplegables** (`slider/` y `slider_form/`) y el equipo entregó el
documento en `slider_form/DEPLOY.md`. Resultado: un hallazgo `CRITICO` — «el equipo no ha
entregado el documento de despliegue» — sobre un equipo que lo había entregado.

**Arreglo.** Variable `DEPLOY_DOC` en el perfil, por defecto `DEPLOY.md`.

---

## L-R2-04 · La heurística de citas castigaba a los documentos buenos

**Qué pasó.** El contraste marca como ALTO todo fichero citado entre comillas invertidas en el
`DEPLOY.md` que no exista en el repositorio. Sobre este proyecto produjo **cinco hallazgos ALTO
falsos**, y los cinco por ser un documento minucioso:

| Citado | Qué es en realidad |
|---|---|
| `admin/cli/checks.php` | script CLI de **Moodle core** |
| `excellib.class.php` | librería de **Moodle core** bajo `$CFG->libdir` |
| `apache2.conf` | configuración del **sistema** |
| `postgresql.conf` | configuración del **motor de base de datos** |
| `pom.xml` | aparece en una lista de tecnologías que el proyecto **NO usa** |

Más un sexto: se imputaba «No hay `.env.example`» a un plugin de Moodle cuyo §6 declara con
evidencia (`grep`) que no usa variables de entorno.

**Por qué importa más de lo que parece.** El incentivo estaba invertido: **cuanto mejor
documentaba un equipo su despliegue, más defectos falsos se le imputaban.** Y un revisor que ve
cinco acusaciones falsas deja de leer la sección entera — que es donde están los hallazgos reales.

**Arreglo.** Tres cambios en `tools/ingest-deploy.sh`:
1. Lista de exclusión para artefactos que nunca son del repositorio (`*.conf`, `admin/*`,
   `lib/*`, `*.class.php`, `config.php`).
2. La detección de «ausencia declarada» mira 2 líneas de contexto, no solo la de la cita: las
   enumeraciones envuelven y la frase que declara la ausencia queda en la línea anterior.
3. Vocabulario ampliado: `ausencias?`, `sin resultados`, `inexistentes?`, `no aplica`.

Resultado: de 7 hallazgos a 1, y el que queda (sin integración continua) es real y lo confirma el
propio documento. Sin regresión sobre `adi`.

---

## L-R2-05 · `HEALTH_PATH` sobre un `try_files` catch-all

**Qué pasó.** El `nginx` de esta plataforma sirve la portada institucional para **cualquier** ruta
inexistente bajo `/zajuna`. `tools/require-live.sh` ya detecta el catch-all comparando contra una
ruta inventada, y aquí **funcionó** (el login y la portada tienen cuerpos distintos, así que la
sonda sí distinguía).

**Anotado igualmente** porque tuvo un segundo efecto, este sí sobre la interpretación: varias
rutas devuelven `200` sin que el fichero exista. Una comprobación por código de estado —incluida
la que el propio `DEPLOY.md` §10.1 propone (`esperado: 404`)— produce falsos positivos de
exposición. Todo hallazgo de fichero servible de esta ronda se verificó leyendo el **cuerpo**.

**Mitigación aplicada:** `HEALTH_EXPECT=logintoken` en `target.env.local`.

---

## L-R2-06 · Un `rc=0` que venía del `tail`, no del comando

**Qué pasó.** `sudo -u postgres pg_dump -f <ruta bajo /home/zlioz>` falló con «Permiso denegado»
—el usuario `postgres` no puede escribir ahí— y la tubería reportó `rc=0` porque el código de
salida era el del `tail` final. El respaldo no existía y el proceso parecía haber terminado bien.

**Se detectó** al comprobar el fichero, no al mirar el código de salida. Es el mismo patrón que
L-R2-01: una operación que *parece* haber ocurrido.

**Recordatorio de método:** después de cualquier paso que produzca un artefacto, comprobar el
artefacto — tamaño, fecha y contenido — y no el código de salida.

---

## L-R2-07 · Mi guion de carga inventó un 19,63% de error que no existía

**Gravedad: ALTA.** No por el daño causado —se detectó antes del informe— sino porque es
exactamente el error que METODOLOGIA §4 pone como ejemplo, cometido por quien lo había leído.

**Qué pasó.** La primera corrida de `make perf` terminó con:

```
✗ 'rate<0.01' rate=19.63%
http_req_failed: 19.63%  218 out of 1110
```

Un 19,63% de error bajo carga se lee como «sistema inestable». El desglose por endpoint decía
otra cosa:

```
✓ login · ✓ index.php · ✓ menu.php · ✓ show_order.php · ✓ saved_filters
✗ /local/slider_form/table_logs.php   →  0% — ✓ 0 / ✗ 218
```

Cuatro pantallas perfectas y **una fallando el 100%**. Idéntico al caso de ADI que la
metodología cita.

**La causa era mía.** `table_logs.php:27-28` exige DOS parámetros obligatorios:

```php
$asunto    = required_param('asunto',     PARAM_TEXT);
$createdAt = required_param('created_at', PARAM_RAW);
```

`k6/smoke.js` llamaba a la ruta **sin ninguno de los dos**, y `authz-matrix.json` pasaba solo
`asunto`. Moodle respondía `404 · «Un parámetro necesario (created_at) faltaba»`.

**Y el error de mi guion enmascaraba el defecto real.** Corregidos ambos parámetros, el endpoint
**sigue fallando**, pero con otro error completamente distinto:

```
SQLSTATE[42703]: Undefined column: no existe la columna «estado»
```

es decir, el hallazgo §3.3. Mi 404 tapaba el 42703. Si hubiera «arreglado» el ruido subiendo el
umbral de error, habría enterrado el hallazgo de verdad.

**La segunda víctima, más peligrosa.** `authz-matrix.json` tenía el mismo defecto, y el motor de
la matriz cuenta `404` como DENEGACIÓN. `table_logs.php` habría figurado como «acceso denegado
correctamente» para el rol de privilegio ALTO — una afirmación falsa sobre la dimensión que este
laboratorio existe para medir. La ironía es que la nota de esa misma regla ya advertía del riesgo
(«sin `asunto`, Moodle responde 404 y la matriz lo leería como denegación») y aun así se le
escapó el segundo parámetro.

**Corrección aplicada.**
- `k6/smoke.js`: se retira `table_logs.php` del bucle de carga, con la razón escrita en el propio
  archivo. Vuelve cuando §3.3 esté corregido; mantenerlo garantizaría incumplir el umbral por una
  causa ya conocida y haría inútil la cifra agregada.
- `playwright/authz-matrix.json`: la regla pasa ahora `asunto` **y** `created_at`.

**Resultado tras la corrección:** `0.00% 0 out of 936`, p95 = 73 ms, 1608 comprobaciones todas
correctas.

**Lección para el método.** «Comprueba si el fallo es del fixture, del perfil o del comando antes
de atribuírselo al proyecto» no basta como intención: hay que comprobarlo **endpoint por
endpoint**, porque un agregado con un solo culpable al 100% es indistinguible de una degradación
general. La señal que lo delató fue `0% — ✓ 0 / ✗ 218`: un fallo del sistema bajo carga casi
nunca es exactamente 0%.

---

## L-R2-08 · La matriz automatizada da 404 donde curl da 200: artefacto del contenedor, no del proyecto

**Gravedad: MEDIA.** No corrompió el informe —se contrastó contra curl antes de creer nada— pero
un operador con menos cuidado habría reportado 14 fallos de autorización inexistentes.

**Qué pasó.** `make e2e` terminó con 14 fallos sobre 66 pruebas. Al desglosarlos:

- **7× «legitimate access must not be blocked»** en `authz-matrix.spec.ts`, para el rol ALTO en
  las páginas del plugin. Sonaba a que el privilegio alto no accedía.
- 3× de mi propio spec (`sesskeyOf('A')` en vez de `sesskeyOf(ctx)`; expectativas de rechazo que
  no contemplaban 404/415). Corregidos.
- Varios de specs GENÉRICOS que no encajan con un plugin de Moodle (main-thread-budget midiendo
  el peso de las imágenes de la landing, security-headers exigiendo CSP que pone Infra).

**La comprobación que lo aclaró.** Un test de diagnóstico dentro del contenedor imprimió:

```
DIAG index.php status= 404
DIAG /my/     status= 200
DIAG cookies= MoodleSessionzajuna@nginx.zajuna.com, MOODLEID1_zajuna@..., PHPSESSID@...
```

La sesión estaba **viva** (`/my/`=200, cookie de Moodle presente): el login del adaptador
`moodle-session` funciona. Pero `index.php` devolvía 404 con esa misma sesión válida.

**Verdad de referencia (curl, mismas cuentas que el navegador):**

| Recurso | ALTO (manager) | BAJO (student) |
|---|---|---|
| index / menu / segmented / show_order / manage_images | 200 + contenido real | 303→login / 403 |

Es decir: **la autorización del plugin es correcta y no tiene ningún bypass.** El 404 del
contenedor es un artefacto de cómo Playwright resuelve `maxRedirects:0` sobre estas rutas, no un
comportamiento del proyecto. La prueba definitiva: la misma secuencia (login + `--max-redirs 0`)
da 200 desde curl en el host y 404 desde `request.get` en el contenedor.

**Por qué el `auth-check` no lo detectó.** `auth-check.spec.ts` valida la sesión con `ctx.get('/')`
—la raíz de la plataforma—, que responde 200 con o sin sesión. Pasa aunque una página que SÍ
exige sesión fallara. Es un punto ciego del propio chequeo previo.

**Decisión.** La dimensión de autorización se juzga por la medición directa (curl + navegador),
que es inequívoca, y NO por el conteo de la suite automatizada en este entorno. El artefacto
`playwright/results.json` de esta corrida se marca como NO CONCLUYENTE en RUN.md: la herramienta
corrió pero su veredicto sobre las rutas del plugin no es fiable aquí.

**Pendiente de núcleo.** (a) `auth-check` debería validar contra una ruta que EXIJA sesión, no la
raíz. (b) Investigar por qué `APIRequestContext.get(maxRedirects:0)` devuelve 404 donde curl
devuelve 200 sobre el mismo endpoint autenticado — probablemente Playwright no reenvía la cookie
en la petición sin redirecciones, o Moodle responde distinto a su User-Agent.

---

## L-R3-01 · Las dimensiones de código analizaban el escritorio, no el repositorio

**Gravedad: ALTA.** No falsea un hallazgo; falsea la **cobertura**, que es lo que da sentido a
los hallazgos.

**Qué pasó.** El contrato del perfil (`targets/_template/target.env`) dice, y decía ya, que un
proyecto de varios repositorios apunte `SRC_PATH` al **directorio padre** porque «el laboratorio
descubre los repos hijos solo». Eso era cierto **solo para `tools/secrets.sh`**. Las demás
dimensiones `needs: source` —semgrep, `trivy fs`, `trivy config`, Syft, Qodana— montaban
`${SRC_PATH}` entero y analizaban lo que hubiera dentro.

Y un directorio padre, en la máquina de quien audita, es una carpeta de trabajo:

```
ANALITICA NOTIFICACIONES/
  analitica_notificaciones/            <- lo auditado
  MANUAL DE INSTALACION ....docx(.pdf) <- 1,7 MB de ofimática
  zv5-menu.png                         <- una captura de pantalla
  .playwright-mcp/                     <- 67 archivos: 40 .yml, 25 .log, un .md
                                          y 001-saved-filters.sql — una migración
                                          de OTRO proyecto (slider_form)
```

**Medido, no supuesto.** Mismo perfil, misma configuración de semgrep, dos montajes:

| Montaje | Objetivos escaneados | Hallazgos |
|---|---|---|
| el directorio padre (antes) | **200** | 4 |
| el repositorio (después) | **93** | 4 |

Los cuatro hallazgos son los mismos, y conviene decirlo así: en este proyecto el ruido **no**
produjo hallazgos falsos. Lo que sí hacía era declarar como cobertura 107 archivos que no son de
este proyecto, uno de ellos una migración de base de datos de un equipo distinto. Un informe que
dice «se analizaron 200 archivos» cuando 107 son un manual de Word y los logs de otra sesión no
miente en sus hallazgos: miente en lo que afirma haber mirado. Y la próxima vez el reparto entre
esos 107 y los hallazgos puede no ser tan afortunado.

Efecto secundario medido y bueno: al montar un repositorio de verdad, semgrep se autolimita a los
archivos versionados («Scan was limited to files tracked by git»). Sobre el padre, que no es
repositorio, no podía.

**Arreglo, en el núcleo.**

- `tools/lib-repos.sh` (nuevo): `discover_repos`, `src_roots`, `non_repo_entries`. **Una** regla,
  donde había cuatro copias a mano (`secrets.sh`, `run-manifest.sh`, `doctor.sh`, `mobile-scan.sh`).
- `lib/dimensions.yml`: campo `per_repo` en `trivy-fs`, `trivy-config`, `sbom`, `semgrep`, `qodana`.
- `tools/run-dimension.sh`: para esas dimensiones, monta cada repositorio descubierto (la variable
  de entorno gana sobre `--env-file` en la interpolación de compose, así que no hubo que tocar
  ningún servicio). Con varios repositorios, un pase por repositorio y fusión al final.
- `tools/sarif-merge.py` (nuevo): el fusionador que estaba incrustado en `secrets.sh`, con su
  regla dura intacta — si ningún pase produjo resultados legibles, NO se escribe el archivo.
- `tools/run-manifest.sh` y `tools/doctor.sh`: **declaran lo que queda fuera**. Acotar la entrada
  en silencio habría sido el mismo defecto por el otro lado.

**Lo que esto vuelve obsoleto.** `QODANA_SUBDIR` existía exactamente para sortear este problema a
mano: nombrar UN sub-repo, dejando el otro sin analizar y sin decirlo. Queda como escotilla vacía
en todos los perfiles.

---

## L-R3-02 · `SRC_PATH=MOVIL`: una ruta relativa que compose convierte en un volumen vacío

**Gravedad: ALTA.** Falla sin dar error, que es la única forma de fallo que importa aquí.

**Qué pasó.** `targets/movil/target.env:13` decía `SRC_PATH=MOVIL`, sin ruta. Dos consecuencias,
ninguna visible:

1. Para las herramientas de `tools/`, `[ -d "MOVIL" ]` desde el laboratorio es **falso**;
   `tools/siguiente.py` marcaba el paso «Tener el código en esta máquina» como no hecho.
2. Para compose, `MOVIL:/repo:ro` no es una ruta: es un **volumen nombrado**. Docker lo crea
   vacío y lo monta. La herramienta analiza la nada y sale con **código 0**.

Es el perfil que se citaba como ejemplo de «así está resuelto lo del directorio padre». No estaba
resuelto: no resolvía a nada.

**Arreglo.** Ruta absoluta en el perfil, y la advertencia escrita en
`targets/_template/target.env` junto a la propia clave, que es donde alguien la va a leer.

**Lo que apareció al arreglarlo, y es lo interesante.** Con la ruta corregida, `MOVIL/` existe
pero **no contiene ningún checkout**: dos `.docx`, dos `.md`, un `.apk` y ningún `.git`. El
proyecto no tiene código en esta máquina. Sin salvaguarda, `make static TARGET=movil` habría
producido hallazgos sobre un documento de Word y el informe los habría llamado calidad del
código. `tools/run-dimension.sh` avisa ahora en voz alta cuando no hay repositorio bajo
`SRC_PATH`. No se niega —un árbol de código sin git es auditable— pero no puede pasar
desapercibido.

---

## L-R3-03 · `stamp.sh` sellaba `commit: desconocido` en todo perfil multi-repo

**Gravedad: ALTA.** Desactivaba en silencio la maquinaria de procedencia entera.

**Qué pasó.** `tools/stamp.sh` hacía `git -C "$SRC_PATH" rev-parse --short HEAD 2>/dev/null ||
echo ''`. Sobre un directorio padre —que es lo que el contrato manda para multi-repo— `rev-parse`
falla, el `|| echo ''` lo tapaba, y **toda** dimensión `needs: source` quedaba sellada
`commit: desconocido`.

**Por qué importa.** Los sellos existen para que un veredicto no pueda sumar evidencia de dos
sistemas distintos (ver `L-R2-01`, donde 122 alertas de otro host se contaron como propias). Un
sello que no sabe contra qué midió no puede invalidar nada: la defensa seguía ahí, escribiendo
archivos, sin defender.

**Arreglo.** El commit se lee de los repositorios descubiertos. Con varios, se nombran todos
(`frontend=abc1234 backend=def5678+sucio`): un identificador solo sirve si identifica lo medido,
y un hash único cuando se auditaron dos árboles es una media verdad que se lee como entera.

---

## L-R3-04 · `detect.sh` tenía su propio lector de `SRC_PATH`, ciego a `target.env.local`

**Gravedad: MEDIA.**

**Qué pasó.** `tools/detect.sh` leía el perfil con un `sed` propio en vez de `tools/lib-env.sh`, y
ese `sed` no aplica el override de `target.env.local` — justo el archivo donde el contrato dice
que viven los valores del despliegue real. Un `SRC_PATH` declarado ahí era invisible aquí, y
`detect` respondía «SRC_PATH not a directory» sobre un perfil correctamente configurado.

Es literalmente la misma deriva documentada en la cabecera de `tools/secrets.sh`, que costó un
«0 secretos» sobre un repositorio con un token de SonarQube commiteado. La sexta copia de un
parser encuentra la misma piedra que las cinco anteriores.

**Arreglo.** `detect.sh` usa `envget`, y censa los repositorios en vez del padre.

---

## L-R3-05 · `mobile-scan.sh`: la comprobación de frescura del APK nunca corría en un repo único

**Gravedad: MEDIA.** Un aviso que no avisa.

**Qué pasó.** La cuarta copia de la regla de descubrimiento, y la única que estaba mal escrita:

```bash
for repo in "$SRC_PATH"/*/; do [ -d "$repo.git" ] || continue
```

Solo mira **subdirectorios**. En un proyecto móvil de un solo repositorio (`SRC_PATH` siendo el
checkout), el bucle no itera nunca y la comprobación de «el APK es más viejo que el código que
dice representar» no se ejecutaba jamás. En silencio.

Es el argumento de `tools/lib-env.sh` con otro traje: cuatro copias de una decisión son cuatro
oportunidades de divergir, y aquí una ya había divergido sin que nada lo dijera.

**Arreglo.** Usa `src_roots` de `tools/lib-repos.sh`.

---

## L-R3-06 · El contraste del contrato acusaba de no traer `login/token.php`

**Gravedad: MEDIA.** Acusación falsa y comprobable — la peor clase.

**Qué pasó.** `make ingest-deploy TARGET=analitica_notificaciones` emitió un **ALTO**:
«DEPLOY.md cita `login/token.php` como si estuviera, pero no está en el repositorio».

`login/token.php` es el endpoint del **núcleo de Moodle** contra el que la aplicación hace POST
para obtener el wstoken (`api/moodle_auth.py`: `f"{settings.moodle_url}/login/token.php"`). No es
un archivo de este repositorio y no puede serlo.

**Es la cuarta vez que esta heurística castiga a un documento bueno** — ya lo hizo cinco veces
con `anuncios_de_plataforma` (`apache2.conf`, `excellib.class.php`…). La regla de fondo que
faltaba: una cita entre comillas puede ser una **ruta HTTP de un sistema externo**, no una
referencia a un archivo del árbol.

**Arreglo.** Exclusión de `login/*` y `webservice/*`, los directorios de entrada de Moodle, contra
el que se integra media fábrica. Comprobado que no altera el resultado de `adi` (su DEPLOY.md no
cita nada bajo esas rutas). Tras el arreglo: 4 hallazgos → 3, y los 3 son ciertos.

---

## L-R3-07 · Dimensión nueva: flujos de usuario en navegador conducidos con MCP

**No es un defecto — es una capacidad que faltaba.** Varias familias de fallo solo aparecen
recorriendo la interfaz REAL con un navegador, y ninguna dimensión automática las veía.

**Qué lo motivó, medido en `analitica_notificaciones`.** Recorriendo el flujo con el servidor MCP
(Playwright) aparecieron tres hallazgos que ZAP, k6 y Playwright-API no dieron:
- la **vista previa** del reporte más pesado devuelve **502 crudo** en producción (no el 503
  documentado): ZAP va sin sesión y no dispara el preview;
- los reportes dependen de un esquema **`midb`** y de tablas custom **no documentadas**: solo se ve
  al generar de verdad contra un Moodle limpio;
- el **JWT** de sesión queda en **localStorage** (robable con XSS): solo visible inspeccionando el
  navegador tras el SSO.

**Qué se añadió, siguiendo el patrón de `device` (conducida, no automatizable desde make):**
- `lib/dimensions.yml`: dimensión `mcp-journey` (kind manual, class browser, needs target-network,
  live, triage), con `script: mcp/flows.md` (script_kind `flujos`, nuevo) y `artifact: mcp/journeys.md`.
- `tools/mcp-journey.sh` (conduce y exige artefacto) y `tools/require-mcp.sh` (la CONTEMPLA en
  `make live`: avisa si los flujos no se recorrieron, para que su ausencia no sea «sin hallazgos»).
- `tools/guion.py`: medidor del `script_kind: flujos` (cuenta flujos del markdown).
- `tools/hallazgos.py`: un hallazgo SIN clave de triaje (o de dimensión conducida) ya no se
  auto-cierra — el registro sabía guardar solo lo que una herramienta re-emite; ahora también
  guarda el juicio humano y el de una dimensión conducida.
- README.md / MANUAL_USO_QA.md: tabla de dimensiones regenerada (doc-check verde).

El guion de este proyecto (`targets/analitica_notificaciones/mcp/flows.md`) lista 8 flujos
(SSO por el plugin, denegación por rol, cabeceras, catch-all, vista previa, generar/descargar,
propiedad IDOR, programados) y la evidencia de R1 está en `reports/.../mcp/journeys.md`.

---

## L-R4-01 · `grep -q` sobre una tubería con `pipefail`: el contraste dijo «sin CI» a un repositorio que sí la tiene

**Síntoma.** `make ingest-deploy TARGET=reportes_de_cursos` emitió `D3 MEDIO — Sin integración
continua`. El repositorio trae `.github/workflows/ci.yml` (11 KB) y `.github/workflows/gate.yml`,
presentes en el commit auditado `ef3493bd`.

**Causa, medida y no deducida.** `tools/ingest-deploy.sh:24` fija `set -uo pipefail`, y la
comprobación era `has .gitlab-ci.yml || tree | grep -q '^\.github/workflows/' || has Jenkinsfile`.
`grep -q` cierra la tubería en la primera coincidencia; `git ls-tree` —que aún estaba escribiendo
1.091 rutas— muere con SIGPIPE; `pipefail` propaga 141 y la condición se evalúa como falsa:

```
$ bash -c 'set -o pipefail; git ls-tree -r --name-only dev | grep -q "^\.github/workflows/"; echo $?'
141
$ bash -c 'set +o pipefail; git ls-tree -r --name-only dev | grep -q "^\.github/workflows/"; echo $?'
0
```

**Por qué importa más de lo que parece.** El fallo depende del TAMAÑO del árbol: cuanto más grande
el repositorio, más seguro es que git siga escribiendo cuando grep cierra, y más seguro el falso
positivo. Es decir, acusa preferentemente a los proyectos grandes. Y produce **la peor clase de
hallazgo**: una acusación falsa y comprobable en treinta segundos por quien la recibe.

**Alcance sobre lo ya entregado.** Comprobado repo por repo: `adi` (674 archivos),
`analitica_notificaciones` (134) y `anuncios_de_plataforma` **no tienen** ningún fichero de CI, así
que el hallazgo que se les entregó era correcto — *por la razón equivocada*. No hay que rectificar
ningún informe; sí hay que saber que esos tres «Sin CI» no los decidió la comprobación, sino el bug.

**Arreglo.** La salida del árbol se materializa antes de filtrarla (`ARBOL_CI="$(tree)"` y
`grep <<< "$ARBOL_CI"`). De paso se reconocen `.gitea/workflows/` —la fábrica se aloja en Gitea, y
acusar de «sin CI» a quien usa las acciones de su propio servidor sería el mismo error— y
`.circleci/`.

## L-R4-02 · El contraste solo sabía de `package-lock.json`: `bun.lock` no contaba como lock

**Síntoma.** `D1 ALTO — vue-app/package.json sin su package-lock.json` sobre un proyecto que
versiona `vue-app/bun.lock` (103 KB) y cuyo contenedor de front arranca con
`bun install --frozen-lockfile`: el lock no solo existe, es **obligatorio** en su despliegue.

**Causa.** `check_manifest package.json package-lock.json` daba por hecho que Node = npm.

**Arreglo.** El segundo argumento pasa a ser la lista de locks ACEPTABLES separados por `|`
(`package-lock.json|yarn.lock|pnpm-lock.yaml|bun.lock|bun.lockb|npm-shrinkwrap.json`); basta con
que exista uno, y el texto del hallazgo los nombra todos para que se vea qué se buscó.

## L-R4-03 · `php.ini` citado para decir que NO se toca, imputado como archivo prometido

**Síntoma.** `D2 ALTO — DEPLOY.md cita php.ini como si estuviera, pero no está en el repositorio`.
La línea citada es `DEPLOY.md:134`: «Se pone en `conf.d`, **no editando** `php.ini`».

**Causa.** La lista de exclusiones de la heurística de citas (L-R2-04, L-R3-06) tenía `*.conf`
pero no `*.ini`. Un `php.ini` es del HOST y jamás es un entregable del repositorio.

**Arreglo.** `*.ini` se excluye igual que `*.conf`.

**Resultado conjunto de las tres correcciones:** el contraste de `reportes_de_cursos` pasó de
**4 hallazgos (1 crítico, 2 altos, 1 medio)** a **1**, y el que queda —`.env.production`
versionado— es un hecho comprobable. Su severidad, en cambio, la decide el triaje: el archivo
contiene una sola variable, `VITE_API_BASE=/zea-api`, y ningún secreto.

## L-R4-04 · `spectral:oas` no entiende OpenAPI 3.2: 14 errores estructurales falsos

**Síntoma.** `make api-lint TARGET=reportes_de_cursos` dio 18 hallazgos; 14 son `oas3-schema`
sobre construcciones perfectamente válidas: `openapi` «debe casar `^3\.0\.\d`», `query` «no se
espera aquí», `jsonSchemaDialect`, `propertyNames`, `identifier`. `docs/api/openapi.json` declara
`openapi: 3.2.0` y usa el método HTTP `QUERY` y `propertyNames`, todo legal en 3.1/3.2.

**Causa.** El ruleset `spectral:oas` (base del guion) valida contra el esquema de OpenAPI **3.0**;
Spectral no soporta 3.1/3.2 en su validación estructural. Es una limitación de la herramienta, no
un defecto del contrato.

**Qué NO se hizo, y por qué.** No se degrada el documento a 3.0 para «acallar» la herramienta:
eso mediría un contrato que no es el del proyecto. Las reglas PROPIAS del guion
(`targets/reportes_de_cursos/spectral.yaml`) sí operan bien sobre 3.2 y son la señal real —
`zea-url-de-produccion-real` y `zea-solo-salud-es-publica` dispararon y confirman dos
incongruencias ya vistas a mano. En el triaje, los 14 `oas3-schema` se cierran como ruido de
herramienta (limitación de versión) y se conserva el artefacto. Si en el futuro varios proyectos
publican 3.2, toca evaluar un validador que lo soporte (p. ej. Redocly/vacuum) como motor de
api-lint; por ahora se declara aquí y en el informe.

## Nota R4 · Validación en vivo de reportes_de_cursos (no es defecto del lab)

Los hallazgos del informe R1 se validaron recorriendo el sistema, no solo leyendo artefactos:
- `/metrics` público y `/api-zea`→CMS: confirmados por curl contra el servidor.
- Control de acceso por curso: confirmado firmando un JWT de curso con la clave REAL del
  despliegue local (`/etc/block_zajuna_early_alert/jwt_private_key.pem`) — curso propio 200, otro
  curso 403 «forbidden: course mismatch», sin token 401. El mecanismo funciona.
- El navegador MCP contra el servidor reveló C9 (el login del tablero rebota a caplms.sena.edu.co,
  otro dominio) y motivó C10 (la API no valida el `typ` del JWT). Ambos al informe del equipo.
La matriz por rol contra el servidor sigue PENDIENTE: el CMS de caplms resiste automatización y la
sesión de otro dominio no viaja a zajunavideo5. No es limitación del laboratorio sino del
enrutamiento del propio despliegue (C9).

## L-R4-05 · api-fuzz (Schemathesis) no puede medir un despliegue HTTPS autofirmado y 100% autenticado

**Síntoma.** `make api-fuzz TARGET=reportes_de_cursos` → 18 Network Errors, 2276 casos generados y
TODOS omitidos. Artefacto (`schemathesis.xml`) presente pero sin señal.

**Tres causas, todas del instrumento, no del proyecto:**
1. **TLS.** El comando de Schemathesis del compose (`docker-compose.yml`, servicio `api-fuzz`) NO
   pasa `--tls-verify=false`. El despliegue local va detrás del nginx del core, HTTPS con
   certificado del vhost `nginx.zajuna.com`: cada petición muere como Network Error. (A diferencia
   de k6, que sí lee `K6_INSECURE_SKIP_TLS_VERIFY`.)
2. **Base path.** El contrato declara el servidor de producción `/api-zea` (o el bare `/api/v1`);
   el despliegue sirve la API bajo `/zea-api/api/v1`. `--url ${APP_INTERNAL_URL}` no reconcilia esa
   diferencia (que es además el hallazgo C5).
3. **Auth.** La API está 100% detrás de JWT de curso y el comando de api-fuzz no inyecta ninguna
   cabecera `Authorization`: aun con TLS y base correctas, todo sería 401 y no se fuzzearía la
   lógica. El bind loopback del API (`127.0.0.1:39097`) impide además apuntar al Go directo por
   HTTP desde el contenedor bridge.

**Veredicto de la dimensión:** NO CONCLUYENTE, artefacto conservado. El CONTRATO sí está cubierto
por `api-lint` (Spectral), que encontró lo real (C5, `/metrics` público), y la conformidad de la
API se validó a mano (401 sin token, 403 cross-course, 400 por parámetros — todos correctos).

**Mejora de laboratorio pendiente (no de este proyecto):** que el servicio `api-fuzz` acepte
`--tls-verify=false` cuando `K6_INSECURE_SKIP_TLS_VERIFY=true` (o una var propia) y permita inyectar
una cabecera `Authorization` (p. ej. `API_FUZZ_AUTH_HEADER`) para poder fuzzear APIs autenticadas.

## L-R5-01 · `ingest-deploy.sh` era el único consumidor de `SRC_PATH` ciego al multi-repo

**Síntoma.** `make ingest-deploy TARGET=encuestas` respondió `ni SRC_PATH con .git ni REPO_URL en
targets/encuestas/target.env — nada que inspeccionar` y salió con 2, sobre un perfil correctamente
configurado: `SRC_PATH` apuntaba al directorio padre con los dos repositorios clonados dentro, tal
como manda el contrato del perfil.

**Causa.** `tools/lib-repos.sh` se anuncia como «el ÚNICO descubridor de repositorios bajo
SRC_PATH» y lo consumen once herramientas. `ingest-deploy.sh` no era una de ellas: tenía escrito a
mano `if [ -n "$SRC" ] && [ -d "$SRC/.git" ]`. Y el propio contrato dice que en un proyecto de
varios repositorios `SRC_PATH` apunta al **directorio padre** — que por definición **no** es un
repositorio. Las dos mitades del laboratorio leían el mismo campo con reglas distintas.

**La mitad silenciosa, que es la grave.** El fallo ruidoso (salir con 2) solo ocurre si el perfil
no declara `REPO_URL`. Si lo declara, el script cae a la rama del clon bare, clona **ese** repo y
emite un cotejo de despliegue perfectamente formado **sobre uno solo de los repositorios, sin
decirlo en ninguna parte**. Es lo que pasó con `reportes_de_cursos`:
`reports/reportes_de_cursos/deploy-contract.md` dice «origen:
`.../Analitica_cursos.git`» y nada en el documento advierte de que `reportes_de_curso` —el segundo
repositorio del proyecto, el del dashboard— no se cotejó. Un cotejo parcial que se lee como total
es el modo de fallo que este laboratorio existe para no cometer.

**Arreglo.** Dos cambios en `tools/ingest-deploy.sh`:
1. Descubre con `src_roots` (lib-repos.sh) y **elige el repositorio que contiene el documento**,
   en vez de exigir que `SRC_PATH` sea un repositorio. Si ninguno lo trae, coteja el primero de
   todos modos, para que el CRÍTICO «no hay documento» se emita con informe en vez de morir sin él.
2. La cabecera del cotejo declara, cuando hay más de un repositorio, **cuál se cotejó y cuáles no**,
   nombrando explícitamente que el contrato de despliegue de los demás NO queda verificado.
   También imprime `documento buscado`, que antes solo salía por consola.

**Alcance sobre lo ya entregado.** `reports/reportes_de_cursos/deploy-contract.md` está incompleto
por esta causa: cubre `Analitica_cursos` y no `reportes_de_curso`. No invalida sus hallazgos (son
reales y sobre el repo que sí se miró), pero su cobertura es menor que la que aparenta. Rehacerlo
es `make ingest-deploy TARGET=reportes_de_cursos` con el arreglo puesto.

## L-R5-02 · Nadie comprueba que el árbol de trabajo esté en la rama que el perfil declara

**Síntoma.** `make detect TARGET=encuestas`, sobre un perfil que declara
`BRANCH=feature/integracion-zajuna` y `DEPLOY_BRANCHES=feature/integracion-zajuna`, censó
`py=1 php=280 js=6 ts=186`, propuso `AUTH_ADAPTER=sanctum` y no vio ningún compose. Tras un
`git checkout feature/integracion-zajuna` en los dos repositorios, el mismo comando censó
`py=0 php=574 js=6 ts=237`, propuso `AUTH_ADAPTER=moodle-session` y encontró tres composes y las
recetas `moodle-plugin` y `postgres`.

**Causa.** Es una asimetría entre las dos mitades del laboratorio, no un error de ninguna:

| | Qué mira |
|---|---|
| `ingest-deploy` | el **commit** de la rama declarada (`git show origin/<rama>:...`) |
| `detect`, `secrets`, `semgrep`, `deps`, `sbom`, `sonar`, `qodana` | el **árbol de trabajo**, sea cual sea la rama en la que esté |

Nada las reconcilia. Un `git clone` deja el checkout en la rama por defecto del remoto, que aquí es
`main` — y `main` es, en `encuestas`, el monorepo de marzo con otra estructura, y en
`encuestas_backend`, literalmente un «Initial commit» con un solo README. El estático habría medido
eso y el informe lo habría presentado como la medida de la rama auditada.

**Por qué es peor que un simple despiste.** No da error, no da aviso, y las cifras que produce son
plausibles: 280 ficheros PHP es una cantidad creíble para este proyecto. La única señal fue que el
adaptador de login propuesto (`sanctum`) no cuadraba con lo que el documento de despliegue describe
(entrada desde Zajuna sin contraseña). Sin esa corazonada, la auditoría entera —secretos,
dependencias, SAST, SBOM— habría corrido sobre la rama equivocada, en silencio y con cobertura
aparentemente completa.

**Arreglo, y el criterio que lo hace útil.** `make doctor` compara ahora, repositorio por
repositorio bajo `src_roots`, la rama del checkout contra **la rama más recientemente actualizada
del remoto** (`for-each-ref --sort=-committerdate`), no contra `BRANCH` del perfil.

El contraste contra el perfil era la idea obvia y es la peor de las dos: `BRANCH` lo escribe la
misma persona que hace el checkout, así que solo comprobaría que el perfil concuerda consigo
mismo. La fecha del último commit es un dato del REMOTO, y por eso puede contradecirte. Y encaja
con cómo trabaja esta fábrica: los equipos viven en ramas `feature/...` y `main` se queda atrás
meses — `analitica_notificaciones` tenía lo entregable en `bd-externa`, `encuestas` lo tiene en
`feature/integracion-zajuna` (2026-08-06) contra un `main` de marzo. La heurística de frescura
acierta en los dos; la de la convención falla en los dos.

Es `warn` y no `bad`: auditar una rama que no es la más fresca es a veces deliberado (una
`release/` estabilizada). Lo que no puede pasar es que ocurra en silencio.

**Mitigación aplicada en esta auditoría.** Los dos checkouts se pusieron en
`feature/integracion-zajuna` ANTES de correr ninguna dimensión estática, y se re-corrió `detect`.

## Nota R5 · Validación en vivo de encuestas contra zajunavideo5 (no es defecto del lab)

Registrado aquí para no perder el método, no porque el laboratorio fallara. Al medir la superficie
pública de `encuestas` en el servidor de prueba del equipo aparecieron tres cosas que exigían
distinguir «fallo del proyecto» de «fallo del guion», que es el trabajo del §4 de METODOLOGIA:

1. **k6 marcó 90 % de error y NO era la app.** La primera corrida (10 VUs) dio `contact-info 200`
   al 16 % pero `contact-info es JSON` al 100 %: la respuesta ERA JSON y NO era 200. Era el
   limitador de tasa (`ratelimit:30` en routes/api.php:123) devolviendo 429 legítimos: 10 VUs
   generan ~360/min contra un tope de 30. Toda la superficie pública está rate-limitada por diseño,
   así que no es cargable sin sesión. El guion se reescribió en dos escenarios: `latencia_base`
   (1 VU, por debajo del tope → mide latencia real, p95 227–347 ms, 100 % éxito) y
   `verifica_ratelimit` (ráfaga → AFIRMA que corta con 429, no con 5xx; 79 % cortado). Un 429 pasó
   de ser un «error» a ser el resultado que se buscaba.

2. **El SSO de tres saltos no se puede automatizar en este entorno, y está BIEN que el adaptador lo
   diga.** El nuevo adaptador `encuestas-sso` (lib/auth) recorre Moodle-form → pase HMAC del plugin
   → token Sanctum. En zajunavideo5 el login web de Moodle rebota a caplms (alternateloginurl), así
   que el paso 1 no completa y el adaptador LANZA con el motivo. `require-auth` abortó la matriz
   autenticada en vez de reportar 20 falsos «denegado». La matriz autenticada queda NO DISPONIBLE
   por bloqueo de entorno; la superficie NO autenticada (9 mecanismos verdes) sí es autoritativa.

3. **Dos hallazgos que las herramientas automáticas no vieron**, solo el recorrido a mano:
   el origen Apache publicado en claro en `:8000` (la API entera sin TLS) y `server_tokens` sin
   apagar (nginx anuncia `nginx/1.24.0 (Ubuntu)`). Ambos van al informe del equipo.

## Nota R5-b · La superficie pública de Encuestas se defendió de TODO lo que se le probó

También para el método: no todo hallazgo es un defecto encontrado. Recorridas a mano las rutas
públicas de `encuestas`, TODAS resistieron: path-traversal en el servido de ficheros → 400/404
(nunca 200 con un fichero del sistema), descarga firmada sin firma → 403, detalle público de una
encuesta inexistente → 404 «Survey not found», y el error del SSO no filtra el motivo del rechazo
(evita el oráculo). El fallback de la SPA a producción recuerda el origen real y fija la vuelta
desde el backend (no desde la URL), cerrando el redirect abierto. Es un frontend maduro; el informe
debe decirlo con el mismo rigor con que señala el puerto 8000.

## Nota R5-c · Despliegue local de encuestas: tres iteraciones del guion ZAP (defectos de MI plan)

Al ejecutar `make dast` sobre encuestas, el plan de ZAP falló tres veces por errores MÍOS, no del
proyecto. Se registran porque cada uno es una forma de que un plan de ZAP mienta:

1. **`fileName: /zap/wrk/urls-publicas.txt`** — el perfil se monta en `/zap/wrk/zap/`, no en
   `/zap/wrk/`. El job `import` no encontraba el fichero y el plan abortaba ANTES del escaneo. Un
   plan que aborta en el import no mide nada, pero el `make` podría leerse como «corrió». Ruta
   corregida a `/zap/wrk/zap/urls-publicas.txt`.
2. **`policy: "encuestas-lectura"`** junto a `policyDefinition` inline — esa clave busca un fichero
   `.policy` con ese nombre y da «Unrecognised active scan policy name», abortando el activeScan.
   La política inline se declara SOLO en `policyDefinition`; se quitó la línea `policy:`.
3. **Regla activa `id: 43` (LFI)** — no existe como escáner activo en `zaproxy/zap-stable`
   («Unrecognised active scan rule ID»). Declarar una regla que el motor no tiene es fingir
   cobertura. Retirada; la 6 (Path Traversal) cubre los dos endpoints de ficheros.
4. **OOM (exit 137)** en el `spiderAjax` con `maxDuration: 5` y el tope por defecto `ZAP_MEM=2g`.
   La máquina tiene 15G libres: se subió `ZAP_MEM=4g` en el perfil y se acotó el AJAX spider a
   2 min (la SPA redirige a Zajuna sin sesión, así que no descubre superficie autenticada de todos
   modos). El tope existe para que la herramienta muera antes que la máquina; con margen, se sube.

Ninguno es un defecto del núcleo del laboratorio: son mi guion de ZAP escrito para este proyecto,
corregido con las cifras/errores reales delante. Se anota como recordatorio de que un plan de ZAP
tiene cuatro formas de no medir nada sin dar error rojo claro.

## Nota R5-d · El despliegue local desde el README-DESPLIEGUE necesitó UN fix (hallazgo del equipo, no del lab)

`docker compose -f deploy/docker-compose.prod.yml up -d --build` levantó el stack pero `migrate`
murió con `Invalid schema name`: el `10-search-path.sql` fija el search_path a `Produc` sin crear
el schema, y las migraciones (no-squashed) no pueden crear la tabla `migrations` en un schema que
no existe. Es un hallazgo del PROYECTO (D1 en COTEJO_DESPLIEGUE.md), no del laboratorio: el manual
está incompleto en su punto más crítico. El fix (una línea, `CREATE SCHEMA IF NOT EXISTS "Produc"`)
se aplicó como insumo del laboratorio y se declaró. Tras él, todas las migraciones completaron y la
API respondió 200 JSON en `/api/contact-info`. La distinción importa: el lab funcionó
correctamente; lo que falló fue el manual del equipo, y eso es exactamente lo que el cotejo mide.

## L-R5-e · El AJAX spider de ZAP sobre una API REST: coste enorme, cobertura cero

**Síntoma.** `make dast TARGET=encuestas` murió TRES veces con exit 137 (SIGKILL por cgroup)
durante el job `spiderAjax`, incluso tras subir `ZAP_MEM` de 2g a 4g.

**Causa, y por qué es un defecto de guion y no del lab.** El `spiderAjax` levanta un Firefox
headless para renderizar una SPA y observar las peticiones que su JavaScript dispara. Yo lo incluí
pensando en la SPA `/encuestados/`. Pero el target efectivo del plan es la **API REST** `/api`
(endpoints JSON): ahí Firefox no descubre absolutamente nada que la lista `urls-publicas.txt` + el
spider normal no traigan ya, y en cambio consume toda la memoria del contenedor. Un coste enorme
por cero cobertura. Además, sobre `/encuestados/` tampoco servía: la SPA redirige a Zajuna sin
sesión, así que Firefox solo veía la home de producción.

**Arreglo.** Se quitó el job `spiderAjax` del plan de este proyecto. La superficie de la SPA se
cubre por la vía correcta —la matriz de Playwright y el recorrido MCP, que sí tienen (o simulan)
sesión— no por un crawler de ZAP. Regla para el futuro: `spiderAjax` solo cuando el target es una
SPA navegable CON sesión; contra una API REST es puro gasto.

**Lección transversal.** Igual que k6 no debe cargar un endpoint rate-limitado (R5-c), ZAP no debe
lanzar un navegador contra una API sin UI. Las dos son la misma idea: elegir el instrumento por lo
que el target ES, no por lo que la plantilla trae encendido.

## L-R6-01 · Dos falsos ALTOS por cita: «no contiene» no era una negación, y un script de `admin/cli/` citado por su basename

**Síntoma.** El primer `make ingest-deploy TARGET=anuncios_del_curso` devolvió **5 hallazgos
(0 críticos · 4 altos · 1 medio)** contra `imagecarousel/DEPLOY.md`. Los cuatro ALTOS decían que
el documento cita `compose.yml`, `docker-compose.yml`, `install_database.php` y
`uninstall_plugins.php` «como si estuvieran, pero no están en el repositorio».

**Los cuatro eran míos.** Comprobado antes de escribir una sola cifra en el informe
(METODOLOGIA §4: si un resultado sorprende, mira primero si el fallo es del fixture, del perfil o
del comando):

- `compose.yml` / `docker-compose.yml` — DEPLOY.md línea 29 los nombra para **negarlos**: «**El
  repositorio no contiene `Dockerfile`, `docker-compose.yml`, `compose.yml`, … Se verificó con una
  búsqueda exhaustiva del árbol completo**». `ABSENCE_RE` reconocía `no hay / no está / no existe /
  no se usa / no trae / no viene` — pero **no `no contiene`**. Un verbo fuera de la alternancia, y
  el precio es acusar al equipo justamente por haber documentado bien su ausencia.
- `install_database.php` / `uninstall_plugins.php` — son scripts del **núcleo de Moodle**
  (verificado: existen en `/var/www/zajuna/admin/cli/`, 6998 y 6348 bytes). DEPLOY.md los invoca
  con su ruta absoluta completa y luego los menciona en prosa por su basename entre comillas
  inversas. El extractor de citas exige que el nombre empiece por alfanumérico, así que la ruta
  con `/` inicial no entra y el caso `admin/*` del `case` no llega a evaluarse: `$cand` es un
  basename pelado. El ALTO resultante dice, literalmente, que a un plugin le falta un fichero de
  Moodle.

**Arreglo (los dos generalizan, no son parches para este proyecto).**
1. `ABSENCE_RE` gana `contien|incluy|posee` en la alternancia de negación.
2. Antes de emitir el ALTO se consulta la evidencia del **propio documento**: si el texto muestra
   ese fichero bajo `admin/cli/`, es del núcleo y no puede vivir en el repositorio de un plugin.
   Se decide con el documento, no con una lista de nombres que habría que ir ampliando.

**Resultado.** De 5 hallazgos a **1**: «Sin integración continua», que es real y se verificó
aparte (`git ls-files` no devuelve nada para `.github|.gitlab-ci|Jenkinsfile|.gitea|workflows`).

**Lección, y es la sexta vez que aparece la misma.** Ya está escrita en L-R3-06, L-R4-01, L-R4-02
y L-R4-03: **cuanto mejor documenta un equipo su integración y sus ausencias, más defectos falsos
le imputaba este contraste.** El sesgo del instrumento va en una sola dirección —castiga la
documentación buena— y por eso cada corrección hay que hacerla en la regla, no en el perfil. Las
dos de hoy son estrictamente supresivas: pueden ocultar un hallazgo legítimo, nunca inventar uno.

## L-R6-02 · ZAP (red bridge) no alcanzaba un despliegue del host servido por hostname real

**Síntoma.** `make dast TARGET=anuncios_del_curso` moría en el primer request:
`Connect to https://nginx.zajuna.com:443 [nginx.zajuna.com/127.0.0.1] failed: Connection refused`.

**Causa.** El servicio `zap` corre en la red bridge del compose (no `network_mode: host`), con un
solo `extra_hosts: host.docker.internal:host-gateway`. El blanco de este proyecto es el core
Zajuna del HOST, cuyo `wwwroot` es `https://nginx.zajuna.com/zajuna`. Dentro del contenedor,
`nginx.zajuna.com` resuelve por el `/etc/hosts` heredado a `127.0.0.1`, que es el propio
contenedor: nada escucha ahí. Apuntar a `host.docker.internal` tampoco vale, porque Moodle
redirige cada petición a su `wwwroot` (el hostname real) y el certificado autofirmado sólo casa
con ese `server_name`.

**Arreglo (genérico, no un hack de perfil).** Se añadió al servicio `zap` una segunda entrada
`extra_hosts` parametrizada: `"${TARGET_HOST_ALIAS:-none.invalid}:host-gateway"`. Cuando un
perfil audita un despliegue del host servido por nombre, fija `TARGET_HOST_ALIAS` en su
`target.env.local` (aquí `nginx.zajuna.com`) y ZAP resuelve ese nombre a la IP del host, con lo
que los redirects de Moodle y el `server_name`/cert casan. Sin la variable, mapea `none.invalid`
(inocuo) y el comportamiento previo no cambia para ningún otro perfil.

**Resultado.** El spider alcanzó el host y encontró 21 URLs; el activeScan arrancó. Es la
contraparte del `host.docker.internal` que ya existía: aquel resuelve "el host" de forma anónima;
este lo resuelve por el nombre por el que el host se conoce a sí mismo, que es lo que un Moodle
con `wwwroot` por hostname exige.

## L-R6-03 · Un spec propio reusó un APIRequestContext tras dispose; y los specs genéricos de peso miden la página Moodle entera

Dos observaciones de la corrida e2e de anuncios_del_curso, ninguna imputable al proyecto auditado.

**(a) Mi spec `imagecarousel-mecanismos.spec.ts` (test de delete.php) falló con "Target page,
context or browser has been closed".** Causa: `loginAs('A')` memoiza y comparte un
`APIRequestContext` por rol (optimización de lib/auth para no re-autenticar), y un `ctx.dispose()`
en un test anterior lo cerró para todos los siguientes que reusan el rol A. Es un defecto de MI
spec, no del sistema: no debe llamar `dispose()` sobre un contexto compartido. La verificación que
ese test buscaba (delete.php exige `confirm_sesskey`) ya está cubierta por lectura de código
(`delete.php:46`) y por la matriz (`delete.php` role B denied → passed). Queda pendiente quitar el
`dispose()` del spec; el hallazgo I1/S1 no depende de él.

**(b) Los specs genéricos `main-thread-budget` reportaron "15.80 MB de imágenes / 94 MPx" sobre el
plugin.** Barrido de veracidad: esa cifra es de la PÁGINA `course/view.php` ENTERA (un curso demo
con otros recursos e imágenes de tema), no del carrusel de prueba, que sólo tenía 2 iconos SVG. El
spec genérico no acota su medición al componente auditado, así que su número no es atribuible a
`mod_imagecarousel`. NO se lleva al informe como hallazgo del plugin. Sí corrobora, de forma
cualitativa, el fondo de I3: emitir imágenes como `data:base64` inline las hace no cacheables y "cada
recarga con caché fría vuelve a pagarlas" — pero la cifra concreta pertenece a la página, no al plugin.

## L-R7-01 · Tercera y cuarta cita falsa: el «se» impersonal, y «existe pero en otro árbol»

**Síntoma.** El primer `make ingest-deploy TARGET=portafolio_del_aprendiz` devolvió **3 hallazgos
(0 críticos · 1 alto · 2 medios)** contra el `DEPLOY.md` recién entregado (commit `9674bda` de
`feature/v2`, 658 líneas). **Dos de los tres eran míos.**

**Falso ALTO — «DEPLOY.md cita `npm-shrinkwrap.json` como si estuviera».** El §3 del documento dice:

> No se requiere Node/npm para correr el plugin. `npm-shrinkwrap.json`, `Gruntfile.js` y `.nvmrc`
> (`lts/iron`) existen en la raíz de Moodle core para el build de temas/JS del core de Moodle, no de
> este plugin — fuera de alcance salvo que también se esté modificando el core.

Comprobado antes de escribir nada (METODOLOGIA §4): los tres ficheros **están de verdad** en
`/var/www/zajuna/` (`npm-shrinkwrap.json` 443.793 bytes, `Gruntfile.js` 9.671, `.nvmrc` 9). El
documento es **exacto**, y aun así se le imputó un ALTO por no traer un fichero que nunca prometió.
Dos causas independientes, y hacían falta las dos:

1. **El «se» impersonal.** `ABSENCE_RE` listaba los verbos pegados a `no ` y trataba el reflexivo
   como casos sueltos (`no se us`, `no se usan`). «No **se** requiere» no casaba con ninguno.
2. **Una categoría que no existía en el patrón.** «Esto existe, pero **no aquí**» no es una
   ausencia, es una declaración de **alcance**. Un plugin vive dentro de un núcleo ajeno: decir
   «pertenece al core» es la forma normal de acotar en este ecosistema, no un caso raro.

**Falso MEDIO — «No hay .env.example».** El §6 dice: «Este proyecto **no usa archivos `.env`** (no
existe `.env`, `.env.example` ni `.env.template` en el repo)», y a continuación documenta la
configuración real en dos tablas (`config.php` de Moodle y `mdl_config_plugins` vía `settings.php`).
Es la respuesta exacta que la comprobación busca — nombra `.env.example` **literalmente** para decir
que no existe — pero la exención exigía la frase «variables de entorno» y este documento habla de los
**ficheros**. La pregunta que importa es *si el documento declara cómo se configura esto*, no con qué
sustantivo lo declara.

**Arreglo (los tres generalizan).**
1. `ABSENCE_RE`: `(se )?` opcional delante del grupo de verbos — cubre de una vez todas las formas
   impersonales y hace innecesarios los parches sueltos que las seis correcciones anteriores fueron
   añadiendo de una en una. Más el verbo `requier`.
2. `ABSENCE_RE`: vocabulario de **alcance** — `fuera de alcance`, `en la raíz de Moodle`,
   `no forma[n] parte de este repo`.
3. La exención de `.env.example` acepta también la negación sobre los **ficheros**, no solo sobre
   «variables de entorno».

**Un callejón sin salida que merece quedar escrito, porque la intuición era razonable y estaba mal.**
Como aquí la frase que descalifica la acusación va **después** de la cita, lo natural era ampliar la
ventana de contexto de `-B2` a `-B2 -A1`. Medido contra los seis `DEPLOY.md` ya congelados, ese solo
cambio **eximía TRECE citas que hoy se reportan**: `docker-compose.yml` e `index.php` en adi,
`pg_hba.conf` en analitica_notificaciones, `ajax/send_segmented.php` en anuncios_de_plataforma, y
`package.json`, `bun.lock`, `ci.yml`, `setup.sh` y dos `version.php` en reportes_de_cursos. Ninguna
por una negación: por arrastrar la primera línea del párrafo siguiente, que en un documento de
despliegue casi siempre trae un «no hay» **sobre otra cosa**. La ventana se queda en `-B2` y el caso
se resuelve en el vocabulario, que sí distingue de qué habla la frase.

Y la asimetría importa: ampliar la ventana **no produce un falso positivo, produce un falso
negativo** — y ese nadie lo ve, porque se manifiesta como un informe más limpio.

**Comprobación de no regresión, hecha antes de dar el arreglo por bueno.** Prueba diferencial del
patrón viejo contra el nuevo sobre los **siete** `DEPLOY.md` congelados, aplicando las precondiciones
reales de la comprobación (el fichero no está en el repo; no aparece bajo `admin/cli/`):
**cero cambios en los seis targets ya auditados**, y en portafolio solo las dos citas que debían caer.
Los otros «flips» que apareció el diferencial (`lib.php`, `bootstrap.php`, `hooks.php`) son inertes:
esos ficheros **sí** están en el repo, así que la comprobación nunca llega al regex.

**Resultado.** De 3 hallazgos a **1**: «Sin integración continua». Y ese es real y además **peor de
lo que la herramienta sabe decir**: `feature/migration` sí tiene `.github/workflows/moodle-release.yml`,
así que la reescritura v2 **perdió** la CI que el proyecto ya tenía. Eso va al informe con esa
evidencia, no con la frase genérica.

**Lección, y es la séptima vez.** Ya está escrita en L-R3-06, L-R4-01, L-R4-02, L-R4-03 y L-R6-01:
**cuanto mejor documenta un equipo sus ausencias, más defectos falsos le imputa este contraste.** El
sesgo del instrumento va siempre en la misma dirección: castiga la documentación buena. Siete
correcciones ampliando una lista de frases sugieren que el diseño toca techo — un `ABSENCE_RE` que
tiene que anticipar cómo redacta cada equipo una negación es una carrera que se pierde. Pendiente de
valorar para R8: en vez de adivinar la negación, comprobar si el fichero citado **existe en el árbol
del núcleo/host declarado** antes de acusar, que es evidencia y no interpretación de prosa.

## L-R7-02 · El adaptador moodle-session de k6 ignoraba el subpath: «100% error» que era un 404 de login

**Síntoma.** El primer `make perf TARGET=portafolio_del_aprendiz` marcó **http_req_failed 100%** con
**353.837 iteraciones en 60 s** (5.897/s). Un número absurdo para «carga»: 5 VUs no hacen 350 mil
iteraciones de 11 páginas cada una en un minuto contra un Moodle real. La cifra misma delataba que
no se estaba midiendo la aplicación.

**Causa, encontrada antes de escribir nada (METODOLOGIA §4).** El adaptador `moodle-session` de
`lib/k6/session.js` construía el login como `${BASE}/login/index.php`. Aquí `BASE` = `APP_INTERNAL_URL`
= `https://nginx.zajuna.com`, pero el core Zajuna se sirve bajo **`/zajuna`**: la ruta real es
`/zajuna/login/index.php`. Sin el prefijo, el GET daba **404**, el `logintoken` salía vacío, el POST
de login fallaba, y cada iteración reintentaba al instante — de ahí las 350 mil iteraciones: no era
carga, era un bucle fallando sin latencia de red real.

Es el mismo modo de fallo que la metodología usa de ejemplo: «0 secretos» porque la herramienta no
arrancó. Aquí, «100% error» porque el login nunca llegó a la página.

**Arreglo (generaliza, no es un parche del perfil).** El adaptador `zea-standalone` YA resolvía esto
con `ZEA_MOODLE_BASE`; `moodle-session` no tenía equivalente. Se le añade `MOODLE_BASE` (mismo
patrón, nombre genérico) delante del login. Un Moodle bajo subpath es lo NORMAL en esta fábrica
—antiplagio y portafolio lo están—, así que el prefijo pertenece a la librería, no al guion de un
proyecto. El guion de k6 del perfil usa la misma variable para sus rutas, y `target.env.local`
declara `MOODLE_BASE=/zajuna`.

Por qué el prefijo NO puede ir en `BASE_URL`: `tools/require-live.sh` construye la sonda como
`${BASE_URL}${HEALTH_PATH}`, y `HEALTH_PATH` ya incluye `/zajuna`. Meterlo también en `BASE_URL`
daría `/zajuna/zajuna/...`. Las dos mitades del laboratorio (k6 y require-live) leen `BASE_URL`, así
que el subpath tiene que ser una variable aparte — exactamente por lo que `ZEA_MOODLE_BASE` existía.

**Resultado.** De «100% error / 353.837 iteraciones» a **0% error, p95 76 ms, 800 peticiones**, con
las 11 páginas del plugin en verde. Los umbrales `K6_P95_MS/K6_ERR_RATE` se fijaron DESPUÉS, con esa
medida delante, y holgados porque la carga fue sobre datos vacíos (los cursos demo no tienen notas).

**Lección.** Un adaptador de autenticación que sirve a «todo Moodle» tiene que contemplar que Moodle
casi nunca está en la raíz del host. La primera versión asumía la raíz porque el primer Moodle que
tocó (encuestas, plugin standalone) estaba ahí. La segunda familia de proyectos —los que viven DENTRO
del core Zajuna en `/zajuna`— rompió el supuesto, y el síntoma apareció como un dato de rendimiento,
no como un error de ruta.

---

## L-R8-01 — semgrep no monta el directorio del target: las reglas propias del proyecto tienen que vivir en `lib/semgrep/`

**Ronda:** #8 (centro_calificaciones), 2026-08-31.

**Qué pasó.** Al escribir el guion de semgrep para este proyecto quise poner sus reglas propias
—los invariantes de ESTE código (SSO por sesskey no validado, identidad de sesión desde la
petición)— en `targets/centro_calificaciones/semgrep/centro-calificaciones.yml`, junto al resto del
perfil, y referenciarlas como `/seclab-target/semgrep/...`. No funciona: el servicio `semgrep` de
`docker-compose.yml` monta `./lib:/seclab-lib:ro` y `./reports/${TARGET_NAME}/semgrep:/reports`,
**pero NO monta `targets/${TARGET}`**. Un `--config=/seclab-target/...` apunta a una ruta que no
existe dentro del contenedor y semgrep aborta.

**Cómo se rodeó (sin tocar la regla del laboratorio todavía).** Se siguió el precedente de #7: el
fichero se puso en `lib/semgrep/centro-calificaciones.yml` (que sí se monta como `/seclab-lib`), igual
que `lib/semgrep/moodle-plugin.yml`. Funciona, pero **mezcla una regla específica de un proyecto en el
directorio compartido del laboratorio**: `lib/` deja de ser «reglas del lab» para tener también reglas
de un target concreto. Es deuda, no solución.

**Dónde está el defecto (en la REGLA, no en el perfil).** El contrato del perfil ya prevé guiones
propios por dimensión dentro de `targets/<t>/` (zap/, k6/, playwright/…). semgrep es la excepción: no
puede leer un guion que viva en el perfil. Lo correcto es que el servicio `semgrep` monte también
`./targets/${TARGET_NAME}/semgrep:/seclab-target/semgrep:ro` (read-only, como los demás), y que la
plantilla `make new` deje un `targets/_template/semgrep/.gitkeep` y un ejemplo. Así las reglas que son
invariantes de UN proyecto viven CON ese proyecto, y `lib/semgrep/` vuelve a ser solo lo transversal
(p.ej. `moodle-plugin.yml`, que sí aplica a cualquier plugin Moodle).

**Pendiente:** añadir el volumen al servicio `semgrep` en `docker-compose.yml` y mover
`centro-calificaciones.yml` a `targets/centro_calificaciones/semgrep/`. Mientras tanto queda en
`lib/semgrep/` y este registro explica por qué.

## L-R8-02 — `gitleaks`: allowlist global es `[allowlist]` (map), no `[[rules.allowlist]]` (slice)

**Ronda:** #8, 2026-08-31. Menor, pero costó una corrida.

Al escribir `targets/centro_calificaciones/gitleaks.toml` puse la lista de exclusiones de placeholders
como `[[rules.allowlist]]` (tabla de array). gitleaks abortó con
`'Rules[2].AllowList' expected a map, got 'slice'` y la dimensión quedó NO EJECUTADA (trufflehog sí
corrió). El esquema correcto para una allowlist GLOBAL es `[allowlist]` (una tabla, no array) al nivel
raíz; `[rules.allowlist]` (singular) es la per-regla. No es un defecto del laboratorio —es del guion que
escribí— pero se anota porque el modo de fallo es silencioso salvo por una línea `FTL` entre el ruido de
`docker compose`, y conviene que la próxima persona lo reconozca al instante.

## L-R8-03 — el reloj de la máquina saltó Aug25→Aug31 a mitad de sesión: `MAX_ARTIFACT_AGE_H` marcó VIEJO artefactos válidos

**Ronda:** #8, 2026-08-31.

**Qué pasó.** Durante la auditoría de centro_calificaciones el reloj del host pasó de `2026-08-25` a
`2026-08-31` (visible en `date -Is` y en los mtime de los artefactos). Las dimensiones estáticas
(gitleaks, trufflehog, semgrep, trivy-fs/config, sbom) corrieron con el reloj en Aug-25 (~17:40); las
posteriores (sonar, ingest-deploy, zap) tras el salto (~Aug-31 10:09). `make gate` marcó
secrets/deps/SAST como **VIEJO (137h > 24h)** y avisó de «procedencias distintas».

**Por qué NO es un collage de mediciones (la comprobación que la metodología exige).** Toda la
procedencia (`reports/.../.provenance/*.json`) registra los MISMOS SHAs en las tres ramas:
`centro_de_actividades=3f84cfa`, `centro_de_calificaciones_sincronizacion=fd04cc9`,
`centro_de_resultados=d084378`. No hubo re-clonado ni pull entre medias; el código auditado es
idéntico en todos los artefactos. El desfase de horas es del reloj del entorno, no de la evidencia.

**Cómo se resolvió.** Se re-corrieron las dimensiones estáticas flagged (secrets, deps, semgrep) para
alinear los timestamps a la ventana reciente y dejar el gate sin el aviso de edad — sin cambiar el
resultado (mismo código, mismos SHAs). No es un defecto del laboratorio: el gate hizo exactamente lo
que debe (avisar de un desfase de edad); se documenta el porqué del desfase para que no se lea como
que se mezclaron dos despliegues.
