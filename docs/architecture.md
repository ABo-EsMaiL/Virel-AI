# Architecture

Virel AI exposes HTTP adapters over one persistent AI Studio browser. The Python package remains `virel`.

| Location | Responsibility |
|---|---|
| `app.py` | Launcher and ASGI app export |
| `get_session.py` | Manual Google login setup |
| `virel/server.py` | FastAPI composition, lifespan and middleware |
| `virel/config.py` | Project-root settings and runtime paths |
| `virel/auth.py` | Gateway Bearer authentication |
| `virel/schemas.py` | Chat input contracts |
| `virel/messages.py` | Prompt conversion and image preparation |
| `virel/routes/` | Chat, Responses, legacy Completions and system routes |
| `virel/browser.py` | Browser lifecycle, UI settings, uploads and generation |
| `virel/dom.py` | JavaScript response extraction and completion state |
| `virel/runtime.py` | One browser manager, limiter and admission semaphore |
| `tests/` | Offline HTTP, DOM and path regression checks |
| `docs/`, `tasks/`, `specs/` | Reference, roadmap, feature contracts and evidence |
| `runtime/` | Private profile/session/upload data; ignored |

## Request flow

1. The server lifespan starts Chromium using the configured profile.
2. An adapter checks auth and admission, converts inputs, and locks the shared browser.
3. The browser prepares the chat/model, attaches media, fills the prompt and runs generation.
4. DOM polling reads response text and generation state; successive changes become deltas.
5. The adapter returns one JSON response or SSE events and releases the lock.

Chat currently drops assistant history; `CLEAR_CHAT_ON_REQUEST=false` shares one conversation. These are inherited limits scheduled for the history/session stage. Do not equate current Responses events with the official Responses protocol.

Add adapters for protocols, not one route per client. Browser selectors stay outside HTTP handlers. Add new modules only when an implemented capability needs a real boundary. One process and one worker are required by the current browser design.

`runtime/session.json` is setup metadata, not proof of a valid login. Profiles contain private account state. Upload lifetime and input trust boundaries require the dedicated media stage.
