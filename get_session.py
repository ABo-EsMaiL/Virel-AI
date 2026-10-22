"""
Virel AI — Google AI Studio Web Session Setup (get_session.py)

This script launches a real Chromium browser via Playwright with a persistent
profile (./runtime/browser-profile). It allows the user to log into Google AI Studio
(https://aistudio.google.com) once.

Multi-Account Support:
    python get_session.py                     # default login (authuser=0)
    python get_session.py --authuser 1        # sign in to second Google account
    python get_session.py --authuser 2        # sign in to third Google account
    python get_session.py --profile ./path    # custom isolated profile folder

Once logged in, the browser session, authentication state, and cookies are
persisted locally. The FastAPI server (app.py) will reuse this persistent session.
"""

import argparse
import asyncio
import json
import os
import time
from playwright.async_api import async_playwright
from virel.config import CHROME_PROFILE_DIR, SESSION_DATA_PATH, TARGET_URL


async def main():
    parser = argparse.ArgumentParser(description="Virel AI Session Setup")
    parser.add_argument("--authuser", type=int, default=None, help="Google authuser index (0, 1, 2, ...)")
    parser.add_argument("--profile", type=str, default=None, help="Custom profile directory")
    args = parser.parse_args()

    prof_dir = args.profile or CHROME_PROFILE_DIR
    target_url = TARGET_URL
    if args.authuser is not None:
        target_url = f"{TARGET_URL}?authuser={args.authuser}"

    print("=" * 65)
    print("Virel AI — Google AI Studio Web Hook Setup")
    print("=" * 65)
    print(f"Profile directory: {prof_dir}")
    print(f"Target URL:        {target_url}")
    if args.authuser is not None:
        print(f"Google Account:    authuser={args.authuser}")
    print("-" * 65)
    print("Instructions:")
    print("  1. A Chromium browser window will open shortly.")
    print("  2. Sign in to your Google Account (or click avatar -> Add account).")
    print("  3. Accept any Google AI Studio terms if it's your first time.")
    print("  4. Once signed in and the prompt box / 'Run' button is ready,")
    print("     press Enter in this terminal to save the session and close.")
    print("-" * 65)
    print("Launching Chromium...")

    async with async_playwright() as p:
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=prof_dir,
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

        try:
            await page.goto(target_url, timeout=60000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"[WARNING] Could not load {target_url} immediately: {e}")

        print("\nChromium is running!")
        print(">> Please complete your Google Sign-In in the browser window. <<")
        print(">> When AI Studio is ready with the prompt textarea visible, <<")
        print(">> return here and PRESS ENTER to save your session. <<\n")

        # Keep the script running until the user presses Enter
        await asyncio.to_thread(input)

        session_data = {
            "status": "ready",
            "profile_dir": os.path.abspath(prof_dir),
            "created_at": int(time.time()),
            "url": page.url,
            "authuser": args.authuser,
        }

        with open(SESSION_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=4)

        print("=" * 65)
        print(f"Session metadata saved to {SESSION_DATA_PATH}!")
        print(f"Your Google login is stored in {prof_dir}.")
        print("You can now start the Gateway server:")
        print("    python app.py")
        print("=" * 65)

        await asyncio.sleep(2)
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
