# VS Code clients: Cline and Continue

These are native-client setup examples, not certified compatibility. Prepared for installed Cline 4.1.24 and Continue 2.0.0. Keep the gateway running locally.

## Cline

In Cline's native provider settings, select OpenAI Compatible:

| Field | Value |
|---|---|
| Base URL | http://localhost:8001/v1 |
| API Key | Your existing Virel gateway key |
| Model ID | gemini-flash-latest |

Keep normal tool approvals. If Plan and Act use separate configurations, choose the same provider/model in both for this trial. Optional sampling overrides can stay unset. Do not paste secrets into a repository or rename Gemini as GPT.

## Continue

[continue.yaml](continue.yaml) is a complete workspace-local model block. Copy it to .continue/models/virel.yaml inside a separate trial project. It enables the existing gateway's native tools and image-input capabilities using the Chat Completions endpoint.

Set VIREL_API_KEY in a private .continue/.env in that workspace, excluded from Git. The YAML references the secret by name; an unrelated terminal variable may not reach the IDE. Reload the window if needed and select Virel Gemini Flash. Use Chat for text and Agent for file tools with normal approvals.

The contextLength 65536/maxTokens 8192 settings are conservative client trial budgets, not measured Gemini/account capacity. Autocomplete, embeddings and reranking are not configured or certified.

## User-run acceptance

Run each client independently in its own workspace. First request a short Arabic reply without file changes or commands. Then place input.txt containing Quantity: 6 and Unit price: 7, and request native file reading and creation of result.txt containing total=42. Verify tool outputs and the actual file.

Configuration/schema checks do not prove live model availability, client tool dialect, media, compaction or simultaneous-client capacity. Native acceptance remains user-owned; no client test, Verify or model request was executed during setup.

Official setup: [Cline](https://docs.cline.bot/provider-config/openai-compatible), [Continue](https://docs.continue.dev/customize/model-providers/top-level/openai), [Continue local blocks/secrets](https://docs.continue.dev/guides/configuring-models-rules-tools).
