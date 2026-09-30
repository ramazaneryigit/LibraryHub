"""add reverse index for entity_relation object-side lookups

The existing unique constraint is led by subject_entity_id, so queries that
filter on (predicate, object_entity_id) cannot seek with it. Application code
does exactly that in three places:

  * routers/relations.py   - "OR er.object_entity_id = :entity_id"
  * routers/search.py      - recursive concept-hierarchy CTE (both branches)
  * routers/persons.py     - merge rewrites relations pointing at the source

Measured on 200k synthetic rows: the current plan is a Parallel Seq Scan
(14.4 ms, 1804 buffers, 200k rows filtered, 0 matched); with this index it is
an Index Only Scan (0.05 ms, 2 buffers). See docs/architecture-v2.md §15.1.

Revision ID: b7c1e4a92f30
Revises: 49f61999a6f3
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b7c1e4a92f30"
down_revision: Union[str, Sequence[str], None] = "49f61999a6f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: plain CREATE INDEX is correct here (12 rows today). Before this
    # runs against a large populated table it must become
    # CREATE INDEX CONCURRENTLY outside a transaction, otherwise it holds a
    # write lock on entity_relation for the duration of the build.
    op.create_index(
        "ix_entity_relation_object_predicate_subject",
        "entity_relation",
        ["object_entity_id", "predicate", "subject_entity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_entity_relation_object_predicate_subject",
        table_name="entity_relation",
    )
