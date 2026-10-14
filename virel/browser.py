"""Persistent AI Studio browser: session, UI controls, generation lifecycle."""

import asyncio
import json
import logging
import re
import time
from typing import AsyncGenerator, List, Optional, Union
from playwright.async_api import async_playwright, BrowserContext, Page

from .config import (CHROME_PROFILE_DIR, HEADLESS, DEFAULT_MODEL, THINKING_MODE, ENABLE_SEARCH_GROUNDING, CLEAR_CHAT_ON_REQUEST, TARGET_URL)
from .dom import FETCH_RESPONSE_STATE

logger = logging.getLogger("virel.webhook")


class WebHookBrowserManager:
    def __init__(self):
        self.playwright = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.lock = asyncio.Lock()
        self.is_ready = False
        self.is_shutting_down = False
        self.active_model = ""
        self.model_verified = False
        self.active_thinking = ""
        self.thinking_verified = False
        self.google_search_enabled = False
        self.search_verified = False
        self.last_tool_calls_count = 0

    async def start(self):
        logger.info(f"Launching persistent Chromium context from: {CHROME_PROFILE_DIR} (headless={HEADLESS}, start-maximized)")
        self.playwright = await async_playwright().start()

        args = [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized"
        ]

        try:
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=CHROME_PROFILE_DIR,
                headless=HEADLESS,
                no_viewport=True,
                args=args,
                ignore_default_args=["--enable-automation"]
            )
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            logger.error(f"Please ensure no other Chromium process is using {CHROME_PROFILE_DIR}.")
            raise e

        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

        # Attach network response listener to capture any Google backend errors
        async def handle_response(response):
            try:
                url = response.url
                if any(k in url.lower() for k in ["alkali", "generatecontent", "runprompt", "clients6.google.com", "streamgeneratecontent"]):
                    if response.status >= 400:
                        try:
                            body = await response.text()
                            logger.error(f"[Google Backend Error {response.status}] URL: {url[:80]} | Response Body: {body[:600]}")
                        except Exception:
                            logger.error(f"[Google Backend Error {response.status}] URL: {url[:80]}")
                    elif "generatecontent" in url.lower() or "runprompt" in url.lower():
                        logger.info(f"[Google Backend Status {response.status}] URL: {url[:80]}")
            except Exception:
                pass

        self.page.on("response", handle_response)
        self.page.on("pageerror", lambda err: logger.warning(f"[Browser Page Error]: {err}"))

        logger.info(f"Navigating to {TARGET_URL} to ensure clean environment...")
        try:
            await self.page.goto(TARGET_URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"Initial page navigation warning: {e}. Page will be ready on demand.")

        # Check if user needs to log in
        if "accounts.google.com" in self.page.url or "welcome" in self.page.url:
            logger.warning("=" * 65)
            logger.warning("[ACTION REQUIRED] Google AI Studio requires Google Account login!")
            logger.warning("Please sign into your Google account in the Chromium window.")
            logger.warning("Waiting for login completion...")
            logger.warning("=" * 65)
            
            # Wait up to 3 minutes for user to sign in
            start_wait = time.time()
            while time.time() - start_wait < 180:
                if self.page.is_closed() or self.is_shutting_down:
                    break
                ta = self.page.locator('.prompt-box-container textarea, textarea[formcontrolname="promptText"], textarea[aria-label*="prompt" i], textarea[placeholder*="Type" i]').first
                if await ta.count() > 0 and await ta.is_visible():
                    logger.info("Login confirmed! Prompt textarea detected.")
                    break
                await asyncio.sleep(2)

        self.is_ready = True
        logger.info("Google AI Studio web page ready!")
        
        await self.ensure_model(DEFAULT_MODEL)
        await self.ensure_thinking_mode()
        await self.ensure_tools(ENABLE_SEARCH_GROUNDING)

    async def ensure_model(self, target_model: Optional[str] = None):
        """Ensures the requested model is selected in Google AI Studio UI."""
        target_model = target_model or DEFAULT_MODEL
        if not target_model or not self.page or self.page.is_closed() or self.is_shutting_down:
            return
            
        norm_target = target_model.lower().replace("gemini-", "").replace("gemini ", "").strip()
        logger.info(f"Target model: '{target_model}'")
        
        try:
            selectors = [
                'button.model-selector-card',
                '.settings-model-selector button',
                '.settings-model-selector',
                'button[aria-label*="Model" i]',
                'ms-model-selector button',
                '.model-selector button',
                'mat-select[aria-label*="Model" i]',
                'ms-model-selector mat-select',
                '.model-selector mat-select',
                '[data-test-id="model-selector"]',
            ]
            
            model_el = None
            for sel in selectors:
                loc = self.page.locator(sel)
                if await loc.count() > 0:
                    try:
                        await loc.first.wait_for(state="visible", timeout=2000)
                        cls = (await loc.first.get_attribute("class") or "").lower()
                        if "upgrade" in cls:
                            continue
                        model_el = loc.first
                        break
                    except Exception:
                        pass
                        
            if not model_el:
                try:
                    all_selects = self.page.locator('mat-select')
                    cnt = await all_selects.count()
                    for i in range(cnt):
                        s = all_selects.nth(i)
                        cls = (await s.get_attribute("class") or "").lower()
                        if "upgrade" in cls:
                            continue
                        label = (await s.get_attribute("aria-label") or "").lower()
                        txt = (await s.inner_text() or "").lower()
                        if "model" in label or any(m in txt for m in ["gemini-3", "3.8", "flash"]):
                            model_el = s
                            break
                except Exception:
                    pass

            current_model_before = ""
            if model_el:
                current_model_before = (await model_el.inner_text() or "").strip()
            else:
                try:
                    current_model_before = await self.page.evaluate('''() => {
                        for (const el of document.querySelectorAll('button, mat-select, [role="button"], .model-picker')) {
                            const t = (el.innerText || '').trim();
                            if (/gemini.*flash|gemini.*pro|flash.*lite/i.test(t) && t.length < 50) {
                                return t;
                            }
                        }
                        return '';
                    }''')
                except Exception:
                    pass

            logger.info(f"Current model before: '{current_model_before}'")

            if current_model_before and (norm_target in current_model_before.lower() or target_model.lower() in current_model_before.lower()):
                self.active_model = current_model_before
                self.model_verified = True
                logger.info(f"Current model after: '{current_model_before}' | MODEL VERIFIED = true")
                return

            if model_el:
                logger.info(f"Changing Model from '{current_model_before}' to '{target_model}'...")
                await model_el.click()
                await asyncio.sleep(0.4)

                options = self.page.locator('mat-option:visible, [role="menuitem"]:visible, [role="option"]:visible')
                opt_count = await options.count()
                available_options = []
                clicked = False
                
                for i in range(opt_count):
                    opt = options.nth(i)
                    text = (await opt.inner_text() or "").strip()
                    available_options.append(text)
                    text_lower = text.lower()
                    if (target_model.lower() in text_lower or 
                        norm_target in text_lower or
                        (norm_target.split("-")[0] in text_lower and "flash" in text_lower)):
                        await opt.click()
                        clicked = True
                        await asyncio.sleep(0.4)
                        current_model_after = (await model_el.inner_text() or "").strip()
                        self.active_model = current_model_after
                        self.model_verified = bool(norm_target in current_model_after.lower() or target_model.lower() in current_model_after.lower())
                        logger.info(f"Current model after: '{current_model_after}' | MODEL VERIFIED = {self.model_verified}")
                        break

                if not clicked:
                    logger.warning(f"Could not find model option matching '{target_model}'. Available options: {available_options}")
                    await self.page.keyboard.press("Escape")
                    self.active_model = current_model_before or target_model
                    self.model_verified = False
                    logger.info(f"Current model after: '{self.active_model}' | MODEL VERIFIED = false")
            else:
                self.active_model = current_model_before or target_model
                self.model_verified = bool(current_model_before and (norm_target in current_model_before.lower() or target_model.lower() in current_model_before.lower()))
                logger.info(f"Current model after: '{self.active_model}' | MODEL VERIFIED = {self.model_verified}")
        except Exception as e:
            logger.warning(f"Failed to set Model: {e}")
            self.model_verified = False

    async def ensure_thinking_mode(self):
        """Ensures the Thinking Mode is set correctly on the current page."""
        if not THINKING_MODE or not self.page or self.page.is_closed() or self.is_shutting_down:
            return
            
        try:
            thinking_select = self.page.locator('mat-select[aria-label="Thinking Level"], mat-select[aria-label*="Thinking" i]')
            
            try:
                await thinking_select.first.wait_for(state="visible", timeout=6000)
            except Exception:
                logger.debug("Thinking Level selector not found or not visible yet.")
                return

            if await thinking_select.count() > 0:
                current_thinking = (await thinking_select.first.inner_text() or "").strip()
                self.active_thinking = current_thinking
                if THINKING_MODE.lower() not in current_thinking.lower():
                    logger.info(f"Changing Thinking Level from '{current_thinking}' to '{THINKING_MODE}'...")
                    await thinking_select.first.click()
                    await asyncio.sleep(0.3)
                    
                    options = self.page.locator('mat-option:visible')
                    count = await options.count()
                    clicked = False
                    available = []
                    for i in range(count):
                        opt = options.nth(i)
                        text = (await opt.inner_text() or "").strip()
                        available.append(text)
                        if THINKING_MODE.lower() in text.lower():
                            await opt.click()
                            clicked = True
                            self.active_thinking = text
                            self.thinking_verified = True
                            logger.info(f"Thinking Level set to '{text}' | THINKING VERIFIED = true")
                            await asyncio.sleep(0.3)
                            break
                    
                    if not clicked:
                        logger.warning(f"Could not find a Thinking Level option matching '{THINKING_MODE}'. Available: {available}")
                        await self.page.keyboard.press("Escape")
                        self.thinking_verified = False
                else:
                    self.active_thinking = current_thinking
                    self.thinking_verified = True
                    logger.info(f"Thinking Level already verified as '{current_thinking}' | THINKING VERIFIED = true")
        except Exception as e:
            logger.warning(f"Failed to set Thinking Mode: {e}")
            self.thinking_verified = False

    async def ensure_tools(self, enable_search: Optional[bool] = None):
        """Ensures Google Search Grounding is configured as requested (default: OFF)."""
        if enable_search is None:
            enable_search = ENABLE_SEARCH_GROUNDING
        if not self.page or self.page.is_closed() or self.is_shutting_down:
            return
            
        try:
            remove_btn = self.page.locator('button[aria-label="Remove Grounding with Google Search"]')
            search_toggle = self.page.locator('button[aria-label="Grounding with Google Search"], button[aria-label*="Google Search" i]')
            
            if not enable_search:
                if await remove_btn.count() > 0:
                    logger.info("Disabling Google Search Grounding via remove button...")
                    await remove_btn.first.click()
                    await asyncio.sleep(0.3)
                elif await search_toggle.count() > 0:
                    checked = await search_toggle.first.get_attribute("aria-checked")
                    if checked == "true":
                        logger.info("Disabling Google Search Grounding via toggle button...")
                        await search_toggle.first.click()
                        await asyncio.sleep(0.3)
                        
                is_off = (await remove_btn.count() == 0)
                if await search_toggle.count() > 0:
                    checked_after = await search_toggle.first.get_attribute("aria-checked")
                    is_off = is_off and (checked_after != "true")
                self.google_search_enabled = not is_off
                self.search_verified = is_off
                logger.info(f"Google Search Grounding: {'ENABLED' if self.google_search_enabled else 'DISABLED'} | SEARCH VERIFIED = {self.search_verified}")
            else:
                if await search_toggle.count() > 0:
                    checked = await search_toggle.first.get_attribute("aria-checked")
                    if checked != "true":
                        logger.info("Enabling Google Search Grounding via toggle button...")
                        await search_toggle.first.click()
                        await asyncio.sleep(0.3)
                is_on = (await remove_btn.count() > 0)
                if await search_toggle.count() > 0:
                    checked_after = await search_toggle.first.get_attribute("aria-checked")
                    is_on = is_on or (checked_after == "true")
                self.google_search_enabled = is_on
                self.search_verified = is_on
                logger.info(f"Google Search Grounding: {'ENABLED' if self.google_search_enabled else 'DISABLED'} | SEARCH VERIFIED = {self.search_verified}")
        except Exception as e:
            logger.warning(f"Failed to ensure tools state: {e}")
            self.search_verified = False

    async def stop(self):
        logger.info("Closing browser context...")
        self.is_shutting_down = True
        self.is_ready = False
        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass
        try:
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass
        logger.info("Browser stopped.")

    async def reset_chat_if_needed(self, model_name: Optional[str] = None):
        """Ensures the chat interface is clean for a new request."""
        if not self.page or self.page.is_closed() or self.is_shutting_down:
            return
        t_reset_start = time.time()
        try:
            await self.page.keyboard.press("Escape")
            await asyncio.sleep(0.1)

            reset_done = False
            try:
                new_btn = self.page.locator('button[aria-label*="New prompt" i], button[aria-label*="New chat" i], a[aria-label*="New prompt" i]').first
                if await new_btn.is_visible():
                    await new_btn.click(timeout=1500)
                    await asyncio.sleep(0.5)
                    ta = self.page.locator('textarea[placeholder*="Type something" i], textarea[aria-label*="prompt" i], ms-autosize-textarea textarea').first
                    if await ta.is_visible():
                        reset_done = True
                        logger.info("Fast chat reset succeeded via UI button.")
            except Exception as e:
                logger.debug(f"Fast reset button click skipped/failed ({e}). Falling back to navigation.")
                reset_done = False

            if not reset_done:
                logger.info("Starting fresh chat session (navigating to new chat)...")
                await self.page.goto(TARGET_URL, timeout=30000, wait_until="domcontentloaded")
                await asyncio.sleep(0.8)

            await self.page.keyboard.press("Escape")
            await self.ensure_model(model_name)
            await self.ensure_thinking_mode()
            await self.ensure_tools(ENABLE_SEARCH_GROUNDING)
            logger.info(f"[TIMING-PREEXEC] Chat reset & setup took {time.time() - t_reset_start:.2f}s (reset_done={reset_done})")
        except Exception as e:
            logger.warning(f"Error resetting chat: {e}")

    # Lifecycle State Constants
    STATE_NO_RESPONSE_STARTED = "NO_RESPONSE_STARTED"
    STATE_RESPONSE_IN_PROGRESS = "RESPONSE_IN_PROGRESS"
    STATE_RESPONSE_COMPLETED = "RESPONSE_COMPLETED"

    @staticmethod
    def get_adaptive_timeouts(case_count: int) -> dict:
        """
        Trigger-based execution configuration:
        - Relies primarily on UI button triggers (Cancel generation vs Disabled/Active).
        - Eliminates arbitrary premature timeout zones (stagnation, first-token).
        - Provides generous initial start window and 20-minute safety ceiling.
        """
        return {
            "initial_start_timeout": 180.0,   # Generous startup grace period to upload/tokenize/start thinking
            "stability_duration": 1.0,        # Once button transitions out of Cancel generation, wait 1.0s for DOM to settle
            "hard_ceiling": 1200.0,           # 20 min safety net ONLY for hung browser/crashed tabs
            "tier": f"trigger-driven ({case_count} cases)"
        }

    async def send_prompt_and_stream(
        self, prompt: str, model_name: Optional[str] = None, batch_size: Optional[int] = None, enable_search: Optional[bool] = None, images: Optional[List[str]] = None
    ) -> AsyncGenerator[Union[dict, str], None]:
        """Injects the prompt (and optional images) into Google AI Studio and yields streaming text deltas."""
        t_req_start = time.time()
        if not self.page or self.page.is_closed() or self.is_shutting_down:
            yield "[Error: Browser page not initialized or server is shutting down]"
            return

        # 0. Check if previous turns have a fatal error ('An internal error has occurred' / 'permission denied')
        # If an error turn exists in the conversation, Google AI Studio rejects all subsequent turns with 403.
        has_fatal_error = False
        try:
            has_fatal_error = await self.page.evaluate('''() => {
                const body = (document.body.innerText || document.body.textContent || '');
                return body.includes('An internal error has occurred') || 
                       body.includes('Failed to generate content') ||
                       body.includes('permission denied');
            }''')
        except Exception:
            pass

        if CLEAR_CHAT_ON_REQUEST or has_fatal_error:
            if has_fatal_error:
                logger.warning("Detected error in previous chat turn. Resetting to fresh chat to prevent 403 Forbidden...")
            await self.reset_chat_if_needed(model_name=model_name)
        else:
            await self.ensure_model(model_name)
            await self.ensure_thinking_mode()

        # Explicitly ensure Google Search Grounding state (default: OFF)
        await self.ensure_tools(enable_search=enable_search)

        # Ensure no stray menus or overlays exist
        try:
            await self.page.keyboard.press("Escape")
            await asyncio.sleep(0.1)
        except Exception:
            pass

        # 1. Count existing completed Model turns (Strict: user turns are excluded)
        initial_model_count = 0
        try:
            initial_model_count = await self.page.evaluate('''() => {
                let allTurns = Array.from(document.querySelectorAll('ms-chat-turn'));
                if (allTurns.length === 0) {
                    allTurns = Array.from(document.querySelectorAll('.chat-turn-container, .chat-turn, [data-turn-role]')).filter(el => {
                        return !el.parentElement.closest('.chat-turn-container, .chat-turn, [data-turn-role]');
                    });
                }
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
                return modelTurns.length;
            }''')
        except Exception as e:
            logger.warning(f"Note inspecting initial turns: {e}")
        logger.info(f"Initial model turns count: {initial_model_count}")

        # 2. Locate the prompt input textarea (No window.scrollTo, no scroll_into_view distortions)
        prompt_locator = self.page.locator(
            '.prompt-box-container textarea, textarea[formcontrolname="promptText"], textarea[aria-label*="prompt" i], textarea[placeholder*="prompt" i], textarea[placeholder*="Type" i]'
        ).last

        try:
            await prompt_locator.wait_for(state="attached", timeout=8000)
            await prompt_locator.wait_for(state="visible", timeout=3000)
        except Exception as e:
            logger.error(f"Could not locate chat prompt input: {e}")
            try:
                await self.page.screenshot(path="debug_missing_input.png")
            except Exception:
                pass
            yield "[Error: Could not locate chat prompt input in Google AI Studio. Check debug_missing_input.png]"
            return

        # 2.5 Attach images if provided (Vision Multi-Modal Support)
        if images:
            logger.info(f"Attaching {len(images)} image(s) to prompt via file input: {images}")
            attached_ok = False
            for attempt in range(1, 4):
                try:
                    file_input = self.page.locator('input[type="file"], [data-test-upload-file-input]').first
                    await file_input.wait_for(state="attached", timeout=10000)
                    await file_input.set_input_files(images)
                    logger.info(f"Files set on input (attempt {attempt}). Waiting for thumbnail chip...")
                    await asyncio.sleep(1.0)
                    for _ in range(16):
                        chip_count = await self.page.locator(
                            '.prompt-box-container img, ms-prompt-box img, .media-chunk, .file-chip, [data-test*="media"], ms-file-chip, [data-test-id*="media"]'
                        ).count()
                        if chip_count > 0:
                            logger.info(f"Detected {chip_count} uploaded media chip(s) in AI Studio UI.")
                            attached_ok = True
                            break
                        await asyncio.sleep(0.5)
                    if attached_ok:
                        break
                except Exception as e:
                    logger.warning(f"Error attaching images on attempt {attempt}: {e}")
                    await asyncio.sleep(1.0)

            if not attached_ok:
                logger.error("CRITICAL: Failed to attach image to Google AI Studio prompt! Aborting to prevent text-only hallucination.")
                yield "[Error: Image could not be attached to Google AI Studio prompt. File upload failed.]"
                return

        # 3. Focus, clear, and insert prompt text cleanly via JAVASCRIPT
        try:
            logger.info("Injecting prompt via JavaScript and triggering native events...")
            ta = self.page.locator('textarea[placeholder*="Type something" i], textarea[aria-label*="prompt" i], ms-autosize-textarea textarea, div[contenteditable="true"]').first
            await ta.wait_for(state="visible", timeout=5000)
            
            # Use JS to set the value instantly (avoids Playwright's fill() dropping chars on huge text)
            await ta.evaluate('''(el, text) => {
                el.value = text;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }''', prompt)
            
            # Settle delay
            await asyncio.sleep(0.1)
            
            # Trigger one native keystroke so Angular/BotGuard registers a trusted event on the non-empty field
            await ta.focus()
            await self.page.keyboard.press("Space")
            await self.page.keyboard.press("Backspace")
            
            await asyncio.sleep(0.4)
        except Exception as e:
            logger.warning(f"Error injecting prompt: {e}")

        # Determine case count from batch_size or prompt inspection
        case_count = batch_size if (batch_size is not None and batch_size > 0) else None
        if not case_count:
            cid_count = prompt.count('"case_id"') or prompt.count("'case_id'")
            case_count = cid_count if cid_count > 0 else 1

        t_cfg = self.get_adaptive_timeouts(case_count)

        # 4. Wait for Run button to become ACTIVE (Tokenization and Image ready)
        logger.info(f"Waiting for Google AI Studio Run button to become active (tokenizing/ready)...")
        run_btn = self.page.locator('button.ctrl-enter-submits, button.ctrl-enter, button[mattooltipclass="run-button-tooltip"], button:has-text("Run")').first
        run_active = False
        t_wait_start = time.time()
        for i in range(50):  # up to 25s for large images/prompts
            try:
                aria_dis = await run_btn.get_attribute("aria-disabled")
                is_dis = await run_btn.is_disabled()
                if aria_dis == "false" and not is_dis:
                    run_active = True
                    logger.info(f"[+] Run button is ACTIVE after {time.time() - t_wait_start:.2f}s! Ready to execute.")
                    break
            except Exception:
                pass
            await asyncio.sleep(0.5)

        current_state = self.STATE_NO_RESPONSE_STARTED
        t_turn_detected: Optional[float] = None
        t_first_token: Optional[float] = None
        stability_start_time: Optional[float] = None
        prev_text = ""
        consecutive_js_errors = 0

        t_submit = time.time()
        t_pre_exec = t_submit - t_req_start
        t_last_growth = t_submit

        try:
            if run_active:
                await run_btn.click()
                logger.info(f"[{case_count} cases] Clicked active Run button. Pre-exec took {t_pre_exec:.2f}s.")
            else:
                logger.warning(f"Run button did not signal active in time. Falling back to native Control+Enter...")
                await ta.focus()
                await self.page.keyboard.press("Control+Enter")
        except Exception as e:
            logger.warning(f"Error submitting via Run button: {e}. Falling back to Control+Enter...")
            try:
                await ta.focus()
                await self.page.keyboard.press("Control+Enter")
            except Exception:
                pass

        logger.info(
            f"[{case_count} cases] Prompt submitted ({len(prompt)} chars). "
            f"Mode: {t_cfg['tier']} | Start Grace: {t_cfg['initial_start_timeout']:.0f}s | "
            f"Trigger: Cancel Generation -> Disabled | Settle: {t_cfg['stability_duration']:.1f}s | "
            f"Ceiling: {t_cfg['hard_ceiling']:.0f}s"
        )


        while (time.time() - t_submit) < t_cfg["hard_ceiling"]:
            now = time.time()
            elapsed = now - t_submit

            if not self.page or self.page.is_closed() or self.is_shutting_down:
                logger.info("Browser session closed or shutting down. Exiting stream.")
                break

            try:
                state = await self.page.evaluate(FETCH_RESPONSE_STATE, initial_model_count)
                consecutive_js_errors = 0
            except Exception as e:
                err_msg = str(e).lower()
                if "closed" in err_msg or "destroyed" in err_msg or "target" in err_msg or self.is_shutting_down:
                    logger.info("Browser closed during stream. Exiting cleanly.")
                    break
                logger.error(f"JS Extraction Error: {e}")
                consecutive_js_errors += 1
                if consecutive_js_errors >= 30:
                    logger.error("JS failed persistently for 30 consecutive attempts. Aborting.")
                    yield {"delta": "", "text": "[Error: Internal extraction logic failed persistently.]"}
                    break
                await asyncio.sleep(0.15)
                continue

            current_text = state.get("text", "")
            is_running = state.get("is_running", False)
            is_run_disabled = state.get("is_run_disabled", False)
            button_text = state.get("button_text", "")
            new_model_turn_started = state.get("new_model_turn_started", False)
            has_error = state.get("has_error", False)
            self.last_tool_calls_count = state.get("tool_calls", 0)

            # Check for fatal or tool call error in AI Studio
            if has_error and not is_running and elapsed > 0.5:
                err_text = state.get("error_text") or "Google AI Studio encountered an error ('permission denied' / 'internal error')"
                logger.error(f"Turn ended with an error from Google AI Studio: {err_text}")
                yield {"delta": "", "text": f"[Error: {err_text}]"}
                break

            # ------------------------------------------------------------------
            # 1. State: NO_RESPONSE_STARTED
            # ------------------------------------------------------------------
            if current_state == self.STATE_NO_RESPONSE_STARTED:
                if is_running or new_model_turn_started or len(current_text) > 0:
                    current_state = self.STATE_RESPONSE_IN_PROGRESS
                    t_turn_detected = now
                    t_last_growth = now
                    logger.info(
                        f"[{case_count} cases] State -> RESPONSE_IN_PROGRESS at {t_turn_detected - t_submit:.2f}s "
                        f"(is_running={is_running}, new_model_turn={new_model_turn_started}, initial_chars={len(current_text)})"
                    )
                else:
                    if elapsed > t_cfg["initial_start_timeout"]:
                        logger.error(f"[{case_count} cases] Generation failed to start within {t_cfg['initial_start_timeout']:.0f}s. State: NO_RESPONSE_STARTED.")
                        yield {"delta": "", "text": f"[Error: NO_RESPONSE_STARTED - Google AI Studio did not start generating within {t_cfg['initial_start_timeout']:.0f}s]"}
                        break

            # ------------------------------------------------------------------
            # 2. State: RESPONSE_IN_PROGRESS (Trigger-Driven Streaming)
            # ------------------------------------------------------------------
            if current_state == self.STATE_RESPONSE_IN_PROGRESS:
                # Milestone: First token/character detected
                if len(current_text) > 0 and t_first_token is None:
                    t_first_token = now
                    logger.info(f"[{case_count} cases] First token/character detected at {t_first_token - t_submit:.2f}s (len: {len(current_text)})")

                # Character growth detection
                if len(current_text) > len(prev_text):
                    delta = current_text[len(prev_text):]
                    prev_text = current_text
                    t_last_growth = now
                    stability_start_time = None  # Reset stability timer when text actively grows
                    yield {"delta": delta, "text": current_text}
                else:
                    # No character growth on this tick
                    if is_running:
                        # ------------------------------------------------------------------
                        # CHECK 1 (Trigger active: Button is Stop or spinner active):
                        # As long as is_running is True, the model is actively thinking or
                        # streaming tokens. DO NOT TIMEOUT! NEVER ABORT!
                        # ------------------------------------------------------------------
                        stability_start_time = None
                    else:
                        # ------------------------------------------------------------------
                        # CHECK 1 TRANSITION:
                        # Button transitioned away from Stop state.
                        # Wait stability_duration to allow final DOM flush.
                        # Only settle if we already have text OR if elapsed is > 5.0s.
                        # ------------------------------------------------------------------
                        if len(current_text) == 0 and elapsed < 5.0:
                            stability_start_time = None
                        else:
                            if stability_start_time is None:
                                stability_start_time = now
                            elif (now - stability_start_time) >= t_cfg["stability_duration"]:
                                current_state = self.STATE_RESPONSE_COMPLETED
                                logger.info(
                                    f"[{case_count} cases] State -> RESPONSE_COMPLETED via trigger "
                                    f"(Button: '{button_text}', is_run_disabled={is_run_disabled}; stable for {t_cfg['stability_duration']:.1f}s at {len(current_text)} chars)"
                                )
                                yield {"delta": "", "text": current_text}
                                break

                    # Always yield the current state so non-streaming callers can access text
                    yield {"delta": "", "text": current_text}

            await asyncio.sleep(0.1)
        else:
            # Loop ended due to hard_ceiling
            if current_state != self.STATE_RESPONSE_COMPLETED:
                logger.error(f"[{case_count} cases] Hard ceiling reached ({t_cfg['hard_ceiling']:.0f}s). State: {current_state}. Aborting.")
                yield {"delta": "", "text": f"[Error: HARD_CEILING_TIMEOUT - Request exceeded safe upper bound {t_cfg['hard_ceiling']:.0f}s]"}

        # ----------------------------------------------------------------------
        # CHECK 2: Response Structure & Completeness Validation
        # ----------------------------------------------------------------------
        validation_error = None
        if current_state == self.STATE_RESPONSE_COMPLETED:
            trimmed_text = prev_text.strip()
            if not trimmed_text:
                validation_error = "EMPTY_RESPONSE: Model finished generating but no text was captured from DOM."
            else:
                # If prompt expected JSON / structured data
                expects_json = ('"items"' in prompt or '"cases"' in prompt or 'json' in prompt.lower() or '{' in prompt)
                if expects_json:
                    is_valid_json = False
                    try:
                        json.loads(trimmed_text)
                        is_valid_json = True
                    except Exception:
                        try:
                            fenced = re.sub(r"^```(?:json)?\s*", "", trimmed_text, flags=re.MULTILINE)
                            fenced = re.sub(r"```\s*$", "", fenced, flags=re.MULTILINE).strip()
                            json.loads(fenced)
                            is_valid_json = True
                        except Exception:
                            m = re.search(r'\{.*\}', trimmed_text, re.DOTALL) or re.search(r'\[.*\]', trimmed_text, re.DOTALL)
                            if m:
                                try:
                                    json.loads(m.group(0))
                                    is_valid_json = True
                                except Exception:
                                    pass

                    if not is_valid_json:
                        if not (trimmed_text.endswith('}') or trimmed_text.endswith(']')):
                            validation_error = f"STREAM_TRUNCATED: Response ended abruptly without closing JSON structure (chars: {len(prev_text)})."
                        else:
                            validation_error = f"INVALID_JSON_RESPONSE: Response completed but could not be parsed as valid JSON (chars: {len(prev_text)})."

        if validation_error:
            logger.error(f"[{case_count} cases] [CHECK 2 VALIDATION FAILED] {validation_error}")
            yield {"delta": "", "text": f"[Error: {validation_error}]"}

        # ----------------------------------------------------------------------
        # Detailed Timing Milestones Logging
        # ----------------------------------------------------------------------
        total_duration = time.time() - t_submit
        turn_str = f"{t_turn_detected - t_submit:.1f}s" if t_turn_detected else "N/A"
        first_token_str = f"{t_first_token - t_submit:.1f}s" if t_first_token else "N/A"
        last_growth_str = f"{t_last_growth - t_submit:.1f}s" if (t_last_growth != t_submit) else "N/A"
        completed_str = f"{total_duration:.1f}s" if current_state == self.STATE_RESPONSE_COMPLETED else "INCOMPLETE"

        t_req_total = time.time() - t_req_start
        self.last_timings = {
            "pre_exec": t_pre_exec,
            "generation": total_duration,
            "total": t_req_total,
            "turn_detected": t_turn_detected - t_submit if t_turn_detected else None,
            "first_token": t_first_token - t_submit if t_first_token else None,
            "state": current_state
        }

        timing_summary = (
            f"{case_count} cases | "
            f"first token: {first_token_str} | "
            f"completed: {completed_str} | "
            f"mode: {t_cfg['tier']}"
        )
        logger.info(f"[TIMING] {timing_summary}")
        logger.info(
            f"[TIMING_DETAILS] {case_count} cases | state: {current_state} | "
            f"turn detected: {turn_str} | first token: {first_token_str} | "
            f"last growth: {last_growth_str} | completed: {completed_str} | "
            f"total: {total_duration:.1f}s | chars: {len(prev_text)} | "
            f"tier: {t_cfg['tier']}"
        )
        logger.info(
            f"[TIMING_BREAKDOWN] {case_count} cases | Total: {t_req_total:.2f}s | "
            f"Pre-exec: {t_pre_exec:.2f}s | Model Gen: {total_duration:.2f}s | Chars: {len(prev_text)}"
        )
        print(f"\n[AI STUDIO TIMING] {timing_summary} (Total Roundtrip: {t_req_total:.2f}s)\n")

        too_many_calls_err = None
        if "too_many_tool_calls" in prev_text.lower() or "too many tool calls" in prev_text.lower():
            too_many_calls_err = prev_text[:500]

        logger.info("=" * 65)
        logger.info(f"[BATCH REPORT] Batch Size: {case_count} cases")
        logger.info(f"  * Google Search Enabled: {self.google_search_enabled} (Verified: {self.search_verified})")
        logger.info(f"  * Tool Calls Count: {self.last_tool_calls_count}")
        logger.info(f"  * Thinking Mode/Level: {self.active_thinking} (Verified: {self.thinking_verified})")
        logger.info(f"  * Generation Time: {total_duration:.2f}s (Total Roundtrip: {t_req_total:.2f}s)")
        logger.info(f"  * Final Status: {current_state}")
        if too_many_calls_err:
            logger.error(f"  * Tool Call Error: {too_many_calls_err}")
        else:
            logger.info(f"  * Tool Call Error: None")
        logger.info("=" * 65)

        elapsed_total = time.time() - t_submit
        is_json = False
        json_err_msg = ""
        try:
            clean_test = prev_text.strip()
            # 1. Direct parse
            try:
                json.loads(clean_test)
                is_json = True
            except Exception as e1:
                # 2. Strip code fences
                clean_test = re.sub(r"^```(?:json)?\s*", "", clean_test, flags=re.MULTILINE)
                clean_test = re.sub(r"```\s*$", "", clean_test, flags=re.MULTILINE).strip()
                try:
                    json.loads(clean_test)
                    is_json = True
                except Exception as e2:
                    # 3. Outer { } or [ ]
                    m = re.search(r'\{.*\}', clean_test, re.DOTALL) or re.search(r'\[.*\]', clean_test, re.DOTALL)
                    if m:
                        json.loads(m.group(0))
                        is_json = True
                    else:
                        json_err_msg = f" (no JSON structure found; direct err: {e1})"
        except Exception as e:
            is_json = False
            json_err_msg = f" ({e})"

        logger.info(
            f"Stream finished in {elapsed_total:.2f}s | chars: {len(prev_text)} | "
            f"Valid JSON: {is_json}{json_err_msg} | Sample: {repr(prev_text[:60])}"
        )
