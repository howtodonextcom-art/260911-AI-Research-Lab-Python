import tempfile
import unittest
from pathlib import Path

from vietlott_mega645.analytics import TOTAL_COMBINATIONS, frequency_frame, outcome_frame, summarize
from vietlott_mega645.client import DrawRecord
from vietlott_mega645.storage import load_records, merge_records, write_dataset


SAMPLE = [
    DrawRecord(date="2026-09-09", id="01560", result=(12, 17, 20, 21, 36, 43)),
    DrawRecord(date="2026-09-11", id="01561", result=(14, 18, 20, 21, 26, 27)),
]


class AnalyticsStorageTests(unittest.TestCase):
    def test_summary_and_frequency(self):
        summary = summarize(SAMPLE)
        self.assertEqual(summary.record_count, 2)
        self.assertEqual(summary.latest_id, "01561")
        freq = frequency_frame(SAMPLE)
        self.assertEqual(int(freq.loc[freq["number"] == 20, "count"].iloc[0]), 2)
        self.assertEqual(int(freq["count"].sum()), 12)

    def test_outcome_model_conserves_combinations(self):
        outcomes = outcome_frame(1)
        self.assertEqual(int(outcomes["combinations"].sum()), TOTAL_COMBINATIONS)

    def test_storage_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = root / "official_mega645.jsonl"
            manifest = root / "official_mega645.manifest.json"
            meta = write_dataset(SAMPLE, dataset_path=dataset, manifest_path=manifest, fetched_at="2026-09-11T00:00:00Z")
            loaded = load_records(dataset)
            self.assertEqual(loaded, SAMPLE)
            self.assertEqual(meta["recordCount"], 2)
            self.assertTrue(manifest.exists())

    def test_merge_detects_conflict_without_overwrite(self):
        incoming = [DrawRecord(date="2026-09-11", id="01561", result=(1, 2, 3, 4, 5, 6))]
        merged, diff = merge_records(SAMPLE, incoming)
        self.assertEqual(diff.conflicts, ("01561",))
        self.assertEqual(merged[-1].result, (14, 18, 20, 21, 26, 27))


if __name__ == "__main__":
    unittest.main()
