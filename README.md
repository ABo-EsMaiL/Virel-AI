# Virel AI

**A browser-backed AI gateway for Google AI Studio.**

Virel AI accepts HTTP requests, submits them through Chromium, reads the visible response, and returns JSON, SSE or supported media files. The gateway key authenticates your clients; generation uses the website interface.

## Quick start

Python 3.12 and an account with access to AI Studio are required.

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m playwright install chromium
Copy-Item .env.example .env
```

Set `VIREL_API_KEY`, `DEFAULT_MODEL`, and `CHROME_PROFILE_DIR` in `.env`. The verified setup uses `HEADLESS=false`. Run `./.venv/Scripts/python.exe get_session.py` for a new Google login, or reuse an existing profile after closing other processes using it.

```powershell
./.venv/Scripts/python.exe -m uvicorn app:app --host 127.0.0.1 --port 8001
```

Use one worker. For n8n in Docker Desktop, listen on `0.0.0.0` and set its ordinary OpenAI credential Base URL to `http://host.docker.internal:8001/v1` with your gateway key.

## Model selection

GET /v1/models returns the last account-UI observation of selectable text, image and speech model IDs. The ordinary n8n model picker uses those IDs directly. Paid, disabled and unimplemented output categories are excluded; each route checks the model category. Unknown capability fields remain null; appearing in the list does not guarantee quota or every modality.

Send the exact model ID in a request. Virel verifies the browser selection before submitting; it never falls back to another model. Unknown IDs return404, unavailable selections503, unsupported categories400. Responses disclose actual model and requested_model separately when a UI alias resolves to a concrete model. The documented audio whisper-1 compatibility alias remains unchanged.

Authenticated GET /v1/models?refresh=true rescans the UI while idle; a busy browser returns429. Ordinary listing reads the snapshot without interrupting generation. Discovery metadata includes observed_at and process-local generation_verified; model-specific thinking/search verification is cleared when controls are absent.

## Text request

POST `/v1/chat/completions` with `Authorization: Bearer <VIREL_API_KEY>`:

```json
{
  "messages": [{"role": "user", "content": "Hello"}]
}
```

Read `choices[0].message.content`. Missing `stream` returns JSON; explicit `stream: true` returns SSE. Browser text is buffered until generation and Markdown rendering finish, then displayed through rapid consecutive text chunks (`X-Virel-Text-Delivery: completed_browser_snapshot_paced`). The first chunk is immediate; later chunks are spaced 25ms apart, at most 60 chunks per completed text delta (up to 1.475s of scheduled display time). Text is preserved exactly. This simulates typing of the completed reply; client/proxy buffering can affect display. Chat supports `stream_options: {"include_usage": true}` for a final usage chunk; Responses uses named lifecycle/text/tool events. Responses text uses POST `/v1/responses` with `{"input":"Hello"}`. Reported usage is returned when observed; unavailable counts remain null.

Optional experimental formatting: set `VIREL_PRESERVE_MARKDOWN=true` and restart to reconstruct common rendered Markdown (code fences, headings, emphasis, lists, links, quotes and tables). The default `false` keeps the original plain-text reader. This is rendered-format reconstruction, not the model's exact Markdown source; CSS, math and citation metadata are not reconstructed. To remove it, set `false`, restart, then delete the isolated `virel/response_markdown.py` module; tools and protocols do not depend on it.


Native n8n OpenAI Chat 1.8 and Responses 2.3 text passed in raw and simplified modes. Clients own memory: send the complete ordered text history with each request. Virel replays it once in a verified fresh browser chat; validated tool-result continuations reuse that chat until the agent finishes. It does not store conversations. History is a text transcript, not native provider role enforcement. Native client acceptance of the repaired SSE path is pending; video output remains deferred. AI Studio changes and account limits can affect generation.

## LangChain

Use the official Python integration (`pip install langchain-openai==1.7.2 openai==3.33.0`):

```python
from langchain_openai import ChatOpenAI

model = ChatOpenAI(
    model="gemini-flash-latest", base_url="http://localhost:8001/v1",
    api_key="<VIREL_API_KEY>", use_responses_api=False,
    stream_usage=True, max_retries=0,
)
for chunk in model.stream("Hello"):
    print(chunk.text, end="", flush=True)
```

For Responses, use `use_responses_api=True, store=False, use_previous_response_id=False` and supply full caller history. Your application executes bound tools and returns matching `ToolMessage` objects. Set `stream_usage` on the model constructor.

Native text/history, sync/async streams, tool loops, images/PDFs and concurrent client requests passed local tests with `langchain-openai1.7.2`, `langchain-core1.6.12` and `openai3.33.0`. These tests use the real SDK and mocked browser generation; live Google acceptance remains user-owned. Supported gateway features and limits below still apply. See the [official integration documentation](https://docs.langchain.com/oss/python/integrations/chat/openai).

## LangGraph

Install `langgraph==1.2.16` alongside the LangChain versions above. Use the official `StateGraph(MessagesState)` and `ToolNode`; the graph belongs to your application:

```python
import asyncio
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.tools import tool

@tool
def multiply(a: int, b: int) -> int:
    """Multiply two integers in the client."""
    return a * b

bound = model.bind_tools([multiply])

async def call_model(state, config):
    return {"messages": [await bound.ainvoke(state["messages"], config)]}

builder = StateGraph(MessagesState)
builder.add_node("model", call_model)
builder.add_node("tools", ToolNode([multiply]))
builder.add_edge(START, "model")
builder.add_conditional_edges("model", tools_condition)
builder.add_edge("tools", "model")
graph = builder.compile()
result = asyncio.run(graph.ainvoke({"messages": [("user", "Calculate 6 times 7.")]}))
print(result["messages"][-1].text)
```

The `model` is the native `ChatOpenAI` configured above; both Chat Completions and full-history Responses are supported by the same graph. Use `graph.astream(..., stream_mode="messages")` for native message events. Checkpoints, task IDs and tools remain client-owned. A checkpoint cannot revive an expired browser tool lease; retries of external actions require application-level idempotency.

Native graph tool loops, streams, pause/resume, task isolation and cancellation passed offline tests with mocked browser generation. Live LangGraph acceptance remains user-owned. See the [official quickstart](https://docs.langchain.com/oss/python/langgraph/quickstart).

## Codex

Codex can select Virel as a custom HTTP Responses provider. Use your actual Gemini model ID and gateway key; keep your existing provider configuration separate:

```toml
model = "gemini-flash-latest"
model_provider = "virel"
model_reasoning_effort = "high"
model_reasoning_summary = "none"
web_search = "disabled"

[model_providers.virel]
name = "Virel AI"
base_url = "http://localhost:8001/v1"
env_key = "VIREL_API_KEY"
wire_api = "responses"
requires_openai_auth = false
supports_websockets = false
request_max_retries = 0
stream_max_retries = 0
stream_idle_timeout_ms = 1200000
```

Responses accepts flat functions and namespace groups of typed JSON functions. Public function names, namespaces and call IDs survive the native relay mapping; the caller still executes every tool. Optional request routing metadata is validated and discarded. `prompt_cache_key` does not enable a gateway cache; an encrypted-reasoning include request does not create reasoning content. Assistant message phases are preserved.

Native CLI0.162.0-alpha.17.2 and0.163.0-alpha.10.2 text/SSE, usage and tool-result transport were checked with mocked browser generation. The test environment blocked Codex shell commands, so actual file read/write acceptance remains pending. No live Codex/Google compatibility is claimed from these checks. Custom freeform/grammar tools, hosted OpenAI tools, remote compaction and WebSockets remain unsupported. Codex may warn that its bundled catalog lacks Gemini metadata; Virel keeps the actual Gemini model identity. See the [official provider configuration](https://developers.openai.com/codex/config-advanced).

## Claude Code

An experimental Anthropic Messages subset is available at POST `/v1/messages`. Native Claude Code2.1.302 was checked in official `--bare` mode (Bash/Edit/Read), with browser generation mocked: text/SSE, reported usage and a real temporary file read/edit cycle. Live Google and full-mode/plugin compatibility remain unverified. Anthropic does not support routing Claude Code to non-Claude models.

Set `ANTHROPIC_BASE_URL=http://localhost:8001` (without /v1), `ANTHROPIC_API_KEY` to your gateway key and `--model gemini-flash-latest`. Keep these in an isolated client environment; model identity remains Gemini. The server executes no client tools. Declared tool defaults are materialized before call IDs/hashes are bound, preserving strict continuation validation.

Required `max_tokens` is applied and verified in the model's native UI range. Adaptive thinking maps to native low/medium/high effort without exposing Claude thinking signatures. Cache hints are accepted as advisory only; no cache is created or counted. Unknown usage remains null. Streaming uses the same paced completed-browser display as other protocols. Stop reasons identify browser completion, tool use, or an observed native MAX_TOKENS terminal. Other provider stop reasons are not inferred.

Exact pre-generation token counting returns501. Signed thinking, thinking budgets, hosted tools, structured outputs, stop sequences, context compaction and media-bearing tool histories are unsupported. Ordinary image/document requests reuse existing media validation. The native CLI may retry an initially failed stream once as JSON; the gateway itself does not retry or replay tools. See the [official gateway protocol](https://code.claude.com/docs/en/llm-gateway-protocol).

## Hermes setup

Run `hermes model`, choose **Custom endpoint**, then enter:

| Setting | Value |
|---|---|
| Base URL | `http://localhost:8001/v1` |
| API key | Your gateway `VIREL_API_KEY` |
| Model | `gemini-flash-latest` |
| API mode, if prompted | `chat_completions` |

Start a fresh Hermes session after saving. This setup follows the [official provider guide](https://hermes-agent.nousresearch.com/docs/integrations/providers/). Shipped Hermes tool schemas and an official OpenAI SDK tool loop passed offline checks. A native Hermes desktop0.22.2+1531 text request with35 client tools declared passed with the user on observed Gemini3.8Flash; live multi-round tool execution and heavy tasks remain unverified. Native effort is `low`, `medium` or `high`; Hermes `max` maps explicitly to native `high`, disclosed by `X-Virel-Reasoning-Requested: max` and `X-Virel-Reasoning-Applied: high`. A remote/container client needs a reachable server address instead of its own localhost.

## Client tools and agents

Chat Completions and Responses accept client-owned `type:function` tools in JSON or SSE mode. Tool histories currently accept text only; file analysis uses a separate ordinary multimodal request before tool rounds. AI Studio receives one real native relay function, `virel_client_tools`, whose array carries original tool names and typed JSON argument objects. Virel validates each against the caller schema and serializes standard client argument strings in `tool_calls` / `function_call` items, preserving quoted HTML and text. Client results return together as one native function response in the same browser chat. `X-Virel-Tool-Transport: native_function_batch` discloses this mapping. Your client executes every tool; Virel never runs them. Structured Outputs is not used for this transport.

Native n8n AI Agent + OpenAI Chat Model + Calculator passed with streaming disabled; the repaired SSE path requires separate user acceptance. Send complete history and original call IDs with each result. Batched assistant calls and interleaved assistant-call/tool-result pairs are both accepted; results are correlated by ID and returned to the browser in the original request order. The first request starts a fresh browser chat; matching results are added together to that same chat without replaying history or tool definitions. Further tool rounds stay there until the final answer. The next execution starts fresh. Independent requests using the same credential receive separate browser pages; a waiting tool loop keeps its own page until matched results arrive, completion, or expiry. This does not cancel actions already running in your client. No extra client node, header or n8n patch is needed. Streamed tool arguments are published once only after the whole native batch passes validation (`X-Virel-Tool-Arguments: validated_complete`); final text uses rapid bounded display pacing after the browser finishes rendering; native tool arguments remain complete, validated and unpaced. Disconnects abort the current browser page before releasing it. Stream failures have no success trailer; missing usage stays null.

One persistent browser supports isolated request pages and multiple waiting tool loops. Active execution defaults to a RAM-aware ceiling of20; bounded admission queues excess work. Child media/text requests can run while a parent waits for client tool results. Idle timeout defaults to600seconds (`VIREL_TOOL_RUN_TTL_SECONDS`); restart, expiry, changed caller/conversational history/settings or stale IDs return409 rather than silently replaying work. System/developer instruction content may refresh between matching rounds (for example a dynamic clock); the latest instructions are forwarded separately from opaque tool outputs. Instruction roles and positions remain bound. Concurrent executions retain separate IDs/pages under the same credential; late, foreign or conflicting results cannot release another loop. Only hashes/call metadata are retained in memory, with no conversation database. Same-chat reuse does not guarantee lower token usage: the website still processes effective context.

There is no fixed gateway count of tool definitions or calls per response. The configured request-byte limit (128MiB by default),32KiB/schema,64KiB arguments,24 nesting levels and actual model/context/output limits still apply. `parallel_tool_calls:false` permits at most one call. Choices `auto`, `none`, `required` and a declared named function are validated; constrained argument decoding is not promised. Schemas support typed objects/properties/required, arrays, enum, const, numeric/size bounds, anyOf/oneOf, nullable/type unions, acyclic local JSON-pointer refs and safe finite patterns. Union nodes use exactly one typed `variant_N` property in the native declaration; Virel restores original values and validates the unchanged caller schema before publishing calls. No tool is removed, schemas are not merged, and arguments are not encoded as nested JSON strings. Empty required lists are omitted only from the native projection so zero-argument tools remain valid after the editor removes empty properties; the original caller schema is retained. Array-item descriptions are retained on the parent array because the editor omits them on item nodes. Saved structural definitions are still checked before submitting a prompt; verification failures include a value-free structural location. Remote/recursive refs, allOf, structural siblings on union/ref nodes, patternProperties, unsafe/unbounded regex, `strict:true`, built-in tools, partial tool-argument streaming and media/tool combinations remain unsupported. The observed AI Studio UI makes native Function calling incompatible with Google Search and URL Context. These are disabled while client functions are available and restored for ordinary requests or `tool_choice:none`. Search runs within Google, not as a gateway tool executor. This UI restriction prevents combined search-and-client-tool requests; Gemini API capabilities do not certify UI availability. The n8n Responses logger may show its own token estimate; HTTP `usage` retains website-reported counts or null. Explicit model IDs select their exact UI card even when a selected alias points to the same canonical model. Temporary model-unavailable errors return `503 upstream_unavailable`; the gateway does not change models or retry generation automatically.

Typed projections apply object keywords (properties/required) only to object branches and items only to array branches, including nullable type unions. Irrelevant typed keywords remain in the original caller schema for validation; they are not emitted as invalid UI fields.

## Image input

Chat user messages accept text and image parts together:

```json
{"messages":[{"role":"user","content":[
  {"type":"text","text":"Describe the animal."},
  {"type":"image_url","image_url":{"url":"https://upload.wikimedia.org/wikipedia/commons/9/9a/Gull_portrait_ca_usa.jpg"}}
]}]}
```

Omit the text part for a default image description. Responses uses `input_image` with a string `image_url`. Both accept PNG/JPEG/WebP/BMP/static-GIF base64 data URIs or public HTTPS URLs. Limits: 4 still images, 5 MiB and 20 million pixels each; 128 MiB request body by default. Static GIF is converted to PNG for browser input. Local paths, redirects, private destinations, input_image.file_id and non-default detail are rejected; use generic input_file for uploaded image IDs. Request upload files are removed afterward.

Native n8n **Message a Model 2.3** passed with binary and URL images. Add text and image entries in the same node to send one request. It requires text, so use a neutral description for a picture without a custom question. **Analyze Image** remains unsupported because its automatic output-token limit is not controlled by the browser adapter. Optional UI response comparisons are skipped without voting; ambiguous usage remains null.

## Image generation and editing

Native n8n **Generate an Image** returns the actual PNG as binary data. Choose By ID and use an available image model such as `gemini-3.1-flash-lite-image` (Nano Banana 2 Lite). POST `/v1/images/generations` accepts:

```json
{"model":"gemini-3.1-flash-lite-image","prompt":"A red circle on white"}
```

Native **Edit an Image** accepts the original binary directly. Select `gpt-image-1`, Size=Auto and Quality=Auto. This is an explicit Virel compatibility selector for `DEFAULT_IMAGE_MODEL`, not GPT execution: n8n 2.3 hides the necessary edit input fields for Gemini IDs. Direct HTTP callers can use the actual Gemini ID with multipart `image` or `image[]` and `prompt` at `/v1/images/edits`.

Both return one image in `data[0].b64_json`, actual/requested model metadata and reported usage when available. Omit `output_format` (or use `auto`) to preserve the original model file byte-for-byte. Explicit `png`, `jpeg` or `webp` requests convert the final file on the server; `encoding` discloses original/output formats and whether conversion occurred. JPEG conversion uses quality100/no chroma subsampling by default; WebP defaults to lossless. Optional `output_compression`0–100 selects JPEG/WebP encoding quality. Transparent source pixels become white only when explicitly converting to JPEG.

| Option | Default and behavior |
|---|---|
| Text model / image model | `DEFAULT_MODEL=gemini-flash-latest` (observed UI alias); `DEFAULT_IMAGE_MODEL` is an eligible observed image model. Explicit model wins; no paid fallback. |
| Thinking / temperature | `high` / `1`; HTTP image `reasoning_effort` and `temperature` override them when the selected UI model supports the values. |
| Shape / resolution | `size=auto`, `aspect_ratio=Auto`, `resolution=1K`; offered ratios are verified in the UI. `size=1024x1024` enforces1:1/1K and actual1024square bytes. Lite exposes1K only. |
| Advanced image controls | HTTP `top_p` defaults0.95; `max_output_tokens` defaults65536, capped by the current UI maximum. Explicit values must pass real UI bounds/readback. |
| Original/output format | Default `auto` preserves the source. Explicit PNG/JPEG/WebP conversion uses existing Pillow; generation remains in AI Studio. |
| Output limits | One image, base64/native binary;20MiB output (`VIREL_MAX_GENERATED_IMAGE_MB`),20million pixels; edit-input limits above. |

HTTP example: `{"prompt":"A kite above a green hill","aspect_ratio":"16:9","temperature":0.4,"reasoning_effort":"minimal","output_format":"jpeg"}`. Image extensions not exposed by a native node require a client that actually sends them. Existing native n8n Generate/Edit work without conversion nodes.

The installed n8n OpenAI2.3 Edit serializer does not send its visible Output Format/Compression fields. Virel handles these standard fields when received; a missing field preserves the original. n8n itself is unchanged. Its Generate node also hides many options for Gemini IDs. Server behavior cannot infer an unsent client selection.

Quality tiers, pixel masks, guaranteed transparency, input fidelity, hosted output URLs, batches and arbitrary resized dimensions remain unavailable. They return field-specific errors with supported alternatives; quality is not silently mapped to resolution or thinking. AI Studio can refuse requests (recitation/safety), and available image models can lack Search/URL tools. Quota/rate-limit UI failures return429 with `upstream_rate_limit`; no automatic retries or stale/input image fallback.

## File inputs

Native n8n **Message a Model 2.3** accepts file entries alongside a text question: use Binary File, public HTTPS URL, or File ID from the official **Upload a File** node. Scanned and ordinary PDFs are submitted as original documents through the same browser upload/readiness checks.

| Input | Processing |
|---|---|
| PDF | Original visual document, including scans |
| TXT, Markdown, code, CSV/TSV, JSON, XML, HTML | Bounded Unicode text |
| DOCX/DOCM, PPTX/PPTM, ODT/ODP, RTF | Server-side text extraction |
| XLS/XLSX/XLSM/XLSB/ODS | Sheet names, cell addresses and cached values |
| Images, audio, video | Existing validated browser media path |

Office extraction excludes embedded images/layout and never runs macros, formulas or links. Legacy binary DOC/PPT, encrypted documents, executables and arbitrary archives are unsupported; use modern Office formats or PDF. Native browser acceptance of new types remains user-owned.

Responses file parts use one source:

```json
{"input":[{"role":"user","content":[
  {"type":"input_text","text":"Summarize this document."},
  {"type":"input_file","file_id":"file-<uploaded-id>"}
]}]}
```

Alternatively use file_url, or filename plus file_data containing strict base64 or a matching data:<mime>;base64,... URI . Default gateway limits:10 PDFs per request,50 MiB and 1000 pages each;128 MiB request body. Configure VIREL_MAX_PDF_MB, VIREL_MAX_PDF_PAGES, VIREL_MAX_PDFS and VIREL_MAX_REQUEST_MB in .env. Encrypted or corrupt PDFs and unsafe URLs are rejected. These are gateway limits, not a guarantee of every model's support.

POST /v1/files accepts multipart file and purpose=user_data or assistants. Authenticated list/retrieve/content/delete endpoints are available. Files remain private to this gateway, expire after one hour and are cleaned every 60 seconds/startup; expired IDs fail immediately. Storage is bounded at 20 files/100 MiB. Configure VIREL_API_KEY to enable stored IDs; request copies are deleted afterward. PDF input does not implement File Search or vector stores.

## Generation controls

Native text requests accept temperature (0–2, subject to the selected UI model) and reasoning effort. Chat uses reasoning_effort; Responses uses reasoning.effort. Explicit max maps to native high with requested/applied response headers; other unknown levels remain unsupported. Missing effort uses THINKING_MODE=high; missing temperature resets an available UI control to1. Unsupported explicit controls return an error before generation.

In the native n8n Responses node, add Reasoning → Effort and set Summary to None; add Temperature separately. No Code or conversion node is needed. Reasoning summaries are not implemented.

ENABLE_URL_CONTEXT=true enables the current model's URL Context tool for links in prompts, alongside Google Search when configured. /health reports actual thinking, temperature and URL-tool verification. Tool availability and URL retrieval still depend on AI Studio and the selected model.

## Video input

The validator accepts MP4/WebM, MOV/M4V, MPEG/MPG, AVI, FLV, WMV, 3GP/3G2 and MKV containers. MP4 and WebM video questions work through the native n8n Responses File Data field: connect the binary file directly, set its filename and add your text question. Virel passes the original video into AI Studio after validation and waits for upload/tokenization readiness. No conversion node or local video model is used.

This is a Virel extension to input_file, not official OpenAI video compatibility. Chat file parts accept the same filename/file_data fields; identifiable direct public HTTPS file_url sources are also supported. Media-only HTTP requests get a description prompt; the native n8n node requires text. Generic file IDs now also support video. Playlists, clipping and video generation are not implemented.

Defaults:50 MiB/video,2 videos/request,20 million pixels/frame; configure VIREL_MAX_VIDEO_MB, VIREL_MAX_VIDEOS and VIREL_MAX_VIDEO_PIXELS. There is no separate duration cap. The HTTP body cap includes base64 overhead; website/model limits still apply. Validation samples a real frame in a bounded child process; request files are removed on completion/error/cancellation. Native MP4/H.264 and WebM/VP9 passed; other encodings and live URL transport need separate acceptance.

## Audio input

Native n8n **Transcribe Audio** and **Translate Audio** operations work with ordinary OpenAI credentials pointed at Virel. Pass a binary audio file directly; transcription preserves the spoken language, translation returns English. Both use the AI Studio browser, not an external transcription service.

POST /v1/audio/transcriptions or /v1/audio/translations with multipart file and model. Native n8n hardcodes whisper-1: Virel accepts it as a compatibility alias for DEFAULT_MODEL. Responses expose actual model and requested_model; Virel does not run Whisper. JSON returns text and observed usage; response_format=text returns plain text. Language hints are prompt guidance. Explicit temperature, timestamps, streaming and subtitle formats are unsupported.

The validator accepts WAV, MP3/MPEG, M4A/M4B/audio-only MP4, OGG/OGA/Opus, FLAC, AAC, AIFF/AIF and audio-only WebM/WEBA containers, checks MIME/container consistency and decodes a sample before upload. WAV and MP3 passed through native n8n; other listed containers passed isolated decoder checks and still need browser acceptance for each encoding. Audio defaults to 25 MiB per file, configurable with VIREL_MAX_AUDIO_MB. There is no additional duration cap; website/model/context and processing deadlines still apply. Request files are removed on completion/error/cancellation. Generic file inputs accept stored audio IDs; dedicated transcription/translation operations still take multipart audio.

Limits are positive gateway settings, not unlimited provider capacity. Raising them cannot override website/account/model limits; base64 also increases the request body size. Original file storage remains 20 files/100 MiB with one-hour expiry. General file inputs default to50MiB/file and20files/request; extraction defaults to2million characters,64MiB expanded archives,200000 spreadsheet cells and512MiB parser memory. VIREL_MAX_FILE_* and VIREL_MAX_DOCUMENT_* configure these guards; limits fail explicitly without truncation.

## Speech output

Native n8n **Generate Audio 2.3** returns real speech generated through AI Studio. POST `/v1/audio/speech`:

```json
{"model":"tts-1","input":"Hello from Virel AI.","voice":"alloy","response_format":"mp3","speed":1}
```

`tts-1` and `tts-1-hd` explicitly select `DEFAULT_SPEECH_MODEL=gemini-3.8-flash-tts`; both use the same actual model. These selectors do not run OpenAI TTS or promise an HD tier. Direct callers can send an eligible observed Gemini TTS ID. Actual/requested model and voice are disclosed in response headers.

| Native voice selector | Actual AI Studio voice |
|---|---|
| `alloy` | `DEFAULT_SPEECH_VOICE=Fola` |
| `echo` / `fable` / `nova` | Bodi / Koda / Lumi |
| `onyx` / `shimmer` | Mako / Sola |

These select Gemini voices, not reproductions of OpenAI voices. Direct callers can request an exact available UI voice name. Selection must be verified before Run; unavailable voices fail explicitly.

Omitted `response_format`/`auto` preserves the original PCM16 mono24kHz WAV byte-for-byte at speed1. Native n8n requests MP3 by default. Explicit `mp3`, `opus` (Ogg), `aac` (ADTS), `flac`, `wav` or `pcm` (raw signed16LE mono24kHz) produce matching files. Existing PyAV performs only requested file encoding and pitch-preserving `speed`0.25–4; speech synthesis stays in the browser. `X-Virel-Source-Format`, `X-Virel-Output-Format`, `X-Virel-Audio-Speed` and `X-Virel-Audio-Processing` disclose processing.

Defaults:4096input characters,50MiB source/output and600seconds source duration, configurable via `VIREL_MAX_SPEECH_CHARACTERS`, `VIREL_MAX_GENERATED_AUDIO_MB`, `VIREL_MAX_SPEECH_SECONDS`. A killable30second worker validates/encodes files; temporary files are removed on completion/error/cancellation. These limits cannot override AI Studio/account quotas. Reported counts use `X-Virel-Input-Tokens`, `X-Virel-Output-Tokens`, `X-Virel-Total-Tokens`; unavailable counts are omitted and provenance headers say unavailable/unknown. Streaming, instructions/style parameters, voice cloning, multiple speakers and text-model thinking/Search controls are unsupported by this route. No n8n patch or local TTS model is required.

## License

Virel AI is licensed under the [Apache License 2.0](LICENSE). Copyright 2026 Ahmed AbdElHady Esmail; see [NOTICE](NOTICE). Original MSEMAX portions retain their [MIT copyright and license notice](LICENSES/MSEMAX-MIT.txt).


## Concurrent requests

One Chromium process/profile hosts independent request pages. Each page has its own model/settings, usage observer and client-tool state. Validated tool results resume their original page; nested ordinary requests can run on other pages. Waiting tool rounds release execution capacity. Completed pages close after response transmission; one control page stays open.

`VIREL_MAX_CONCURRENT=20` is an upper ceiling. Available-memory reserve and configurable per-active-task growth headroom can reduce running work. `VIREL_MAX_QUEUE`, `VIREL_QUEUE_TIMEOUT_SECONDS` and `VIREL_MAX_WAITING_TABS` bound waiting work; see `.env.example`. Linux container memory limits are included when available. Queue exhaustion returns429; streamed failures use the protocol error event. Memory estimates do not guarantee protection from every OS/provider failure.

`/health` reports pool counts and opaque page IDs; authenticated diagnostics accept `?page_id=...`. Its model/settings fields describe the control page. Client-tool IDs identify continuations; standard requests do not expose ordinary parent/child ancestry. No history store, tool executor or client changes are required. Keep one server worker per profile. Actual Google parallel capacity and multi-client acceptance remain unverified; extra pages do not increase account quotas.

## Text output limits

Chat Completions, Responses and legacy text requests accept max_tokens, max_completion_tokens or max_output_tokens as a positive integer. Matching aliases are allowed; conflicting values fail before generation. The gateway applies the limit to AI Studio's existing Maximum output tokens control and verifies its native model range and readback. It does not ignore the limit or truncate text locally. Omitted/null limits keep existing behavior. A correlated native MAX_TOKENS terminal is reported as length (Chat/legacy), incomplete with max_output_tokens (Responses), or max_tokens (Messages). This may legitimately contain no visible text, including a one-token connection probe consumed by thinking. Unknown empty responses remain errors; the gateway never inflates the requested cap or fabricates probe success.

## OpenCode setup

[examples/opencode.json](examples/opencode.json) configures the native @ai-sdk/openai-compatible provider against http://localhost:8001/v1. Supply the existing gateway key as VIREL_API_KEY in the client environment; the example contains no secret. Put the example in a separate trial project, start OpenCode, and select virel/gemini-flash-latest. Tool actions require approval.

This is an initial setup example, not certified OpenCode compatibility. Native configuration parsing was checked with OpenCode 1.18.33; live text and tool acceptance remain pending. Existing gateway protocols and client-owned execution/history are unchanged.

## VS Code clients

[Native Cline and Continue setup](examples/vscode-clients.md) includes the local gateway fields, a secret-free Continue YAML model block, and independent text/file acceptance steps. Setup is prepared for Cline 4.1.24 and Continue 2.0.0; live client acceptance remains pending. Existing gateway contracts are unchanged.

## Claude Desktop alias gateway

For the user-authorized Claude Desktop compatibility trial, set its Gateway base URL to http://localhost:8001/claude, use the existing gateway key and Bearer authentication. Its /v1/models view derives one routing alias per currently selectable AI Studio card: for example, claude-3.8-flash routes to the real gemini-3.8-flash. These are **Gemini routing aliases, not Anthropic Claude models or equivalent capabilities**. Original /v1 endpoints, Gemini IDs and all existing clients remain unchanged.

Alias discovery is dynamic, not a list of ten hardcoded names. Every browser startup/recovery discards its previous catalog and observes the current model picker; Paid/disabled/unsupported rows stay excluded. Cached model reads do not run inference; ?refresh=true explicitly rescans an idle control page. Selectable/free indicates the observed UI state, not remaining quota.

The alias route retains existing Messages validation, settings, JSON/SSE, usage and client-owned tool continuations. It additionally accepts Desktop's inline system text entries without relabeling or reordering; the ordinary /v1/messages contract is unchanged. Alias discovery does not guarantee a Desktop effort selector; supplied effort still uses the existing native thinking mapping. Catalog metadata and completed messages disclose the real model; headers disclose the alias/requested UI ID, with verified actual-model metadata in the completed stream event (and a header for JSON). Listed image/speech models retain their existing output-adapter restrictions; listing does not add media generation to Messages. Native Desktop inference acceptance remains user-owned; model listing alone does not certify chat, tools or workspace startup.

Custom Messages tools also support automatic on-demand loading: definitions marked defer_loading:true stay out of the model prompt and native declarations until a successful client tool result returns a tool_reference to that declared tool. The gateway validates the reference and loads the original definition on the same owned page before continuing; the client still executes every tool. Ordinary tools remain immediately available. No .env switch or per-client toggle is required. This supports custom client-side tool discovery, not Anthropic-hosted search tools; actual Desktop tool discovery remains pending native verification.

Typed additionalProperties dictionaries are projected to native arrays of unique string-key/typed-value entries and restored to ordinary client JSON dictionaries before original-schema validation. Fixed properties, key constraints, required entries and nested values are retained; duplicate keys fail instead of overwriting data. Existing boolean and empty-schema additionalProperties forms keep their previous native shape. This is a browser transport detail and requires no client configuration.
