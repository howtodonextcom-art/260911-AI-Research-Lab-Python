from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Iterable

from .client import BASE_URL, DrawRecord, serialize_jsonl

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PACKAGE_ROOT / "data"
DEFAULT_DATASET_PATH = DEFAULT_DATA_DIR / "official_mega645.jsonl"
DEFAULT_MANIFEST_PATH = DEFAULT_DATA_DIR / "official_mega645.manifest.json"
OFFICIAL_HISTORY_URL = f"{BASE_URL}/vi/trung-thuong/ket-qua-trung-thuong/winning-number-645"


@dataclass(frozen=True, slots=True)
class DatasetDiff:
    added: int
    unchanged: int
    conflicts: tuple[str, ...]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def dataset_sha256(records: Iterable[DrawRecord]) -> str:
    return hashlib.sha256(serialize_jsonl(records).encode("utf-8")).hexdigest()


def load_records(path: Path = DEFAULT_DATASET_PATH) -> list[DrawRecord]:
    if not path.exists():
        return []
    records: list[DrawRecord] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            records.append(
                DrawRecord(
                    date=str(row["date"]),
                    id=str(row["id"]),
                    result=tuple(int(number) for number in row["result"]),
                )
            )
        except Exception as exc:  # noqa: BLE001 - preserve the exact row number for users.
            raise ValueError(f"Invalid JSONL row {line_number} in {path}: {exc}") from exc
    return sorted(records, key=lambda record: (record.date, record.id))


def load_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, object] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def merge_records(existing: Iterable[DrawRecord], incoming: Iterable[DrawRecord]) -> tuple[list[DrawRecord], DatasetDiff]:
    by_id = {record.id: record for record in existing}
    added = 0
    unchanged = 0
    conflicts: list[str] = []

    for record in incoming:
        current = by_id.get(record.id)
        if current is None:
            by_id[record.id] = record
            added += 1
            continue
        if current.date != record.date or current.result != record.result:
            conflicts.append(record.id)
            continue
        unchanged += 1

    return sorted(by_id.values(), key=lambda row: (row.date, row.id)), DatasetDiff(
        added=added,
        unchanged=unchanged,
        conflicts=tuple(sorted(conflicts)),
    )


def build_manifest(
    records: Iterable[DrawRecord],
    *,
    fetched_at: str | None = None,
    source_url: str = OFFICIAL_HISTORY_URL,
    mode: str = "official-history-table",
) -> dict[str, object]:
    ordered = sorted(records, key=lambda record: (record.date, record.id))
    return {
        "schemaVersion": 1,
        "product": "mega645",
        "source": {
            "id": "vietlott.vn",
            "url": source_url,
            "mode": mode,
            "license": "public official website, no explicit reuse license found",
        },
        "recordCount": len(ordered),
        "firstDrawDate": ordered[0].date if ordered else None,
        "latestDrawDate": ordered[-1].date if ordered else None,
        "latestDrawId": ordered[-1].id if ordered else None,
        "fetchedAt": fetched_at or utc_now_iso(),
        "datasetSha256": dataset_sha256(ordered),
        "validation": {
            "valid": True,
            "duplicates": len(ordered) - len({record.id for record in ordered}),
            "conflicts": 0,
        },
    }


def write_dataset(
    records: Iterable[DrawRecord],
    *,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    fetched_at: str | None = None,
    source_url: str = OFFICIAL_HISTORY_URL,
) -> dict[str, object]:
    ordered = sorted(records, key=lambda record: (record.date, record.id))
    manifest = build_manifest(ordered, fetched_at=fetched_at, source_url=source_url)
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(dataset_path, serialize_jsonl(ordered))
    _write_atomic(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def _write_atomic(path: Path, content: str) -> None:
    temp = path.with_name(f"{path.name}.{datetime.now(timezone.utc).timestamp():.0f}.tmp")
    try:
        temp.write_text(content, encoding="utf-8")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()
