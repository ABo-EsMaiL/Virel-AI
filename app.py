"""Launch Virel AI; implementation lives in virel/. Also supports uvicorn app:app."""

import os
import sys
from virel.server import app
from virel.config import PORT


if __name__ == "__main__":
    if "--reset-accounts" in sys.argv or "--reset" in sys.argv or os.getenv("VIREL_RESET_ACCOUNTS", "").lower() in ("1", "true", "yes"):
        from virel.runtime import account_manager
        account_manager.reset_all_cooldowns()
        sys.argv = [a for a in sys.argv if a not in ("--reset-accounts", "--reset")]
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=False)
