# Cambios del laboratorio — ronda R2 (Anuncios de Plataforma)

Mejoras al núcleo del lab surgidas de auditar `anuncios_de_plataforma` (prioridad #4). Cada una
nació de un fallo medido, no de una idea a priori; el detalle interno está en
`BITACORA_LABORATORIO.md`.

## Núcleo (`tools/`)

- **`ingest-deploy.sh`** — tres correcciones que evitan hallazgos falsos sobre proyectos con buen
  DEPLOY.md:
  - `DEPLOY_BRANCHES` ahora se lee del perfil (antes solo del entorno, y se ignoraba en silencio).
  - `DEPLOY_DOC` permite que el documento viva en un subdirectorio (`slider_form/DEPLOY.md`), no
    solo en la raíz — necesario en repos con varios componentes.
  - La heurística de "fichero citado y ausente" excluye artefactos de Moodle core / sistema
    (`*.conf`, `admin/*`, `*.class.php`, `config.php`), mira 2 líneas de contexto para detectar
    ausencias declaradas, y amplía el vocabulario de negación. Redujo 7 hallazgos → 1 real, sin
    regresión en `adi`.

- **`gate.sh`** — respeta `E2E_NO_CONCLUYENTE=1`: cuando una corrida e2e no es fiable en su
  entorno (contenedor que devuelve 404 donde curl da 200), su conteo no vota, pero el artefacto se
  conserva y la razón queda visible. No es un silencio: es una declaración con motivo.

- **`mcp-traza.sh`** (nuevo) — recoge en un rastro legible lo que un recorrido de navegador MCP
  deja disperso: red, consola y sesión de cada paso, con índice cronológico. Pensado para validar
  un informe contra el flujo real.

- **`report.py`** — la sección de reproducción enlaza `reports/<t>/mcp-evidencia/` cuando existe,
  para que el lector llegue de cada hallazgo a su prueba observada en vivo. Condicional: los
  targets sin evidencia MCP no ven la línea.

## Requisito de método confirmado

`require-live.sh` y el triaje endpoint-por-endpoint atraparon dos veces el modo de fallo de
METODOLOGIA §4 (un agregado con un solo culpable al 100%): el 19,63% de error de k6 y el 404 de
ZAP reciclado. Ambos eran del laboratorio, no del proyecto. Ver L-R2-07 y L-R2-01 en la bitácora.
