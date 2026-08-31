"""Envuelve `agent.tools.search_documents`/`traverse_graph` como tools de
Strands: acá es donde el loop agéntico deja de ser un pipeline con Strands
encima y pasa a ser el modelo el que decide CUÁNDO llamar cada una y CON
QUÉ argumentos (qué `target` ancla la búsqueda, si hace falta navegar el
grafo y desde qué entidad).

Las dos tools devuelven texto plano (lo que el modelo necesita leer para
redactar) pero ADEMÁS acumulan la `Evidence` real en un `EvidenceCollector`
compartido: es lo que le permite a `agent.gate_hook.CoverageGateHook`
evaluar cobertura con el mismo `agent.gate.evaluate_coverage` que usa el
pipeline fijo, sin tener que re-parsear el string que ya se le mandó al
modelo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from strands import tool
from strands.tools.decorator import DecoratedFunctionTool

from second_brain.agent.tools import Evidence, search_documents, traverse_graph
from second_brain.config import Stack
from second_brain.retrieval import LexicalIndex, resolve_targets


@dataclass
class EvidenceCollector:
    """Acumula toda la evidencia de este turno agéntico, más el rastro de
    qué `target`/entidad resolvió cada llamada — para que quien orquesta el
    turno (`agent.strands_agent.answer_agentic`) sepa, DESPUÉS de que el
    modelo terminó de decidir, cuál fue el sujeto sobre el que ancló los
    guards de salida (`agent.postprocess.apply_guards`), sin tener que
    resolverlo de nuevo por su cuenta.
    """

    items: list[Evidence] = field(default_factory=list)
    resolved_targets: list[str] = field(default_factory=list)

    def add(self, evidence: list[Evidence]) -> None:
        self.items.extend(evidence)

    def register_target(self, target: str | None, stack: Stack) -> None:
        if not target:
            return
        resueltos = resolve_targets(target, stack)
        if resueltos:
            self.resolved_targets = resueltos


def _format_evidence(items: list[Evidence]) -> str:
    if not items:
        return "Sin resultados: no hay evidencia indexada para esta búsqueda."
    return "\n".join(f'[source:{item.doc_id}] "{item.text}"' for item in items)


def build_tools(
    stack: Stack, lexical_index: LexicalIndex, collector: EvidenceCollector
) -> list[DecoratedFunctionTool]:
    """Arma las dos tools del turno, cerradas sobre `stack`/`lexical_index`
    y acumulando en `collector`. Se llama una vez POR TURNO (no se
    reutiliza entre preguntas) porque `collector` es específico de un turno.
    """

    @tool(name="search_documents")
    def _search_documents_tool(question: str, target: str | None = None) -> str:
        """Busca evidencia citable en la base de conocimiento indexada.

        Args:
            question: La pregunta o sub-pregunta a buscar.
            target: Nombre del documento/entidad sobre el que ancla la
                pregunta si la pregunta nombra un sujeto claro (por
                ejemplo 'core-billing', 'reportes-frontend'). Dejalo vacío
                si la pregunta no nombra un sujeto específico.
        """
        collector.register_target(target, stack)
        evidencia = search_documents(question, stack, lexical_index, target=target)
        collector.add(evidencia)
        return _format_evidence(evidencia)

    @tool(name="traverse_graph")
    def _traverse_graph_tool(
        entity: str, kind: str = "blast_radius", max_hops: int = 3
    ) -> str:
        """Recorre el grafo de dependencias de Nexora Corp desde `entity`.

        Args:
            entity: Slug de la entidad raíz del traversal (por ejemplo
                'core-billing', 'auth-cache').
            kind: 'blast_radius' (default, quién depende de `entity`),
                'vecinos' (vecindario directo) o 'camino_entre' (requiere
                pasar también un destino — no soportado desde esta tool,
                usá 'blast_radius' o 'vecinos').
            max_hops: Cuántos saltos como máximo recorrer.
        """
        evidencia = traverse_graph(entity, stack, kind=kind, max_hops=max_hops)
        collector.add(evidencia)
        return _format_evidence(evidencia)

    return [_search_documents_tool, _traverse_graph_tool]
