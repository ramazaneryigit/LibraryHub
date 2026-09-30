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

    @application.get("/", include_in_schema=False)
    def root():
        return FileResponse("app/static/index.html")

    # The curation panel. A plain path rather than `/static/admin.html` because
    # it is a place people are sent, not an asset.
    @application.get("/admin", include_in_schema=False)
    def admin_panel():
        return FileResponse("app/static/admin.html")

    return application


app = create_app()
