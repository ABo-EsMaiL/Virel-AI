"""Persistent AI Studio browser: session, UI controls, generation lifecycle."""

import asyncio
import json
import logging
import re
import time
import uuid
from contextlib import aclosing
from typing import AsyncGenerator, List, Optional, Union
from playwright.async_api import async_playwright, BrowserContext, Page

from .config import (RUNTIME_DIR, CHROME_PROFILE_DIR, HEADLESS, DEFAULT_MODEL, THINKING_MODE, ENABLE_SEARCH_GROUNDING, ENABLE_URL_CONTEXT, TARGET_URL)
from .dom import FETCH_RESPONSE_STATE
from .usage import BrowserUsageObserver
from .models import MODEL_SELECTOR, MODEL_ROWS, READ_MODEL_ROWS, catalog_from_rows, selected_id, IMAGE_MODEL_ICONS
from .errors import GatewayError
from .image_output import ensure_image_settings, read_image_output

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
        self.model_catalog = {}
        self.model_catalog_observed = False
        self.catalog_observed_at = 0
        self.generated_models = set()
        self.model_error = "MODEL_UNAVAILABLE"
        self.active_temperature = None
        self.temperature_verified = False
        self.url_context_enabled = False
        self.url_context_verified = False
        self.active_thinking = ""
        self.thinking_verified = False
        self.google_search_enabled = False
        self.search_verified = False
        self.last_tool_calls_count = 0
        self.last_usage = None
        self.comparison_skipped = False
        self.usage_observer = BrowserUsageObserver()

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
                        logger.error("Google backend response status=%s", response.status)
                    elif "generatecontent" in url.lower() or "runprompt" in url.lower():
                        logger.info(f"[Google Backend Status {response.status}] URL: {url[:80]}")
            except Exception:
                pass

        self.page.on("request", self.usage_observer.on_request)
        self.page.on("response", self.usage_observer.on_response)
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

        prompt_ui = self.page.locator('textarea[aria-label*="prompt" i], textarea[placeholder*="Type" i], textarea[formcontrolname="promptText"]').first
        try:
            await prompt_ui.wait_for(state="visible", timeout=8000)
            self.is_ready = True
        except Exception:
            self.is_ready = False
            logger.warning("AI Studio prompt UI unavailable; authenticated requests will return 503.")
            return
        logger.info("Google AI Studio web page ready!")

        await self.ensure_model(DEFAULT_MODEL)
        await self.ensure_thinking_mode()
        await self.ensure_tools(ENABLE_SEARCH_GROUNDING)
        await self.ensure_url_context()
        self.is_ready = self.model_catalog_observed

    async def _open_model_picker(self):
        await self.page.locator(MODEL_SELECTOR).first.click()
        await self.page.locator(MODEL_ROWS).first.wait_for(state='visible', timeout=6000)

    async def refresh_model_catalog(self):
        """Caller owns the browser lock; publish only complete observations."""
        if not self.page or self.page.is_closed() or self.is_shutting_down:
            raise GatewayError(503, 'AI Studio model picker is unavailable.', 'model_catalog_unavailable')
        try:
            await self._open_model_picker()
            catalog = catalog_from_rows(await self.page.evaluate(READ_MODEL_ROWS))
            if not any(item['status'] == 'selectable' for item in catalog.values()):
                raise GatewayError(503, 'AI Studio returned no selectable text models.', 'model_catalog_unavailable')
            self.model_catalog = catalog
            self.catalog_observed_at = int(time.time())
            self.model_catalog_observed = True
        except GatewayError:
            raise
        except Exception:
            raise GatewayError(503, 'AI Studio model discovery failed.', 'model_catalog_unavailable') from None
        finally:
            await self.page.keyboard.press('Escape')
            await self.page.locator(MODEL_ROWS).first.wait_for(state='hidden', timeout=2000)

    def require_model(self, identifier, output_kind="text"):
        item = self.model_catalog.get(identifier)
        if item is None:
            raise GatewayError(404, 'Requested model was not observed in the AI Studio catalog.', 'model_not_found')
        if item['status'] == 'unavailable':
            raise GatewayError(503, 'Requested UI model is disabled or requires paid access.', 'model_unavailable')
        actual = self.model_catalog.get(item.get('resolved_id', identifier), item)
        if actual['status'] == 'unavailable':
            raise GatewayError(503, 'Resolved UI model is disabled or requires paid access.', 'model_unavailable')
        allowed = IMAGE_MODEL_ICONS if output_kind == 'image' else ({'audio_magic_eraser'} if output_kind == 'speech' else {'spark'})
        if output_kind == 'speech' and actual['capabilities'].get('output_modalities') != ['audio']:
            raise GatewayError(400, 'This is not an observed speech-output model.', 'unsupported_model_capability')
        if item['status'] != 'selectable' or actual['capabilities']['ui_category_icon'] not in allowed:
            raise GatewayError(400, 'This model requires an output adapter that is not implemented.', 'unsupported_model_capability')
        return item

    async def ensure_model(self, target_model: Optional[str] = None, output_kind="text"):
        """Select one exact observed card and verify the resulting canonical ID."""
        self.model_verified = False
        self.active_model = ''
        self.model_error = 'MODEL_UNAVAILABLE'
        self.active_temperature = None
        self.temperature_verified = False
        self.url_context_enabled = False
        self.url_context_verified = False
        self.active_thinking = ''
        self.thinking_verified = False
        self.google_search_enabled = False
        self.search_verified = False
        target_model = target_model or DEFAULT_MODEL
        if not self.page or self.page.is_closed() or self.is_shutting_down:
            return
        try:
            if not self.model_catalog_observed or target_model not in self.model_catalog:
                await self.refresh_model_catalog()
            item = self.require_model(target_model, output_kind=output_kind)
            expected = item.get('resolved_id', target_model)
            control = self.page.locator(MODEL_SELECTOR).first
            current = selected_id(await control.inner_text(), self.model_catalog)
            if current != expected:
                try:
                    await self._open_model_picker()
                    current_catalog = catalog_from_rows(await self.page.evaluate(READ_MODEL_ROWS))
                    if target_model not in current_catalog:
                        raise GatewayError(404, 'Requested model is no longer present.', 'model_not_found')
                    self.model_catalog = current_catalog
                    self.catalog_observed_at = int(time.time())
                    item = self.require_model(target_model, output_kind=output_kind)
                    expected = item.get('resolved_id', target_model)
                    card = self.page.locator(MODEL_ROWS + '[id="model-carousel-row-models/' + target_model + '"]').first
                    if await card.is_disabled() or await card.get_attribute('aria-disabled') == 'true':
                        return
                    await card.click()
                finally:
                    await self.page.keyboard.press('Escape')
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    current = selected_id(await control.inner_text(), self.model_catalog)
                    if current == expected:
                        break
                    await asyncio.sleep(.2)
            self.active_model = current or ''
            self.model_verified = current == expected
            logger.info('Model requested=%s active=%s verified=%s', target_model, self.active_model, self.model_verified)
        except GatewayError as error:
            self.model_error = 'MODEL_NOT_FOUND' if error.status_code == 404 else ('UNSUPPORTED_MODEL' if error.status_code == 400 else 'MODEL_UNAVAILABLE')
        except Exception as error:
            logger.warning('Model selection could not be verified: %s', str(error).splitlines()[0])

    async def ensure_thinking_mode(self, effort=None):
        """Apply the current request, never a preceding request's override."""
        self.active_thinking = ""
        self.thinking_verified = False
        target = effort if effort is not None else THINKING_MODE
        if not target or not self.page or self.page.is_closed() or self.is_shutting_down:
            return
        try:
            control = self.page.locator('mat-select[aria-label*="Thinking" i]').first
            if await control.count() and await control.is_visible():
                selected = control.locator(".mat-mdc-select-min-line").first
                if not await selected.count():
                    selected = control
                if (await selected.inner_text()).strip().lower() != target:
                    await control.click()
                    options = self.page.locator('mat-option:visible')
                    for i in range(await options.count()):
                        if (await options.nth(i).inner_text()).strip().lower() == target:
                            await options.nth(i).click()
                            await options.first.wait_for(state="hidden", timeout=2000)
                            break
                    else:
                        await self.page.keyboard.press("Escape")
                self.active_thinking = (await selected.inner_text()).strip().lower()
                self.thinking_verified = self.active_thinking == target
        except Exception:
            logger.warning("Thinking level could not be verified.")
        if effort is not None and not self.thinking_verified:
            raise GatewayError(400, "Requested thinking level is unavailable for this UI model.", "unsupported_parameter", param="reasoning_effort")

    async def ensure_temperature(self, temperature=None):
        self.active_temperature = None
        self.temperature_verified = False
        control = self.page.locator('input[aria-label="Temperature"][role="spinbutton"], input[aria-label="Temperature"][type="number"]').first
        if not await control.count() or not await control.is_visible() or not await control.is_enabled():
            if temperature is not None:
                raise GatewayError(400, "Temperature control is unavailable for this UI model.", "unsupported_parameter", param="temperature")
            return
        target = 1 if temperature is None else temperature
        low = await control.get_attribute('aria-valuemin') or await control.get_attribute('min')
        high = await control.get_attribute('aria-valuemax') or await control.get_attribute('max')
        if (low is not None and target < float(low)) or (high is not None and target > float(high)):
            raise GatewayError(400, "Temperature is outside the current model's UI range.", "unsupported_parameter")
        try:
            await control.fill(str(target))
            await control.press("Tab")
            self.active_temperature = float(await control.input_value())
            self.temperature_verified = abs(self.active_temperature - target) < 1e-9 and await control.get_attribute('aria-invalid') != 'true'
        except Exception:
            logger.warning("Temperature could not be verified.")
        if not self.temperature_verified:
            raise GatewayError(503, "AI Studio temperature could not be verified.", "settings_unavailable")

    async def ensure_url_context(self):
        self.url_context_enabled = False
        self.url_context_verified = False
        if not self.page or self.page.is_closed() or self.is_shutting_down:
            return
        try:
            control = self.page.locator('button[role="switch"][aria-label="Browse the url context" i]').first
            if not await control.count() or not await control.is_visible() or not await control.is_enabled():
                return
            if (await control.get_attribute('aria-checked') == 'true') != ENABLE_URL_CONTEXT:
                await control.click()
            self.url_context_enabled = await control.get_attribute('aria-checked') == 'true'
            self.url_context_verified = self.url_context_enabled == ENABLE_URL_CONTEXT
        except Exception:
            logger.warning("URL Context could not be verified.")

    async def ensure_tools(self, enable_search: Optional[bool] = None):
        """Observe/configure search only when its current-model controls exist."""
        self.google_search_enabled = False
        self.search_verified = False
        if enable_search is None:
            enable_search = ENABLE_SEARCH_GROUNDING
        if not self.page or self.page.is_closed() or self.is_shutting_down:
            return

        try:
            remove_btn = self.page.locator('button[aria-label="Remove Grounding with Google Search"]')
            search_toggle = self.page.locator('button[aria-label="Grounding with Google Search"], button[aria-label*="Google Search" i]')

            if await remove_btn.count() == 0 and await search_toggle.count() == 0:
                return
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
                if await remove_btn.count() == 0 and await search_toggle.count() > 0:
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

    async def reset_chat_if_needed(self, model_name: Optional[str] = None, output_kind="text") -> bool:
        """Never replay caller history into a retained browser conversation."""
        if not self.page or self.page.is_closed() or self.is_shutting_down:
            return False
        try:
            await self.page.goto(TARGET_URL, timeout=30000, wait_until="domcontentloaded")
            await self.page.keyboard.press("Escape")
            await self.ensure_model(model_name, output_kind=output_kind)
            if output_kind == 'speech':
                return self.model_verified
            prompt = self.page.locator('.prompt-box-container textarea, textarea[formcontrolname="promptText"], textarea[aria-label*="prompt" i], textarea[placeholder*="Type" i]').last
            await prompt.wait_for(state="visible", timeout=8000)
            turns = self.page.locator('ms-chat-turn, .chat-turn-container, .chat-turn, [data-turn-role]')
            if await turns.count() or (await prompt.input_value()).strip():
                logger.warning("Fresh-chat verification failed; refusing to reuse browser context.")
                return False
            await self.ensure_thinking_mode()
            await self.ensure_tools(ENABLE_SEARCH_GROUNDING)
            await self.ensure_url_context()
            return True
        except Exception:
            logger.warning("Fresh-chat navigation or prompt verification failed.")
            return False

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

    async def send_prompt_and_stream(self, prompt, model_name=None, batch_size=None, enable_search=None, images=None, request_id=None, reasoning_effort=None, temperature=None, output_kind="text", image_size="auto", image_settings=None):
        attempt_id = request_id or uuid.uuid4().hex
        self.last_usage = None
        self.comparison_skipped = False
        self.usage_observer.begin(attempt_id, prompt)
        final_text = ""
        failed = False
        try:
            async with aclosing(self._generate_in_page(prompt, model_name, batch_size, enable_search, images, reasoning_effort=reasoning_effort, temperature=temperature, output_kind=output_kind, image_size=image_size, image_settings=image_settings)) as stream:
                async for item in stream:
                    if isinstance(item, dict):
                        failed |= "error" in item
                        final_text = item.get("text", final_text)
                    else:
                        final_text += item
                    yield item
            if output_kind == "text" and not failed and final_text.strip() and self.model_verified:
                self.generated_models.add(self.active_model)
        finally:
            usage = await self.usage_observer.finish(attempt_id)
            self.last_usage = None if self.comparison_skipped else usage

    async def attach_files(self, paths: List[str]) -> bool:
        """Do not run until all current-request attachment chips are ready."""
        try:
            file_input = self.page.locator('input[type="file"], [data-test-upload-file-input]').first
            await file_input.wait_for(state="attached", timeout=8000)
            await file_input.set_input_files(paths)
            ready = """(expected) => {
                const selector = '.prompt-media-item-container, .prompt-box-container .file-chip, ms-prompt-box ms-file-chip';
                const chips = Array.from(document.querySelectorAll(selector)).filter(el => !el.parentElement?.closest(selector));
                const busy = Array.from(document.querySelectorAll('.prompt-box-container [role="progressbar"], ms-prompt-box [role="progressbar"], .prompt-box-container mat-progress-spinner, ms-prompt-box ms-spinner'))
                    .some(el => el.getClientRects().length > 0);
                const unloaded = chips.some(el => Array.from(el.querySelectorAll('img')).some(img => !img.complete || img.naturalWidth === 0));
                return chips.length === expected && !busy && !unloaded;
            }"""
            # AI Studio Trusted Types blocks wait_for_function's eval; direct evaluation works.
            deadline = time.monotonic() + self.get_adaptive_timeouts(len(paths))["initial_start_timeout"]
            while time.monotonic() < deadline:
                if await self.page.evaluate(ready, len(paths)):
                    return True
                await asyncio.sleep(0.25)
            logger.warning("Media attachment readiness timed out.")
            return False
        except Exception as error:
            logger.warning("Media upload or attachment readiness failed (%s).", type(error).__name__)
            return False

    async def _generate_in_page(
        self, prompt: str, model_name: Optional[str] = None, batch_size: Optional[int] = None, enable_search: Optional[bool] = None, images: Optional[List[str]] = None, reasoning_effort=None, temperature=None, output_kind="text", image_size="auto", image_settings=None
    ) -> AsyncGenerator[Union[dict, str], None]:
        """Injects the prompt (and optional images) into Google AI Studio and yields streaming text deltas."""
        t_req_start = time.time()
        if not self.page or self.page.is_closed() or self.is_shutting_down:
            yield {"error": "[Error: Browser page not initialized or server is shutting down]"}
            return

        if not await self.reset_chat_if_needed(model_name=model_name, output_kind=output_kind):
            yield {"error": "[Error: RESET_FAILED - could not establish an empty chat]"}
            return

        if not self.model_verified:
            yield {"error": "[Error: " + self.model_error + " - requested model is not verified]"}
            return

        if reasoning_effort is not None:
            await self.ensure_thinking_mode(reasoning_effort)
        await self.ensure_temperature(temperature)
        if output_kind == "image":
            await ensure_image_settings(self.page, image_size, image_settings)

        # Preserve the requested/current Google Search state.
        await self.ensure_tools(enable_search=enable_search)
        if enable_search is True and not (self.google_search_enabled and self.search_verified):
            yield {"error": "[Error: UNSUPPORTED_GOOGLE_SEARCH - requested search is not available]"}
            return

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
                await self.page.screenshot(path=f"{RUNTIME_DIR}/debug_missing_input.png")
            except Exception:
                pass
            yield {"error": "[Error: Could not locate chat prompt input in Google AI Studio. Check debug_missing_input.png]"}
            return

        if images and not await self.attach_files(images):
            yield {"error": "[Error: Media upload could not establish all ready attachments]"}
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
        run_deadline = time.monotonic() + (t_cfg["initial_start_timeout"] if images else 25)
        while time.monotonic() < run_deadline:
            try:
                aria_dis = await run_btn.get_attribute("aria-disabled")
                is_dis = await run_btn.is_disabled()
                if aria_dis != "true" and not is_dis:
                    run_active = True
                    logger.info(f"[+] Run button is ACTIVE after {time.time() - t_wait_start:.2f}s! Ready to execute.")
                    break
            except Exception:
                pass
            await asyncio.sleep(0.5)

        if images and not run_active:
            yield {"error": "[Error: MEDIA_TOKENIZATION_TIMEOUT - media processing did not enable Run]"}
            return

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


        previous_image_identity = None
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
                    yield {"error": "[Error: Internal extraction logic failed persistently.]"}
                    break
                await asyncio.sleep(0.15)
                continue

            image_ready = False
            if output_kind == "image":
                image_state = await read_image_output(self.page, initial_model_count)
                image_ready = image_state['ready']
                if image_state['broken']:
                    raise GatewayError(502, "AI Studio returned a broken image preview.", "upstream_image_broken")
                if image_state['identity'] != previous_image_identity:
                    stability_start_time = None
                    previous_image_identity = image_state['identity']
                if image_state['count'] and not image_ready and not state.get('is_running'):
                    stability_start_time = None
                    if elapsed > t_cfg['initial_start_timeout']:
                        raise GatewayError(504, "AI Studio image preview did not become ready.", "upstream_timeout")
                    await asyncio.sleep(.15)
                    continue

            current_text = state.get("text", "")
            is_running = state.get("is_running", False)
            is_run_disabled = state.get("is_run_disabled", False)
            button_text = state.get("button_text", "")
            new_model_turn_started = state.get("new_model_turn_started", False)
            has_error = state.get("has_error", False)
            self.last_tool_calls_count = state.get("tool_calls", 0)

            if not is_running:
                comparison = self.page.get_by_text("Which response do you prefer?", exact=True)
                if await comparison.is_visible():
                    await self.page.get_by_role("button", name="Skip", exact=True).click(timeout=3000)
                    self.comparison_skipped = True
                    await comparison.wait_for(state="hidden", timeout=5000)
                    stability_start_time = None
                    logger.info("Skipped optional response comparison without voting; usage is unavailable for this attempt.")
                    continue

            # Check for fatal or tool call error in AI Studio
            if has_error and not is_running and elapsed > 0.5:
                err_text = state.get("error_text") or "Google AI Studio encountered an error ('permission denied' / 'internal error')"
                logger.error("AI Studio generation ended with an error.")
                yield {"error": f"[Error: {err_text}]"}
                break

            # ------------------------------------------------------------------
            # 1. State: NO_RESPONSE_STARTED
            # ------------------------------------------------------------------
            if current_state == self.STATE_NO_RESPONSE_STARTED:
                if is_running or new_model_turn_started or len(current_text) > 0 or image_ready:
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
                        yield {"error": f"[Error: NO_RESPONSE_STARTED - Google AI Studio did not start generating within {t_cfg['initial_start_timeout']:.0f}s]"}
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
                        if len(current_text) == 0 and not image_ready and elapsed < 5.0:
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
                yield {"error": f"[Error: HARD_CEILING_TIMEOUT - Request exceeded safe upper bound {t_cfg['hard_ceiling']:.0f}s]"}

        # ----------------------------------------------------------------------
        # CHECK 2: Response Structure & Completeness Validation
        # ----------------------------------------------------------------------
        validation_error = None
        if current_state == self.STATE_RESPONSE_COMPLETED:
            trimmed_text = prev_text.strip()
            if output_kind == "image":
                output = await read_image_output(self.page, initial_model_count, include_data=True)
                yield {"delta": "", "text": prev_text, "image": output['data']}
            elif not trimmed_text:
                validation_error = "EMPTY_RESPONSE: Model finished generating but no text was captured from DOM."

        if validation_error:
            logger.error(f"[{case_count} cases] [CHECK 2 VALIDATION FAILED] {validation_error}")
            yield {"error": f"[Error: {validation_error}]"}

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
            f"Valid JSON: {is_json}{json_err_msg}"
        )

    async def generate_speech(self, text, model, voice, request_id):
        """Caller owns the shared lock; speech has its own observed editor."""
        from .speech import generate_in_speech_page
        self.last_usage = None
        self.last_timings = {}
        self.usage_observer.begin(request_id, text)
        try:
            return await generate_in_speech_page(self, text, model, voice)
        finally:
            self.last_usage = await self.usage_observer.finish(request_id)
            logger.info('Speech request %s model=%s usage=%s', request_id, self.active_model,
                self.last_usage.responses() if self.last_usage else 'unavailable')
