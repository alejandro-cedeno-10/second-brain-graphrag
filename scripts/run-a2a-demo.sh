#!/usr/bin/env bash
# La demo de cierre A2A, en un solo comando: levanta el servidor A2A (Agent
# Card + loop agéntico completo) y corre el "agente de soporte" cliente
# contra él, mostrando el intercambio en vivo (descubrimiento de la Agent
# Card, streaming de progreso, respuesta final con sus citas). Los DOS
# procesos corren en contenedores separados (`a2a-server`/`a2a-client`,
# perfil `a2a` de docker-compose.yml), resolviéndose por nombre de servicio
# de compose — nunca por `127.0.0.1`, que dentro de cada contenedor sería él
# mismo.
#
# Uso:
#   scripts/run-a2a-demo.sh
#
# El servidor A2A queda arriba después de correr (para Q&A en vivo con
# `python demo.py a2a-client` apuntando al mismo endpoint, o para otra
# corrida de `docker compose run --rm a2a-client`). Apagarlo con
# `docker compose stop a2a-server` o `docker compose down`.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

log_step "Second Brain GraphRAG — demo de cierre A2A (servidor + agente de soporte)"

require_docker
require_image "second-brain-demo-a2a:local" "docker compose build a2a-server"

log_step "Levantando FalkorDB..."
compose up -d falkordb
wait_service_healthy falkordb 60

log_step "Levantando el servidor A2A (corre su propia ingesta antes de publicar la Agent Card, es idempotente)..."
compose up -d a2a-server
wait_service_healthy a2a-server 180

log_step "Agent Card publicada en http://localhost:9500/.well-known/agent-card.json"
log_step "Corriendo el agente de soporte (segundo proceso) contra el servidor A2A..."
log_info ""

compose run --rm a2a-client

log_info ""
log_ok "Demo A2A terminada."
log_info ""
log_info "El servidor A2A sigue arriba (para Q&A en vivo o para otra pregunta):"
log_info "  docker compose run --rm a2a-client python demo.py a2a-client \"<otra pregunta>\" --endpoint http://a2a-server:9500"
log_info "  docker compose logs -f a2a-server"
log_info "  docker compose stop a2a-server     # o: docker compose down"
