# Serves the built React frontend. Kept out of main.py because it has to be
# mounted after every API route, and putting it in its own file makes that
# ordering obvious instead of "whatever happens to be at the bottom".

from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# the built frontend. vite writes it here; the Dockerfile copies the same path.
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def mount_frontend(app: FastAPI) -> None:
    """
    Call this last, after every router is included, so nothing here can shadow
    /api or /health. Only mounts when a build exists — without it the API still
    runs fine, which is what you want when working on the backend alone.
    """
    if not DIST.is_dir():
        @app.get("/")
        async def no_frontend():
            return {
                "detail": "No frontend build found. Run `npm install && npm run build` in frontend/, "
                          "or use the Vite dev server on :5173.",
            }
        return

    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        # an /api path that got this far matched no endpoint above, so it's a
        # typo or a removed route. answer 404 rather than handing back HTML,
        # which would otherwise fail somewhere far from the actual mistake.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="No such endpoint.")

        # any other path returns the app shell and lets react-router decide
        # what to render, so refreshing on /reports/abc works like a real URL
        candidate = DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)  # favicon, robots.txt, and friends
        return FileResponse(DIST / "index.html")
