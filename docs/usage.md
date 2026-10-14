# Token usage contract

Stage 002 implements request-correlated JSON usage from the browser's own GenerateContent response. Native n8n Chat text returned reported counts; see [evidence](../specs/002-n8n-text/evidence.md). Session aggregation and full protocol streaming remain later stages. Word counts are never token counts.

| Level | Record |
|---|---|
| Request | ID, actual model, input/output/total, provenance, accuracy and outcome |
| Browser attempt | Attempt ID correlated with the request; retries may consume tokens |
| Session | Session ID, request count, reported totals and estimated/unknown portions |
| Context | Current effective context size, separate from cumulative consumption |

## Sources and accuracy

Prefer counts correlated to the current generation, observed from the UI or the response received by that browser. Observing browser traffic does not authorize adding Google API/SDK calls or an API-key dependency.

Distinguish reported, estimated and unknown per field. A context counter is not automatically per-request consumption. Missing thinking/cache/media values are not measured zeros. An OpenAI tokenizer does not prove Gemini usage. Partial observations must not be presented as complete measured totals.

Google documents usage metadata for its API, but this does not prove that AI Studio exposes the same data. [Google token documentation](https://ai.google.dev/gemini-api/docs/generate-content/tokens). Generated token usage can exceed visible text. [OpenAI token documentation](https://developers.openai.com/api/docs/guides/token-counting).

## Client mapping

Chat uses `prompt_tokens`, `completion_tokens`, `total_tokens`; Responses uses `input_tokens`, `output_tokens`, `total_tokens`. Match protocol meanings without double-counting cached/thinking subsets. Retain provenance separately. Choose null/omission/estimation behavior through SDK and native-client tests; never fill absent observations with fabricated integers.

Streaming usage belongs in the protocol's final event/chunk when requested. Cancellation, failure and missing final metadata retain partial/unknown states, not an invented zero. Deltas are not separate requests.

Full-history replay consumes the effective context again on each generation. Session cumulative consumption and current context size are different metrics. Retried attempts are counted separately; repeated observation of one attempt is deduplicated. Virel telemetry does not establish Google billing or remaining quota.

Store IDs/counts/outcomes in private runtime storage, without prompts, cookies or uploaded contents. Session isolation and its aggregation are stage 003 work.

## Acceptance checks

Multilingual/code/history inputs; current vs stale metadata; JSON vs SSE; incomplete observations; retry/cancel/failure; isolated sessions; media/tools/thinking/cache when those stages implement them.

## Current implementation

`virel/usage.py` observes only browser-generated HTTPS GenerateContent requests tied to the active attempt and matching prompt. Completed metadata is checked against total=input+output. Reasoning is included in output once; cache is an input subset. Absent optional details are omitted. Unknown/inconsistent framing produces null usage. JSON responses carry X-Request-ID, X-Virel-Usage-Source and X-Virel-Usage-Accuracy.

The array-wire framing is an observed website detail and can change. Core counts are accepted only when complete and consistent. The fixture is sanitized, with field meanings checked against [Google's official protobuf source](https://github.com/googleapis/googleapis/blob/master/google/ai/generativelanguage/v1beta/generative_service.proto).
