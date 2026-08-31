# Multi-stage: `base` instala solo las dependencias de runtime (sin boto3,
# sin pytest/ruff) para que la imagen que corre la demo en vivo sea chica y
# no cargue nada que el modo local no necesita. `test` y `aws` extienden
# `base` con sus propios extras — cada uno paga solo el peso que usa.
#
# El GraphRAG Toolkit de AWS Labs (`graphrag-lexical-graph`, PyPI real —
# ver SPIKE_COMPATIBILIDAD.md §1) y su contrib de FalkorDB (git, no PyPI)
# viven en `base` para que TODAS las imágenes (runtime/test/aws/web) corran
# de verdad sobre el toolkit, no como un opcional aparte. Si esta capa
# fallara (sin red el día de la charla), `adapters/graphrag_toolkit.py`
# cae solo al cliente `falkordb` directo — la imagen sigue sirviendo la
# demo igual, no es un punto único de falla del build.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

WORKDIR /app

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin demo

RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir . \
    && pip install --no-cache-dir ".[graphrag]" \
    && pip install --no-cache-dir hatchling hatch-requirements-txt \
    && pip install --no-cache-dir --no-build-isolation \
        "git+https://github.com/awslabs/graphrag-toolkit.git@218bf37382412cd1ff72d8a5f64755c012976bb4#subdirectory=lexical-graph-contrib/falkordb"

FROM base AS runtime

COPY demo.py ./
COPY corpus ./corpus

RUN mkdir -p /app/.data && chown -R demo:demo /app

USER demo

ENV SECOND_BRAIN_MODE=local

CMD ["python", "demo.py", "--help"]

FROM base AS test

RUN pip install --no-cache-dir .[dev]

COPY demo.py ./
COPY tests ./tests
COPY corpus ./corpus

RUN mkdir -p /app/.data && chown -R demo:demo /app

USER demo

CMD ["python", "-m", "pytest", "-v"]

FROM base AS aws

RUN pip install --no-cache-dir .[aws]

COPY demo.py ./
COPY corpus ./corpus

RUN mkdir -p /app/.data && chown -R demo:demo /app

USER demo

ENV SECOND_BRAIN_MODE=aws

CMD ["python", "demo.py", "--help"]

# Imagen para AgentCore Runtime (`infra/stacks/agentcore_stack.py`).
# El contrato del Runtime con protocolo MCP: contenedor linux/arm64 (AgentCore
# solo acepta ARM64 — buildear con `docker buildx --platform linux/arm64`),
# escuchando en 0.0.0.0:8000 con el endpoint MCP en /mcp (el default de
# FastMCP streamable-http). Modo aws: el bucket/indice de S3 Vectors llegan
# por variables de entorno declaradas en el propio Runtime (CDK).
FROM aws AS agentcore

EXPOSE 8000

CMD ["python", "demo.py", "mcp-server", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]

# `a2a-server`/`a2a-client` (docker-compose.yml, perfil `a2a`) necesitan
# `a2a-sdk`, que NO llega transitivo de `strands-agents` base (a diferencia
# de `mcp`, por eso `mcp-server` corre sobre la imagen `runtime` sin este
# stage) — de ahí el extra `[a2a]` propio, mismo patrón que `test`/`aws`.
FROM base AS a2a

RUN pip install --no-cache-dir .[a2a]

COPY demo.py ./
COPY corpus ./corpus

RUN mkdir -p /app/.data && chown -R demo:demo /app

USER demo

ENV SECOND_BRAIN_MODE=local

CMD ["python", "demo.py", "--help"]

# Build de producción de la UI en una etapa Node separada: el resultado
# (`dist/`, HTML/JS/CSS estático) es lo único que cruza a la imagen Python
# final, sin arrastrar `node_modules` ni el toolchain de Vite a runtime.
FROM node:20-slim AS ui-build

WORKDIR /ui

RUN corepack enable && corepack prepare pnpm@9 --activate

COPY web/ui/package.json web/ui/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY web/ui ./
RUN pnpm run build

FROM base AS web

RUN pip install --no-cache-dir .[web]

COPY demo.py ./
COPY corpus ./corpus
COPY web/__init__.py web/api.py ./web/
COPY --from=ui-build /ui/dist ./web/ui/dist

RUN mkdir -p /app/.data && chown -R demo:demo /app

USER demo

ENV SECOND_BRAIN_MODE=local

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "web.api:app", "--host", "0.0.0.0", "--port", "8000"]
