"""Initial schema.

The initial migration creates the schema from the ORM metadata rather than
transcribing twelve tables by hand; later migrations are written explicitly
(autogenerate against this baseline works because the two are identical).
"""
from alembic import op
import sqlalchemy as sa

from rns.db.models import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_signals_embedding_hnsw ON signals "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
