"""Cross-cutting concerns: configuration, identifiers, security and text.

Nothing here imports from `app.db` or `app.api`. These modules are leaves, which
is what makes them safe to import from anywhere -- including from inside the ORM
model modules, where a cycle would be fatal.
"""
