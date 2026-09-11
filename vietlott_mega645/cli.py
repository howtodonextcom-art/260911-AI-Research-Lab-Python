from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .client import VietlottMega645Client, serialize_jsonl, write_jsonl
from .storage import DEFAULT_DATA_DIR, load_records, merge_records, write_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read public Vietlott Mega 6/45 draw pages.")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    latest = subparsers.add_parser("latest", help="Fetch the latest public draw detail page.")
    latest.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")

    draw = subparsers.add_parser("draw", help="Fetch one draw detail page by id.")
    draw.add_argument("draw_id", help="Five-digit draw id, for example 01561.")
    draw.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")

    history = subparsers.add_parser("history", help="Fetch paginated public history rows.")
    history.add_argument("--max-pages", type=int, default=2, help="Maximum pages to fetch; omit with --all for full history.")
    history.add_argument("--all", action="store_true", help="Fetch until the public endpoint stops returning rows.")
    history.add_argument("--delay", type=float, default=0.5, help="Delay between paginated requests.")
    history.add_argument("--output", type=Path, help="Write canonical JSONL to this file.")
    history.add_argument("--include-source", action="store_true", help="Include source_url in JSON output.")
    history.add_argument("--pretty", action="store_true", help="Print a compact summary instead of JSONL.")

    sync = subparsers.add_parser("sync", help="Crawl official Vietlott history and save local JSONL + manifest.")
    sync.add_argument("--max-pages", type=int, default=2, help="Maximum pages to fetch; omit with --all for full history.")
    sync.add_argument("--all", action="store_true", help="Fetch until the public endpoint stops returning rows.")
    sync.add_argument("--delay", type=float, default=0.5, help="Delay between paginated requests.")
    sync.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="Directory for official_mega645 files.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = VietlottMega645Client(timeout_seconds=args.timeout)

    if args.command == "latest":
        row = client.fetch_latest().to_dict()
        print(json.dumps(row, ensure_ascii=False, indent=2 if args.pretty else None))
        return 0

    if args.command == "draw":
        row = client.fetch_draw(args.draw_id).to_dict()
        print(json.dumps(row, ensure_ascii=False, indent=2 if args.pretty else None))
        return 0

    if args.command == "history":
        max_pages = None if args.all else args.max_pages
        records = client.fetch_history(max_pages=max_pages, delay_seconds=args.delay)
        if args.output:
            write_jsonl(args.output, records, include_source=args.include_source)
        if args.pretty:
            first = min(records, key=lambda row: row.date, default=None)
            latest = max(records, key=lambda row: row.date, default=None)
            print(
                json.dumps(
                    {
                        "records": len(records),
                        "first": first.to_dict() if first else None,
                        "latest": latest.to_dict() if latest else None,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif not args.output:
            print(serialize_jsonl(records, include_source=args.include_source), end="")
        return 0

    if args.command == "sync":
        max_pages = None if args.all else args.max_pages
        dataset_path = args.data_dir / "official_mega645.jsonl"
        manifest_path = args.data_dir / "official_mega645.manifest.json"
        existing = load_records(dataset_path)
        incoming = client.fetch_history(max_pages=max_pages, delay_seconds=args.delay)
        merged, diff = merge_records(existing, incoming)
        if diff.conflicts:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error": "conflicts detected",
                        "conflicts": list(diff.conflicts),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1
        manifest = write_dataset(merged, dataset_path=dataset_path, manifest_path=manifest_path)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "fetched": len(incoming),
                    "added": diff.added,
                    "unchanged": diff.unchanged,
                    "recordCount": manifest["recordCount"],
                    "firstDrawDate": manifest["firstDrawDate"],
                    "latestDrawDate": manifest["latestDrawDate"],
                    "latestDrawId": manifest["latestDrawId"],
                    "datasetSha256": manifest["datasetSha256"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")
