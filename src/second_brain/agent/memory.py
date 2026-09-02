"""Cablea `ports.MemoryPort` al agente: fail-open, formateo del bloque de
texto que ve el modelo, y el addendum de prompt que le explica las reglas.

Único lugar donde `agent.strands_tools`/`agent.strands_agent` tocan
`stack.memory` directamente — así el fail-open (una falla de red/permisos
JAMÁS puede tumbar un turno, invariante de la charla) y el formateo de
recuerdos viven en un solo sitio, sin que cada llamador tenga que repetir
el mismo `try/except`.

`recall_memory_fail_open`/`remember_turn_fail_open` están escritas para
servir a CUALQUIER camino del agente (el agéntico las usa hoy desde la
tool `recall_memory` de `agent.strands_tools`; el pipeline fijo podría
encadenarlas igual el día que se cablee memoria ahí) — por eso reciben
`trace` explícito en vez de asumir un hook que lo escriba por ellas.
"""

from __future__ import annotations

import logging

from second_brain.config import Stack
from second_brain.ports import MemoryHint, TraceStep

_LOGGER = logging.getLogger(__name__)

MEMORY_PROMPT_ADDENDUM = """

MEMORIA (una tercera herramienta, `recall_memory`): trae recuerdos de \
turnos anteriores de esta sesión y del perfil del actor (hechos guardados, \
preferencias declaradas). Llamala ANTES de `search_documents`/\
`traverse_graph` cuando la pregunta dependa de contexto conversacional (una \
referencia anafórica como "eso", "el mismo", "como dijimos antes") o pueda \
estar sujeta a una preferencia declarada.

REGLA NO NEGOCIABLE SOBRE MEMORIA: lo que devuelve `recall_memory` es una \
PISTA, JAMÁS EVIDENCIA. Nunca la cites con `[source:...]`, nunca la \
presentes como si viniera de la base de conocimiento indexada, y nunca uses \
SOLO un recuerdo para sostener una afirmación — toda afirmación sigue \
necesitando su propia evidencia real de `search_documents`/`traverse_graph`. \
Un "hecho" recordado puede ser FALSO (nadie lo verificó todavía): tratalo \
igual que cualquier otra afirmación relacional de tu propia prosa, sujeta al \
mismo escrutinio.

Una PREFERENCIA recordada puede cambiar el FORMATO de tu respuesta (más \
corta, en viñetas, sin jerga técnica, en otro idioma, etc.) — NUNCA los \
hechos que afirmás ni las citas que usás.\
"""
"""Se concatena a `AGENTIC_SYSTEM_PROMPT` SOLO cuando la memoria está activa
para este turno (`stack.memory` configurado + `actor_id`/`session_id`
explícitos — ver `agent.strands_agent.answer_agentic`): la constante del
prompt base nunca se edita in-place, así que con memoria apagada la salida
sigue siendo byte a byte la de hoy.
"""

_KIND_LABEL_ES = {
    "hecho": "LTM hechos",
    "preferencia": "LTM preferencias",
    "turno_stm": "STM sesión",
}


def format_memory_hints(hints: list[MemoryHint]) -> str:
    """Arma el bloque de texto que lee el modelo, en el mismo espíritu que
    `agent.strands_tools._format_evidence` pero con la etiqueta `[origen]`
    en vez de `[source:doc_id]` a propósito: ningún recuerdo debe poder
    confundirse con una marca de cita real, ni para el modelo ni para un
    regex de guard (`agent.guards._CITATION_PATTERN` busca literalmente
    `source:`).
    """
    if not hints:
        return "Sin recuerdos: no hay memoria guardada para este actor/sesión."
    return "\n".join(
        f'[{_KIND_LABEL_ES.get(hint.kind, hint.kind)}] "{hint.text}"' for hint in hints
    )


def recall_memory_fail_open(
    stack: Stack, actor_id: str, session_id: str, query: str, trace: list[TraceStep]
) -> list[MemoryHint]:
    """`stack.memory.recall(...)` degradado a "sin recuerdos" ante cualquier falla.

    Solo traza acá la rama de ERROR (`herramienta.recordar_memoria.error`):
    la línea de ÉXITO la arma quien orquesta el turno con el formato visual
    que le corresponda a ese camino (en el agéntico,
    `agent.tool_trace_hook.ToolTraceHook`, igual que para
    `search_documents`/`traverse_graph`) — apendearla también acá
    duplicaría la línea en la traza del camino agéntico.

    Si `stack.memory` es `None` (memoria apagada o sin configurar) esto es
    un no-op que devuelve `[]` sin loguear nada: no es una falla, es el
    estado por default.
    """
    if stack.memory is None:
        return []
    try:
        return stack.memory.recall(actor_id, session_id, query)
    except Exception as error:
        _LOGGER.warning(
            "recall_memory_fail_open: fallo recuperando memoria (actor=%r, sesión=%r): %s",
            actor_id,
            session_id,
            error,
        )
        trace.append(
            TraceStep(
                stage="herramienta.recordar_memoria.error",
                detail=f"memoria no disponible, degradando a sin recuerdos: {error}",
            )
        )
        return []


def remember_turn_fail_open(
    stack: Stack,
    actor_id: str,
    session_id: str,
    question: str,
    answer_text: str,
    trace: list[TraceStep],
) -> None:
    """Guarda el turno (pregunta + respuesta) para que una sesión futura lo
    pueda recordar — fail-open, nunca tumba el turno actual.

    EVENTUALMENTE CONSISTENTE en AgentCore Memory real: un `CreateEvent`
    que vuelve exitoso no garantiza que un `recall` INMEDIATAMENTE después
    (mismo turno, turno siguiente en la misma sesión, o la extracción a LTM
    de hechos/preferencias) ya lo vea — la escritura y la extracción son
    asíncronas del lado del servicio. Este turno queda guardado igual;
    simplemente no asumas que es recuperable de inmediato. `FakeMemoryStore`
    (modo local) sí ve su propio escrito al instante porque es RAM del
    mismo proceso — la inconsistencia es una propiedad del backend real, no
    algo que el puerto simule a propósito.
    """
    if stack.memory is None:
        return
    try:
        stack.memory.remember_turn(actor_id, session_id, question, answer_text)
    except Exception as error:
        _LOGGER.warning(
            "remember_turn_fail_open: fallo guardando turno (actor=%r, sesión=%r): %s",
            actor_id,
            session_id,
            error,
        )
        trace.append(
            TraceStep(
                stage="memoria.guardado.error",
                detail=f"no se pudo guardar el turno: {error}",
            )
        )
        return
    trace.append(
        TraceStep(
            stage="memoria.guardado",
            detail=f"turno guardado (actor={actor_id}, sesión={session_id})",
        )
    )
