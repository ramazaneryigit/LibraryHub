"""enforce entity subtype type integrity

Revision ID: 71eb6083b10d
Revises: 83c5b28687f9
Create Date: 2026-09-15 10:58:56.769295

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "71eb6083b10d"
down_revision: Union[str, Sequence[str], None] = "83c5b28687f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SUBTYPE_TABLES = {
    "persons": "PERSON",
    "collective_agents": "ORGANIZATION",
    "concepts": "CONCEPT",
    "works": "WORK",
    "expressions": "EXPRESSION",
    "manifestations": "MANIFESTATION",
    "items": "ITEM",
    "places": "PLACE",
    "time_spans": "TIME_SPAN",
}


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_entity_subtype_type()
        RETURNS trigger AS $$
        DECLARE
            actual_type varchar(50);
        BEGIN
            SELECT entity_type
            INTO actual_type
            FROM entities
            WHERE id = NEW.entity_id;

            IF actual_type IS DISTINCT FROM TG_ARGV[0] THEN
                RAISE EXCEPTION
                    'Entity % must have entity_type %, found %',
                    NEW.entity_id,
                    TG_ARGV[0],
                    actual_type;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    for table_name, expected_type in SUBTYPE_TABLES.items():
        trigger_name = f"trg_{table_name}_validate_entity_type"

        op.execute(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT OR UPDATE OF entity_id
            ON {table_name}
            FOR EACH ROW
            EXECUTE FUNCTION validate_entity_subtype_type('{expected_type}');
            """
        )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_entity_type_change_with_subtype()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.entity_type IS DISTINCT FROM OLD.entity_type THEN

                IF EXISTS (
                    SELECT 1
                    FROM persons
                    WHERE entity_id = OLD.id
                )
                OR EXISTS (
                    SELECT 1
                    FROM collective_agents
                    WHERE entity_id = OLD.id
                )
                OR EXISTS (
                    SELECT 1
                    FROM concepts
                    WHERE entity_id = OLD.id
                )
                OR EXISTS (
                    SELECT 1
                    FROM works
                    WHERE entity_id = OLD.id
                )
                OR EXISTS (
                    SELECT 1
                    FROM expressions
                    WHERE entity_id = OLD.id
                )
                OR EXISTS (
                    SELECT 1
                    FROM manifestations
                    WHERE entity_id = OLD.id
                )
                OR EXISTS (
                    SELECT 1
                    FROM items
                    WHERE entity_id = OLD.id
                )
                OR EXISTS (
                    SELECT 1
                    FROM places
                    WHERE entity_id = OLD.id
                )
                OR EXISTS (
                    SELECT 1
                    FROM time_spans
                    WHERE entity_id = OLD.id
                )
                THEN
                    RAISE EXCEPTION
                        'Entity % cannot change entity_type from % to because a subtype record exists',
                        OLD.id,
                        OLD.entity_type;
                END IF;

            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_entities_prevent_type_change
        BEFORE UPDATE OF entity_type
        ON entities
        FOR EACH ROW
        EXECUTE FUNCTION prevent_entity_type_change_with_subtype();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_entities_prevent_type_change ON entities;"
    )

    op.execute(
        "DROP FUNCTION IF EXISTS prevent_entity_type_change_with_subtype();"
    )

    for table_name in SUBTYPE_TABLES:
        trigger_name = f"trg_{table_name}_validate_entity_type"

        op.execute(
            f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name};"
        )

    op.execute(
        "DROP FUNCTION IF EXISTS validate_entity_subtype_type();"
    )
