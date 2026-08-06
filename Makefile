# SECURITY-LAB — thin targets. Each goal is one docker-compose invocation of one
# dedicated tool, or one script in tools/. No analysis logic lives in this file.
#
#   make help                     list every goal
#   make new     TARGET=proyecto  scaffold a new target profile
#   make detect  TARGET=proyecto  sniff the stack and propose target.env
#   make doctor  TARGET=proyecto  preflight (docker, disk, ports, permissions)
#   make static  TARGET=proyecto  everything that needs no running app
#   make gate    TARGET=proyecto  fail (exit != 0) when thresholds are breached
#
# TARGET selects targets/<name>/. Set a default here if your team audits one project
# most of the time; leaving it empty forces the choice to be explicit.
TARGET ?=

T        = targets/$(TARGET)
ENVFILE  = $(T)/target.env
# Override local, opcional y NUNCA versionado: valores que no pueden salir de esta máquina
# (host del despliegue, credenciales de las cuentas de prueba). target.env es el contrato del
# perfil y se versiona; target.env.local son los valores. compose aplica el último --env-file
# que gana, así que este va después.
ENVLOCAL = $(wildcard $(T)/target.env.local)
ENVFILE_F= --env-file $(ENVFILE) $(if $(ENVLOCAL),--env-file $(ENVLOCAL),)
RUNTIME  = $(wildcard $(T)/compose.runtime.yml)
RUNTIME_F= $(if $(RUNTIME),-f $(RUNTIME),)
DC       = docker compose $(ENVFILE_F) -f docker-compose.yml $(RUNTIME_F)
REPORTS  = reports/$(TARGET)

# Every goal except help/new/list needs a valid target profile.
guard:
	@test -n "$(TARGET)" || { echo "ERROR: set TARGET=<name>. Available: $$(ls targets | tr '\n' ' ')"; exit 2; }
	@test -f "$(ENVFILE)" || { echo "ERROR: $(ENVFILE) not found. Run: make new TARGET=$(TARGET)"; exit 2; }
	@# Pre-create every output directory as the HOST user. Tools run under different UIDs:
	@# most run as root and can write anywhere, but ZAP runs unprivileged and fails with
	@# "AccessDeniedException" on a directory a root container created first. Whoever gets
	@# there first decides the owner, so we get there first.
	@mkdir -p $(REPORTS) $(REPORTS)/trivy $(REPORTS)/semgrep $(REPORTS)/sbom $(REPORTS)/sonar \
	          $(REPORTS)/qodana $(REPORTS)/zap $(REPORTS)/k6 $(REPORTS)/playwright $(REPORTS)/build \
	          $(REPORTS)/api $(REPORTS)/mobile $(REPORTS)/device

.PHONY: budget help list new detect doctor guard require-live require-auth clone up down purge status gate dashboard run-manifest doc-check ui ui-stop ui-logs \
        sonar qodana semgrep secrets deps config-scan image-scan sbom mobile-scan static \
        build dast perf perf-jmeter e2e device-e2e live all api-lint api-fuzz

help:             ##[admin] show this list, grouped by what each goal needs
	@echo ""
	@echo "  \033[1m[code]\033[0m  needs only a source checkout. No deployment, no credentials."
	@grep -hE '^[a-z0-9_-]+:.*?##\[code\]' $(MAKEFILE_LIST) | sort | awk 'BEGIN{FS=":.*?##.code. "};{printf "    \033[36m%-14s\033[0m %s\n",$$1,$$2}'
	@echo ""
	@echo "  \033[1m[live]\033[0m  needs the application answering: yours, or one the lab brings up."
	@grep -hE '^[a-z0-9_-]+:.*?##\[live\]' $(MAKEFILE_LIST) | sort | awk 'BEGIN{FS=":.*?##.live. "};{printf "    \033[36m%-14s\033[0m %s\n",$$1,$$2}'
	@echo ""
	@echo "  \033[1m[admin]\033[0m housekeeping."
	@grep -hE '^[a-z0-9_-]+:.*?##\[admin\]' $(MAKEFILE_LIST) | sort | awk 'BEGIN{FS=":.*?##.admin. "};{printf "    \033[36m%-14s\033[0m %s\n",$$1,$$2}'
	@echo ""
	@echo "  Targets available: $$(ls targets | tr '\n' ' ')"

list:             ##[admin] list target profiles
	@ls targets

# ---- onboarding a new project ----
new:              ##[admin] scaffold targets/$(TARGET) from the template
	@tools/new-target.sh "$(TARGET)"

detect:           ##[admin] sniff the source tree and propose target.env values
	@tools/detect.sh "$(TARGET)"

doctor: guard     ##[admin] preflight: docker, disk, free ports, reports permissions
	@tools/doctor.sh "$(TARGET)"

# ---- source ----
clone: guard      ##[code] fetch REPO_URL@BRANCH into work/$(TARGET) (only if SRC_PATH is not local)
	$(DC) --profile clone run --rm clone

# ---- static analysis: works with NO running app ----
secrets: guard    ##[code] gitleaks + trufflehog: every repo's history + a working-tree pass
	@tools/secrets.sh "$(TARGET)"

deps: guard       ##[code] Trivy filesystem scan (dependency CVEs + secrets + misconfig)
	@tools/run-dimension.sh "$(TARGET)" trivy-fs

config-scan: guard ##[code] Trivy over the target's own Dockerfiles / compose / k8s
	@tools/run-dimension.sh "$(TARGET)" trivy-config

image-scan: guard ##[code] Trivy over a built image:  make image-scan TARGET=x IMAGE=repo:tag
	@IMAGE=$(IMAGE) tools/run-dimension.sh "$(TARGET)" trivy-image

sbom: guard       ##[code] Syft SBOM + licences
	@tools/run-dimension.sh "$(TARGET)" sbom

mobile-scan: guard ##[code] MobSF over the distributable bundle (.apk/.ipa/.aab)
	@# The source tree is not what reaches the user. On a mobile project the audited object is the
	@# signed artifact, which carries compiled config, bundled assets and third-party SDKs that no
	@# repository scan sees. Declare it with MOBILE_ARTIFACT in target.env; absent = NOT AVAILABLE.
	@tools/mobile-scan.sh "$(TARGET)"

semgrep: guard    ##[code] polyglot SAST with taint tracking
	@tools/run-dimension.sh "$(TARGET)" semgrep

sonar: guard      ##[code] SonarQube server + scanner
	@# Sonar es la única herramienta del lab que necesita un SERVIDOR, y cada perfil levanta el
	@# suyo en el mismo puerto: auditar un segundo proyecto sin apagar el primero moría con
	@# "port is already allocated", un error que no nombra al culpable. Ver el script.
	@tools/sonar-free-port.sh "$(TARGET)"
	$(DC) --profile static up -d sonarqube
	@# Un servidor recién arrancado no trae token, y el scanner sin token responde 401 —dimensión
	@# que "corrió" sin dejar análisis. tools/sonar-token.sh acuña uno con las credenciales admin
	@# (genérico, idempotente); si el target ya declara SONAR_TOKEN, lo respeta. El -e lo inyecta
	@# en el scanner y el export sin que tenga que vivir en target.env.
	@tok=$$(tools/sonar-token.sh "$(TARGET)"); \
	test -n "$$tok" || { echo "sonar: sin token, no se ejecuta el scanner"; exit 1; }; \
	$(DC) --profile static run --rm -e SONAR_TOKEN="$$tok" sonar-scanner; \
	$(DC) --profile static run --rm -e SONAR_TOKEN="$$tok" sonar-export
	@# Without this the analysis exists only inside the server: absent from the gate, from
	@# RUN.md and from the report. A dimension that ran and left no artifact is indistinguishable
	@# from one that never ran, which is the failure this lab keeps insisting must not happen.
	@tools/sonar-sarif.py $(REPORTS)/sonar
	@tools/stamp.sh "$(TARGET)" sonar || true
	@# El servidor ya cumplio: el analisis vive en sonar.sarif y en issues.json. Dejarlo encendido
	@# cuesta tres procesos JVM (web, compute engine y Elasticsearch) que siguen compitiendo por la
	@# RAM del operador hasta el proximo `make down` — y en una maquina de 15 GB con un navegador y
	@# un editor abiertos, eso fue una congelacion de 21 minutos y un OOM kill sobre VSCode.
	@# `stop`, no `down`: el volumen sobrevive, asi que la siguiente corrida no reindexa desde cero.
	@# SONAR_KEEP=1 lo deja arriba para consultar la interfaz en 127.0.0.1:$(SONAR_PORT).
	@if [ -z "$(SONAR_KEEP)" ]; then \
	  $(DC) --profile static stop sonarqube >/dev/null 2>&1 && \
	  echo "sonar: servidor detenido (SONAR_KEEP=1 para dejarlo arriba)"; \
	fi

qodana: guard     ##[code] JetBrains Qodana (linter resuelto desde LANGS; QODANA_IMAGE lo fija a mano)
	@# Antes: `QODANA_IMAGE=` vacío = salto declarado. Los CUATRO perfiles versionados lo tenían
	@# vacío y la dimensión no corrió jamás en ningún proyecto (reports/*/qodana/report/ vacío).
	@# Un campo obligatorio, a mano, con el nombre exacto de una imagen que además depende de la
	@# licencia, no se rellena nunca. Ahora lo resuelve tools/qodana-image.sh desde LANGS, y el
	@# perfil solo interviene para fijar una imagen concreta o para desactivarlo (QODANA_IMAGE=none).
	@img=$$(tools/qodana-image.sh "$(TARGET)"); \
	if [ -z "$$img" ]; then \
	  echo "qodana: NO DISPONIBLE para este perfil (razón arriba). No es un PASS: run-manifest"; \
	  echo "        y el informe siguen leyendo el artefacto ausente como NO EJECUTADO."; \
	else \
	  QODANA_IMAGE="$$img" tools/run-dimension.sh "$(TARGET)" qodana || true; \
	fi
	@# Mismo criterio que ZAP: Qodana sale != 0 cuando ENCUENTRA cosas (su umbral de fallo), y una
	@# herramienta informa, no juzga —el veredicto es de `make gate`—. Pero "ignora el código de
	@# salida" no puede tapar una herramienta que no corrió, así que el criterio de éxito es el
	@# artefacto. Y sin esta conversión no había artefacto que el gate supiera leer: Qodana dejaba
	@# su HTML y su propio SARIF, el gate no miraba ninguno, y 134 hallazgos medidos sobre
	@# antiplagio no aparecían en el veredicto ni en el informe.
	@tools/qodana-sarif.py $(REPORTS)/qodana || true

static: secrets deps config-scan sbom semgrep qodana sonar  ##[code] every static tool

# ---- runtime-dependent (needs the target's compose.runtime.yml) ----
up: guard         ##[live] start the target's runtime
	$(DC) --profile runtime up -d --build

build: guard      ##[code] the target's production build, if it has one
	@# El servicio de build (por defecto `front-build`) vive en el compose.runtime.yml del target,
	@# porque CÓMO se compila es conocimiento del proyecto. Un perfil de peldaño 2 (apunta a un
	@# despliegue externo) no trae overlay: el build NO APLICA, no es un error —mismo criterio que
	@# api-lint/qodana. Sin esto `make all` moría con "no such service: front-build".
	@svc=$${BUILD_SERVICE:-front-build}; \
	if [ -z "$(RUNTIME)" ] || ! $(DC) config --services 2>/dev/null | grep -qx "$$svc"; then \
	  echo "build: no existe el servicio '$$svc' en un compose.runtime.yml del target — NOT AVAILABLE para este perfil."; \
	else \
	  $(DC) --profile build run --rm "$$svc"; \
	fi

dast: guard require-live       ##[live] OWASP ZAP against the running app
	@# ZAP exits non-zero on plan WARNINGS (an unreachable seed URL, say), which would abort the
	@# pipeline over a note. Same principle as `make gate`: a tool reports, it does not judge.
	@# But "ignore the exit code" must not hide a tool that never ran, so the success criterion
	@# becomes the artifact: ZAP is done when its report exists.
	-@tools/run-dimension.sh "$(TARGET)" zap
	@test -s $(REPORTS)/zap/zap-report.json \
	  || { echo "ZAP produced no report — check permissions on $(REPORTS)/zap and the plan"; exit 1; }
	@# ZAP escribe SU formato, no SARIF. Sin esta conversión el gate cuenta 0 alertas sobre un
	@# informe lleno y estampa PASS — el mismo modo de fallo que sarif_count: aprobar lo que no
	@# se sabe leer. El HTML queda para personas; el SARIF, para el gate y el informe.
	@tools/zap-sarif.py $(REPORTS)/zap || true
	@echo "ZAP report: $(REPORTS)/zap/zap-report.html"

perf: guard require-live       ##[live] k6 load test
	@tools/run-dimension.sh "$(TARGET)" k6

perf-jmeter: guard require-live ##[live] load with an existing JMeter .jmx plan (second engine)
	@# Not a substitute for `perf`. It exists so a team's own .jmx — usually the only executable
	@# description of a realistic journey they have — can be run as authored instead of rewritten.
	@test -f targets/$(TARGET)/jmeter/$${JMETER_PLAN:-plan.jmx} \
	  || { echo "no plan at targets/$(TARGET)/jmeter/ — JMeter measures nothing without one."; \
	       echo "NOT AVAILABLE for this profile (which is not the same as 'no findings')."; exit 2; }
	@# JMeter refuses to start when results.jtl already exists ("is not empty") and refuses to
	@# write into a non-empty -o directory. Both abort the run BEFORE any request is made, so the
	@# previous run's numbers stay on disk and the operator reads a stale report as a fresh one.
	@rm -rf $(REPORTS)/jmeter/results.jtl $(REPORTS)/jmeter/html
	@tools/run-dimension.sh "$(TARGET)" jmeter
	@echo "JMeter report: $(REPORTS)/jmeter/html/index.html"

api-lint: guard   ##[code] Spectral: is the OpenAPI description itself sound
	@# The spec is part of the repository, so this needs no running app. Absent spec = the
	@# dimension is NOT AVAILABLE, which the manifest records differently from NOT RUN.
	@# Se lee con tools/envget.sh, NO con un sed en linea: ese sed ignoraba target.env.local, que
	@# es justo donde el laboratorio documenta que van los valores del despliegue real. Con el spec
	@# declarado en el .local, este goal respondia "no publica OpenAPI" y la dimension se reportaba
	@# NO DISPONIBLE teniendo el documento delante.
	@if [ -z "$$(tools/envget.sh $(TARGET) OPENAPI_SPEC)$$(tools/envget.sh $(TARGET) OPENAPI_SPEC_URL)" ]; then \
	  echo "api-lint: OPENAPI_SPEC is empty — this project publishes no OpenAPI document."; \
	  echo "          NOT AVAILABLE, not skipped: there is nothing to lint."; \
	else \
	  spec="$$(tools/envget.sh $(TARGET) OPENAPI_SPEC)"; \
	  [ -n "$$spec" ] || spec="$$(tools/envget.sh $(TARGET) OPENAPI_SPEC_URL)"; \
	  OPENAPI_SPEC="$$spec" tools/run-dimension.sh "$(TARGET)" api-lint || true; \
	  test -s $(REPORTS)/api/spectral.sarif \
	    || { echo "api-lint: no spectral.sarif — the dimension did NOT run"; exit 1; }; \
	fi
	@# Spectral exits != 0 when it FINDS things (--fail-severity error). Same rule as every other
	@# tool here: a tool reports, `make gate` judges. Letting the exit code through aborted
	@# `make static` on a spec with findings — which is precisely the spec worth auditing. The
	@# success criterion is the artifact, so a tool that genuinely failed still stops the run.

api-fuzz: guard require-live   ##[live] Schemathesis: does the API obey its own contract
	@# Schemathesis sale != 0 cuando ENCUENTRA violaciones de contrato, que es justo el caso que
	@# interesa auditar. Dejar pasar ese codigo abortaba el goal sobre una corrida CORRECTA: la
	@# herramienta informa, `make gate` juzga — la misma regla que ya siguen zap, qodana y
	@# api-lint. El criterio de exito es el ARTEFACTO, asi que una herramienta que fallo de verdad
	@# (sin dejar XML) sigue deteniendo la corrida.
	@if [ -z "$$(tools/envget.sh $(TARGET) OPENAPI_SPEC)$$(tools/envget.sh $(TARGET) OPENAPI_SPEC_URL)" ]; then \
	  echo "api-fuzz: no OPENAPI_SPEC / OPENAPI_SPEC_URL — NOT AVAILABLE for this profile."; \
	else \
	  tools/run-dimension.sh "$(TARGET)" api-fuzz || true; \
	  test -s $(REPORTS)/api/schemathesis.xml \
	    || { echo "api-fuzz: no schemathesis.xml — la dimension NO se ejecuto"; exit 1; }; \
	fi

device-e2e: guard  ##[live] the app on a real device, journey by journey (adb, host tooling)
	@# The one dimension that is not hermetic: the phone is attached to this machine. Everything
	@# else measures a server; this measures what the user's session actually does over time —
	@# idle, logout, re-login rate limits, cleared data. Needs a TTY: it is conducted, not run.
	@tools/device-e2e.sh "$(TARGET)"

e2e: guard require-live require-auth  ##[live] Playwright functional / authz flows
	@# require-auth es nuevo y sustituye a la SIEMBRA. El laboratorio creaba las dos cuentas antes
	@# de auditar (seed-users.sh + fixture SQL, 407 lineas, ya eliminadas): una matriz de
	@# autorizacion sobre cuentas fabricadas por el propio laboratorio mide el accesorio, no el
	@# control de acceso del sistema. Ahora las credenciales las entrega el operador QA y se
	@# comprueban ANTES — sin eso, dos credenciales malas producian 30 specs en rojo que se leian
	@# como 30 fallos de autorizacion.
	@tools/run-dimension.sh "$(TARGET)" playwright

budget: guard require-live     ##[live] presupuesto del hilo principal del navegador (R8 3.22)
	$(DC) --profile e2e run --rm playwright sh -c "mkdir -p /run && cp -r /e2e/. /run/ && mkdir -p /run/lib && cp -r /seclab-lib/. /run/lib/ && cd /run && npm init -y >/dev/null 2>&1 && npm i -D @playwright/test@1.49.0 >/dev/null 2>&1 && npx playwright test lib/specs/main-thread-budget.spec.ts --reporter=line"

live: dast perf e2e  ##[live] every dimension that needs the application answering

all: static live  ##[live] full pipeline (bring the application up first)

require-live: guard
	@tools/require-live.sh "$(TARGET)"

require-auth: guard
	@tools/require-auth.sh "$(TARGET)"

# ---- run bookkeeping ----
run-manifest: guard ##[admin] write reports/$(TARGET)/RUN.md (commit, digests, envelope, coverage)
	@tools/run-manifest.sh "$(TARGET)"

gate: guard       ##[admin] exit != 0 when the thresholds in target.env are breached
	@tools/gate.sh "$(TARGET)"

dashboard: guard  ##[admin] build reports/$(TARGET)/index.html — one readable page from every tool
	@tools/dashboard.py "$(TARGET)"

doc-check:        ##[admin] ¿README y MANUAL siguen coincidiendo con lib/dimensions.yml?
	@# La tabla de dimensiones de los documentos era la séptima copia de la misma lista, y
	@# estaba tan desactualizada como las otras seis. Una tabla en un .md envejece más rápido
	@# que el código porque nada falla cuando miente; esto es lo que la hace fallar.
	@tools/doc-check.sh

status: guard     ##[admin] what is up, what has been run, what is missing
	@tools/status.sh "$(TARGET)"

# ---- web interface ----
# Lab-wide, not per target: no TARGET and no --env-file. LAB_DIR must be the lab's absolute
# path on the HOST, because the container mounts itself at that same path (see the ui service).
# Compose validates the WHOLE file even when starting a single service, so the tool services'
# variables must resolve to something syntactically valid. These placeholders are never used:
# no tool service is started by this goal. Without them, an unset SRC_PATH yields the mount
# spec ":/repo:ro" and compose refuses to parse the file at all.
#
# SRC_MOUNT: where the audited checkouts live, mounted read-only so the UI can see them. The
# lab's parent directory by default; override it when your code lives elsewhere:
#   make ui SRC_MOUNT=/home/dev/repos
# Computed with `dirname`, not with make's $(dir ...): make's text functions split their argument
# on whitespace, so a lab living under a path with spaces would come out as five separate words.
SRC_MOUNT ?= $(shell dirname "$(CURDIR)")

# The UI runs as the operator so the files it creates stay editable from the host, plus the
# docker socket's group so it can still reach the daemon.
UI_UID     = $(shell id -u)
UI_GID     = $(shell id -g)
DOCKER_GID = $(shell stat -c '%g' /var/run/docker.sock 2>/dev/null || echo 999)

UI_DC = LAB_DIR="$(CURDIR)" SRC_MOUNT="$(SRC_MOUNT)" SRC_PATH="$(CURDIR)" TARGET_NAME=_ui \
        UI_UID="$(UI_UID)" UI_GID="$(UI_GID)" DOCKER_GID="$(DOCKER_GID)" \
        APP_INTERNAL_URL=http://unused docker compose -f docker-compose.yml --profile ui

ui:               ##[admin] start the local web interface on 127.0.0.1 (holds the Docker socket)
	@$(UI_DC) up -d --build ui
	@tools/ui-check-bind.sh
	@echo ""
	@echo "  QA-harness:  http://127.0.0.1:$${UI_PORT:-7777}"
	@echo "  Solo para este equipo. No la publiques: tiene el socket de Docker."
	@echo ""

ui-stop:          ##[admin] stop the web interface
	@$(UI_DC) down

ui-logs:          ##[admin] follow the web interface's own log
	@$(UI_DC) logs -f ui

# ---- teardown ----
down: guard       ##[admin] stop everything and drop volumes (no residue)
	$(DC) --profile clone --profile runtime --profile static --profile build \
	      --profile dast --profile perf --profile e2e --profile prod \
	      down -v --remove-orphans

purge: guard      ##[admin] delete this target's reports (data policy: they may hold real data)
	@echo "Deleting $(REPORTS)/ — this is irreversible."
	@read -p "Type the target name to confirm: " c; test "$$c" = "$(TARGET)" || { echo "aborted"; exit 1; }
	rm -rf $(REPORTS)
