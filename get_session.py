"""
Virel — Google AI Studio Web Session Setup (get_session.py)

This script launches a real Chromium browser via Playwright with a persistent
profile (./runtime/browser-profile). It allows the user to log into Google AI Studio
(https://aistudio.google.com) once.

Once logged in, the browser session, authentication state, and cookies are
persisted locally in ./runtime/browser-profile. The FastAPI server (app.py) will
reuse this persistent session to automate chat completions.

Usage:
    python get_session.py

Author: Mohamed (Virel) & Antigravity
License: MIT
"""

import os
import json
import time
import asyncio
from playwright.async_api import async_playwright
from virel.config import CHROME_PROFILE_DIR, SESSION_DATA_PATH, TARGET_URL


async def main():
    print("=" * 65)
    print("Virel — Google AI Studio Web Hook Setup")
    print("=" * 65)
    print(f"Profile directory: {CHROME_PROFILE_DIR}")
    print(f"Target URL:        {TARGET_URL}")
    print("-" * 65)
    print("Instructions:")
    print("  1. A Chromium browser window will open shortly.")
    print("  2. Sign in to your Google Account (if prompted).")
    print("  3. Accept any Google AI Studio terms if it's your first time.")
    print("  4. Once signed in and the prompt box / 'Run' button is ready,")
    print("     press Enter in this terminal to save the session and close.")
    print("-" * 65)
    print("Launching Chromium...")

    async with async_playwright() as p:
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=CHROME_PROFILE_DIR,
                headless=False,
                no_viewport=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                ]
            )
        except Exception as e:
            print(f"\n[ERROR] Failed to launch Chromium: {e}")
            print("Tip: If you haven't installed Playwright browsers, run:")
            print("     playwright install chromium")
            return

        page = context.pages[0] if context.pages else await context.new_page()

        # Add network monitoring so we can observe manual successful requests
        async def handle_response(response):
            try:
                url = response.url
                if "alkali" in url:
                    status = response.status
                    if status >= 400:
                        body = await response.text()
                        print(f"\n[NETWORK ERROR] alkali endpoint returned {status}: {body[:200]}")
                    else:
                        print(f"\n[NETWORK SUCCESS] alkali endpoint returned {status}!")
                elif "GenerateContent" in url or "StreamGenerateContent" in url:
                    print(f"\n[NETWORK] GenerateContent endpoint returned {response.status}")
            except Exception:
                pass

        page.on("response", handle_response)

        print(f"Navigating to {TARGET_URL}...")
        try:
            await page.goto(TARGET_URL, timeout=60000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Warning during page load: {e}")

        print("\n[INFO] The browser is now open. The session is active.")
        print("Please send a test message manually in the browser to observe the network responses.")
        print("When you are done testing, PRESS ENTER in this terminal to save the session and close.")

        # Keep the script running until the user presses Enter
        await asyncio.to_thread(input)

        session_data = {
            "status": "ready",
            "profile_dir": os.path.abspath(CHROME_PROFILE_DIR),
            "created_at": int(time.time()),
            "url": page.url,
        }

        with open(SESSION_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=4)

        print("=" * 65)
        print(f"Session metadata saved to {SESSION_DATA_PATH}!")
        print(f"Your Google login is stored in {CHROME_PROFILE_DIR}.")
        print("You can now start the OpenAI-compatible Gateway server:")
        print("    python app.py")
        print("=" * 65)

        await asyncio.sleep(2)
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
