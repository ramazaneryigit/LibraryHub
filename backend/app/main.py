"""The FastAPI application.

Two mounts of one router
------------------------
`/api/v1` is the contract. The unversioned paths are the ones every existing
client already calls -- the shipped front end, the seed scripts, the operational
scripts -- and they stay, excluded from the schema so they are not advertised to
anybody new.

Mounting the same router twice rather than writing a redirect is the honest
choice here: a redirect would silently change what a `POST` does for clients that
do not follow redirects, which is most of them, and keeping the handlers in one
place means the two paths cannot drift apart.
"""

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.v1 import api_router

API_VERSION = "1.0.0"


def create_app() -> FastAPI:
    application = FastAPI(
        title="LibraryHub API",
        version=API_VERSION,
    )

    application.include_router(api_router, prefix="/api/v1")

    # The paths clients already use. Out of the schema on purpose: they are kept
    # for compatibility, not offered.
    application.include_router(api_router, include_in_schema=False)

    application.mount(
        "/static",
        StaticFiles(directory="app/static"),
        name="static",
    )

    @application.middleware("http")
    async def revalidate_static_assets(request, call_next):
        """Make the browser check before reusing a script or a stylesheet.

        `StaticFiles` sends `Last-Modified` and an ETag but no `Cache-Control`,
        and with none a browser may reuse a file without asking. That is how a
        fix ships and the person who reported the bug still sees the old page --
        which happened here, twice, and both times looked like the fix had not
        worked.

        `no-cache` rather than `no-store`: it means "revalidate", so the answer is
        still a cheap 304 and the asset is not re-sent.
        """

        response = await call_next(request)

        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"

        return response

    @application.get("/", include_in_schema=False)
    def root():
        return FileResponse("app/static/index.html")

    # The curation panel. A plain path rather than `/static/admin.html` because
    # it is a place people are sent, not an asset.
    @application.get("/admin", include_in_schema=False)
    def admin_panel():
        return FileResponse("app/static/admin.html")

    # A library's own workspace: what an institution sees when its staff sign in.
    @application.get("/kutuphane", include_in_schema=False)
    def library_workspace():
        return FileResponse("app/static/kutuphane.html")

    # A publisher's: which libraries hold its books.
    @application.get("/yayinevi", include_in_schema=False)
    def publisher_workspace():
        return FileResponse("app/static/yayinevi.html")

    # Loading a library's MARC file, and reading what the last run could not.
    @application.get("/iceaktarma", include_in_schema=False)
    def ingest_workspace():
        return FileResponse("app/static/iceaktarma.html")

    # Health check endpoint for container orchestration and monitoring.
    @application.get("/health", include_in_schema=False)
    def health():
        """Minimal health check. Returns 200 if the app is responsive."""
        return {"status": "healthy", "version": API_VERSION}

    return application


app = create_app()
