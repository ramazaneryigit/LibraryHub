"""Request and response models: the shape of the API contract.

One module per resource, mirroring `app.api.v1.routes`. Handlers import
from here, so what the API accepts can be read in one place instead of
being spread across the functions that use it.
"""
