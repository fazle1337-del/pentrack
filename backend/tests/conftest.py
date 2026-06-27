"""Test-wide environment defaults, applied before app modules import (so the
lru_cached get_settings() picks them up). Keeps imports of app.main from trying
to create /data/attachments or reach a real Postgres."""

import os
import tempfile

os.environ.setdefault("ATTACHMENTS_DIR", tempfile.mkdtemp(prefix="pentrack-attach-"))
os.environ.setdefault("DATABASE_URL", "sqlite://")
