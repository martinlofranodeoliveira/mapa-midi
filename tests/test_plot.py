"""Geometria numérica do gráfico e artefatos locais/headless."""

from contextlib import redirect_stderr
from copy import deepcopy
from io import StringIO
import struct
import unittest
from unittest.mock import patch
import warnings
from xml.etree import ElementTree

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from mapa_midi.analysis import analyze
from mapa_midi.errors import MidiError
from mapa_midi.models import Event, Limits, Snapshot, Track
from mapa_midi.plot import _build_figure, render_plot


def report_for(*rows):
    events, tracks = [], []
    for track, row in enumerate(rows):
        name = None
        for index, (tick, kind, fields) in enumerate(row):
            fields = dict(fields)
            channel = fields.pop("channel", None)
            events.append(Event(track, index, tick, kind, channel is None, None, channel, tuple(sorted(fields.items()))))
            if kind == "track_name" and name is None:
                name = fields["name"]
        tracks.append(Track(track, name, row[-1][0], len(row)))
    return analyze(Snapshot("b" * 64, 123, 0 if len(rows) == 1 else 1, 480, "utf-8", 0, tuple(tracks), tuple(events)))


def on(tick, note=60):
    return tick, "note_on", {"channel": 0, "note": note, "velocity": 80}


def off(tick, note=60):
    return tick, "note_off", {"channel": 0, "note": note, "velocity": 0}


def end(tick):
    return tick, "end_of_track", {}


class PlotTests(unittest.TestCase):
    def test_fraction_coordinates_cross_tempo_and_event_provenance(self):
        # Independent arithmetic: onset240=1/4; end1440=7/4; length3/2.
        report = report_for(
            [(0, "set_tempo", {"tempo": 500000}), (480, "set_tempo", {"tempo": 1000000}),
             (960, "set_tempo", {"tempo": 250000}), end(1440)],
            [on(240), off(1440), end(1440)],
        )
        figure = _build_figure(report)
        try:
            self.assertIsInstance(figure.canvas, FigureCanvasAgg)
            axes = figure.axes[0]
            self.assertEqual(len(axes.patches), 1)
            rect = axes.patches[0]
            self.assertEqual(rect.get_gid(), "note-t1-e0")
            self.assertAlmostEqual(rect.get_x(), 0.25)
            self.assertAlmostEqual(rect.get_width(), 1.5)
            self.assertAlmostEqual(rect.get_y() + rect.get_height() / 2, 60)
            self.assertGreater(rect.get_height(), 0)
            tempo = next(collection for collection in axes.collections if collection.get_gid() == "tempo-changes")
            self.assertEqual([segment[0][0] for segment in tempo.get_segments()], [0, 0.5, 1.5])
        finally:
            figure.clear()

    def test_authoritative_fraction_not_decimal_presentation(self):
        report = report_for([on(240), off(480), end(480)])
        report["notes"][0]["start_seconds"]["decimal"] = "999.000000000"
        report["notes"][0]["duration_seconds"]["decimal"] = "999.000000000"
        figure = _build_figure(report)
        try:
            rect = figure.axes[0].patches[0]
            self.assertEqual(rect.get_x(), 0.25)
            self.assertEqual(rect.get_width(), 0.25)
        finally:
            figure.clear()

    def test_zero_and_open_notes_are_only_start_markers(self):
        report = report_for([on(0, 64), off(0, 64), on(120), end(960)])
        figure = _build_figure(report)
        try:
            axes = figure.axes[0]
            self.assertEqual(len(axes.patches), 0)
            self.assertEqual(len(axes.lines), 0)
            markers = {artist.get_gid(): artist.get_offsets().tolist() for artist in axes.collections}
            self.assertEqual(markers, {"zero-t0-e0": [[0, 64]], "open-t0-e2": [[0.125, 60]]})
            labels = [text.get_text() for text in figure.legends[0].get_texts()]
            self.assertIn("Duração zero", labels)
            self.assertIn("Aberta · só início observado", labels)
        finally:
            figure.clear()

    def test_ambiguity_is_visibly_distinguished(self):
        report = report_for([on(0), on(120), off(240), off(360), end(480)])
        figure = _build_figure(report)
        try:
            self.assertEqual([rect.get_hatch() for rect in figure.axes[0].patches], ["//", "//"])
            self.assertIn("FIFO ambíguo", [text.get_text() for text in figure.legends[0].get_texts()])
        finally:
            figure.clear()

    def test_empty_file_has_real_empty_state_and_no_fabricated_notes(self):
        report = report_for([end(0)])
        figure = _build_figure(report)
        try:
            axes = figure.axes[0]
            self.assertFalse(axes.patches)
            self.assertFalse(axes.collections)
            self.assertTrue(any("Nenhuma mensagem note-on" in text.get_text() for text in axes.texts))
            self.assertLess(axes.get_xlim()[0], axes.get_xlim()[1])
        finally:
            figure.clear()
        result = render_plot(report)
        self.assertGreater(len(result["rolo.svg"]), 1000)
        self.assertTrue(result["rolo.png"].startswith(b"\x89PNG\r\n\x1a\n"))

    def test_render_is_reproducible_svg_text_and_fixed_png(self):
        report = report_for([(0, "track_name", {"name": "Demonstração"}), on(0), off(480), end(480)])
        before = deepcopy(report)
        result = render_plot(report)
        self.assertEqual(report, before)
        self.assertEqual(result, render_plot(report))
        self.assertEqual(set(result), {"rolo.svg", "rolo.png"})
        self.assertEqual(struct.unpack(">II", result["rolo.png"][16:24]), (1440, 960))
        svg = ElementTree.fromstring(result["rolo.svg"])
        ns = {"s": "http://www.w3.org/2000/svg"}
        self.assertTrue(svg.findall(".//s:text", ns))
        self.assertIsNotNone(svg.find(".//s:g[@id='note-t0-e1']", ns))
        self.assertFalse(svg.findall(".//s:image", ns))
        self.assertNotIn(b"<dc:date>", result["rolo.svg"])
        self.assertNotIn(b"@font-face", result["rolo.svg"])
        for element in svg.iter():
            for key, value in element.attrib.items():
                if key.endswith("href"):
                    self.assertTrue(value.startswith("#"), value)

    def test_control_unicode_and_math_labels_sanitized_in_view_only(self):
        name = "A\x00\n\t\u202e$5 <x> \U0001f6f8"
        report = report_for([(0, "track_name", {"name": name}), on(0), off(480), end(480)])
        before = deepcopy(report)
        stderr = StringIO()
        with redirect_stderr(stderr), warnings.catch_warnings(record=True) as caught:
            result = render_plot(report)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(caught, [])
        self.assertEqual(report, before)
        text = result["rolo.svg"].decode("utf-8")
        self.assertIn(r"A\u0000\u000a\u0009\u202e$5 &lt;x&gt;", text)
        self.assertNotIn("\u202e", text)
        self.assertNotIn("\x00", text)
        self.assertIn(r"\U0001f6f8", text)

    def test_long_name_is_abbreviated_only_in_graph(self):
        name = "Produto " * 200
        report = report_for([(0, "track_name", {"name": name}), on(0), off(10), end(10)])
        figure = _build_figure(report)
        try:
            label = figure.legends[0].get_texts()[0].get_text()
            self.assertTrue(label.endswith("…"))
            self.assertLess(len(label), 60)
            self.assertEqual(report["tracks"][0]["name"], name)
        finally:
            figure.clear()

    def test_plot_limits_reject_without_truncating_analysis(self):
        report = report_for([on(0), off(1), on(2, 61), off(3, 61), end(3)])
        self.assertEqual(report["summary"]["note_count"], 2)
        with self.assertRaises(MidiError) as raised:
            render_plot(report, Limits(max_plot_notes=1))
        self.assertEqual(raised.exception.code, "plot_note_limit")
        report = report_for([on(0), off(1), end(1)], [on(0, 70), off(1, 70), end(1)])
        with self.assertRaises(MidiError) as raised:
            render_plot(report, Limits(max_plot_tracks=1))
        self.assertEqual(raised.exception.code, "plot_track_limit")
        with self.assertRaises(MidiError) as raised:
            render_plot(report, Limits(max_report_bytes=100))
        self.assertEqual(raised.exception.code, "report_limit")
        with self.assertRaises(MidiError) as raised:
            render_plot(report, Limits(max_plot_notes=True))
        self.assertEqual(raised.exception.code, "invalid_limits")

    def test_no_gui_or_pyplot_is_needed(self):
        report = report_for([end(0)])
        with patch("matplotlib.pyplot.show", side_effect=AssertionError("GUI proibida")), patch("matplotlib.pyplot.figure", side_effect=AssertionError("pyplot proibido")):
            self.assertEqual(set(render_plot(report)), {"rolo.svg", "rolo.png"})

    def test_bad_report_or_renderer_failure_cannot_echo_input(self):
        report = report_for([on(0), off(480), end(480)])
        bad = deepcopy(report)
        bad["notes"][0]["duration_seconds"]["denominator"] = "0"
        with self.assertRaises(MidiError) as raised:
            render_plot(bad)
        self.assertEqual(raised.exception.code, "invalid_report")
        with patch.object(Figure, "savefig", side_effect=ValueError("nome-sensivel\n")):
            with self.assertRaises(MidiError) as raised:
                render_plot(report)
        self.assertEqual(raised.exception.code, "plot_failed")
        self.assertNotIn("nome-sensivel", str(raised.exception))
        stderr = StringIO()
        original = Figure.savefig

        def warn_then_save(figure, *args, **kwargs):
            warnings.warn("conteudo-sensivel", UserWarning)
            return original(figure, *args, **kwargs)

        with redirect_stderr(stderr), patch.object(Figure, "savefig", new=warn_then_save):
            with self.assertRaises(MidiError) as raised:
                render_plot(report)
        self.assertEqual(raised.exception.code, "plot_warning")
        self.assertEqual(stderr.getvalue(), "")
        self.assertNotIn("conteudo-sensivel", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
