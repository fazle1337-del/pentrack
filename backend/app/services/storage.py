import os
import uuid
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()


class LocalStorage:
    """Local filesystem storage. Swap for an Azure Blob implementation
    later by matching this interface (save / full_path / delete)."""

    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, filename: str, data: bytes) -> str:
        # Store with a UUID prefix to avoid collisions; keep original name.
        safe_name = f"{uuid.uuid4().hex}__{filename}"
        path = self.base_dir / safe_name
        with open(path, "wb") as f:
            f.write(data)
        return safe_name  # storage_path stored in DB

    def full_path(self, storage_path: str) -> Path:
        return self.base_dir / storage_path

    def delete(self, storage_path: str) -> None:
        path = self.full_path(storage_path)
        if path.exists():
            os.remove(path)


storage = LocalStorage(settings.attachments_dir)
