"""Add nullable model column to metric_sample."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_metric_sample_model"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("metric_sample", sa.Column("model", sa.String(120), nullable=True))
# end def


def downgrade() -> None:
    with op.batch_alter_table("metric_sample") as batch_op:
        batch_op.drop_column("model")
    # end with
# end def
