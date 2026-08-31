"""Configura el exporter OTel NATIVO de Strands para el loop agéntico, sin
tocar la traza propia (`agent.trace`/`TraceStep`): las dos coexisten y no
compiten. `TraceStep` sigue alimentando `demo.py --trace` y la UI web
(eventos AG-UI por SSE, ver `web/api.py`) — es la vista pensada para la
demo, con el vocabulario en español del dominio (`gate.cobertura`,
`herramienta.buscar_documentos`, `🔗 anclaje`...). OpenTelemetry es la vista
OPERATIVA que un backend real (CloudWatch GenAI Observability, Jaeger,
cualquier collector OTLP) consumiría en producción, con los spans que
Strands ya genera de fábrica para cada invocación de modelo y cada tool
call. Ninguna reemplaza a la otra.

Variables de entorno (documentadas en `.env.example`):

- `SECOND_BRAIN_OTEL_ENABLED` (`"true"`/`"false"`, default `"false"`):
  prende el exporter. Mientras esté apagado, este módulo ni siquiera
  importa `strands.telemetry` — cero costo si no se usa.
- `SECOND_BRAIN_OTEL_CONSOLE` (`"true"`/`"false"`, default `"false"`):
  además imprime cada span por stdout — útil para ver el árbol de spans en
  un ensayo local sin levantar un collector.
- `OTEL_EXPORTER_OTLP_ENDPOINT`: el env var ESTÁNDAR de OpenTelemetry
  (p.ej. `http://localhost:4318`). Si `SECOND_BRAIN_OTEL_ENABLED=true` y
  este está seteado, los spans se mandan ahí. Sin este env var, el
  exporter OTLP no se registra (evita reintentos de conexión contra un
  endpoint que no existe).

Requiere el extra `strands-agents[otel]` (NO instalado por default: agrega
el exporter OTLP y sus dependencias, que el modo 100% offline no
necesita). Sin ese extra, `SECOND_BRAIN_OTEL_ENABLED=true` deja un warning
en el log y sigue sin exportar nada — nunca rompe el turno ni la traza
propia, fail-open igual que el resto de la capa de observabilidad
(`agent.guards.canary`).
"""

from __future__ import annotations

import logging
import os

_LOGGER = logging.getLogger(__name__)
_ya_configurado = False


def configure_observability() -> None:
    """Idempotente: la primera llamada configura el exporter (si corresponde),
    cualquier llamada posterior es un no-op. Pensada para invocarse una vez
    por proceso desde `agent.strands_agent.answer_agentic`, así que ni la
    CLI ni el backend web tienen que acordarse de llamarla por su cuenta.
    """
    global _ya_configurado
    if _ya_configurado:
        return
    _ya_configurado = True

    if os.environ.get("SECOND_BRAIN_OTEL_ENABLED", "false").strip().lower() != "true":
        return

    try:
        from strands.telemetry import StrandsTelemetry

        telemetry = StrandsTelemetry()
        if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
            telemetry.setup_otlp_exporter()
        if os.environ.get("SECOND_BRAIN_OTEL_CONSOLE", "false").strip().lower() == "true":
            telemetry.setup_console_exporter()
    except ImportError:
        # `strands.telemetry` importa sin el extra `[otel]`, pero
        # `setup_otlp_exporter()` hace el import real (`opentelemetry.exporter...`)
        # recién adentro, al llamarla — por eso el catch envuelve las DOS
        # llamadas, no solo el import de `StrandsTelemetry`.
        _LOGGER.warning(
            "SECOND_BRAIN_OTEL_ENABLED=true pero falta el extra 'strands-agents[otel]' "
            "(pip install 'strands-agents[otel]'); no se exportan trazas OTel. "
            "La traza propia (TraceStep, --trace, UI web) sigue funcionando igual."
        )
