"""Compatibilidad de memoria con Strands, aparte de dónde vive el recuerdo.

Las implementaciones reales de `second_brain.ports.MemoryPort` NO viven acá:
siguen el mismo patrón que el resto de puertos del dominio —
`adapters.local.fake_memory_store.FakeMemoryStore` (RAM, sin AWS) y
`adapters.aws.agentcore_memory_store.AgentCoreMemoryStore` (`boto3` sobre
`bedrock-agentcore`) — para no romper la convención de que "cada
implementación de un `*Port` vive en `adapters/local/*.py` o
`adapters/aws/*.py` según el modo" que ya sigue `FakeEmbeddings`,
`MemoryVectorStore`, `ScriptedLlm`, `FalkorGraphStore`, `BedrockLlm`,
`BedrockRerank`, `S3VectorsStore`.

Este paquete existe solo para `strands_compat.MemoryPortStrandsAdapter`:
envuelve cualquier `MemoryPort` para cumplir
`strands.memory.types.MemoryStore` y poder engancharlo a
`strands.memory.memory_manager.MemoryManager`, si hiciera falta (el camino
agéntico real de la demo usa una tool explícita en cambio — ver
`agent.strands_tools`). No es un adapter "local" ni "aws" — es transversal a
los dos backends de memoria — por eso vive aparte en vez de forzarlo dentro
de `adapters/`.
"""
