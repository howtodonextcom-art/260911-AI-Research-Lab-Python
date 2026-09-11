from __future__ import annotations

from dataclasses import dataclass
from math import comb
from typing import Iterable

import pandas as pd

from .client import DrawRecord

MIN_NUMBER = 1
MAX_NUMBER = 45
DRAW_SIZE = 6
TICKET_PRICE_VND = 10_000
TOTAL_COMBINATIONS = comb(45, 6)
FIXED_PRIZES = {
    5: 10_000_000,
    4: 300_000,
    3: 30_000,
}


@dataclass(frozen=True, slots=True)
class DatasetSummary:
    record_count: int
    first_date: str | None
    latest_date: str | None
    latest_id: str | None
    expected_per_number: float
    fixed_prize_expectation_vnd: float


def sorted_records(records: Iterable[DrawRecord]) -> list[DrawRecord]:
    return sorted(records, key=lambda record: (record.date, record.id))


def records_to_frame(records: Iterable[DrawRecord]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": record.date,
                "id": record.id,
                "numbers": " ".join(f"{number:02d}" for number in record.result),
                "result": list(record.result),
            }
            for record in sorted_records(records)
        ]
    )


def summarize(records: Iterable[DrawRecord]) -> DatasetSummary:
    ordered = sorted_records(records)
    expected = len(ordered) * DRAW_SIZE / MAX_NUMBER if ordered else 0
    return DatasetSummary(
        record_count=len(ordered),
        first_date=ordered[0].date if ordered else None,
        latest_date=ordered[-1].date if ordered else None,
        latest_id=ordered[-1].id if ordered else None,
        expected_per_number=expected,
        fixed_prize_expectation_vnd=fixed_prize_expectation(),
    )


def frequency_frame(records: Iterable[DrawRecord]) -> pd.DataFrame:
    ordered = sorted_records(records)
    counts = {number: 0 for number in range(MIN_NUMBER, MAX_NUMBER + 1)}
    last_seen = {number: None for number in range(MIN_NUMBER, MAX_NUMBER + 1)}

    for index, record in enumerate(ordered):
        for number in record.result:
            counts[number] += 1
            last_seen[number] = index

    expected = len(ordered) * DRAW_SIZE / MAX_NUMBER if ordered else 0
    rows = []
    for number in range(MIN_NUMBER, MAX_NUMBER + 1):
        count = counts[number]
        gap = len(ordered) if last_seen[number] is None else len(ordered) - 1 - int(last_seen[number])
        rows.append(
            {
                "number": number,
                "count": count,
                "expected": expected,
                "delta": count - expected,
                "delta_percent": 0 if expected == 0 else ((count - expected) / expected) * 100,
                "gap": gap,
            }
        )
    return pd.DataFrame(rows)


def outcome_frame(ticket_count: int = 1) -> pd.DataFrame:
    rows = []
    for matches in range(7):
        combinations = comb(DRAW_SIZE, matches) * comb(MAX_NUMBER - DRAW_SIZE, DRAW_SIZE - matches)
        probability = combinations / TOTAL_COMBINATIONS
        payout = FIXED_PRIZES.get(matches)
        rows.append(
            {
                "matches": matches,
                "combinations": combinations,
                "probability_single_ticket": probability,
                "probability_portfolio_linear": min(1, ticket_count * probability),
                "fixed_payout_vnd": payout or 0,
            }
        )
    return pd.DataFrame(rows)


def fixed_prize_expectation() -> float:
    return sum(
        row["probability_single_ticket"] * row["fixed_payout_vnd"]
        for row in outcome_frame(1).to_dict("records")
    )


def top_numbers(records: Iterable[DrawRecord], limit: int = 6, ascending: bool = False) -> pd.DataFrame:
    frame = frequency_frame(records).sort_values(
        ["count", "gap", "number"],
        ascending=[ascending, not ascending, True],
    )
    return frame.head(limit).reset_index(drop=True)


def latest_draw(records: Iterable[DrawRecord]) -> DrawRecord | None:
    ordered = sorted_records(records)
    return ordered[-1] if ordered else None
