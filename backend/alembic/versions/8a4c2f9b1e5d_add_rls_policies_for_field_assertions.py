"""RLS politikaları field_assertions için - paydaşlar kendi source_system_id ile yazabilir

Revision ID: 8a4c2f9b1e5d
Revises: 7f016f35c95d
Create Date: 2026-10-02 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8a4c2f9b1e5d'
down_revision: Union[str, Sequence[str], None] = '7f016f35c95d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enable RLS on field_assertions and create policies."""
    
    # Enable RLS on field_assertions
    op.execute("ALTER TABLE field_assertions ENABLE ROW LEVEL SECURITY")
    
    # Policy 1: Platform admin (current_user_role = 'admin' in control.users) can read/write all
    op.execute("""
        CREATE POLICY field_assertions_admin_all
        ON field_assertions
        USING (
            current_setting('libraryhub.admin_mode')::boolean = true
        )
        WITH CHECK (
            current_setting('libraryhub.admin_mode')::boolean = true
        )
    """)
    
    # Policy 2: Users can only INSERT/UPDATE field_assertions with their own source_system_id
    # The source_system_id of the current user comes from control.users.subject_entity_id
    # which points to a source_system (for publishers/agencies)
    op.execute("""
        CREATE POLICY field_assertions_own_source
        ON field_assertions
        FOR INSERT
        WITH CHECK (
            source_system_id IN (
                SELECT id FROM source_systems 
                WHERE id = current_setting('libraryhub.user_source_system_id')::uuid
            )
            OR current_setting('libraryhub.user_source_system_id') IS NULL
        )
    """)
    
    # Policy 3: UPDATE only own assertions (same source_system_id)
    op.execute("""
        CREATE POLICY field_assertions_own_update
        ON field_assertions
        FOR UPDATE
        USING (
            source_system_id IN (
                SELECT id FROM source_systems 
                WHERE id = current_setting('libraryhub.user_source_system_id')::uuid
            )
            OR current_setting('libraryhub.user_source_system_id') IS NULL
        )
        WITH CHECK (
            source_system_id IN (
                SELECT id FROM source_systems 
                WHERE id = current_setting('libraryhub.user_source_system_id')::uuid
            )
            OR current_setting('libraryhub.user_source_system_id') IS NULL
        )
    """)
    
    # Policy 4: Everyone can SELECT (public knowledge)
    op.execute("""
        CREATE POLICY field_assertions_read_all
        ON field_assertions
        FOR SELECT
        USING (true)
    """)
    
    # Policy 5: Curators (admin role) can DELETE assertions (tombstone-style)
    op.execute("""
        CREATE POLICY field_assertions_admin_delete
        ON field_assertions
        FOR DELETE
        USING (
            current_setting('libraryhub.admin_mode')::boolean = true
        )
    """)
    

def downgrade() -> None:
    """Remove RLS policies and disable RLS."""
    
    op.execute("DROP POLICY IF EXISTS field_assertions_admin_all ON field_assertions")
    op.execute("DROP POLICY IF EXISTS field_assertions_own_source ON field_assertions")
    op.execute("DROP POLICY IF EXISTS field_assertions_own_update ON field_assertions")
    op.execute("DROP POLICY IF EXISTS field_assertions_read_all ON field_assertions")
    op.execute("DROP POLICY IF EXISTS field_assertions_admin_delete ON field_assertions")
    
    op.execute("ALTER TABLE field_assertions DISABLE ROW LEVEL SECURITY")
