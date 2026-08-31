"""El second brain expuesto como HERRAMIENTA para otros agentes: servidor MCP.

Contraste estructural con `second_brain.a2a` (léase junto a ese paquete,
no por separado): acá el second brain presta sus dos manos sueltas
(`search_documents`/`traverse_graph`, las mismas funciones de
`second_brain.agent.tools`) para que un agente AJENO arme su propio
razonamiento — MCP conecta un agente con SUS herramientas. En
`second_brain.a2a` el second brain presta su agente COMPLETO (loop,
coverage gate, guards) detrás de una Agent Card — A2A conecta agentes
ENTRE SÍ. Ningún módulo de este paquete importa nada de `second_brain.a2a`
ni al revés: son dos superficies de exposición independientes sobre el
mismo dominio (`second_brain.agent.tools`, `second_brain.config.Stack`).
"""

from __future__ import annotations
