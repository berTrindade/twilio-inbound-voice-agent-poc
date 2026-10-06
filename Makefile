# One command to run the whole thing. See README.md.
COMPOSE := docker compose --env-file .env -f infra/docker-compose.yml

# A container cannot reach the Mac's GPU, so a model inside one runs on CPU:
# 12.8s per turn against 1.7s, measured with `make eval`. Docker Model Runner
# solves it by running the model outside the VM on macOS and in a container
# with CUDA on Linux, so one setup is fast on both.
SMALL_MODEL := ai/qwen2.5:7B-Q4_K_M
BIG_MODEL   := ai/llama3.1:8B-Q4_K_M

DASHBOARD_PORT ?= 3000
RUNNER_PORT    ?= 8080

.DEFAULT_GOAL := help

.env:
	cp .env.example .env

up: .env ## Start everything and pull the models
	@$(MAKE) --no-print-directory model-runner
	$(COMPOSE) up -d --build
	@grep -qE '^LLM_PROVIDER=[[:space:]]*groq' .env 2>/dev/null \
		|| $(MAKE) --no-print-directory models \
		|| echo "  Model pull did not finish. Re-run 'make up' to resume it."
	@$(MAKE) --no-print-directory ready
	@$(MAKE) --no-print-directory seed || true
	@$(MAKE) --no-print-directory urls

# Always printed, even when the model pull above was interrupted: the stack is
# serving either way, and losing these two lines reads as a total failure.
urls:
	@echo ""
	@echo "  Talk to the agent   http://localhost:$(DASHBOARD_PORT)/chat"
	@echo "  Dashboard           http://localhost:$(DASHBOARD_PORT)"
	@echo ""

# The stack can come up and still be unable to answer, because every model
# failure is caught and spoken as "Sorry, I didn't catch that". Saying so here
# is the difference between a broken setup and an agent that looks stupid.
ready:
	@body=""; i=0; \
	while [ $$i -lt 45 ]; do \
		body=$$(curl -sf --max-time 2 http://localhost:$(RUNNER_PORT)/health/ready 2>/dev/null); \
		[ -n "$$body" ] && break; \
		i=$$((i+1)); sleep 2; \
	done; \
	if [ -z "$$body" ]; then \
		echo ""; \
		echo "  The call runner is not answering on :$(RUNNER_PORT)."; \
		echo "  'make logs' will say why. If the port is taken, set RUNNER_PORT in .env."; \
	elif ! echo "$$body" | grep -q '"ready": *true'; then \
		echo ""; \
		echo "  Started, but not ready to take a call:"; \
		echo ""; \
		echo "$$body" | tr ',' '\n' | grep -i 'detail' | sed 's/^[ "]*/      /'; \
		echo ""; \
		echo "  Until that is fixed the agent answers everything with"; \
		echo "  \"Sorry, I didn't catch that\". 'make logs' has the rest."; \
	fi

# Model Runner ships with Docker Desktop, and enabling its TCP port is what lets
# `make eval` reach the same model the containers use. Not fatal if it fails:
# the stack still runs, and the Groq path in .env does not need it at all.
model-runner:
	@docker model status >/dev/null 2>&1 && exit 0; \
	docker desktop enable model-runner --tcp=12434 >/dev/null 2>&1 || { \
		echo ""; \
		echo "  Could not enable Docker Model Runner (it needs Docker Desktop)."; \
		echo "  Everything else still starts, but the agent has no local model to call."; \
		echo "  Either update Docker Desktop, or uncomment the four Groq lines in"; \
		echo "  .env to run the models hosted instead. See README.md."; \
		echo ""; }

models: ## Pull the two models (about 10 GB, first run only)
	@echo "  Pulling about 10 GB of models. Expect 10-40 minutes on a first run."
	@echo "  This happens once. Ctrl-C is safe: 'make up' resumes where it stopped."
	docker model pull $(SMALL_MODEL)
	docker model pull $(BIG_MODEL)

# Runs in the container because that is what can reach Postgres. Idempotent, so
# `make up` calling it is safe on every run, not just the first.
seed: .env ## Write example calls so the dashboard has something to show
	@$(COMPOSE) exec -T voice-agent python -m voice_agent.scripts.demo_data

unseed: .env ## Remove the example calls
	@$(COMPOSE) exec -T voice-agent python -m voice_agent.scripts.demo_data --clear

observability: .env ## Add Grafana, Tempo, Prometheus and Loki on :3001
	COMPOSE_PROFILES=observability \
	OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317 \
	$(COMPOSE) up -d
	@echo "  Grafana   http://localhost:3001"

logs: .env ## Follow the call runner logs
	$(COMPOSE) logs -f voice-agent

ps: .env ## Show what is running
	$(COMPOSE) ps

# COMPOSE_PROFILES so these also catch the optional observability containers.
down: .env ## Stop everything, keep the database
	COMPOSE_PROFILES=observability $(COMPOSE) down --remove-orphans

clean: .env ## Stop everything and delete the data
	COMPOSE_PROFILES=observability $(COMPOSE) down -v --remove-orphans

# These two run on the host rather than in a container, so unlike `make up` they
# need a local Python toolchain. Checked here because the root README promises
# Docker is all you need, which is true of everything except these.
require-poetry:
	@command -v poetry >/dev/null 2>&1 || { \
		echo ""; \
		echo "  'make test' and 'make eval' run on the host, not in Docker, so they"; \
		echo "  need Python 3.13+ and Poetry, then the project's dependencies:"; \
		echo ""; \
		echo "      https://python-poetry.org/docs/#installation"; \
		echo "      cd apps/voice-agent && poetry install"; \
		echo ""; \
		echo "  Nothing else in this repo needs them. 'make up' is Docker only."; \
		echo ""; \
		exit 1; }

test: require-poetry ## Run the call runner test suite
	cd apps/voice-agent && poetry run pytest -q

# Runs on the host, so it reads .env directly rather than through compose.
# Scores whatever LLM_PROVIDER points at, which is the point of it.
eval: .env require-poetry ## Score the small interpreter against the golden battery
	@set -a; . ./.env; set +a; \
	if [ "$$LLM_PROVIDER" != "groq" ]; then \
		url=""; \
		curl -sf --max-time 2 http://localhost:12434/api/tags >/dev/null 2>&1 \
			&& url=http://localhost:12434; \
		[ -n "$$url" ] || { curl -sf --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 \
			&& url=http://127.0.0.1:11434; }; \
		[ -n "$$url" ] || { \
			echo ""; \
			echo "  No model runtime is answering, so every case would score as a"; \
			echo "  failure and look like a bad model rather than a bad URL."; \
			echo ""; \
			echo "  Docker Model Runner needs its TCP port open to be reachable"; \
			echo "  from the host, which is where this eval runs:"; \
			echo ""; \
			echo "      docker desktop enable model-runner --tcp=12434"; \
			echo ""; \
			echo "  Or run it against Groq instead by uncommenting the four Groq"; \
			echo "  lines in .env."; \
			echo ""; \
			exit 1; }; \
		export OLLAMA_BASE_URL=$$url; \
	fi; \
	export SMALL_MODEL_ID=$${SMALL_MODEL_ID:-$(SMALL_MODEL)}; \
	cd apps/voice-agent && poetry run python scripts/llm_eval/run.py $(ARGS)

help:
	@echo ""
	@echo "  make up      first time and every time. Everything else is optional."
	@echo ""
	@grep -hE '^[a-z]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/|/' | awk -F'|' '{printf "  %-10s %s\n", $$1, $$2}'
	@echo ""

.PHONY: up urls ready model-runner models seed unseed observability logs ps down clean require-poetry test eval help
