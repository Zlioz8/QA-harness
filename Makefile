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
RUNTIME  = $(wildcard $(T)/compose.runtime.yml)
RUNTIME_F= $(if $(RUNTIME),-f $(RUNTIME),)
DC       = docker compose --env-file $(ENVFILE) -f docker-compose.yml $(RUNTIME_F)
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
	          $(REPORTS)/qodana $(REPORTS)/zap $(REPORTS)/k6 $(REPORTS)/playwright $(REPORTS)/build

.PHONY: help list new detect doctor guard clone up down purge status gate dashboard run-manifest \
        sonar qodana semgrep secrets deps config-scan image-scan sbom static \
        build dast perf e2e all

help:             ## show this list
	@grep -hE '^[a-z0-9_-]+:.*?##' $(MAKEFILE_LIST) | sort | awk 'BEGIN{FS=":.*?## "};{printf "  \033[36m%-14s\033[0m %s\n",$$1,$$2}'
	@echo ""
	@echo "  Targets available: $$(ls targets | tr '\n' ' ')"

list:             ## list target profiles
	@ls targets

# ---- onboarding a new project ----
new:              ## scaffold targets/$(TARGET) from the template
	@tools/new-target.sh "$(TARGET)"

detect:           ## sniff the source tree and propose target.env values
	@tools/detect.sh "$(TARGET)"

doctor: guard     ## preflight: docker, disk, free ports, reports permissions
	@tools/doctor.sh "$(TARGET)"

# ---- source ----
clone: guard      ## fetch REPO_URL@BRANCH into work/$(TARGET) (only if SRC_PATH is not local)
	$(DC) --profile clone run --rm clone

# ---- static analysis: works with NO running app ----
secrets: guard    ## gitleaks + trufflehog over the full git history
	$(DC) --profile static run --rm gitleaks
	$(DC) --profile static run --rm trufflehog

deps: guard       ## Trivy filesystem scan (dependency CVEs + secrets + misconfig)
	$(DC) --profile static run --rm trivy

config-scan: guard ## Trivy over the target's own Dockerfiles / compose / k8s
	$(DC) --profile static run --rm trivy-config

image-scan: guard ## Trivy over a built image:  make image-scan TARGET=x IMAGE=repo:tag
	IMAGE=$(IMAGE) $(DC) --profile static run --rm trivy-image

sbom: guard       ## Syft SBOM + licences
	$(DC) --profile static run --rm syft

semgrep: guard    ## polyglot SAST with taint tracking
	$(DC) --profile static run --rm semgrep

sonar: guard      ## SonarQube server + scanner
	$(DC) --profile static up -d sonarqube
	$(DC) --profile static run --rm sonar-scanner

qodana: guard     ## JetBrains Qodana (image chosen by QODANA_IMAGE in target.env)
	$(DC) --profile static run --rm qodana

static: secrets deps config-scan sbom semgrep qodana sonar  ## every static tool

# ---- runtime-dependent (needs the target's compose.runtime.yml) ----
up: guard         ## start the target's runtime
	$(DC) --profile runtime up -d --build

build: guard      ## the target's production build, if it has one
	$(DC) --profile build run --rm front-build

dast: guard       ## OWASP ZAP against the running app
	@# ZAP exits non-zero on plan WARNINGS (an unreachable seed URL, say), which would abort the
	@# pipeline over a note. Same principle as `make gate`: a tool reports, it does not judge.
	@# But "ignore the exit code" must not hide a tool that never ran, so the success criterion
	@# becomes the artifact: ZAP is done when its report exists.
	-$(DC) --profile dast run --rm zap
	@test -s $(REPORTS)/zap/zap-report.json \
	  || { echo "ZAP produced no report — check permissions on $(REPORTS)/zap and the plan"; exit 1; }
	@echo "ZAP report: $(REPORTS)/zap/zap-report.html"

perf: guard       ## k6 load test
	$(DC) --profile perf run --rm k6

e2e: guard        ## Playwright functional / authz flows
	$(DC) --profile e2e run --rm playwright

all: static dast perf e2e  ## full pipeline (run `make up` first)

# ---- run bookkeeping ----
run-manifest: guard ## write reports/$(TARGET)/RUN.md (commit, digests, envelope, coverage)
	@tools/run-manifest.sh "$(TARGET)"

gate: guard       ## exit != 0 when the thresholds in target.env are breached
	@tools/gate.sh "$(TARGET)"

dashboard: guard  ## build reports/$(TARGET)/index.html — one readable page from every tool
	@tools/dashboard.py "$(TARGET)"

status: guard     ## what is up, what has been run, what is missing
	@tools/status.sh "$(TARGET)"

# ---- teardown ----
down: guard       ## stop everything and drop volumes (no residue)
	$(DC) --profile clone --profile runtime --profile static --profile build \
	      --profile dast --profile perf --profile e2e --profile prod \
	      down -v --remove-orphans

purge: guard      ## delete this target's reports (data policy: they may hold real data)
	@echo "Deleting $(REPORTS)/ — this is irreversible."
	@read -p "Type the target name to confirm: " c; test "$$c" = "$(TARGET)" || { echo "aborted"; exit 1; }
	rm -rf $(REPORTS)
