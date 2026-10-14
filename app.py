"""Launch Virel AI; implementation lives in virel/. Also supports uvicorn app:app."""

from virel.server import app
from virel.config import PORT


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=False)
