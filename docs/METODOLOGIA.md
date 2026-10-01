# Metodología de auditoría — cómo se usa este laboratorio

> **Para quién es este documento.** Para quien vaya a auditar un proyecto con esta herramienta,
> en cualquier sesión, sobre cualquier proyecto y en cualquier máquina. No presupone haber
> estado en las sesiones anteriores ni conocer los proyectos ya auditados.
>
> **Empieza siempre por `make siguiente TARGET=<proyecto>`.** Este documento explica *por qué*
> el método es como es; ese comando dice *dónde estás y qué toca ahora*. Si solo lees una cosa,
> que sea el comando: es el que conoce el estado real.

---

## 1. La misión

**Medir el estado de un proyecto con evidencia reproducible, y no afirmar nunca más de lo que se
midió.**

Las dos mitades importan igual. La primera es obvia. La segunda es la que hace que el informe
valga algo: un laboratorio que exagera su cobertura produce tranquilidad falsa, y la tranquilidad
falsa es peor que no medir — porque sustituye a la decisión de medir.

De ahí sale todo lo demás, incluidas las cosas que parecen inconvenientes:

- Una dimensión que **no se ejecutó** no puede parecerse a una que no encontró nada.
- Una dimensión que corrió con el **ejemplo genérico** midió otro proyecto con el nombre de este.
- Un hallazgo **sin juicio humano** todavía no es un hallazgo del informe.
- Un dato que el laboratorio **fabricó** (una cuenta, una tabla, un `composer.json`) no puede
  presentarse como una medida del sistema.

## 2. El bucle, y qué hace cada mitad

```
   TÚ                      LA HERRAMIENTA              TÚ
   ──                      ──────────────              ──
   aportas los insumos  →  procesa  →                  interpretas
   escribes el guion                                   trías
                                                       redactas el juicio
```

Las tres partes son obligatorias, y **saltarse la primera o la tercera no da error**. Ese es el
modo de fallo real de esta herramienta, y ya ocurrió: se dio por cubierta la autorización de un
proyecto con el archivo de política escrito pero **ningún test**, y la comprobación hecha a mano
con `curl` en paralelo a una herramienta que no podía ejecutarse. El informe habría dicho
"autorización verificada". Nada lo desmintió porque no había nada que lo desmintiera.

Por eso hoy el laboratorio **se niega** en los tres puntos:

| Se niega a… | Quién lo hace | Por qué |
|---|---|---|
| medir contra una aplicación caída | `tools/require-live.sh` | un ZAP limpio contra algo apagado es idéntico a uno contra algo seguro |
| medir autorización con una sola cuenta | `tools/require-auth.sh` | hace falta que el privilegio BAJO intente lo del ALTO |
| dar por buena una dimensión con guion genérico | `tools/guion-check.py` | el guion es el techo de la cobertura |
| escribir un informe vacío como si fuera limpio | `tools/secrets.sh`, `make dast` | la ausencia de escaneo no es ausencia de hallazgos |
| aprobar sin veredicto | `tools/gate.sh` | `skip` no es `PASS` |
| dar por auditado un evento sin oráculo | `tools/aaa-oracle.sh` | «se registró» solo lo dice la tabla de auditoría, no el 200 de la respuesta |

## 3. Los insumos: qué te toca aportar a ti

`make siguiente` los pide en orden. Aquí está el porqué de los que cuestan.

### El guion de cada herramienta — lo que más se salta

El **guion** es el archivo que la herramienta interpreta: el plan de ZAP, el script de k6, las
reglas de gitleaks, los tests de Playwright. Es el **techo de la cobertura**: una dimensión no
puede encontrar nada fuera de lo que su guion ejercita.

`make new` deja los guiones de la plantilla, y son ejemplos, no configuraciones. Escribirlos para
el proyecto es trabajo de criterio, no de copiar:

- **gitleaks** — las reglas genéricas marcan el código que *maneja* credenciales. En un PHP
  cualquiera, `public ?string $password;` sale como fuga. Ese ruido entierra las reales. Escribe
  reglas sobre las formas que ESE proyecto usa de verdad (léelas de su `.env.example`), y acota
  por ruta: en `.php` una asignación con `password` casi siempre es una variable.
- **ZAP** — el crawler no descubre lo que no está enlazado. Si el router hace coincidencia exacta
  de URI, o hay endpoints AJAX, hay que listarlos: sin eso, la mitad de la superficie no aparece
  en el escaneo y nadie lo nota.
- **k6** — sin autenticar mide la pantalla de login. Y solo lectura: un `/store` bajo carga es un
  incidente, no una medición.
- **Playwright** — `authz-matrix.json` es la política (qué rol alcanza qué) y la escribe una
  persona leyendo el código. Los tests propios cubren los MECANISMOS que ese sistema declara
  tener: CSRF, limitador de intentos, regeneración de sesión.

Si una dimensión no aplica, **decláralo**: `GUION_NO_APLICA=qodana,jmeter` en `target.env`. Una
declaración con razón es una afirmación honesta; el silencio no.

### Dos cuentas de privilegio distinto

La autorización es la única dimensión que ningún escáner cubre solo. **El laboratorio no crea
las cuentas**: si las fabrica él, la matriz mide un accesorio suyo — con los roles que él eligió —
y no el control de acceso del sistema. Se piden al equipo. Si no las hay, la dimensión es NO
DISPONIBLE, que no es «sin hallazgos».

### El modelo de amenazas (STRIDE) es un insumo

Es el único guion que describe el sistema **entero** y no una muestra de él: qué activos hay, qué
datos procesan y guardan, por qué enlaces se hablan (protocolo, autenticación, autorización) y qué
fronteras de confianza los separan. Se escribe **leyendo la arquitectura**, no el código, en
`targets/<t>/amenazas/threagile.yaml`; Threagile lo evalúa con sus reglas, cada una con su letra
STRIDE, y deja riesgos contables (`make amenazas`). Ninguna regla builtin es Repudiation: la R se
declara en el modelo (`individual_risk_categories`) y se mide con la auditoría de AAA.

Regla: **una amenaza modelada sin control medido es un hallazgo, no una laguna.** Se cierra con
una sonda que pasa (veredicto `mitigado`, que nombra la medición), o con un juicio en el triaje
con razón escrita — nunca borrándola del modelo.

### Los tres pilares AAA tienen guion propio

STRIDE dice *qué puede pasar*; AAA dice *qué hace el sistema con la identidad*, y son tres
preguntas distintas con tres guiones distintos:

- **Autenticación** (`aaa/authn.json`): qué debe responder el login y la sesión — una contraseña
  incorrecta, un refresh usado como access, la credencial vieja tras cerrar sesión, la superficie
  sin sesión, el limitador. El motor es genérico (`lib/specs/authn.spec.ts`) y entra por el
  adaptador del perfil; el guion declara solo las expectativas de ESTE sistema.
- **Autorización** (`playwright/authz-matrix.json`): la matriz que ya existía — qué rol alcanza
  qué —, ahora con su propio artefacto y veredicto.
- **Auditoría** (`aaa/acct.json`): qué evento debe dejar rastro y dónde. Lo comprueba un oráculo
  de solo lectura contra la tabla de auditoría de la aplicación (`AAA_DB_URL`, en `.local`); sin él
  la auditoría es NO DISPONIBLE, que no es «sin hallazgos».

`make aaa` corre los tres y sustituye a `make e2e` cuando el perfil trae guiones AAA. Una sonda
que este stack no puede ejecutar (sin refresh, sin logout) **consta** como no aplicable; no falla
ni desaparece.

### Lo que el repositorio no trae

Algunos proyectos no se despliegan desde su propio repositorio: falta el manifiesto de
dependencias, una migración, un esquema. `make ingest-deploy` lo detecta y lo convierte en
hallazgo con evidencia. **Puedes aportar el insumo para poder medir** — un `composer.json`
reconstruido, una tabla deducida — pero entonces:

1. Se marca como aportado por el laboratorio, en el propio archivo.
2. La dimensión que dependía de él se declara **NO AUTORITATIVA** en el informe.
3. La ausencia sigue siendo el hallazgo.

Y hay un límite: **deja de deducir cuando empieces a inventar**. Si para que una pantalla cargue
hay que adivinar columnas una a una, ya no estás midiendo el sistema, estás midiendo tu
reconstrucción. Declara NO CUBIERTO con su razón — la razón *es* el hallazgo.

## 4. Interpretar: la parte que no se delega

Un número de una herramienta no es una conclusión. Tres casos reales de este laboratorio:

- **«19% de error bajo carga.»** Suena a sistema inestable. El desglose decía otra cosa: login
  10/10, cuatro pantallas 90/90, y **una** fallando 90 de 90. No era inestabilidad: era un
  endpoint roto al 100%. Reportar el agregado habría dicho lo contrario de la verdad.
- **«500 hallazgos de calidad, umbral 500 → PASS.»** La API declaraba 736 y solo se descargaba
  la primera página. El número que llegaba al veredicto era un tamaño de página.
- **«0 secretos.»** La herramienta no había llegado a arrancar.

La regla: **antes de escribir una cifra, pregunta de dónde sale y qué la haría mentir.** Y cuando
un resultado sorprenda, comprueba primero si el fallo es tuyo — del fixture, del perfil, del
comando — antes de atribuírselo al proyecto. Distinguir un fallo del entorno de uno del sistema
auditado es parte del trabajo, no un preámbulo.

## 4.bis Fundamentar el riesgo: de «severidad Alta» a prueba con marco

Entre juzgar los hallazgos y emitir el veredicto hay un paso que el informe por sí solo no cubre:
**probar que cada riesgo confirmado es tangible y anclarlo a marcos reconocidos.** Un equipo de
desarrollo que recibe «severidad Alta» aprende poco, y una fábrica que aspira a certificarse
(ISO/IEC 27001) necesita trazabilidad: por cada riesgo, un documento que demuestre *dónde vive, por
qué medios se ejecuta y con qué evidencia*, mapeado a OWASP, MITRE (CWE/ATT&CK), STRIDE, CVSS y los
controles del Anexo A de ISO 27001.

`make riesgos TARGET=<proyecto>` verifica que cada hallazgo confirmado tiene su
`targets/<t>/riesgos/<ID>.md` con esas secciones pobladas para ESE hallazgo. `make riesgos
ANDAMIAR=1` crea los esqueletos. Es el mismo principio que los guiones: **el laboratorio se niega**
a dar el paso por completo mientras un confirmado no tenga su fundamentación — una severidad sin
prueba ni marco es una afirmación, no un hallazgo defendible.

No es una PoC («corre estos comandos»). Es un documento **probatorio y FORMATIVO**: su doble
destinatario es el desarrollador que debe entender la base del fallo para no repetirlo, y el auditor
de certificación que necesita ver el control mapeado. La matriz consolidada
(`reports/<t>/MATRIZ_MARCOS.md`) cruza todos los hallazgos contra todos los marcos en una tabla, y
el informe enlaza cada ficha desde su hallazgo.

Una honestidad que el paso preserva: cuando un marco NO aplica (un fallo de disponibilidad por error
propio no tiene vector CVSS ni técnica ATT&CK; un riesgo de proceso no encaja en STRIDE), se DICE,
en vez de forzar una casilla. Forzar el encaje enseñaría al equipo un mapeo falso.

## 4.ter STRIDE: de la letra al artefacto

Las seis letras dejan de ser prosa. Salen de tres sitios, y el informe los cruza en una tabla:

| Fuente | Qué aporta la letra | Artefacto |
|---|---|---|
| Threagile sobre el modelo | una por REGLA (el mapa vive en `tools/threagile-sarif.py`) | `reports/<t>/amenazas/threagile.sarif` |
| las sondas AAA | una opcional por sonda, declarada en el guion | `reports/<t>/aaa/aaa.json` |
| las fichas `riesgos/<ID>.md` | la sección `## STRIDE` de cada hallazgo confirmado | el propio documento |

Una letra con amenazas modeladas y sin sondas es un control que se da por supuesto; una letra
con sondas y sin amenazas es una medición sin modelo detrás. Las dos cosas se ven en la matriz.

## 4.quater AAA: del control a la sonda

Un control de identidad no se describe: se **ejercita**. La sonda declara qué debe responder el
sistema y el motor lo pide de verdad, con las credenciales que entregó el equipo, a través del
adaptador. Tres consecuencias:

- **Presupuesto 0.** Una sonda de autenticación que falla, una regla de la matriz que un rol
  alcanza sin derecho, o un evento que no dejó rastro, son un control que no está. No se
  administran por umbral: se corrigen, o se aceptan en el triaje con razón escrita.
- **La auditoría necesita oráculo.** «Se registró» solo lo dice la tabla de auditoría, no el 200
  de la respuesta. Sin `AAA_DB_URL` el pilar queda NO DISPONIBLE y el gate lo imprime aparte.
- **El presupuesto de logins es real.** Un login crudo por rol y archivo, uno fallido por sonda;
  contra un limitador (movil: 10 por minuto y por IP) eso es lo que cabe junto a `auth-check` y la
  matriz. `E2E_PACE_MS` espacia; `workers: 1` en `playwright.config.ts` evita la carrera.

## 4.quinquies Carga y capacidad: de «un p95» a una afirmación

`make perf` responde una pregunta pequeña: *¿esta corrida cumple el umbral?* La pregunta que
llega de fuera es otra —*¿cuánta gente aguanta, qué se rompe primero y qué hay que comprar o
arreglar?*— y un número suelto no la contesta. La contestan tres cosas juntas:

```bash
make perf-escalera TARGET=<proyecto>     # sube por pasos; para en el primero que incumple
make capacidad     TARGET=<proyecto>     # rodilla, quiebre, recurso saturado, costo unitario
tools/perf-capacidad.py comparar <corrida-A> <corrida-B>    # antes y después de un cambio
```

**La regla de evidencia.** Fuente directa es el código en su commit, el sistema corriendo y una
medición con su comando. Un README, un informe anterior o un umbral heredado son hipótesis. Una
prueba de carga vieja también: `summary.json` no dice contra qué commit ni qué despliegue midió,
y el veredicto la cuenta igual. Antes de citar una corrida, mira su sello
(`reports/<t>/.provenance/k6.json`) y su fecha; si no tiene sello, no es evidencia de hoy.

**El modelo sale de tráfico real, no de un documento.** Lo que la aplicación pide de verdad está
en el log del proxy de un despliegue que alguien usó. De ahí salen las secuencias por pantalla y
el ritmo; el perfil guarda el extractor junto al modelo (en `movil`, `carga/grabacion.py`). Lo
que ese tráfico NO da es la mezcla de una población: si lo generó un probador, la mezcla es un
supuesto y se escribe como tal, dentro del guion.

**Seis errores que fabrican un número bonito**, todos medidos aquí:

- *Una cuenta para todos los usuarios virtuales.* El backend cachea por persona y la prueba mide
  la caché. → una cuenta por usuario virtual (`k6/datos/cuentas.json`, nunca versionado).
- *Una IP para todos.* Entra el límite por IP y se mide el muro. → `CARGA_IPS=por-vu` contra un
  despliegue propio que confíe en ese salto de proxy; o se deja a propósito y se lee como lo que
  es: un aula detrás de un NAT.
- *Juzgar con la rampa dentro.* Durante la rampa la concurrencia aún no es la del paso. → el SLO
  se juzga en la meseta (`detalle.json`, campo `meseta`).
- *Iniciar sesión dentro de la carga.* El login es raro en el uso real y suele estar limitado. →
  las sesiones se abren en `setup()`; el login tiene su propia prueba.
- *Medir con la máquina ocupada.* Generador y sistema comparten host: cualquier otra cosa que
  corra entra en la cifra. → se para lo ajeno, y `perf-capacidad` avisa si el host entero pasó
  del 85 % de CPU: ese paso describe el equipo, no la aplicación.
- *Un cliente que no es el de la app.* k6 no manda `Accept-Encoding`; el cliente nativo de Android
  negocia gzip solo. Con compresión en el servidor, k6 mide 56 KB donde la app recibe 4 KB
  (2026-10-01). → `CARGA_CABECERAS` con lo que el cliente real manda siempre, y la cifra de bytes
  se contrasta con el teléfono.

**La telemetría es lo que convierte el quiebre en un diagnóstico.** El perfil declara qué se mira
(`PERF_WATCH_CONTAINERS`, `PERF_WATCH_PROCS`) y cuál es el techo de cada pieza (`PERF_TECHOS`),
leído de su configuración efectiva: un proceso de un solo hilo tiene techo en un núcleo aunque el
contenedor tenga cuatro. Sin techos declarados el informe dice «recurso limitante: no atribuido»,
y eso también es un resultado: el cuello está en algo que no se mira.

**Tres marcas, y no se promueve ninguna.** Cada cifra de `CAPACIDAD.md` es *medida*, *extrapolada*
(proyección lineal desde el costo unitario) o *supuesta* (la demanda). Una escalera en un solo
sobre no demuestra cómo escala el sistema al añadir recursos: para eso se repite con otro sobre y
se ajusta la curva (`perf-capacidad.py curva`).

**Lo que una escalera no puede decir.** Nada de lo que el perfil no vigila; nada de un servidor
que no sea el medido; y nada sobre la demanda real, que llega de fuera.

## 5. El entregable

`make informe TARGET=<proyecto>` produce
`INFORME_TECNICO_VERIFICACION_R<n>_<PROYECTO>.md`: el canal entre QA, el equipo de desarrollo y
el líder técnico.

- Sale **completo en todo lo verificable** y con marcas `⟨PENDIENTE: …⟩` donde hace falta una
  persona. Las marcas son feas a propósito: un informe con huecos visibles es honesto; uno que
  los rellena con generalidades, no.
- **Todo lo que contiene debe ser accionable por su destinatario.** Los defectos del propio
  laboratorio NO van ahí — van a `BITACORA_LABORATORIO.md`, que es interno. Se registran con el
  mismo rigor: una medición vale lo que valga su instrumento.
- La numeración de ronda sale del registro (`targets/<t>/hallazgos.tsv`), no de la memoria de
  nadie. Un hallazgo conserva su identificador entre rondas, y eso permite decir «abierto desde
  R3» — que convierte un problema técnico en uno de proceso.
- Regenerar el informe es idempotente. La ronda avanza solo con `RONDA_NUEVA=1`, después de
  volver a medir.

## 6. Re-auditar: lo caro no se repite

Cuando el equipo entrega correcciones, **no se vuelve a montar nada**:

| Sobrevive | Se rehace |
|---|---|
| el perfil entero (`targets/<t>/`): guiones, recetas, matriz, semillas | los escaneos (~10-15 min) |
| el triaje (claves sin número de línea, a propósito) | |
| las imágenes de herramientas y del runtime | |

Re-auditar es `make ingest-deploy static live gate TARGET=<t>` y `make informe RONDA_NUEVA=1`.
Cero trabajo humano salvo triar lo nuevo.

## 7. La máquina

Un proyecto a la vez. Lo que satura no es escanear: es acumular despliegues levantados.
`make doctor` avisa de contenedores de otros perfiles y de huérfanos. Entre proyectos,
`make down TARGET=<t>`.

Los topes de memoria por dimensión están calibrados para una máquina modesta y **son
ajustables por perfil** cuando la tuya es mayor (`ZAP_MEM`). Súbelos mirando la RAM real que
imprime `make doctor`, no a ojo: el tope existe para que la herramienta muera antes que la
máquina.

## 8. Arranque en frío — proyecto nuevo, sesión nueva, máquina nueva

```bash
make new       TARGET=<proyecto>        # esqueleto del perfil
$EDITOR targets/<proyecto>/target.env   # SRC_PATH y REPO_URL
make siguiente TARGET=<proyecto>        # y a partir de aquí, obedecer lo que diga
```

`make siguiente` conoce el estado real y encadena el resto. No hay nada más que recordar.
