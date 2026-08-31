# Prompt de arranque — QA prioridad #2 (Reportes de Cursos)

> Copia todo lo que sigue como primer mensaje de la nueva sesión.

---

Trabajo en /home/zlioz/MANUALES DE DESPLIEGUE WITH REPORT/SECURITY-LAB
(rama feat/adi-contrato-despliegue del repo git@github.com:Zlioz8/QA-harness.git — hay
trabajo local; los perfiles de adi (#1) y anuncios_de_plataforma (#4) ya están auditados y
commiteados, sírvete de ellos como ejemplos trabajados).

Soy el encargado de QA de la fábrica de software de git.fsrisaralda.com. Audito los proyectos
en el orden de "Lista de prioridad - QA.xlsx" (raíz del laboratorio). Toca la **PRIORIDAD #2,
Reportes de Cursos** (desarrollador: Luis Andrés Ríos). Es **multi-repo**, dos repositorios:

  ssh://git@git.fsrisaralda.com:2222/fabrica_zajuna/analitica_cursos.git
  ssh://git@git.fsrisaralda.com:2222/fabrica_zajuna/reportes_de_curso.git

Ubicación local (créala y clona ahí los DOS repos, uno al lado del otro):
  /home/zlioz/MANUALES DE DESPLIEGUE WITH REPORT/REPORTES DE CURSOS

SRC_PATH debe apuntar a ESE directorio padre, no a cada repo: el laboratorio descubre los repos
anidados solo (secrets, manifiesto y doctor usan esa regla). Precedente resuelto: el perfil
`movil` es multi-repo; míralo para SRC_PATH y sonar.sources.

ANTES DE EMPEZAR:
1. `make down TARGET=anuncios_de_plataforma` — una dimensión pesada a la vez (METODOLOGIA §7).
2. Lee METODOLOGIA.md en la raíz. Fija la misión y el bucle: yo aporto insumos y escribo el
   guion de cada herramienta, la herramienta procesa, yo interpreto. Saltarse la primera o la
   tercera parte no da error — da un informe que parece completo.
3. El punto de entrada es siempre: `make siguiente TARGET=reportes_de_cursos`. Mira el estado
   real en disco y dice el próximo paso. Obedécelo.

Ejemplos trabajados: targets/adi/ (PHP monorepo) y targets/anuncios_de_plataforma/ (plugin
Moodle, multi-plugin, desplegado en bare metal). Formato del entregable:
reports/adi/INFORME_TECNICO_VERIFICACION_R1_ADI.md. La taxonomía viene de la serie R3–R10 de
Costos Web.

DATOS YA VERIFICADOS de estos repos (no los des por supuestos, confírmalos):
- Ramas de `analitica_cursos`: analitica_cursos, feature/migration, main, sync/analitica_cursos.
- Ramas de `reportes_de_curso`: dashboard, main.
- NINGUNO tiene `dev` ni `dev2`. El valor por defecto de DEPLOY_BRANCHES no sirve: pregúntame
  qué rama audito ANTES de medir nada, y fíjalo con `DEPLOY_BRANCHES=<rama>` en target.env.
  Si cada repo entrega su DEPLOY.md en un subdirectorio, usa `DEPLOY_DOC=<ruta>` (mejora de R2).

REGLAS QUE NO SE NEGOCIAN:
- Nada genérico. Cada herramienta necesita su guion escrito PARA este proyecto: reglas de
  gitleaks sobre las formas de secreto que ESTE código usa (léelas de su .env.example / config),
  plan de ZAP con las rutas reales, k6 autenticado y de SOLO LECTURA, matriz de autorización
  leída del código. `make guiones TARGET=...` falla si algo corre con el ejemplo de la
  plantilla. Lo que no aplique se DECLARA en GUION_NO_APLICA con su razón.
- El laboratorio NO crea cuentas. La matriz de autorización necesita dos cuentas REALES de
  privilegio distinto, pedidas al equipo o al despliegue. Sin ellas esa dimensión es NO
  DISPONIBLE (que no es "sin hallazgos"). Si te toca crearlas tú, decláralas NO AUTORITATIVAS.
- Antes de escribir una cifra, pregúntate de dónde sale y qué la haría mentir. Si un resultado
  sorprende, comprueba primero si el fallo es del fixture, del perfil o del comando —
  endpoint por endpoint, no en agregado — antes de atribuírselo al proyecto. (En R2, un 19,63%
  de error de k6 y un 404 de ZAP resultaron ser defectos del guion y del entorno, no del código.)
- Valores que no salen de esta máquina (URL del despliegue, credenciales) van en
  targets/<t>/target.env.local (gitignored).

MULTI-REPO — revisa que las dimensiones que asumen un solo árbol se comporten bien:
- sonar.sources y SOURCE_DIRS deben listar los sub-repos (ver movil).
- El contrato de despliegue (ingest-deploy) mira UN repo por corrida; si ambos entregan
  DEPLOY.md, decide cuál gobierna o córrelo dos veces. `movil` es el precedente.
- gitleaks y trufflehog SÍ descubren los sub-repos solos.

VALIDACIÓN POR FLUJO (mejora de R2, úsala si hay despliegue vivo):
- Recorre los hallazgos con el navegador MCP (Playwright) y contrasta que el informe coincide
  con lo que el sistema hace de verdad. `tools/mcp-traza.sh <target>` recoge el rastro de
  red/consola/sesión de cada paso en reports/<t>/mcp-evidencia/, y report.py lo enlaza solo.
- Si la suite e2e en contenedor no es fiable en su entorno (da 404 donde curl da 200), juzga la
  autorización por la medición directa curl+navegador y marca `E2E_NO_CONCLUYENTE=1` en
  target.env: el conteo no vota, el artefacto se conserva.

Empieza por `make down TARGET=anuncios_de_plataforma`, luego lee METODOLOGIA.md, y dime qué
encuentras al correr `make siguiente TARGET=reportes_de_cursos`.
