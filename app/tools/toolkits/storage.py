# app/tools/toolkits/storage.py

import json
from pathlib import Path

from app.tools.base import Toolkit


class StorageTools(Toolkit):
    namespace = "storage"

    def __init__(self):
        self.root = Path(__file__).parent.parent.parent.parent.resolve()
        self.proj_root = (self.root / "workspace").resolve()
        self.store_path = (self.root / "store.json").resolve()

    def _read_store(self) -> dict[str, str]:
        if not self.store_path.exists():
            return {}

        try:
            with self.store_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"store.json is corrupted: {e}") from e

        if not isinstance(data, dict):
            raise ValueError("store.json must contain a JSON object")

        return data

    def _write_store(self, data: dict[str, str]) -> None:
        with self.store_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)

    async def store(self, key: str, value: str) -> str:
        """Store a value under the given key."""
        if not key.strip():
            raise ValueError("key must not be empty")

        data = self._read_store()
        data[key] = value
        self._write_store(data)

        return value

    async def retrieve(self, key: str) -> str:
        """Retrieve the value stored under the given key."""
        data = self._read_store()

        if key not in data:
            raise KeyError(f"no value stored under key: {key}")

        return data[key]

    async def delete(self, key: str) -> str:
        """Delete the value stored under the given key."""
        data = self._read_store()

        if key not in data:
            raise KeyError(f"no value stored under key: {key}")

        value = data.pop(key)
        self._write_store(data)

        return value


if __name__ == "__main__":
    import asyncio

    async def _main() -> None:
        tools = StorageTools()
        print("store:", await tools.store("greeting", "hello world"))
        print("retrieve:", await tools.retrieve("greeting"))
        print("delete:", await tools.delete("greeting"))

    asyncio.run(_main())