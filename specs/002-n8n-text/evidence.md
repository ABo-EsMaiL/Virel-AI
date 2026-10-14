# Native text evidence — stage 002

## Verified

2026-10-14: n8n Docker 2.41.4, native OpenAI node 1.8, Text / Message, raw output. One manual workflow named **Virel AI - Native text smoke** is used for every stage; do not create separate test workflows.

Both a native CLI execution and the user's editor execution returned `VIREL_N8N_OK` through Chromium / AI Studio. Selected model: `gemini-3.8-flash`; headed browser; existing user-selected profile; fresh chat per request.

The user then executed the same native node with observed usage enabled and received:

```json
{
  "prompt_tokens": 18,
  "completion_tokens": 108,
  "total_tokens": 126,
  "completion_tokens_details": {"reasoning_tokens": 100}
}
```

The gateway log independently recorded the same request totals. Output includes 8 visible tokens and 100 reasoning tokens. Counts are generation metadata, not a word-count estimate or a Google billing/quota report. Missing observations return null usage with unavailable/unknown provenance.

41 offline tests pass, including the 17 foundation tests. Covered: JSON default, output_text shape, measured usage/reset/correlation, exact model identity, catalog/auth, error/timeout/readiness, malformed input and unsupported options. Existing Chat SSE is preserved; full native Responses streaming and session totals remain later stages.

## Native Chat and Responses acceptance

The same workflow now contains Chat raw, Chat simplified, Responses raw and Responses simplified nodes in sequence. The first four-node attempt stopped at Chat raw: AI Studio displayed `Failed to generate content. Please try again.` The gateway returned HTTP 502 rather than a successful error-text completion. This is failure-path evidence, not a successful four-node acceptance.

A subsequent manual execution through the official n8n MCP succeeded in 34 seconds. All four nodes returned `VIREL_N8N_OK`; n8n recorded tokenUsage metadata in raw and simplified modes.

| Native node | Version / operation | Input | Output | Total |
|---|---|---:|---:|---:|
| Chat raw | 1.8 / message | 18 | 136 | 154 |
| Chat simplified | 1.8 / message | 18 | 185 | 203 |
| Responses raw | 2.3 / response | 18 | 160 | 178 |
| Responses simplified | 2.3 / response | 18 | 112 | 130 |

Simplified output omits the top-level protocol usage object; n8n retains input/output token metadata on the execution. [Sanitized native results](native-results.json), [workflow reference](native-workflow.json). The reference omits credentials; assign your existing OpenAI credential when configuring the existing smoke workflow. This is text acceptance for these exact operations, not certification of every OpenAI node or media/tool/agent feature.

Self-review found and repaired a shared validator collision with legacy prompt input, and distinguished browser failure items from legitimate model text beginning `[Error:`. All 41 checks pass; no foundation test was removed. Spec Kit convergence found no remaining application requirements; delivery/CI remain tracked separately.

## Tooling

n8n MCP OAuth login succeeded. Workflow-level Available in MCP was saved and direct read/manual execution succeeded. Preserve workflow settings when editing through MCP. The CLI's community-package warning concerns the existing custom provider's missing @langchain/anthropic dependency; no installed package was changed. CLI broker conflicts were isolated with a per-process port override.

Secrets, raw execution data, Google response signatures, credentials and profiles remain in ignored runtime storage. Published fixtures must omit credential IDs/keys and authorization data.

The final reviewed browser-error representation also passed a second four-node native execution in 30 seconds. Native modelSearch with the existing OpenAI credential returned gemini-3.8-flash from the gateway catalog. Malformed legacy Responses messages were subsequently fixed through a focused failing/passing regression; the native input shape is unchanged.
