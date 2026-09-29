"""Preserve decision-time evidence without inventing history for old decisions."""

from alembic import op
import sqlalchemy as sa

revision = "c91f4a20de76"
down_revision = "b33d2019e9b3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reconciliation_decisions", sa.Column("evidence_snapshot", sa.JSON(), nullable=True))
    # PostgreSQL enforces write-once snapshots, including NULL on legacy records.
    op.execute("""
        CREATE FUNCTION libraryhub_guard_decision_snapshot() RETURNS trigger AS $$
        BEGIN
            IF NEW.evidence_snapshot::jsonb IS DISTINCT FROM OLD.evidence_snapshot::jsonb THEN
                RAISE EXCEPTION 'Decision evidence snapshot cannot be modified';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_decision_snapshot_immutable
        BEFORE UPDATE OF evidence_snapshot ON reconciliation_decisions
        FOR EACH ROW EXECUTE FUNCTION libraryhub_guard_decision_snapshot();
    """)


def downgrade():
    op.execute("DROP TRIGGER trg_decision_snapshot_immutable ON reconciliation_decisions")
    op.execute("DROP FUNCTION libraryhub_guard_decision_snapshot()")
    op.drop_column("reconciliation_decisions", "evidence_snapshot")
