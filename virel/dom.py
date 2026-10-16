"""AI Studio DOM response-state reader executed inside Chromium."""

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
            const alertEl = document.querySelector('mat-snack-bar-container, .toast, [role="alert"]');
            if (alertEl) {
                const atxt = (alertEl.innerText || alertEl.textContent || '').toLowerCase();
                if (atxt.includes('permission denied') || atxt.includes('internal error') || atxt.includes('failed to generate') || atxt.includes('too_many_tool_calls') || atxt.includes('too many tool calls')) {
                    hasError = true;
                    errorText = alertEl.innerText || alertEl.textContent || '';
                }
            }

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

            // Iterate backwards to find all consecutive model turns at the end of the chat
            const modelTurnsToExtract = [];
            const newModelTurns = new Set(modelTurns.slice(initialCount));
            for (let i = allTurns.length - 1; i >= 0; i--) {
                const t = allTurns[i];
                if (isUserTurn(t)) {
                    break;
                }
                if (isModelTurn(t) && newModelTurns.has(t)) {
                    modelTurnsToExtract.push(t);
                }
            }

            // They were collected backwards, so reverse them to chronological order
            modelTurnsToExtract.reverse();

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
        }'''
