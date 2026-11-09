import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import mido

from mapa_midi import Limits, MidiError, read_bytes
from mapa_midi.analysis import analyze
from mapa_midi.publication import publish_bytes
from mapa_midi.reports import prepare_output


def midi_bytes():
    song = mido.MidiFile(type=0, ticks_per_beat=480, charset="utf-8")
    song.tracks.append(mido.MidiTrack([
        mido.MetaMessage("track_name", name=" =HYPERLINK(\"x\")\t<script>|*[a](b)"),
        mido.MetaMessage("text", text="linha\n\x00fim"),
        mido.Message("note_on", note=60, velocity=70),
        mido.Message("note_on", note=60, velocity=0, time=480),
        mido.Message("note_on", note=62, velocity=50),
        mido.MetaMessage("end_of_track", time=480),
    ]))
    stream = io.BytesIO()
    song.save(file=stream)
    return stream.getvalue()


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = midi_bytes()
        cls.report = analyze(read_bytes(cls.source, charset="utf-8"))

    def test_json_preserves_text_and_rationals(self):
        restored = json.loads(prepare_output(self.report, "json"))
        self.assertEqual(restored, self.report)
        self.assertEqual(restored["events"][1]["fields"]["text"], "linha\n\x00fim")
        self.assertEqual(restored["notes"][0]["duration_seconds"], {"numerator":"1", "denominator":"2", "decimal":"0.500000000"})
        self.assertEqual(restored["notes"][1]["end_tick"], None)

    def test_csv_facts_bom_and_formula_presentation(self):
        prepared = prepare_output(self.report, "csv")
        with zipfile.ZipFile(io.BytesIO(prepared)) as archive:
            self.assertEqual(set(archive.namelist()), {"eventos.csv", "notas.csv", "manifesto.json"})
            raw = archive.read("eventos.csv")
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            self.assertIn(b"\r\n", raw)
            events = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
            self.assertEqual(len(events), 6)
            self.assertTrue(events[0]["track_name"].startswith("' =HYPERLINK"))
            self.assertEqual(json.loads(events[1]["fields_json"])["text"], "linha\n\x00fim")
            notes = list(csv.DictReader(io.StringIO(archive.read("notas.csv").decode("utf-8-sig"))))
            self.assertEqual(notes[0]["duration_seconds_numerator"], "1")
            self.assertEqual(notes[0]["duration_seconds_denominator"], "2")
            self.assertEqual(notes[0]["off_kind"], "note_on_zero")
            self.assertEqual(notes[1]["end_tick"], "")

    def test_markdown_escapes_untrusted_text(self):
        md = prepare_output(self.report, "markdown").decode("utf-8")
        self.assertNotIn("<script>", md)
        self.assertIn("&lt;script&gt;", md)
        self.assertNotIn("*[a](b)", md)
        self.assertIn("\\|", md)
        self.assertNotIn("\x00", md)
        self.assertIn("0000", md)
        self.assertIn("1/2 s", md)
        self.assertIn("## Todos os eventos", md)

    def test_bundle_members_digests_and_repeatability(self):
        one = prepare_output(self.report, sample=self.source)
        self.assertEqual(one, prepare_output(self.report, sample=self.source))
        with zipfile.ZipFile(io.BytesIO(one)) as archive:
            self.assertEqual(archive.testzip(), None)
            self.assertEqual(set(archive.namelist()), {"resumo.json", "resumo.md", "eventos.csv", "notas.csv", "rolo.svg", "rolo.png", "manifesto.json", "exemplo.mid"})
            manifest = json.loads(archive.read("manifesto.json"))
            self.assertEqual(set(manifest["members"]), set(archive.namelist()) - {"manifesto.json"})
            self.assertEqual(manifest["source_sha256"], hashlib.sha256(self.source).hexdigest())
            for name, record in manifest["members"].items():
                data = archive.read(name)
                self.assertEqual(record, {"size_bytes":len(data), "sha256":hashlib.sha256(data).hexdigest()})

    def test_limits_apply_to_all_outputs(self):
        for kind in ("json", "markdown", "csv", "bundle"):
            with self.subTest(kind=kind), self.assertRaises(MidiError) as caught:
                prepare_output(self.report, kind, limits=Limits(max_report_bytes=20))
            self.assertEqual(caught.exception.code, "report_limit")

    def test_plot_failure_does_not_degrade_to_partial_bundle(self):
        with patch("mapa_midi.plot.render_plot", side_effect=MidiError("plot_limit", "limite")):
            with self.assertRaises(MidiError):
                prepare_output(self.report)
        self.assertTrue(prepare_output(self.report, "json").startswith(b"{"))

    def test_sample_must_be_the_captured_bytes(self):
        with self.assertRaises(MidiError):
            prepare_output(self.report, sample=b"outro")


class PublicationTests(unittest.TestCase):
    def test_new_file_and_existing_regular_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.json"
            publish_bytes(path, b"novo")
            with self.assertRaises(MidiError) as caught:
                publish_bytes(path, b"substituto")
            self.assertEqual(caught.exception.code, "output_exists")
            self.assertEqual(path.read_bytes(), b"novo")
            self.assertEqual([p.name for p in Path(directory).iterdir()], ["out.json"])

    @unittest.skipIf(os.name == "nt", "Symlink no Windows pode exigir privilégio administrativo.")
    def test_broken_symlink_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out"
            path.symlink_to("missing")
            with self.assertRaises(MidiError):
                publish_bytes(path, b"novo")
            self.assertTrue(path.is_symlink())
            self.assertEqual(os.readlink(path), "missing")

    def test_link_failure_cleans_only_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out"
            with patch("mapa_midi.publication.os.link", side_effect=PermissionError("conteúdo privado")):
                with self.assertRaises(MidiError) as caught:
                    publish_bytes(path, b"novo")
            self.assertNotIn("privado", str(caught.exception))
            self.assertEqual(list(Path(directory).iterdir()), [])


class CliTests(unittest.TestCase):
    def run_cli(self, directory, *args):
        return subprocess.run([sys.executable, "-m", "mapa_midi", *args], cwd=directory,
                              capture_output=True, encoding="utf-8", timeout=90)

    def test_all_formats_keep_input_and_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = midi_bytes()
            (root / "input.mid").write_bytes(source)
            for kind in ("bundle", "json", "csv", "markdown"):
                dest = "report-" + kind
                result = self.run_cli(root, "inspecionar", "input.mid", "--charset", "utf-8", "--formato", kind, "--saida", dest)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("1 diagnósticos", result.stdout)
                self.assertNotIn("HYPERLINK", result.stdout + result.stderr)
                before = (root / dest).read_bytes()
                again = self.run_cli(root, "inspecionar", "input.mid", "--charset", "utf-8", "--formato", kind, "--saida", dest)
                self.assertEqual(again.returncode, 2)
                self.assertIn("output_exists", again.stderr)
                self.assertEqual((root / dest).read_bytes(), before)
            self.assertEqual((root / "input.mid").read_bytes(), source)
            same = self.run_cli(root, "inspecionar", "input.mid", "--saida", "input.mid", "--formato", "json")
            self.assertEqual(same.returncode, 2)
            self.assertEqual((root / "input.mid").read_bytes(), source)

    def test_bad_file_has_no_report_or_content_echo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "input.mid").write_bytes(b"conteudo-secreto" * 10)
            result = self.run_cli(root, "inspecionar", "input.mid", "--saida", "out.zip")
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("conteudo-secreto", result.stderr + result.stdout)
            self.assertFalse((root / "out.zip").exists())
            self.assertFalse(list(root.glob(".mapa-midi-*")))

    def test_example_is_usable_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_cli(root, "exemplo", "--saida", "demo.zip")
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(root / "demo.zip") as archive:
                report = json.loads(archive.read("resumo.json"))
                (root / "exemplo.mid").write_bytes(archive.read("exemplo.mid"))
            result = self.run_cli(root, "inspecionar", "exemplo.mid", "--charset", "utf-8", "--saida", "out.json", "--formato", "json")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((root / "out.json").read_bytes()), report)


if __name__ == "__main__":
    unittest.main()
