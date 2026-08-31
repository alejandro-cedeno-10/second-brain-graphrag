#!/usr/bin/env bash
# Funciones compartidas por los demás scripts de `demo/scripts/`. Se importa
# con `source scripts/_lib.sh`, nunca se ejecuta directo — por eso no lleva
# permiso +x. Todo lo que valida "¿está el entorno listo?" vive acá una sola
# vez: los tres scripts que arrancan procesos (`start-demo.sh`,
# `run-a2a-demo.sh`, `run-mcp-server.sh`) se corren en vivo, bajo presión, el
# día de la charla — necesitan fallar con un mensaje claro, no con un
# stacktrace, si falta Docker, si falta una imagen sin construir o si la
# ingesta nunca corrió.

set -euo pipefail

SCRIPT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(cd "${SCRIPT_LIB_DIR}/.." && pwd)"
readonly SCRIPT_LIB_DIR DEMO_DIR

if [ -t 1 ]; then
    readonly _COLOR_RED=$'\033[0;31m'
    readonly _COLOR_YELLOW=$'\033[0;33m'
    readonly _COLOR_GREEN=$'\033[0;32m'
    readonly _COLOR_CYAN=$'\033[0;36m'
    readonly _COLOR_RESET=$'\033[0m'
else
    readonly _COLOR_RED="" _COLOR_YELLOW="" _COLOR_GREEN="" _COLOR_CYAN="" _COLOR_RESET=""
fi

log_info() { printf '%s\n' "$*"; }
log_step() { printf '%s==> %s%s\n' "${_COLOR_CYAN}" "$*" "${_COLOR_RESET}"; }
log_ok() { printf '%s✔ %s%s\n' "${_COLOR_GREEN}" "$*" "${_COLOR_RESET}"; }
log_warn() { printf '%s⚠ %s%s\n' "${_COLOR_YELLOW}" "$*" "${_COLOR_RESET}" >&2; }
log_error() { printf '%s✘ %s%s\n' "${_COLOR_RED}" "$*" "${_COLOR_RESET}" >&2; }

fail() {
    log_error "$1"
    exit "${2:-1}"
}

# Envoltorio de `docker compose` que siempre apunta al compose file de
# `demo/`, sin importar desde qué directorio se haya invocado el script.
compose() {
    docker compose --project-directory "${DEMO_DIR}" -f "${DEMO_DIR}/docker-compose.yml" "$@"
}

require_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        fail "No se encontró el comando 'docker'. Instalá Docker Desktop (o el motor de Docker) antes de seguir: https://docs.docker.com/get-docker/"
    fi
    if ! docker info >/dev/null 2>&1; then
        fail "Docker no está corriendo (o esta terminal no tiene permisos para hablarle). Abrí Docker Desktop y esperá a que termine de iniciar, después volvé a correr este script."
    fi
    if ! docker compose version >/dev/null 2>&1; then
        fail "Falta el plugin 'docker compose' (Compose v2). Actualizá Docker Desktop o instalá el plugin: https://docs.docker.com/compose/install/"
    fi
}

# Corta con un mensaje accionable en vez de dejar que `docker compose`
# arranque un build de >9 minutos a mitad de una demo en vivo. El build se
# hace UNA VEZ, con paciencia, ANTES de viajar al venue — nunca ahí.
require_image() {
    local image="$1"
    local build_hint="$2"
    if ! docker image inspect "$image" >/dev/null 2>&1; then
        log_error "Falta la imagen '${image}' — todavía no se construyó."
        log_error "El build tarda MÁS DE 9 MINUTOS (llama-index, scikit-learn y spacy son pesados) — hacelo una sola vez, con paciencia, y siempre ANTES de viajar al venue, nunca ahí:"
        log_error ""
        log_error "    ${build_hint}"
        log_error ""
        exit 1
    fi
}

# Espera a que un servicio con healthcheck definido en docker-compose.yml
# quede 'healthy'. Falla rápido y con logs a mano si el servicio ya está
# corriendo y quedó 'unhealthy' — no tiene sentido seguir esperando.
wait_service_healthy() {
    local service="$1"
    local timeout_seconds="${2:-180}"
    local elapsed=0
    local status state

    log_step "Esperando a que '${service}' esté sano (hasta ${timeout_seconds}s)..."
    while true; do
        # `--all`: `docker compose ps` sin esa bandera NO lista contenedores
        # parados — un `mcp-server`/`a2a-server` que se cayó (falló su
        # `ingest`) queda invisible para este chequeo sin `--all`, y el
        # script espera el timeout entero en vez de fallar rápido con el log
        # a mano (bug real, encontrado corriendo esto con FalkorDB
        # inalcanzable a propósito).
        state="$(compose ps --all --format '{{.State}}' "$service" 2>/dev/null || true)"
        if [ "$state" = "exited" ] || [ "$state" = "dead" ]; then
            log_error "'${service}' se cayó antes de quedar sano — probablemente falló la ingesta (¿corpus montado? ¿FalkorDB alcanzable?) o el arranque del proceso. Últimas líneas de su log:"
            compose logs --tail 20 "$service" >&2 || true
            exit 1
        fi

        status="$(compose ps --all --format '{{.Health}}' "$service" 2>/dev/null || true)"
        if [ "$status" = "healthy" ]; then
            log_ok "'${service}' está sano."
            return 0
        fi
        if [ "$status" = "unhealthy" ]; then
            log_error "'${service}' arrancó pero su healthcheck quedó en 'unhealthy'. Últimas líneas de su log:"
            compose logs --tail 20 "$service" >&2 || true
            exit 1
        fi

        if [ "$elapsed" -ge "$timeout_seconds" ]; then
            fail "'${service}' no quedó sano después de ${timeout_seconds}s. Mirá qué pasó: docker compose logs ${service}"
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
}
