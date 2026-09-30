"""defer the entity subtype checks to commit

The problem this fixes
----------------------
Nine tables -- works, persons, manifestations and the rest -- carry a trigger
that refuses a row whose `entities` row is missing or has the wrong type. The
check is correct; *when* it ran was not.

It ran `BEFORE INSERT`, immediately, which meant the `entities` row had to exist
first inside the same transaction. SQLAlchemy orders its INSERTs across mappers
that have no `relationship()` between them by **mapper name**, and a mapper name
is its module-qualified class name. While every model lived in one module that
accident happened to sort `app.models.Entity` before `app.models.Work`, and the
trigger was satisfied by luck. Splitting the models by domain changed the names
to `app.db.models.bibliographic.Work` and `app.db.models.identity.Entity`, the
sort flipped, the subtype row went in first, and every create of a Work, Person,
Concept, Expression, Manifestation, Place, TimeSpan, CollectiveAgent or
ClassificationNode began failing with

    Entity ... must have entity_type WORK, found <NULL>

Nothing was wrong with the data or the constraint. The ordering was never
guaranteed in the first place -- it only looked like it was.

Why deferring is the fix
------------------------
An entity and its subtype row are always written in one transaction, so the
invariant is a statement about the transaction, not about one statement. A
deferrable constraint trigger says exactly that: check it at COMMIT, when both
rows exist. The rule is unchanged and still enforced; the ORM is freed from an
obligation it never explicitly agreed to.

The alternative -- tuning mapper names, or adding a `relationship()` to nine
models purely to influence flush order -- would have preserved the fragility
rather than removed it.

Immediate checks are still immediate for anything that only inserts a subtype
row, because the deferral ends at commit.

Revision ID: d2e5f04bc159
Revises: c2d5f93ab048
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d2e5f04bc159"
down_revision: Union[str, Sequence[str], None] = "c2d5f93ab048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, entity_type, trigger name) -- taken from the definitions the immediate
# triggers already had, so the rule is carried across and not retyped.
SUBTYPES = (
    ("classification_nodes", "CLASSIFICATION"),
    ("collective_agents", "ORGANIZATION"),
    ("concepts", "CONCEPT"),
    ("expressions", "EXPRESSION"),
    ("manifestations", "MANIFESTATION"),
    ("persons", "PERSON"),
    ("places", "PLACE"),
    ("time_spans", "TIME_SPAN"),
    ("works", "WORK"),
)


def _trigger_name(table: str) -> str:
    return f"trg_{table}_validate_entity_type"


def upgrade() -> None:
    for table, entity_type in SUBTYPES:
        name = _trigger_name(table)

        op.execute(f"drop trigger if exists {name} on public.{table}")

        # `after` rather than `before`: the row is written and the constraint is
        # evaluated at commit instead. `constraint` is what makes it deferrable
        # -- a plain trigger cannot be.
        op.execute(
            f"create constraint trigger {name} "
            f"after insert or update of entity_id on public.{table} "
            "deferrable initially deferred "
            "for each row execute function "
            f"validate_entity_subtype_type('{entity_type}')"
        )


def downgrade() -> None:
    for table, entity_type in SUBTYPES:
        name = _trigger_name(table)

        op.execute(f"drop trigger if exists {name} on public.{table}")
        op.execute(
            f"create trigger {name} "
            f"before insert or update of entity_id on public.{table} "
            "for each row execute function "
            f"validate_entity_subtype_type('{entity_type}')"
        )
