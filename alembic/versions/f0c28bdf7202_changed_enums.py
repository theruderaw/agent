"""Changed enums

Revision ID: f0c28bdf7202
Revises: 84f988a39af7
Create Date: 2026-08-18 09:15:48.187576

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0c28bdf7202'
down_revision: Union[str, Sequence[str], None] = '84f988a39af7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


new_state_enum = sa.Enum(
    "start",
    "model_call",
    "skill_requested",
    "tool_call",
    "waiting_for_user",
    "final",
    "refused",
    "stop",
    "failed",
    name="state_new",
)

old_state_enum = sa.Enum(
    "start",
    "model_call",
    "model_output",
    "skill_requested",
    "skill_received",
    "tool_call",
    "tool_result",
    "tool_failed",
    "waiting_for_user",
    "final",
    "refused",
    "stop",
    "failed",
    name="state_old",
)


def upgrade() -> None:
    bind = op.get_bind()

    new_state_enum.create(bind, checkfirst=True)

    op.execute(
        "ALTER TABLE runs ALTER COLUMN state TYPE state_new "
        "USING state::text::state_new"
    )

    op.execute("DROP TYPE state")
    op.execute("ALTER TYPE state_new RENAME TO state")


def downgrade() -> None:
    bind = op.get_bind()

    old_state_enum.create(bind, checkfirst=True)

    op.execute(
        "ALTER TABLE runs ALTER COLUMN state TYPE state_old "
        "USING state::text::state_old"
    )

    op.execute("DROP TYPE state")
    op.execute("ALTER TYPE state_old RENAME TO state")
