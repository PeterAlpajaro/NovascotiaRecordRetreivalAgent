from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class StateStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"processed_uids": [], "ignored_uids": []}
        try:
            return json.loads(self.path.read_text())
        except json.JSONDecodeError:
            return {"processed_uids": [], "ignored_uids": []}

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True))
        tmp.replace(self.path)

    def has_processed(self, uid: str) -> bool:
        return uid in set(self.data.get("processed_uids", []))

    def mark_processed(self, uid: str) -> None:
        values = list(dict.fromkeys([*self.data.get("processed_uids", []), uid]))
        self.data["processed_uids"] = values[-500:]
        self.save()

    def has_ignored(self, uid: str) -> bool:
        return uid in set(self.data.get("ignored_uids", []))

    def mark_ignored(self, uid: str) -> None:
        values = list(dict.fromkeys([*self.data.get("ignored_uids", []), uid]))
        self.data["ignored_uids"] = values[-500:]
        self.save()
