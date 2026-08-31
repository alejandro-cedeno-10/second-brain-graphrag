#!/usr/bin/env bash
# Levanta el second brain como servidor MCP por `streamable-http` (perfil
# `mcp` de docker-compose.yml) — el transporte que sirve para un cliente MCP
# que hable HTTP contra un contenedor, a diferencia de `stdio` (el default
# de `demo.py mcp-server`), que solo tiene sentido cuando el propio cliente
# lanza el proceso como subproceso local y le habla por su stdin/stdout.
#
# Uso:
#   scripts/run-mcp-server.sh
#
# Para un cliente MCP LOCAL (Claude Code u otro cliente de escritorio) NO
# uses este script ni este servicio: usá el transporte `stdio` apuntando
# directo al proceso, sin Docker de por medio — ver el bloque de
# configuración de `.mcp.json` en el README.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

log_step "Second Brain GraphRAG — servidor MCP (streamable-http)"

require_docker
require_image "second-brain-demo:local" "docker compose build mcp-server"

log_step "Levantando FalkorDB..."
compose up -d falkordb
wait_service_healthy falkordb 60

log_step "Levantando el servidor MCP (corre su propia ingesta antes de servir, es idempotente)..."
compose up -d mcp-server
wait_service_healthy mcp-server 180

log_ok "Servidor MCP arriba: streamable-http en http://localhost:8765/mcp"
log_info ""
log_info "Round-trip real contra este endpoint (tools/list + tools/call): con el SDK 'mcp'"
log_info "(mcp.client.streamable_http.streamablehttp_client) o cualquier cliente que hable"
log_info "streamable-http. Este servidor NO habla stdio — no sirve para un cliente MCP de"
log_info "escritorio (Claude Code) apuntándole directo; para eso, fuera de Docker:"
log_info "  <python del venv> demo.py mcp-server        # stdio, el default"
log_info ""
log_info "Logs en vivo:  docker compose logs -f mcp-server"
log_info "Apagarlo:      docker compose stop mcp-server     # o: docker compose down"
