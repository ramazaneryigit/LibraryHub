"""the item identifier lookup index the previous revision forgot

`b1c4e8f29a37` created `tenant.item_identifiers` with a unique constraint on
`(tenant_id, scheme, value)` and a model that also declares an index on
`item_id`. The migration did not create it, so the model and the database
disagreed and `alembic check` failed.

Why this is a separate revision rather than a correction
--------------------------------------------------------
The previous revision had already been applied. Its downgrade drops
`tenant.item_identifiers` and its upgrade rebuilds the contents by reading
`public.identifiers` -- rows that were cascaded away when the ITEM entities were
deleted. Re-running it would therefore silently produce an empty table: the three
identifiers it exists to preserve would be gone, and nothing would say so. That is
the concrete reason applied migrations are not edited, and it is worth a one-line
revision to respect it.

Revision ID: c2d5f93ab048
Revises: b1c4e8f29a37
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c2d5f93ab048"
down_revision: Union[str, Sequence[str], None] = "b1c4e8f29a37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_item_identifiers_item",
        "item_identifiers",
        ["item_id"],
        schema="tenant",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_item_identifiers_item",
        table_name="item_identifiers",
        schema="tenant",
    )
