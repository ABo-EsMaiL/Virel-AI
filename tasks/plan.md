# Virel AI roadmap

Stage 002 is authorized and next. The table is a development sequence, not a supported-capabilities list. Each stage keeps earlier checks green and records actual native-client evidence. A Code or replacement HTTP node does not count as native n8n support.

| Stage / proposed branch | Work | Acceptance |
|---|---|---|
| `001-project-foundation` | Independent package, docs, Spec Kit and CI | Delivered; 17 offline checks |
| `002-n8n-text` | Native credential/text JSON; readiness/errors; request usage | Actual native Chat Completion succeeds; honest failures and usage |
| `003-history-sessions` | Role-preserving history; isolated delta sessions; usage ledger | Two conversations stay isolated; no duplicated context/consumption |
| `004-n8n-vision` | Image-only/image+text; limited validated URL/binary/base64 | Native image analysis; invalid input fails |
| `005-n8n-responses-pdf` | Responses JSON; PDF upload/IDs/lifecycle | Native Model Response consumes PDF and returns usable output |
| `006-n8n-audio-input` | Transcription/translation and limits | Native audio operations on known fixtures |
| `007-model-routing` | Real model/capability catalog and verified UI choice | Correct model or explicit unavailability |
| `008-video-input` | Validated video input when a native client exposes it | Actual client input and model support verified |
| `009-n8n-images` | Image generation/edit with real artifacts | Native operation returns valid reusable file |
| `010-n8n-audio-output` | Audio generation | Native operation returns playable output |
| `011-n8n-video-output` | Video jobs/status/download | Native operation finishes or fails explicitly |
| `012-tools-agents` | Tool choice/calls/results and execution loops | Native agent completes a real client tool cycle |
| `013-streaming` | Live deltas, protocol events, cancel/timeout and final usage | Text arrives before completion; termination/usage are correct |
| `014-langchain` | Native supported integration | Invoke/history/media/tools/stream regression matrix |
| `015-langgraph` | Graph state and tool loops | Resume/cancel/isolation through the same integration |
| `016-codex` | Required Responses/events/client tools | Real file/tool cycle in the actual client |
| `017-claude-code` | Anthropic Messages adapter | Actual client loop and backend limits tested |
| `018-other-clients` | VS Code/OpenCode/Hermes, one at a time | Version/custom-endpoint/protocol matrix for each client |

Move streaming earlier when a client requires it. Media generation requires actual website/account/model support. Extra operations such as embeddings/moderation are not supported by implication.

## History policy

Full-history request → fresh browser chat and one faithful replay. Delta-only request → isolated persistent session with ID/reset/expiry. Independent request → fresh chat. The current shared `clear=false` behavior is not isolated sessions. Fresh chats do not bypass context or account limits.

## Usage

Stage 002 begins request usage; 003 adds session aggregation; media/tool stages extend counting; streaming adds protocol-specific final usage. Prefer current-request observations and distinguish reported/estimated/unknown. See [usage contract](../docs/usage.md).

## Delivery

Spec → branch → plan/tasks → tested implementation → native evidence → review/PR/checks → merge/tag. One feature at a time. Record client version, operation, actual model, input, result and regression outcomes.
