"""AI Studio DOM response-state reader executed inside Chromium."""

import json

ERROR_SELECTORS = 'mat-snack-bar-container, .toast, [role="alert"], ms-chat-turn .error-message, ms-chat-turn ms-error-chunk'
ERROR_PATTERN = r"permission denied|internal error|failed to generate|too_many_tool_calls|too many tool calls|quota exceeded|daily limit of requests|rate limit|model (?:isn.t|is not) available right now|model is currently unavailable|model is overloaded|service unavailable|something went wrong"

START_ERROR_WATCH = r"""() => {
    window.__virelGenerationErrors?.observer.disconnect();
    const state = {error: '', observer: null};
    const selectors = __SELECTORS__;
    const pattern = new RegExp(__PATTERN__, 'i');
    const capture = node => {
        const el = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
        if (!el) return;
        const candidates = [el.closest(selectors), ...el.querySelectorAll(selectors)].filter(Boolean);
        for (const candidate of candidates) {
            const text = (candidate.innerText || candidate.textContent || '').trim().slice(0, 1200);
            if (pattern.test(text)) state.error = text;
        }
    };
    state.observer = new MutationObserver(records => {
        for (const record of records) {
            if (record.type === 'characterData') capture(record.target);
            for (const node of record.addedNodes) capture(node);
        }
    });
    state.observer.observe(document.body, {subtree: true, childList: true, characterData: true});
    window.__virelGenerationErrors = state;
}""".replace('__SELECTORS__', json.dumps(ERROR_SELECTORS)).replace('__PATTERN__', json.dumps(ERROR_PATTERN))

STOP_ERROR_WATCH = """() => {
    window.__virelGenerationErrors?.observer.disconnect();
    delete window.__virelGenerationErrors;
}"""

FETCH_RESPONSE_STATE = '''(initialCount) => {
            // 1. Locate the Run/Stop action button in Google AI Studio
            const allButtons = Array.from(document.querySelectorAll('button'));
            const actionBtn = document.querySelector(
                'button.ctrl-enter-submits, button.ctrl-enter, button[mattooltipclass="run-button-tooltip"]'
            ) || allButtons.find(b => {
                const cls = (b.className || '').toLowerCase();
                const txt = (b.innerText || '').toLowerCase();
                return cls.includes('ctrl-enter') || (txt.includes('stop') && !b.disabled) || (txt.includes('run') && cls.includes('primary'));
            });

            let isRunning = false;
            let isRunDisabled = false;
            let buttonText = "";

            if (actionBtn) {
                buttonText = (actionBtn.innerText || actionBtn.textContent || '').trim().toLowerCase();
                const ariaLabel = (actionBtn.getAttribute('aria-label') || '').toLowerCase();
                const ariaDis = actionBtn.getAttribute('aria-disabled');
                const isDis = actionBtn.disabled || ariaDis === 'true' || actionBtn.classList.contains('mat-button-disabled');

                // If button contains "stop", or has the progress_activity icon:
                const hasStop = buttonText.includes('stop') || ariaLabel.includes('stop') || ariaLabel.includes('cancel');
                const hasProgress = buttonText.includes('progress_activity') || actionBtn.querySelector('mat-spinner, ms-spinner, mat-progress-spinner') !== null;

                if ((hasStop || hasProgress) && !isDis) {
                    isRunning = true;
                } else if (buttonText.includes('run')) {
                    if (isDis) {
                        isRunDisabled = true;
                    }
                }
            }

            // Also check for any active spinners or thinking sections across the entire page
            const hasSpinner = document.querySelector(
                'mat-progress-spinner, .typing-indicator, ms-spinner, .thought-activity-host[aria-expanded="true"], [data-test-id*="spinner" i]'
            ) !== null;

            if (hasSpinner) {
                isRunning = true;
            }

            // Check for internal errors and tool call errors
            let hasError = false;
            let errorText = "";
            const watch = window.__virelGenerationErrors;
            const pattern = new RegExp(__PATTERN__, 'i');
            errorText = watch ? watch.error : Array.from(document.querySelectorAll(__SELECTORS__))
                .map(el => (el.innerText || el.textContent || '').trim()).find(text => pattern.test(text)) || '';
            hasError = Boolean(errorText);

            const bodyTxt = (document.body.innerText || '');
            if (bodyTxt.includes('too_many_tool_calls') || bodyTxt.includes('Too many tool calls')) {
                hasError = true;
                errorText = 'TOO_MANY_TOOL_CALLS: ' + bodyTxt.slice(0, 500);
            }

            // Count tool call chips in chat turns
            let toolCallsCount = 0;
            const toolChips = document.querySelectorAll('ms-chat-turn ms-grounding-chip, ms-chat-turn ms-search-query, ms-chat-turn .grounding-chip, ms-chat-turn .tool-call, ms-chat-turn [data-test-id*="tool" i]');
            toolCallsCount = toolChips.length;

            if (hasError) {
                return { text: "", is_running: isRunning, has_error: true, error_text: errorText, tool_calls: toolCallsCount };
            }

            // Find all chat turns (top-level elements only)
            let allTurns = Array.from(document.querySelectorAll('ms-chat-turn'));
            if (allTurns.length === 0) {
                allTurns = Array.from(document.querySelectorAll('.chat-turn-container, .chat-turn, [data-turn-role]')).filter(el => {
                    return !el.parentElement.closest('.chat-turn-container, .chat-turn, [data-turn-role]');
                });
            }
            if (allTurns.length === 0) {
                return { text: "", is_running: isRunning, has_error: false };
            }

            // Count model turns using strict model turn vs user turn discriminators
            const isUserTurn = (t) => {
                if (t.querySelector('.user-prompt-container')) return true;
                const author = (t.querySelector('.author-label, .turn-author, .role-label, ms-author-label')?.innerText || '').toLowerCase();
                if (author.includes('user') || author.includes('you')) return true;
                const role = (t.getAttribute('data-turn-role') || '').toLowerCase();
                const cls = (t.className || (t.getAttribute('class') || '')).toLowerCase();
                if (role === 'user' || cls.includes('user')) return true;
                return false;
            };

            const isModelTurn = (t) => {
                if (isUserTurn(t)) return false;
                if (t.querySelector('.model-prompt-container')) return true;
                const author = (t.querySelector('.author-label, .turn-author, .role-label, ms-author-label')?.innerText || '').toLowerCase();
                if (author.includes('model') || author.includes('gemini')) return true;
                const role = (t.getAttribute('data-turn-role') || '').toLowerCase();
                const cls = (t.className || (t.getAttribute('class') || '')).toLowerCase();
                if (role === 'model' || cls.includes('model')) return true;
                return Boolean(t.querySelector('ms-thought-chunk, .thought-activity-host, [aria-label*="thumb" i], [aria-label*="Good response" i], [aria-label*="Bad response" i]'));
            };

            const modelTurns = allTurns.filter(isModelTurn);
            const currentModelCount = modelTurns.length;
            const newModelTurnStarted = (currentModelCount > initialCount);

            // A final answer can be an unlabelled chunk after its labelled thought turn.
            const modelTurnsToExtract = [];
            const newModelTurns = new Set(modelTurns.slice(initialCount));
            let inNewModelTurn = false;
            for (const t of allTurns.slice(allTurns.findLastIndex(isUserTurn) + 1)) {
                if (isModelTurn(t)) {
                    inNewModelTurn = newModelTurns.has(t);
                } else {
                    inNewModelTurn = inNewModelTurn &&
                        t.matches('ms-chat-turn.text-chunk-host') &&
                        !t.getAttribute('data-turn-role') &&
                        !t.querySelector('.author-label, .turn-author, .role-label, ms-author-label, ms-function-response-chunk') &&
                        Boolean(t.querySelector('ms-text-chunk, ms-code-block, ms-code-chunk, .cmark-node, ms-function-call-chunk'));
                }
                if (inNewModelTurn) modelTurnsToExtract.push(t);
            }

            // Only typed function components in new model turns are callable output.
            const functionCalls = newModelTurnStarted ? modelTurnsToExtract.flatMap(turn =>
                Array.from(turn.querySelectorAll('ms-function-call-chunk')).filter(chunk =>
                    !chunk.closest('ms-thought-chunk, .thought-activity-host')).map(chunk => ({
                        name: (chunk.querySelector('.title-text')?.textContent || '').trim().slice(0, 65),
                        arguments: (chunk.querySelector('pre code')?.textContent || '')
                    }))) : [];

            // Extract text from these model turns
            let fullText = "";

            modelTurnsToExtract.forEach(currentNode => {
                const chunks = Array.from(currentNode.querySelectorAll('ms-text-chunk, ms-code-block, ms-code-chunk, .cmark-node'));
                if (chunks.length > 0) {
                    const topLevelChunks = chunks.filter(c => {
                        return !c.parentElement.closest('ms-text-chunk, ms-code-block, ms-code-chunk, .cmark-node');
                    });

                    topLevelChunks.forEach(chunk => {
                        if (chunk.closest('ms-thought-chunk, .thought-activity-host, ms-function-call-chunk')) return;

                        const selectorsToRemove = '.mat-expansion-panel-header, .code-block-header, button, mat-icon, .material-symbols-outlined, ms-citation-chunk, .citation';

                        const hiddenStates = [];
                        chunk.querySelectorAll(selectorsToRemove).forEach(n => {
                            hiddenStates.push({ node: n, display: n.style.display });
                            n.style.display = 'none';
                        });

                        try {
                            const t = (chunk.innerText || '').trim();
                            if (t) {
                                if (fullText.length > 0) fullText += '\\n\\n';
                                fullText += t;
                            }
                        } finally {
                            hiddenStates.forEach(item => {
                                item.node.style.display = item.display;
                            });
                        }
                    });
                }
            });

            // AI Studio reports safety refusals as a warning, without a text chunk.
            if (!fullText.trim() && !isRunning && modelTurnsToExtract.some(node => /prohibited content/i.test(node.innerText || ''))) {
                return { text: "", is_running: false, has_error: true,
                    error_text: "CONTENT_BLOCKED: AI Studio rejected this request (Prohibited content).",
                    new_model_turn_started: newModelTurnStarted, tool_calls: toolCallsCount };
            }

            return {
                model_turn_id: modelTurnsToExtract.at(-1)?.id || "",
                function_calls: functionCalls,
                text: fullText.trim(),
                is_running: isRunning,
                is_run_disabled: isRunDisabled,
                button_text: buttonText,
                has_error: false,
                error_text: "",
                new_model_turn_started: newModelTurnStarted,
                tool_calls: toolCallsCount
            };
        }'''.replace('__SELECTORS__', json.dumps(ERROR_SELECTORS)).replace('__PATTERN__', json.dumps(ERROR_PATTERN))


def response_state_script(preserve_markdown=False):
    """Opt-in formatting at the text seam; disabled needs no optional module."""
    if not preserve_markdown:
        return FETCH_RESPONSE_STATE
    from .response_markdown import RENDER_MARKDOWN
    return FETCH_RESPONSE_STATE.replace(
        "const t = (chunk.innerText || '').trim();",
        "const t = (" + RENDER_MARKDOWN + ")(chunk);",
    )
