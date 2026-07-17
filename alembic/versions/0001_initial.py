"""Create encrypted local state and rebuildable usage index."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "credential",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("encryption_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_credential_provider", "credential", ["provider"])
    op.create_table(
        "source",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "indexed_file",
        sa.Column("path", sa.Text(), primary_key=True),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("modified_ns", sa.Integer(), nullable=False),
        sa.Column("byte_offset", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_table(
        "metric_sample",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("service", sa.String(80), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("metric_key", sa.String(120), nullable=False),
        sa.Column("metric_name", sa.String(200), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_seconds", sa.Integer(), nullable=True),
        sa.Column("usage_kind", sa.String(20), nullable=False),
        sa.Column("percentage", sa.Float(), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=True),
        sa.Column("maximum_value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(80), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
    )
    for column in ("source_path", "source_id", "service", "provider", "account_id", "metric_key", "observed_at"):
        op.create_index(f"ix_metric_sample_{column}", "metric_sample", [column])
    # end for
    op.create_table(
        "fetch_run",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_fetch_run_account_id", "fetch_run", ["account_id"])
    op.create_index("ix_fetch_run_provider", "fetch_run", ["provider"])
    op.create_table(
        "crawl_state",
        sa.Column("account_id", sa.String(36), primary_key=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("last_percentage", sa.Float(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.create_index("ix_crawl_state_next_run_at", "crawl_state", ["next_run_at"])
# end def


def downgrade() -> None:
    for table in ("crawl_state", "fetch_run", "metric_sample", "indexed_file", "source", "credential"):
        op.drop_table(table)
    # end for
# end def
