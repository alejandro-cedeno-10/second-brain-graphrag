/**
 * Cliente mínimo del protocolo AG-UI sobre SSE, consumido por `fetch` en vez
 * de `EventSource` porque el endpoint recibe la pregunta por POST (body
 * JSON) y `EventSource` solo soporta GET. Parsea el framing `event:`/`data:`
 * línea a línea desde el stream de bytes de la respuesta.
 */
export async function streamAgUi(url, body, onEvent, { signal } = {}) {
  const respuesta = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })

  if (!respuesta.ok || !respuesta.body) {
    throw new Error(`El backend respondió ${respuesta.status}`)
  }

  const lector = respuesta.body.getReader()
  const decodificador = new TextDecoder('utf-8')
  let buffer = ''

  let eventoActual = 'message'
  let datosActuales = []

  const despacharSiHayEvento = () => {
    if (datosActuales.length === 0) return
    const crudo = datosActuales.join('\n')
    datosActuales = []
    try {
      onEvent(eventoActual, JSON.parse(crudo))
    } catch {
      onEvent(eventoActual, crudo)
    }
    eventoActual = 'message'
  }

  while (true) {
    const { value, done } = await lector.read()
    if (done) break
    buffer += decodificador.decode(value, { stream: true })
    const lineas = buffer.split('\n')
    buffer = lineas.pop() ?? ''

    for (const linea of lineas) {
      const limpia = linea.endsWith('\r') ? linea.slice(0, -1) : linea
      if (limpia === '') {
        despacharSiHayEvento()
        continue
      }
      if (limpia.startsWith('event:')) {
        eventoActual = limpia.slice(6).trim()
      } else if (limpia.startsWith('data:')) {
        datosActuales.push(limpia.slice(5).trim())
      }
    }
  }
  despacharSiHayEvento()
}
