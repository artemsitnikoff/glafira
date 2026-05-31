from abc import ABC, abstractmethod
from pathlib import Path
import asyncio
import uuid


class StorageService(ABC):
    @abstractmethod
    async def save(self, content: bytes, *, company_id, candidate_id, filename: str) -> str:
        """Save file and return storage_path"""
        ...

    @abstractmethod
    def get_path(self, storage_path: str) -> Path:
        """Get full path from storage_path"""
        ...

    @abstractmethod
    async def delete(self, storage_path: str) -> None:
        """Delete file by storage_path"""
        ...


class LocalStorageService(StorageService):
    def __init__(self, root: Path):
        self.root = root

    async def save(self, content: bytes, *, company_id, candidate_id, filename: str) -> str:
        rel = Path(str(company_id)) / str(candidate_id) / f"{uuid.uuid4()}_{filename}"
        full = self.root / rel

        # Синхронный дисковый I/O (до 10 МБ) выносим в поток, чтобы не блокировать event loop.
        def _write() -> None:
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_bytes(content)

        await asyncio.to_thread(_write)
        return str(rel)

    def get_path(self, storage_path: str) -> Path:
        return self.root / storage_path

    async def delete(self, storage_path: str) -> None:
        p = self.get_path(storage_path)

        def _delete() -> None:
            if p.exists():
                p.unlink()

        await asyncio.to_thread(_delete)


# Global instance
storage_root = Path(__file__).parent.parent.parent / "storage"
storage_service = LocalStorageService(storage_root)