"""Launch Virel AI; implementation lives in virel/. Also supports uvicorn app:app."""

import os
import sys
import threading
import time
import webbrowser
from virel.server import app
from virel.config import PORT


if __name__ == "__main__":
    if "--no-browser" in sys.argv or "--dashboard-only" in sys.argv:
        os.environ["VIREL_AUTO_START_BROWSER"] = "false"
        sys.argv = [a for a in sys.argv if a not in ("--no-browser", "--dashboard-only")]

    if "--open-dashboard" in sys.argv:
        sys.argv = [a for a in sys.argv if a != "--open-dashboard"]
        def _launch_browser():
            time.sleep(1.2)
            webbrowser.open(f"http://127.0.0.1:{PORT}/dashboard")
        threading.Thread(target=_launch_browser, daemon=True).start()

    if "--reset-accounts" in sys.argv or "--reset" in sys.argv or os.getenv("VIREL_RESET_ACCOUNTS", "").lower() in ("1", "true", "yes"):
        from virel.runtime import account_manager
        account_manager.reset_all_cooldowns()
        sys.argv = [a for a in sys.argv if a not in ("--reset-accounts", "--reset")]
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=False)
