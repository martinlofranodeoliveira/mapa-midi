"""Durable external-consumer recordings are distinct from a fresh live run."""
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.check_interop import check_manual, check_recordings, decoded_facts, ROOT


class IndependentConsumerTests(unittest.TestCase):
    def test_complete_recorded_events_and_separate_manual_oracles(self):
        result = check_recordings(ROOT / "fixtures" / "midicsv")
        self.assertEqual(sum(case["events"] for case in result["valid_cases"].values()), 90)
        self.assertEqual(sum(case["notes"] for case in result["valid_cases"].values()), 22)
        self.assertEqual(len(result["recorded_nonconforming_consumer_acceptance"]), 2)

    def test_packaged_original_sample_matches_independent_fixture(self):
        self.assertEqual((ROOT / "src" / "mapa_midi" / "samples" / "exemplo.mid").read_bytes(),
                         (ROOT / "fixtures" / "midicsv" / "exemplo.mid").read_bytes())

    def test_recording_byte_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "recordings"
            shutil.copytree(ROOT / "fixtures" / "midicsv", copy)
            path = copy / "exemplo.mid"
            path.write_bytes(path.read_bytes() + b"X")
            with self.assertRaises(AssertionError):
                check_recordings(copy)

    def test_independent_metadata_text_and_payload_meaning(self):
        _, events = decoded_facts((ROOT / "fixtures" / "midicsv" / "metadata.decoded.csv").read_bytes())
        self.assertEqual(events[1]["fields"]["text"], "control\nand\ttab")
        self.assertEqual(events[2]["fields"]["denominator"], 8)
        self.assertEqual(events[6]["fields"]["pitch"], -8192)
        self.assertEqual(events[9]["fields"]["payload_bytes"], 4)
        self.assertEqual(events[9]["fields"]["status_byte"], 240)
        self.assertEqual(events[11]["fields"]["type_byte"], 106)
        self.assertNotIn("data", events[9]["fields"])


if __name__ == "__main__":
    unittest.main()
