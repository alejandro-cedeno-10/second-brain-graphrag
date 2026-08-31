# Atajos de la demo — Docker es el camino principal (ver el README y
# `scripts/*.sh`). Ejecutar desde `demo/` (Git Bash / Linux / macOS): los
# scripts que invocan estos targets son `.sh` (POSIX), no PowerShell.
# `make.ps1` sigue existiendo para PowerShell nativo en Windows, pero dejó
# de ser el camino recomendado — usalo solo si de verdad no tenés `make` ni
# una shell POSIX a mano.
#
# El build de las imágenes tarda MÁS DE 9 MINUTOS (llama-index,
# scikit-learn y spacy) — se hace una sola vez, con paciencia, ANTES de
# viajar al venue (`make build` o `docker compose build`), nunca ahí.

.PHONY: build start up down ingest demo test lint demo-aws aws-env web web-dev-api web-dev-ui mcp-server a2a-demo

# Build de TODAS las imágenes (incluidas `a2a`/`mcp`), una sola vez. Correr
# esto ANTES de viajar al venue, con paciencia (>9 minutos, red estable).
build:
	docker compose --profile test --profile web --profile aws --profile a2a --profile mcp build

# El comando del día de la charla: FalkorDB + ingesta + UI web, un solo
# comando, sin reconstruir nada (asume `make build`/`docker compose build`
# ya corrido). Falla con un mensaje claro si falta Docker o si falta
# construir la imagen — nunca con un stacktrace crudo.
start:
	bash scripts/start-demo.sh

up:
	docker compose up -d --build

down:
	docker compose down

ingest:
	docker compose run --rm demo python demo.py ingest

demo:
	@for pregunta in \
		"¿Quién lidera el Proyecto Beta?" \
		"Si modifico la API de core-billing, ¿qué módulos se rompen?" \
		"¿Cuál fue la facturación del Q4 2025?" \
		"¿Quién es la CTO y cuánto gana?" \
		"¿Por qué el frontend de reportes no emite eventos de Amplitude?" ; do \
		echo "" ; \
		echo "==================================================================" ; \
		echo "PREGUNTA: $$pregunta" ; \
		echo "==================================================================" ; \
		docker compose run --rm demo python demo.py query --trace "$$pregunta" ; \
		read -p "-- Presioná ENTER para la próxima pregunta --" _ ; \
	done

test:
	docker compose --profile test run --rm test

lint:
	docker compose --profile test run --rm test python -m ruff check src tests demo.py

# Requiere SECOND_BRAIN_MODE=aws explícito (nunca corre AWS por accidente):
#   SECOND_BRAIN_MODE=aws make demo-aws
demo-aws:
	@if [ "$(SECOND_BRAIN_MODE)" != "aws" ]; then \
		echo "ERROR: make demo-aws requiere SECOND_BRAIN_MODE=aws explícito." ; \
		echo "Uso:   SECOND_BRAIN_MODE=aws make demo-aws" ; \
		exit 1 ; \
	fi
	docker compose --profile aws run --rm demo-aws python demo.py check

# UI de presentación en Docker (FalkorDB + ingesta + web en un solo comando):
# deja todo accesible en http://localhost:8000.
web:
	docker compose --profile web up -d --build web

# UI en modo desarrollo (hot-reload): requiere el venv activado
# (`pip install -e .[web]`) y FalkorDB corriendo (`docker compose up -d falkordb`).
# Corre el backend y el frontend en dos procesos, cada uno en su terminal:
#   make web-dev-api   # terminal 1: FastAPI con --reload en :8000
#   make web-dev-ui    # terminal 2: Vite dev server en :5173 (proxy a :8000)
web-dev-api:
	python -m uvicorn web.api:app --reload --port 8000

web-dev-ui:
	cd web/ui && pnpm install && pnpm run dev

# Post-deploy: lee los outputs de CloudFormation de los 4 stacks (ya
# desplegados con `cdk deploy --all` en infra/) y escribe demo/.env con
# SECOND_BRAIN_MODE=aws. Ver infra/README.md.
aws-env:
	cd infra && python despues-del-deploy.py --out ../.env

# El second brain como servidor MCP, en Docker, por `streamable-http`
# (perfil `mcp`, puerto 8765) — ver `scripts/run-mcp-server.sh`. El
# transporte `stdio` (el que espera un cliente de escritorio como Claude
# Code) sigue siendo un proceso local fuera de Docker: `<venv>/bin/python
# demo.py mcp-server` (ver el bloque de configuración en el README), no
# este target.
mcp-server:
	bash scripts/run-mcp-server.sh

# La demo de cierre A2A, en Docker: DOS contenedores reales (servidor A2A +
# "agente de soporte" cliente, perfil `a2a`), 100% offline — ver
# `scripts/run-a2a-demo.sh`.
a2a-demo:
	bash scripts/run-a2a-demo.sh
