# api

Empty for now — activates at roadmap step 5.

Will hold the FastAPI app: REST endpoints for configuring/starting a simulation run, and a WebSocket
channel that streams simulation frames every N iterations to the frontend.

This is the orchestration layer — it wires together `config/` (settings), `ingestion/` (loading real
data), `simulation/` (running steps), and `validation/` (computing metrics), and exposes the result over
HTTP/WebSocket. Nothing else in the backend imports `api/`; the frontend only ever talks to it over the
network, never by importing backend code directly.
