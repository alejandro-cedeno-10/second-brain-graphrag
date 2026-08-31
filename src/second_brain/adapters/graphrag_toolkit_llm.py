"""Shim que envuelve un `LlmPort` propio como LLM de LlamaIndex.

El GraphRAG Toolkit corre sobre LlamaIndex (`Settings.llm`), no conoce
`second_brain.ports.LlmPort`. Este módulo es el único puente entre los dos
mundos: no duplica lógica de generación, solo traduce la llamada.
Vive separado de `graphrag_toolkit.py` para que ese adapter no tenga que
importar `llama_index.core.llms` a nivel de módulo (el import ya es lazy
adentro de la función que lo usa).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from llama_index.core.base.llms.types import CompletionResponse, LLMMetadata
from llama_index.core.llms import CustomLLM

if TYPE_CHECKING:
    from second_brain.ports import LlmPort


class LlmPortAsLlamaIndexLlm(CustomLLM):
    """Adapter mínimo: `LlmPort.generate` detrás de la interfaz `CustomLLM`.

    Solo implementa `complete`/`stream_complete` (síncronos) porque es lo
    que usa el pipeline de extracción del toolkit; no se pretende cubrir la
    superficie completa de LlamaIndex, solo la necesaria para que
    `LexicalGraphIndex.extract_and_build` pueda pedir texto libre.
    """

    llm_port: Any = None
    context_window: int = 8192
    num_output: int = 2048

    def __init__(self, llm_port: LlmPort, **kwargs: Any) -> None:
        super().__init__(llm_port=llm_port, **kwargs)

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(context_window=self.context_window, num_output=self.num_output)

    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        respuesta = self.llm_port.generate(
            system="", messages=[{"role": "user", "content": prompt}]
        )
        return CompletionResponse(text=respuesta.text)

    def stream_complete(self, prompt: str, formatted: bool = False, **kwargs: Any):
        yield self.complete(prompt, formatted=formatted, **kwargs)
