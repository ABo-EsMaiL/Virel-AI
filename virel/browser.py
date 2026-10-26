"""Persistent AI Studio browser: session, UI controls, generation lifecycle."""

import asyncio
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from contextlib import aclosing
from typing import AsyncGenerator, List, Optional, Union
from playwright.async_api import async_playwright, BrowserContext, Page, Error as PlaywrightError

from .config import (RUNTIME_DIR, CHROME_PROFILE_DIR, HEADLESS, DEFAULT_MODEL, THINKING_MODE, ENABLE_SEARCH_GROUNDING, ENABLE_URL_CONTEXT, TARGET_URL, TOOL_RUN_TTL_SECONDS, PRESERVE_MARKDOWN)
from .dom import response_state_script, START_ERROR_WATCH, STOP_ERROR_WATCH
from .function_ui import disable_functions, ensure_functions
from .tool_batch import disable_structured, verify_continuation, prepare_result
from .tool_runs import ToolRun
from .usage import BrowserUsageObserver
from .models import MODEL_SELECTOR, MODEL_ROWS, READ_MODEL_ROWS, catalog_from_rows, selected_id, selected_card_id, IMAGE_MODEL_ICONS
from .errors import GatewayError
from .image_output import ensure_image_settings, read_image_output

FETCH_RESPONSE_STATE = response_state_script(PRESERVE_MARKDOWN)

logger = logging.getLogger("virel.webhook")



async def dismiss_popups(page) -> bool:
    """Dismiss common onboarding/policy modals and popups in Google AI Studio."""
    dismissed = False
    try:
        selectors = [
            'button:has-text("Get started")',
            'button:has-text("Got it")',
            'button:has-text("Dismiss")',
            'button:has-text("I agree")',
            'button:has-text("Accept")',
            'button:has-text("Continue")',
            'button:has-text("تخطي")',
            'button[aria-label="Close"]',
            'button[aria-label="Dismiss"]',
            'mat-dialog-container button.close-button',
            'mat-dialog-actions button',
            '.welcome-dialog button',
        ]
        for sel in selectors:
            btn = page.locator(sel).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click(timeout=1000)
                dismissed = True
                await asyncio.sleep(0.15)
        await page.keyboard.press("Escape")
    except Exception:
        pass
    return dismissed


class BrowserPage:
    def __init__(self):
        self.request_id = "control"
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
        self.tool_run = ToolRun(TOOL_RUN_TTL_SECONDS)
        self.last_batch_turn = ""
        self.last_usage = None
        self.last_finish_reason = None
        self.last_timings = {}
        self.comparison_skipped = False
        self.usage_observer = BrowserUsageObserver()


    def attach_page_listeners(self):
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


    async def _open_model_picker(self):
        await self.page.locator(MODEL_SELECTOR).first.click()
        dialog = self.page.locator(f'{MODEL_ROWS}, input[placeholder*="Search" i], [role="dialog"], mat-dialog-container, #picker').first
        try:
            await dialog.wait_for(state='visible', timeout=8000)
        except Exception:
            pass

    async def refresh_model_catalog(self):
        """Caller owns the browser lock; publish only complete observations."""
        self.tool_run.require_idle()
        if not self.page or self.page.is_closed() or self.is_shutting_down:
            raise GatewayError(503, 'AI Studio model picker is unavailable.', 'model_catalog_unavailable')
        try:
            await self._open_model_picker()
            combined_rows = []
            seen_keys = set()
            for cat in ("All", "Images", "Audio", "Featured"):
                try:
                    chip = self.page.locator(
                        'button, [role="tab"], [role="radio"], mat-chip, .mat-mdc-chip, .filter-chip, .category-chip'
                    ).filter(has_text=re.compile(rf'^\s*{cat}\s*$', re.I)).first
                    if await chip.count() > 0 and await chip.is_visible():
                        await chip.click()
                        await asyncio.sleep(0.18)
                except Exception:
                    pass
                try:
                    rows = await self.page.evaluate(READ_MODEL_ROWS)
                    if isinstance(rows, list):
                        for r in rows:
                            key = r.get("id") or r.get("display_name") or str(r)
                            if key not in seen_keys:
                                seen_keys.add(key)
                                combined_rows.append(r)
                except Exception:
                    pass

            catalog = catalog_from_rows(combined_rows)
            if not any(item['status'] == 'selectable' for item in catalog.values()):
                raise GatewayError(503, 'AI Studio returned no selectable models.', 'model_catalog_unavailable')
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
        from .config import DEFAULT_SPEECH_MODEL
        is_speech_id = identifier in (DEFAULT_SPEECH_MODEL, 'tts-1', 'tts-1-hd') or identifier.endswith('-tts') or '-tts-' in identifier
        if output_kind != 'speech' and is_speech_id:
            raise GatewayError(400, 'This model requires an output adapter that is not implemented.', 'unsupported_model_capability')

        if output_kind == 'speech' and is_speech_id:
            item = self.model_catalog.get(identifier)
            if item is not None and item.get('status') == 'unavailable':
                raise GatewayError(503, 'Requested UI model is disabled or requires paid access.', 'model_unavailable')
            return item or {
                'id': identifier,
                'display_name': identifier,
                'status': 'selectable',
                'capabilities': {'input_modalities': None, 'output_modalities': ['audio'], 'ui_category_icon': 'audio_magic_eraser', 'source': 'ai_studio_ui'}
            }

        if not is_speech_id and identifier:
            from .config import DEFAULT_MODEL
            if (
                identifier.startswith(('gpt-', 'o1', 'o3', 'o4', 'chatgpt-', 'claude-', 'anthropic/', 'openai/', 'deepseek-', 'llama-', 'mistral-', 'qwen-', 'sol-'))
                or identifier in ('default', 'auto')
                or (identifier.startswith('gemini-') and identifier not in self.model_catalog)
            ):
                logger.info('Routing external client model alias %s -> %s', identifier, DEFAULT_MODEL)
                identifier = DEFAULT_MODEL

        item = self.model_catalog.get(identifier)
        if item is None:
            raise GatewayError(404, 'Requested model was not observed in the AI Studio catalog.', 'model_not_found')
        if item['status'] == 'unavailable':
            raise GatewayError(503, 'Requested UI model is disabled or requires paid access.', 'model_unavailable')
        actual = self.model_catalog.get(item.get('resolved_id', identifier), item)
        if actual['status'] == 'unavailable':
            raise GatewayError(503, 'Resolved UI model is disabled or requires paid access.', 'model_unavailable')

        if output_kind == 'image':
            is_image = actual['capabilities'].get('output_modalities') == ['image'] or actual['capabilities'].get('ui_category_icon') in IMAGE_MODEL_ICONS
            if not is_image or item['status'] != 'selectable':
                raise GatewayError(400, 'This model requires an output adapter that is not implemented.', 'unsupported_model_capability')
        elif output_kind == 'speech':
            is_speech = actual['capabilities'].get('output_modalities') == ['audio'] or actual['capabilities'].get('ui_category_icon') == 'audio_magic_eraser'
            if not is_speech or item['status'] != 'selectable':
                raise GatewayError(400, 'This is not an observed speech-output model.', 'unsupported_model_capability')
        else:
            is_image = actual['capabilities'].get('output_modalities') == ['image'] or actual['capabilities'].get('ui_category_icon') in IMAGE_MODEL_ICONS
            is_speech = actual['capabilities'].get('output_modalities') == ['audio'] or actual['capabilities'].get('ui_category_icon') == 'audio_magic_eraser'
            if is_image or is_speech or item['status'] != 'selectable':
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
        from .config import DEFAULT_SPEECH_MODEL
        target_model = target_model or (DEFAULT_SPEECH_MODEL if output_kind == 'speech' else DEFAULT_MODEL)
        if not self.page or self.page.is_closed() or self.is_shutting_down:
            return

        is_speech = (output_kind == 'speech') or target_model.endswith('-tts') or '-tts-' in target_model or (target_model in (DEFAULT_SPEECH_MODEL, 'tts-1', 'tts-1-hd'))
        if target_model and not is_speech:
            from .config import DEFAULT_MODEL
            if (
                target_model.startswith(('gpt-', 'o1', 'o3', 'o4', 'chatgpt-', 'claude-', 'anthropic/', 'openai/', 'deepseek-', 'llama-', 'mistral-', 'qwen-', 'sol-'))
                or target_model in ('default', 'auto')
                or (target_model.startswith('gemini-') and target_model not in self.model_catalog)
            ):
                logger.info('Routing external client model alias %s -> %s', target_model, DEFAULT_MODEL)
                target_model = DEFAULT_MODEL

        # Check if already selected on the page
        control = self.page.locator(MODEL_SELECTOR).first
        if await control.count() > 0 and await control.is_visible():
            try:
                label = await control.inner_text()
                if is_speech and ('tts' in label.lower() or target_model in label):
                    self.active_model = target_model
                    self.model_verified = True
                    self.model_error = ''
                    logger.info('Speech model %s already active (label: %s)', target_model, label.replace('\n', ' '))
                    return
                elif not is_speech and self.model_catalog:
                    selected = selected_card_id(label, self.model_catalog)
                    current = selected_id(label, self.model_catalog)
                    if selected == target_model:
                        self.active_model = current or target_model
                        self.model_verified = True
                        self.model_error = ''
                        logger.info('Model requested=%s selected=%s active=%s verified=%s', target_model, selected, self.active_model, self.model_verified)
                        return
            except Exception:
                pass

        try:
            # For non-speech models, pre-validate via require_model
            expected = None
            if not is_speech:
                if not self.model_catalog_observed or target_model not in self.model_catalog:
                    await self.refresh_model_catalog()
                item = self.require_model(target_model, output_kind=output_kind)
                expected = item.get('resolved_id', target_model)

            # Open model picker dialog
            try:
                await self._open_model_picker()

                # Handle category chip in model picker
                if is_speech:
                    audio_chip = self.page.locator(
                        'button, [role="tab"], [role="radio"], mat-chip, .mat-mdc-chip, .filter-chip, .category-chip'
                    ).filter(has_text=re.compile(r'^\s*Audio\s*$', re.I)).first
                    if await audio_chip.count() > 0 and await audio_chip.is_visible():
                        logger.info("Selecting 'Audio' category chip in model picker...")
                        await audio_chip.click()
                        await asyncio.sleep(0.3)
                else:
                    # Switch back to Featured for general text / image models
                    feat_chip = self.page.locator(
                        'button, [role="tab"], [role="radio"], mat-chip, .mat-mdc-chip, .filter-chip, .category-chip'
                    ).filter(has_text=re.compile(r'^\s*Featured\s*$', re.I)).first
                    if await feat_chip.count() > 0 and await feat_chip.is_visible():
                        await feat_chip.click()
                        await asyncio.sleep(0.2)
                if output_kind == 'image':
                    img_chip = self.page.locator(
                        'button, [role="tab"], [role="radio"], mat-chip, .mat-mdc-chip, .filter-chip, .category-chip'
                    ).filter(has_text=re.compile(r'^\s*Images\s*$', re.I)).first
                    if await img_chip.count() > 0 and await img_chip.is_visible():
                        logger.info("Selecting 'Images' category chip in model picker...")
                        await img_chip.click()
                        await asyncio.sleep(0.3)

                # Locate model card: try direct card, or search box
                search_box = self.page.locator('input[placeholder*="Search" i], input[aria-label*="Search" i]').first
                card_selector = (
                    f'{MODEL_ROWS}[id="model-carousel-row-models/{target_model}"], '
                    f'button.content-button[id*="{target_model}"], '
                    f'ms-model-card:has-text("{target_model}"), '
                    f'.model-card:has-text("{target_model}"), '
                    f'button:has-text("{target_model}")'
                )
                card = self.page.locator(card_selector).first

                if (await card.count() == 0 or not await card.is_visible()) and await search_box.count() > 0 and await search_box.is_visible():
                    logger.info("Filtering model search input with: %s", target_model)
                    await search_box.fill(target_model)
                    await asyncio.sleep(0.3)
                    card = self.page.locator(card_selector).first

                if is_speech and (await card.count() == 0 or not await card.is_visible()):
                    card = self.page.locator(
                        'button.content-button:has-text("Flash TTS"), '
                        'ms-model-card:has-text("Flash TTS"), '
                        '.model-card:has-text("Flash TTS"), '
                        'button:has-text("Flash TTS")'
                    ).first

                if await card.count() == 0:
                    raise GatewayError(404, 'Requested model is no longer present.', 'model_not_found')

                # Verify card is not disabled or paid
                card_text = await card.inner_text()
                if 'Paid' in card_text and 'Free' not in card_text:
                    raise GatewayError(503, 'Requested UI model is disabled or requires paid access.', 'model_unavailable')
                if await card.is_disabled() or await card.get_attribute('aria-disabled') == 'true':
                    raise GatewayError(503, 'Requested UI model is disabled.', 'model_unavailable')

                await card.click()
                await asyncio.sleep(0.3)

                # Check for confirmation prompt (e.g. Switch prompt / Create new dialog)
                switch_btn = self.page.locator('button:has-text("Switch"), button:has-text("Create"), mat-card.create-dialog-card button').first
                if await switch_btn.count() > 0 and await switch_btn.is_visible():
                    await switch_btn.click()
                    await asyncio.sleep(0.3)

            finally:
                await self.page.keyboard.press('Escape')

            if is_speech:
                speech_prompt = self.page.locator('mat-card.create-dialog-card, ms-speech-prompt, textarea[aria-label="Speech block text"]').first
                try:
                    await speech_prompt.wait_for(state='visible', timeout=8000)
                except Exception:
                    pass
                self.active_model = target_model
                self.model_verified = True
                self.model_error = ''
                logger.info('Speech model requested=%s active=%s verified=%s', target_model, self.active_model, self.model_verified)
                return

            # Verification for non-speech models
            selected = None
            current = None
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                label = await control.inner_text()
                selected = selected_card_id(label, self.model_catalog)
                current = selected_id(label, self.model_catalog)
                if selected == target_model and (expected is None or current == expected):
                    break
                await asyncio.sleep(.2)

            self.active_model = current or target_model
            self.model_verified = (selected == target_model and (expected is None or current == expected)) if self.model_catalog else True
            logger.info('Model requested=%s selected=%s active=%s verified=%s', target_model, selected if self.model_catalog else target_model, self.active_model, self.model_verified)
        except GatewayError as error:
            logger.warning("ensure_model GatewayError for %s (kind=%s): %s", target_model, output_kind, error.detail if hasattr(error, "detail") else str(error))
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

    async def cancel_generation(self):
        """The caller holds browser ownership until navigation aborts the current page."""
        self.tool_run.clear()
        self.last_usage = None
        self.model_verified = False
        self.thinking_verified = False
        self.temperature_verified = False
        self.search_verified = False
        self.url_context_verified = False
        self.last_batch_turn = ""
        try:
            if self.page and not self.page.is_closed():
                await self.page.goto("about:blank", wait_until="commit", timeout=5000)
        except Exception:
            self.is_ready = False
            logger.warning("Cancelled generation could not release its page; browser marked unavailable.")


    async def reset_chat_if_needed(self, model_name: Optional[str] = None, output_kind="text") -> bool:
        """Never replay caller history into a retained browser conversation."""
        if not self.page or self.page.is_closed() or self.is_shutting_down:
            if self.context and not getattr(self, "context_closed", False) and not self.is_shutting_down:
                try:
                    self.page = await self.context.new_page()
                    self.attach_page_listeners()
                except Exception:
                    return False
            else:
                return False
        try:
            from .runtime import account_manager
            target_url = account_manager.get_target_url()
            await self.page.goto(target_url, timeout=35000, wait_until="domcontentloaded")
            await dismiss_popups(self.page)
            await self.page.keyboard.press("Escape")
            await self.ensure_model(model_name, output_kind=output_kind)
            if output_kind == 'speech':
                return self.model_verified
            prompt = self.page.locator('.prompt-box-container textarea, textarea[formcontrolname="promptText"], textarea[aria-label*="prompt" i], textarea[placeholder*="Type" i]').last
            await prompt.wait_for(state="visible", timeout=15000)
            turns = self.page.locator('ms-chat-turn, .chat-turn-container, .chat-turn, [data-turn-role]')
            if await turns.count() or (await prompt.input_value()).strip():
                logger.warning("Fresh-chat verification failed; refusing to reuse browser context.")
                return False
            await self.ensure_thinking_mode()
            await disable_functions(self.page)
            await disable_structured(self.page)
            await self.ensure_tools(ENABLE_SEARCH_GROUNDING)
            await self.ensure_url_context()
            return True
        except Exception as e:
            if ("target" in str(e).lower() or "closed" in str(e).lower()) and self.context and not getattr(self, "context_closed", False) and not self.is_shutting_down:
                try:
                    self.page = await self.context.new_page()
                    self.attach_page_listeners()
                    return await self.reset_chat_if_needed(model_name=model_name, output_kind=output_kind)
                except Exception:
                    pass
            logger.warning("Fresh-chat navigation or prompt verification failed: %s", repr(e))
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

    async def send_prompt_and_stream(self, prompt, model_name=None, batch_size=None, enable_search=None, images=None, request_id=None, reasoning_effort=None, temperature=None, output_kind="text", image_size="auto", image_settings=None, function_settings=None, continuation=None, max_output_tokens=None):
        attempt_id = request_id or uuid.uuid4().hex
        self.last_usage = None
        self.last_finish_reason = None
        self.comparison_skipped = False
        self.last_batch_turn = ""
        self.usage_observer.begin(attempt_id, prompt)
        final_text = ""
        result = {}
        try:
            async with aclosing(self._generate_in_page(prompt, model_name, batch_size, enable_search, images, reasoning_effort=reasoning_effort, temperature=temperature, output_kind=output_kind, image_size=image_size, image_settings=image_settings, function_settings=function_settings, continuation=continuation, max_output_tokens=max_output_tokens)) as stream:
                async for item in stream:
                    if isinstance(item, dict):
                        if "error" in item:
                            yield item
                            return
                        result.update(item)
                        final_text = item.get("text", final_text)
                    else:
                        final_text += item
                    # Rendered Markdown can replace earlier text; it is not an append-only stream.
            if output_kind == "text" and final_text.strip() and self.model_verified:
                self.generated_models.add(self.active_model)
        finally:
            try:
                if self.page and not self.page.is_closed():
                    await self.page.evaluate(STOP_ERROR_WATCH)
            except Exception:
                logger.debug("Generation error watcher cleanup failed.")
            usage = await self.usage_observer.finish(attempt_id)
            self.last_usage = None if self.comparison_skipped else usage
            self.last_finish_reason = None if self.comparison_skipped else self.usage_observer.last_finish_reason
        yield {**result, "text": final_text, "delta": final_text, "finish_reason": self.last_finish_reason}

    async def ensure_max_output_tokens(self, value):
        """Apply the caller's native output cap, with readback before Send."""
        try:
            control = self.page.locator('input[aria-label="Maximum output tokens"]').first
            advanced = self.page.get_by_role("button", name=re.compile("Advanced settings", re.I)).first
            if not await control.is_visible() and await advanced.count() and await advanced.is_visible():
                await advanced.click()
            if not await control.count() or not await control.is_visible() or not await control.is_enabled():
                raise GatewayError(400, "max_tokens control is unavailable for this UI model.", "unsupported_parameter")
            low = await control.get_attribute("aria-valuemin") or await control.get_attribute("min")
            high = await control.get_attribute("aria-valuemax") or await control.get_attribute("max")
            if (low is not None and value < float(low)) or (high is not None and value > float(high)):
                raise GatewayError(400, "max_tokens exceeds the selected UI model range.", "unsupported_parameter")
            await control.fill(str(value))
            await control.press("Tab")
            if float(await control.input_value()) != value or await control.get_attribute("aria-invalid") == "true":
                raise GatewayError(503, "AI Studio max_tokens setting could not be verified.", "settings_unavailable")
        except (ValueError, PlaywrightError):
            raise GatewayError(503, "AI Studio max_tokens control is unavailable.", "settings_unavailable") from None

    async def attach_files(self, paths: List[str]) -> bool:
        """Do not run until all current-request attachment chips are ready."""
        try:
            file_names = [Path(p).name for p in paths]
            logger.info("Uploading %d attachment(s) to AI Studio prompt box: %s", len(paths), file_names)
            file_input = self.page.locator('input[type="file"], [data-test-upload-file-input]').first
            await file_input.wait_for(state="attached", timeout=8000)
            await file_input.set_input_files(paths)
            ready = """(expected) => {
                const selector = '.prompt-media-item-container, .prompt-box-container .file-chip, ms-prompt-box ms-file-chip, ms-audio-chip, ms-attachment-chip, .file-chip';
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
                    logger.info("All %d attachment(s) verified ready in AI Studio prompt box.", len(paths))
                    return True
                await asyncio.sleep(0.25)
            logger.warning("Media attachment readiness timed out.")
            return False
        except Exception as error:
            logger.warning("Media upload or attachment readiness failed (%s).", type(error).__name__)
            return False

    async def _generate_in_page(
        self, prompt: str, model_name: Optional[str] = None, batch_size: Optional[int] = None, enable_search: Optional[bool] = None, images: Optional[List[str]] = None, reasoning_effort=None, temperature=None, output_kind="text", image_size="auto", image_settings=None, function_settings=None, continuation=None, max_output_tokens=None
    ) -> AsyncGenerator[Union[dict, str], None]:
        """Injects the prompt (and optional images) into Google AI Studio and yields streaming text deltas."""
        t_req_start = time.time()
        if not self.page or self.page.is_closed() or self.is_shutting_down:
            yield {"error": "[Error: Browser page not initialized or server is shutting down]"}
            return

        if continuation is not None:
            model_count = await self.page.locator("ms-chat-turn .model-prompt-container").count()
            state = await self.page.evaluate(FETCH_RESPONSE_STATE, max(0, model_count - 1))
            await verify_continuation(self.page, continuation, state)
            if continuation.get("refresh_functions"):
                await ensure_functions(self.page, function_settings, preserve_pending=True)
                state = await self.page.evaluate(FETCH_RESPONSE_STATE, max(0, model_count - 1))
                await verify_continuation(self.page, continuation, state)
        else:
            self.tool_run.require_idle()
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

            if function_settings:
                await ensure_functions(self.page, function_settings)
                self.google_search_enabled = False
                self.search_verified = True
                self.url_context_enabled = False
                self.url_context_verified = True

            # Preserve the requested/current Google Search state.
            await self.ensure_tools(enable_search=enable_search)
            if enable_search is True and not (self.google_search_enabled and self.search_verified):
                yield {"error": "[Error: UNSUPPORTED_GOOGLE_SEARCH - requested search is not available]"}
                return

        if max_output_tokens is not None:
            await self.ensure_max_output_tokens(max_output_tokens)

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

        # Determine case count from batch_size or prompt inspection
        case_count = batch_size if (batch_size is not None and batch_size > 0) else None
        if not case_count:
            cid_count = prompt.count('"case_id"') or prompt.count("'case_id'")
            case_count = cid_count if cid_count > 0 else 1

        t_cfg = self.get_adaptive_timeouts(case_count)

        if continuation is not None:
            run_btn = await prepare_result(self.page, prompt, continuation)
            run_active = True
        else:
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
                    await self.page.screenshot(path=f"{RUNTIME_DIR}/debug_missing_input_{self.request_id}.png")
                except Exception:
                    pass
                yield {"error": "[Error: Could not locate chat prompt input in Google AI Studio.]"}
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

            if function_settings is not None and not run_active:
                raise GatewayError(503, "AI Studio native function submission is not ready; nothing was sent.", "browser_not_ready")
            if images and not run_active:
                yield {"error": "[Error: MEDIA_TOKENIZATION_TIMEOUT - media processing did not enable Run]"}
                return

        current_state = self.STATE_NO_RESPONSE_STARTED
        t_turn_detected: Optional[float] = None
        t_first_token: Optional[float] = None
        stability_start_time: Optional[float] = None
        prev_text = ""
        consecutive_js_errors = 0

        await self.page.evaluate(START_ERROR_WATCH)
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
            if function_settings is not None:
                raise GatewayError(503, "AI Studio native function submission could not be verified; no retry was made.", "upstream_error") from None
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


        function_calls = []
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

            if function_settings is not None:
                self.last_batch_turn = state.get("model_turn_id", "")
                function_calls = state.get("function_calls", [])
            current_text = state.get("text", "")
            is_running = state.get("is_running", False)
            is_run_disabled = state.get("is_run_disabled", False)
            button_text = state.get("button_text", "")
            new_model_turn_started = state.get("new_model_turn_started", False)
            has_error = state.get("has_error", False)
            self.last_tool_calls_count = len(function_calls) if function_settings is not None else state.get("tool_calls", 0)

            if not is_running:
                comparison = self.page.get_by_text("Which response do you prefer?", exact=True)
                if await comparison.is_visible():
                    await self.page.get_by_role("button", name="Skip", exact=True).click(timeout=3000)
                    self.comparison_skipped = True
                    await comparison.wait_for(state="hidden", timeout=5000)
                    stability_start_time = None
                    logger.info("Skipped optional response comparison without voting; usage is unavailable for this attempt.")
                    continue

                # General skip button on any comparison or rating dialog
                skip_btn = self.page.locator('button:has-text("Skip"), button:has-text("تخطي"), [aria-label*="Skip" i]').first
                if await skip_btn.count() > 0 and await skip_btn.is_visible():
                    try:
                        await skip_btn.click(timeout=2000)
                        self.comparison_skipped = True
                        stability_start_time = None
                        logger.info("Clicked 'Skip' on visible response comparison/feedback prompt.")
                        continue
                    except Exception:
                        pass

            # Check for fatal or tool call error in AI Studio
            if has_error and not is_running and elapsed > 0.5:
                err_text = state.get("error_text") or "Google AI Studio encountered an error ('permission denied' / 'internal error')"
                logger.error("AI Studio generation error: %s", err_text[:1200])
                yield {"error": f"[Error: {err_text}]"}
                break

            # ------------------------------------------------------------------
            # 1. State: NO_RESPONSE_STARTED
            # ------------------------------------------------------------------
            if current_state == self.STATE_NO_RESPONSE_STARTED:
                if is_running or new_model_turn_started or len(current_text) > 0 or image_ready or function_calls:
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

                # Rendering can also shorten or replace the current snapshot.
                if current_text != prev_text:
                    delta = current_text[len(prev_text):] if current_text.startswith(prev_text) else ""
                    prev_text = current_text
                    t_last_growth = now
                    stability_start_time = None
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
                        # An observed output-limit terminal also permits an empty completion.
                        # ------------------------------------------------------------------
                        if len(current_text) == 0 and not image_ready and not function_calls and elapsed < 5.0 and self.usage_observer.last_finish_reason != "max_tokens":
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
                                yield {"delta": "", "text": current_text, "finish_reason": self.usage_observer.last_finish_reason}
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
            elif function_settings is not None and function_calls:
                yield {"delta": "", "text": prev_text, "function_calls": function_calls}
            elif not trimmed_text and self.usage_observer.last_finish_reason != "max_tokens":
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
        self.tool_run.require_idle()
        self.last_usage = None
        self.last_finish_reason = None
        self.last_timings = {}
        self.usage_observer.begin(request_id, text)
        try:
            return await generate_in_speech_page(self, text, model, voice)
        finally:
            self.last_usage = await self.usage_observer.finish(request_id)
            logger.info('Speech request %s model=%s usage=%s', request_id, self.active_model,
                self.last_usage.responses() if self.last_usage else 'unavailable')


    async def switch_account(self, new_account):
        """Switch active Google account in this browser page or manager session."""
        from .runtime import account_manager
        target_url = account_manager.get_target_url(new_account)
        logger.info(f"Switching active browser session/page to {new_account.id} ({new_account.label}) at {target_url}...")
        if not self.page or self.page.is_closed():
            if hasattr(self, "profile_dir"):
                self.profile_dir = new_account.profile_dir
            return
        current_prof = getattr(self, "profile_dir", getattr(new_account, "profile_dir", None))
        if new_account.profile_dir == current_prof or not hasattr(self, "stop"):
            await self.page.goto(target_url, timeout=45000, wait_until="domcontentloaded")
            await dismiss_popups(self.page)
            await self.page.keyboard.press("Escape")
            if getattr(self, "active_model", None):
                await self.ensure_model(self.active_model)
            self.model_catalog_observed = False
            await self.refresh_model_catalog()
            logger.info(f"Switched page in-place to {new_account.id} successfully.")
        else:
            await self.stop()
            self.profile_dir = new_account.profile_dir
            await self.start()


class WebHookBrowserManager(BrowserPage):
    """Sole persistent Chromium/profile lifecycle owner; request pages never launch it."""
    def __init__(self):
        super().__init__()
        self.context_closed = False
        self.profile_dir = CHROME_PROFILE_DIR
        self.needs_login = False
        self.engine_running = False

    def _on_context_closed(self, context):
        if context is self.context:
            self.context_closed = True
            self.is_ready = False

    async def start(self):
        self.is_shutting_down = False
        self.is_ready = False
        # A restarted context must never advertise its previous UI observation.
        self.model_catalog = {}
        self.model_catalog_observed = False
        self.catalog_observed_at = 0
        prof_dir = getattr(self, "profile_dir", CHROME_PROFILE_DIR)
        logger.info(f"Launching persistent Chromium context from: {prof_dir} (headless={HEADLESS}, start-maximized)")
        self.playwright = await async_playwright().start()

        args = [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--mute-audio",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-ipc-flooding-protection",
        ]
        if os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER"):
            args.extend(["--no-sandbox", "--disable-dev-shm-usage"])

        try:
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=prof_dir,
                headless=HEADLESS,
                no_viewport=True,
                args=args,
                ignore_default_args=["--enable-automation"]
            )
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            logger.error(f"Please ensure no other Chromium process is using {CHROME_PROFILE_DIR}.")
            raise e

        self.context_closed = False
        self.context.on("close", self._on_context_closed)
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

        self.attach_page_listeners()

        from .runtime import account_manager
        active_acc = account_manager.get_active_account()
        target_url = account_manager.get_target_url(active_acc)
        logger.info(f"Navigating to {target_url} (account: {active_acc.id} / {active_acc.label}) to ensure clean environment...")
        try:
            await self.page.goto(target_url, timeout=60000, wait_until="domcontentloaded")
            await dismiss_popups(self.page)
            await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"Initial page navigation warning: {e}. Page will be ready on demand.")

        # Check if user needs to log in
        if "accounts.google.com" in self.page.url or "welcome" in self.page.url:
            self.needs_login = True
            self.engine_running = True
            self.is_ready = False
            logger.warning("[ACTION REQUIRED] Google AI Studio requires Google Account login! Open /dashboard -> Live Browser Studio (or run get_session.py) to sign in.")
            return
        self.needs_login = False
        self.engine_running = True

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
        await disable_functions(self.page)
        await disable_structured(self.page)
        await self.ensure_tools(ENABLE_SEARCH_GROUNDING)
        await self.ensure_url_context()
        self.is_ready = self.model_catalog_observed


    async def stop(self):
        self.tool_run.clear()
        logger.info("Closing browser context...")
        self.is_shutting_down = True
        self.is_ready = False
        self.engine_running = False
        self.needs_login = False
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
