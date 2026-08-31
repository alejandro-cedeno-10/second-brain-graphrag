"""El second brain expuesto como AGENTE para otros agentes: servidor y
cliente A2A (Agent2Agent, ver https://a2aproject.github.io/A2A/latest/).

Contraste estructural con `second_brain.mcp` (léase junto a ese paquete,
no por separado): acá el second brain NO presta herramientas sueltas —
presta su agente COMPLETO (`agent.strands_agent.answer_agentic`: loop
agéntico, coverage gate, guards de salida) detrás de una Agent Card
pública. Quien lo llama nunca ve `search_documents`/`traverse_graph`, solo
ve una pregunta entrando y una respuesta CON SUS CITAS saliendo — A2A
conecta agentes ENTRE SÍ, no un agente con sus herramientas.

`server.py` es el lado que EXPONE al second brain como agente descubrible.
`support_agent.py` es el lado que lo CONSUME: un segundo agente ajeno a
Nexora que lo descubre por su Agent Card y le pregunta — la demo de cierre
de la charla.
"""

from __future__ import annotations
