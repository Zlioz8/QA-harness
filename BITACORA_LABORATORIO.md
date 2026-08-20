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
