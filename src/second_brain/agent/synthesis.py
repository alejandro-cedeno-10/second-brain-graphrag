"""EL PATRÓN 3: anclaje al sujeto.

Un LLM al que se le da evidencia desigual sobre varios sujetos tiende a
pivotear en silencio hacia el que tiene MÁS evidencia, aunque no sea el
sujeto preguntado — es la trampa que la P5 de la demo está diseñada para
tentar (`reportes-frontend` tiene un documento corto; `dashboard` y
`onboarding` tienen catálogos enteros de eventos de la misma herramienta de
analítica). Este módulo pelea esa tendencia en dos frentes:

1. `SYSTEM_SYNTHESIS` (constante de módulo, nunca formateada por turno) le
   pone nombre a la regla y la ilustra con un ejemplo MAL y dos BIEN —
   incluyendo la excepción crítica de preguntas relacionales.
2. `build_user_message` la refuerza estructuralmente: separa la
   evidencia en dos bloques ANTES de que el LLM la vea (evidencia sobre el
   sujeto vs. evidencia de comparación), así que aunque el modelo no siguiera
   la instrucción al pie de la letra, la separación ya está hecha en los
   datos, no solo pedida en el prompt.

`decompose` es el tercer aporte: parte la pregunta en facetas y le pone
sujeto a cada una cuando el texto de la pregunta lo nombra con un patrón
reconocible (kebab-case, nombre propio, sigla). Es deliberadamente ciego a
resolución semántica (no sabe que "el frontend de reportes" es
`reportes-frontend`) — esa resolución ya la hizo `resolve_targets` río
arriba; acá alcanza con no pivotear cuando la pregunta SÍ lo dice explícito.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from second_brain.agent.facets import split_into_facets
from second_brain.agent.gate import Coverage
from second_brain.agent.tools import Evidence

_LOGGER = logging.getLogger(__name__)

SYSTEM_SYNTHESIS = """\
Sos el sintetizador final de un agente GraphRAG. Tu única fuente de verdad \
es la evidencia que te paso en el mensaje del usuario, ya recuperada y \
citada por otras herramientas — no tenés acceso a la base de conocimiento \
por tu cuenta, ni podés completar con un dato que no esté en la evidencia.

FORMATO DE CITA: cada afirmación basada en evidencia lleva inmediatamente \
después la marca `[source:doc_id]`, usando EXACTAMENTE el `doc_id` que \
aparece en el bloque de evidencia — no lo abrevies ni lo inventes. Una \
afirmación sin evidencia que la sostenga no lleva marca; si no tenés \
evidencia para algo, decilo en vez de afirmarlo.

REGLA DE ANCLAJE AL SUJETO (no negociable):

1. Abrí la respuesta con lo que la evidencia SOBRE EL SUJETO PREGUNTADO \
dice, aunque sea poco. El primer párrafo habla del sujeto de la pregunta, \
nunca de otro que tenga más evidencia disponible.
2. Si esa evidencia es delgada, DECILO explícitamente ("en la \
documentación indexada de X solo aparece Y") en vez de pivotear en \
silencio hacia un sujeto distinto que tenga más para decir.
3. La evidencia de OTROS sujetos entra solo como comparación EXPLÍCITAMENTE \
marcada ("a diferencia de...", "mientras que...") — nunca se presenta como \
si respondiera la pregunta original.
4. PROHIBIDO cerrar con "revisá vos el código/la documentación de X" \
cuando el turno YA tiene evidencia citable de X: eso abandona el trabajo \
que la evidencia ya hizo.

LA EXCEPCIÓN CRÍTICA — preguntas relacionales: cuando la pregunta es sobre \
QUIÉN CONSUME, QUÉ SE ROMPE o QUÉ DEPENDE DE algo, el ancla es sobre el \
SUJETO, no sobre en qué documento vive la cita. Lo que un vecino del grafo \
HACE CON el sujeto (lo consume, depende de él, lo llama) es evidencia SOBRE \
el sujeto, no evidencia de otro tema — abrí con eso DIRECTO y SIN marca de \
comparación, aunque la cita venga del documento del vecino.

Ejemplo MAL (rompe el ancla, pivotea en silencio):
  Pregunta: "¿Por qué reportes-frontend no emite eventos de Amplitude?"
  Mal: "Amplitude es el sistema de analítica de Nexora Corp. `dashboard` \
integra Amplitude con un catálogo de 10 eventos [source:frontends/dashboard.md] \
y `onboarding` lo usa para medir el funnel de bienvenida \
[source:frontends/onboarding.md]." — nunca menciona a `reportes-frontend`: \
pivotea hacia los sujetos con más evidencia en vez de responder por el \
sujeto preguntado.

Ejemplo BIEN #1 (ancla + comparación marcada):
  Misma pregunta. Bien: "En la documentación indexada de `reportes-frontend`, \
el tracking se implementa con el composable `useTracking`, que envía \
eventos a Google Tag Manager; no hay ninguna integración con Amplitude \
[source:frontends/reportes-frontend.md]. A diferencia de `dashboard` y \
`onboarding`, que sí integran Amplitude con catálogos extensos de eventos \
[source:frontends/dashboard.md], la decisión de arquitectura (ADR-014) fue \
no adoptarlo ahí por ser una superficie de bajo tráfico \
[source:arquitectura/decisiones.md]."

Ejemplo BIEN #2 (excepción crítica: relacional, sin marca):
  Pregunta: "Si modifico la API de core-billing, ¿qué módulos se rompen?"
  Bien: "Tres módulos consumen `core-billing` y se verían afectados: \
`pagos` llama a `GET /billing/rates` antes de autorizar cobros \
[source:pagos], `notificaciones` depende del evento `billing.updated` \
[source:notificaciones], y `reportes-backend` lo consume directo y también \
de forma transitiva vía `pagos` [source:reportes-backend]." — ningún vecino \
se marca como comparación: lo que hacen CON `core-billing` es la respuesta.

HONESTIDAD: si la evidencia cubre solo una parte de lo preguntado, respondé \
esa parte con su cita y declará explícitamente el vacío ("la base de \
conocimiento indexada no tiene datos de nómina de las personas") en vez de \
inventar un número, un nombre o un hecho que no esté en la evidencia.\
"""


@dataclass
class SubQuestion:
    """Una faceta de la pregunta, con el sujeto que investiga si se lo pudo nombrar."""

    text: str
    subject: str | None = None


_KEBAB_PATTERN = re.compile(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+)+\b")
_PROPER_NOUN_PATTERN = re.compile(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+\b")
_ACRONYM_PATTERN = re.compile(r"\b[A-ZÁÉÍÓÚÑ]{2,6}\b")


def decompose(question: str) -> list[SubQuestion]:
    """Parte `question` en facetas y nombra el sujeto de cada una cuando puede.

    El sujeto se busca primero en la faceta misma; si esa faceta no lo
    nombra pero la pregunta completa sí (p.ej. "¿Quién es la CTO y cuánto
    gana?": la segunda faceta no dice "CTO"), hereda el sujeto global — así
    ninguna faceta que investiga el comportamiento del sujeto se queda sin
    anclar. Si ni la pregunta completa nombra un sujeto reconocible (sin
    resolución semántica: eso es trabajo de `resolve_targets`, no de
    esta función), se deja constancia con un warning de observabilidad y se
    sigue de largo — nunca aborta.
    """
    facetas_texto = split_into_facets(question) or [question]
    sujeto_global = _extract_subject(question)
    subpreguntas = [
        SubQuestion(text=faceta, subject=_extract_subject(faceta) or sujeto_global)
        for faceta in facetas_texto
    ]
    if sujeto_global is None:
        _LOGGER.warning(
            "decompose: ninguna faceta de la pregunta nombra un sujeto "
            "reconocible por patrón (pregunta=%r)",
            question,
        )
    return subpreguntas


def _extract_subject(text: str) -> str | None:
    for patron in (_KEBAB_PATTERN, _PROPER_NOUN_PATTERN, _ACRONYM_PATTERN):
        match = patron.search(text)
        if match:
            return match.group(0)
    return None


def build_user_message(
    question: str,
    evidence: list[Evidence],
    subquestions: list[SubQuestion],
    coverage: Coverage,
) -> str:
    """Arma el mensaje de usuario con la evidencia YA separada por anclaje.

    La separación en dos bloques (sujeto vs. comparación) es la mitad
    estructural del patrón 3: no depende de que el LLM entienda la
    instrucción del system prompt, porque los datos ya vienen partidos así.
    """
    directa = [item for item in evidence if item.is_target]
    comparacion = [item for item in evidence if not item.is_target]
    lineas = [
        f"Pregunta del usuario: {question}",
        "",
        f"Cobertura evaluada por el gate: {coverage.value}",
        "",
        _facets_line(subquestions),
        "",
        "EVIDENCIA SOBRE EL SUJETO PREGUNTADO (abrí la respuesta con esto,",
        "sin marca de comparación):",
        *_format_evidence(directa),
        "",
        "EVIDENCIA DE COMPARACIÓN (otros sujetos — marcá explícitamente como",
        "contraste, nunca como si respondiera la pregunta):",
        *_format_evidence(comparacion),
    ]
    return "\n".join(lineas)


def _facets_line(subquestions: list[SubQuestion]) -> str:
    if not subquestions:
        return "Facetas detectadas: (ninguna)"
    partes = [
        f"{sub.text} (sujeto: {sub.subject})" if sub.subject else sub.text
        for sub in subquestions
    ]
    return "Facetas detectadas: " + "; ".join(partes)


def _format_evidence(items: list[Evidence]) -> list[str]:
    if not items:
        return ["  (sin evidencia en este bloque)"]
    return [f'  [source:{item.doc_id}] "{item.text}"' for item in items]
