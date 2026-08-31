#!/usr/bin/env bash
# Arranque completo de la demo, un solo comando: FalkorDB + ingesta del
# corpus + UI web, y te deja con la URL lista. Es el script que se corre el
# día de la charla — asume que las imágenes ya se construyeron ANTES de
# viajar al venue (`docker compose build`, ver el README): NO reconstruye
# nada acá (el build tarda más de 9 minutos, no es algo para arrancar a
# mitad de una demo en vivo).
#
# Uso:
#   scripts/start-demo.sh
#
# Para arrancar de cero (borrando la ingesta/el grafo previos):
#   docker compose down -v && scripts/start-demo.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

log_step "Second Brain GraphRAG — arranque completo (FalkorDB + ingesta + UI web)"

require_docker
require_image "second-brain-demo-web:local" "docker compose build web"

log_step "Levantando FalkorDB y la UI web (la UI corre su propia ingesta al arrancar, es idempotente)..."
compose up -d falkordb web

wait_service_healthy falkordb 60
wait_service_healthy web 180

log_ok "Todo arriba. Abrí la demo en: http://localhost:8000"
log_info ""
log_info "Otros comandos útiles:"
log_info "  docker compose logs -f web     # seguir la ingesta y los logs de la UI en vivo"
log_info "  docker compose down            # apagar todo, conservando la ingesta"
log_info "  docker compose down -v         # apagar y borrar la ingesta/el grafo (arranque limpio la próxima vez)"
