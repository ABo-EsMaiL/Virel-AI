# Data model

Request/attempt: unique ID, protocol, requested/observed model, outcome and optional observed usage. Reset browser-associated observation before each locked generation; bind callbacks to the current generation request. No cross-request carryover.

Usage: input/output/total integers only when supported by correlated metadata; optional observed thinking/cache detail. Preserve source and completeness independently from the client protocol shape. Unknown or inconsistent totals do not become usage integers.

Failure: public message, stable code/type and HTTP status. Never convert the browser's error result into assistant text or a normal stop event.
