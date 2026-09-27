"""Persistence for handoff-pack reviews and sign-off (``data/memory/signoffs.json``).

The departing person owns this state: they confirm, correct or remove each item, then sign off. Kept as a small
JSON file (not the graph DB) so it survives a memory rebuild and is trivially auditable.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from keepline.config import MEMORY_DIR
from keepline.contracts import HandoffItem, HandoffPack

SIGNOFF_PATH = MEMORY_DIR / "signoffs.json"
STATUSES = ("pending_review", "confirmed", "corrected", "removed")


def item_key(item: HandoffItem) -> str:
    """Stable id for an item across rebuilds (section + title + receipts), so reviews are not lost on refresh."""
    raw = "|".join([item.section, item.title, ",".join(item.fact_ids), ",".join(c.doc_id for c in item.citations)])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def load_all(path: Path = SIGNOFF_PATH) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_all(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def person_state(person_id: str, path: Path = SIGNOFF_PATH) -> dict[str, Any]:
    return load_all(path).get(person_id, {"items": {}, "signed_off": False, "signed_off_at": None})


def set_item(person_id: str, key: str, status: str, correction: str | None = None, path: Path = SIGNOFF_PATH) -> None:
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")
    data = load_all(path)
    st = data.setdefault(person_id, {"items": {}, "signed_off": False, "signed_off_at": None})
    st["items"][key] = {"status": status, "correction": correction, "at": datetime.now().isoformat(timespec="seconds")}
    # Any change after sign-off re-opens the pack: the signature must cover what is actually in it.
    st["signed_off"], st["signed_off_at"] = False, None
    _save_all(data, path)


def sign_off(person_id: str, path: Path = SIGNOFF_PATH, when: datetime | None = None) -> datetime:
    data = load_all(path)
    st = data.setdefault(person_id, {"items": {}, "signed_off": False, "signed_off_at": None})
    when = when or datetime.now()
    st["signed_off"], st["signed_off_at"] = True, when.isoformat(timespec="seconds")
    _save_all(data, path)
    return when


def reset(person_id: str, path: Path = SIGNOFF_PATH) -> None:
    data = load_all(path)
    data.pop(person_id, None)
    _save_all(data, path)


def apply_state(pack: HandoffPack, path: Path = SIGNOFF_PATH) -> HandoffPack:
    """Overlay persisted review statuses/corrections and the sign-off onto a freshly built pack (in place)."""
    st = person_state(pack.person_id, path)
    for it in pack.items:
        rec = st["items"].get(item_key(it))
        if rec:
            it.status = rec["status"]
            if rec.get("status") == "corrected" and rec.get("correction"):
                it.detail = rec["correction"]
    pack.signed_off = bool(st.get("signed_off"))
    pack.signed_off_at = datetime.fromisoformat(st["signed_off_at"]) if st.get("signed_off_at") else None
    return pack
