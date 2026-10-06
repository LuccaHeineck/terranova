import { messages } from '../i18n'
import { WS_BASE_URL } from './config'
import { isDone } from '../types/simulation'
import type { SimulationFrame, StreamMessage } from '../types/simulation'

export interface StreamHandlers {
  onFrame: (frame: SimulationFrame) => void
  onDone: () => void
  onError: (message: string) => void
}

/** Opens the run's WebSocket stream and returns a function that closes it. */
export function openSimulationStream(runId: string, handlers: StreamHandlers): () => void {
  const socket = new WebSocket(`${WS_BASE_URL}/simulations/${runId}/stream`)

  socket.onmessage = (event) => {
    const message: StreamMessage = JSON.parse(event.data)
    if (isDone(message)) {
      handlers.onDone()
    } else {
      handlers.onFrame(message)
    }
  }

  socket.onerror = () => {
    handlers.onError(messages().stream.socketError)
  }

  // An unknown or already-consumed run_id is rejected server-side with
  // close(code=4004) *before* accept() - it never arrives as a JSON message,
  // only as a close event, so it has to be handled here.
  socket.onclose = (event) => {
    if (event.code === 4004) {
      handlers.onError(messages().stream.runNotFound)
    } else if (!event.wasClean) {
      handlers.onError(messages().stream.closedUnexpectedly(event.code))
    }
  }

  return () => socket.close()
}
