from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routers import (
    health,
    relations,
    persons,
    works,
    work_agents,
    classifications,
    identifiers,
    item_agents,
    collective_agents,
    concepts,
    expressions,
    manifestations,
    items,
    search,
    reconciliation,
)



app = FastAPI(
    title="LibraryHub API",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(relations.router)
app.include_router(persons.router)
app.include_router(works.router)
app.include_router(work_agents.router)
app.include_router(classifications.router)
app.include_router(identifiers.router)
app.include_router(item_agents.router)
app.include_router(collective_agents.router)
app.include_router(concepts.router)
app.include_router(expressions.router)
app.include_router(manifestations.router)
app.include_router(items.router)
app.include_router(search.router)
app.include_router(reconciliation.router)

app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static",
)


   

@app.get("/", include_in_schema=False)
def root():
    return FileResponse("app/static/index.html")

