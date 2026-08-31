"""El agente y sus capas de honestidad: el corazón de la charla.

Tres propiedades no negociables se sostienen entre estos módulos, ninguna
sola alcanza:

  tools.py           Las dos manos del agente — devuelven evidencia CON CITAS,
                     jamás prosa, para que nada de lo que el LLM ve llegue
                     sin su fuente pegada.
  gate.py            El coverage gate — decide ANTES de invocar el LLM si hay
                     evidencia para intentar responder. Sin evidencia, la
                     abstención no le cuesta un token al modelo.
  synthesis.py       El patrón de anclaje al sujeto — el system prompt que
                     evita que la síntesis pivote en silencio hacia el
                     documento con más contenido en vez de responder por el
                     sujeto preguntado.
  guards.py          Las capas de salida, baratas y deterministas: recortan
                     citas fabricadas, defanguean URLs no evidenciadas y
                     miden el drift de un turno sin tocar la respuesta.
  orchestrator.py    El loop completo: resolver objetivos → herramientas →
                     gate → síntesis anclada → guards → canario. Fail-open en
                     lo accesorio, fail-closed solo en el gate.
"""
