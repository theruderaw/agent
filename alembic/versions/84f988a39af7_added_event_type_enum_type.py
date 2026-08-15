"""Added Event Type enum type

Revision ID: 84f988a39af7
Revises: 01b891abc0ee
Create Date: 2026-08-16 02:47:12.884817

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "84f988a39af7"
down_revision: Union[str, Sequence[str], None] = "01b891abc0ee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


event_type_enum = sa.Enum(
    "model_input",
    "model_output",
    "skill_requested",
    "skill_received",
    "tool_call",
    "tool_result",
    "tool_failed",
    "ask_user",
    "user_input",
    "final",
    "refused",
    name="eventtype",
)


def upgrade() -> None:
    bind = op.get_bind()

    event_type_enum.create(bind, checkfirst=True)

    op.add_column(
        "events",
        sa.Column("sequence", sa.Integer(), nullable=False),
    )

    op.alter_column(
        "events",
        "event_type",
        existing_type=sa.VARCHAR(),
        type_=event_type_enum,
        existing_nullable=False,
        postgresql_using="event_type::eventtype",
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.alter_column(
        "events",
        "event_type",
        existing_type=event_type_enum,
        type_=sa.VARCHAR(),
        existing_nullable=False,
    )

    op.drop_column("events", "sequence")

    event_type_enum.drop(bind, checkfirst=True)