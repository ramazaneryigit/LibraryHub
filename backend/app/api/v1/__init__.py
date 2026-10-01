"""API v1.

Every route module is collected here and mounted once by `main`. Adding a resource
is one import and one call rather than an edit to a flat list that had grown to
sixteen lines.

The prefix is applied at the mount, not here, and that is deliberate: it is what
lets the same router be mounted a second time on the unversioned paths without
carrying `/api/v1` along with it.
"""

from fastapi import APIRouter

from .routes import (
    academic,
    admin,
    assertions,
    auth,
    classifications,
    collective_agents,
    concepts,
    expressions,
    health,
    identifiers,
    ingestion,
    ingest,
    isbn,
    manifestations,
    persons,
    publisher,
    reconciliation,
    relations,
    search,
    tenant,
    work_agents,
    works,
)

__all__ = ["api_router"]


api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(tenant.router)
api_router.include_router(assertions.router)
api_router.include_router(isbn.router)
api_router.include_router(publisher.router)
api_router.include_router(academic.router)
api_router.include_router(ingest.router)
api_router.include_router(works.router)
api_router.include_router(work_agents.router)
api_router.include_router(persons.router)
api_router.include_router(collective_agents.router)
api_router.include_router(concepts.router)
api_router.include_router(expressions.router)
api_router.include_router(manifestations.router)
api_router.include_router(identifiers.router)
api_router.include_router(relations.router)
api_router.include_router(classifications.router)
api_router.include_router(search.router)
api_router.include_router(reconciliation.router)
api_router.include_router(ingestion.router)
