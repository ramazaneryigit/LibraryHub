"""enforce agent entity type integrity

Revision ID: 08f81b9d2a23
Revises: 71eb6083b10d
Create Date: 2026-09-15 12:12:47.665580

"""
from typing import Sequence, Union

from alembic import op


revision: str = '08f81b9d2a23'
down_revision: Union[str, Sequence[str], None] = '71eb6083b10d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION validate_agent_entity_type()
        RETURNS TRIGGER AS $$
        DECLARE
            agent_type VARCHAR(50);
        BEGIN
            SELECT entity_type
            INTO agent_type
            FROM entities
            WHERE id = NEW.agent_entity_id;

            IF agent_type NOT IN ('PERSON', 'ORGANIZATION') THEN
                RAISE EXCEPTION
                    'Agent entity % must have entity_type PERSON or ORGANIZATION, found %',
                    NEW.agent_entity_id,
                    agent_type;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_work_agent_validate_type
        BEFORE INSERT OR UPDATE ON work_agent_relation
        FOR EACH ROW
        EXECUTE FUNCTION validate_agent_entity_type();
    """)

    op.execute("""
        CREATE TRIGGER trg_expression_agent_validate_type
        BEFORE INSERT OR UPDATE ON expression_agent_relation
        FOR EACH ROW
        EXECUTE FUNCTION validate_agent_entity_type();
    """)

    op.execute("""
        CREATE TRIGGER trg_manifestation_agent_validate_type
        BEFORE INSERT OR UPDATE ON manifestation_agent_relation
        FOR EACH ROW
        EXECUTE FUNCTION validate_agent_entity_type();
    """)

    op.execute("""
        CREATE TRIGGER trg_item_agent_validate_type
        BEFORE INSERT OR UPDATE ON item_agent_relation
        FOR EACH ROW
        EXECUTE FUNCTION validate_agent_entity_type();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_agent_entity_type_change()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.entity_type <> OLD.entity_type
               AND EXISTS (
                   SELECT 1
                   FROM work_agent_relation
                   WHERE agent_entity_id = OLD.id
               )
               OR NEW.entity_type <> OLD.entity_type
               AND EXISTS (
                   SELECT 1
                   FROM expression_agent_relation
                   WHERE agent_entity_id = OLD.id
               )
               OR NEW.entity_type <> OLD.entity_type
               AND EXISTS (
                   SELECT 1
                   FROM manifestation_agent_relation
                   WHERE agent_entity_id = OLD.id
               )
               OR NEW.entity_type <> OLD.entity_type
               AND EXISTS (
                   SELECT 1
                   FROM item_agent_relation
                   WHERE agent_entity_id = OLD.id
               )
            THEN
                RAISE EXCEPTION
                    'Entity % cannot change entity_type because it is used as an agent',
                    OLD.id;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_entities_prevent_agent_type_change
        BEFORE UPDATE OF entity_type ON entities
        FOR EACH ROW
        EXECUTE FUNCTION prevent_agent_entity_type_change();
    """)


def downgrade() -> None:
    op.execute("""
        DROP TRIGGER IF EXISTS trg_entities_prevent_agent_type_change
        ON entities;
    """)

    op.execute("""
        DROP FUNCTION IF EXISTS prevent_agent_entity_type_change();
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_item_agent_validate_type
        ON item_agent_relation;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_manifestation_agent_validate_type
        ON manifestation_agent_relation;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_expression_agent_validate_type
        ON expression_agent_relation;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_work_agent_validate_type
        ON work_agent_relation;
    """)

    op.execute("""
        DROP FUNCTION IF EXISTS validate_agent_entity_type();
    """)
