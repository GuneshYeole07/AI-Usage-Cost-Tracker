"""initial schema: sessions, turns, labels

Revision ID: 0001
Revises:
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _existing() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    have = _existing()  # tables may already exist if the app was started before migrating
    if "sessions" not in have:
        op.create_table(
            "sessions",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("user", sa.String(64), nullable=False, index=True),
            sa.Column("project", sa.String(64), nullable=False),
            sa.Column("source", sa.String(32), nullable=False),
            sa.Column("is_simulated", sa.Boolean, nullable=False, index=True),
            sa.Column("task_type", sa.String(32), nullable=True),
            sa.Column("started_at", sa.DateTime, nullable=False, index=True),
            sa.Column("ended_at", sa.DateTime, nullable=False),
        )
    if "turns" not in have:
        op.create_table(
            "turns",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("session_id", sa.String(64), sa.ForeignKey("sessions.id", ondelete="CASCADE"), index=True),
            sa.Column("idx", sa.Integer, nullable=False),
            sa.Column("timestamp", sa.DateTime, nullable=False, index=True),
            sa.Column("model", sa.String(64), nullable=False),
            sa.Column("input_tokens", sa.Integer, nullable=False),
            sa.Column("output_tokens", sa.Integer, nullable=False),
            sa.Column("cache_creation_tokens", sa.Integer, nullable=False),
            sa.Column("cache_read_tokens", sa.Integer, nullable=False),
            sa.Column("tool_calls", sa.Integer, nullable=False),
            sa.Column("tool_errors", sa.Integer, nullable=False),
            sa.Column("tool_names", sa.JSON, nullable=False),
            sa.Column("file_reads", sa.JSON, nullable=False),
        )
    if "labels" not in have:
        op.create_table(
            "labels",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("session_id", sa.String(64), nullable=False, index=True),
            sa.Column("rule", sa.String(32), nullable=False),
            sa.Column("is_waste", sa.Boolean, nullable=False),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False),
            sa.UniqueConstraint("session_id", "rule", name="uq_label_session_rule"),
        )


def downgrade() -> None:
    for table in ("labels", "turns", "sessions"):
        op.drop_table(table)
