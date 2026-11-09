"""Oráculos de mensagens/ticks escritos à mão, sem relógio ou merge do Mido."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
import json
import unittest

from mapa_midi.analysis import _seconds, analyze
from mapa_midi.errors import MidiError
from mapa_midi.models import Event, Limits, Snapshot, Track


def make_snapshot(*rows, ppqn=480, format=None):
    """Rows are absolute ticks, type and fields; this is not a MIDI decoder."""
    tracks, events = [], []
    for track_index, row in enumerate(rows):
        port, name = None, None
        for index, (tick, kind, original_fields) in enumerate(row):
            fields = dict(original_fields)
            channel = fields.pop("channel", None) if kind in {"note_on", "note_off", "control_change", "program_change", "aftertouch", "pitchwheel", "polytouch"} else None
            event = Event(track_index, index, tick, kind, channel is None and kind != "sysex", port, channel, tuple(sorted(fields.items())))
            events.append(event)
            if kind == "midi_port":
                port = fields["port"]
            if kind == "track_name" and name is None:
                name = fields["name"]
        tracks.append(Track(track_index, name, row[-1][0], len(row)))
    return Snapshot("a" * 64, 100, (0 if len(rows) == 1 else 1) if format is None else format,
                    ppqn, "latin1", 0, tuple(tracks), tuple(events))


def on(tick, note=60, velocity=80, channel=0):
    return tick, "note_on", {"note": note, "velocity": velocity, "channel": channel}


def off(tick, note=60, velocity=32, channel=0):
    return tick, "note_off", {"note": note, "velocity": velocity, "channel": channel}


def eot(tick):
    return tick, "end_of_track", {}


def fraction(value):
    return Fraction(int(value["numerator"]), int(value["denominator"]))


class AnalysisTests(unittest.TestCase):
    def test_default_tempo_one_quarter(self):
        report = analyze(make_snapshot([on(0), off(480), eot(960)]))
        self.assertEqual(fraction(report["notes"][0]["duration_seconds"]), Fraction(1, 2))
        self.assertEqual(report["notes"][0]["note_name"], "C4")
        self.assertEqual(fraction(report["summary"]["duration_seconds"]), 1)
        self.assertEqual(report["tempo_map"], [{"tick": 0, "tempo_us_per_quarter": 500000,
                                               "start_seconds": {"numerator": "0", "denominator": "1", "decimal": "0.000000000"},
                                               "source_event": None, "default": True}])
        self.assertEqual(report["summary"]["tempo_changes"], 0)
        self.assertIn("C4=60", report["scope"]["pairing"])

    def test_tempo_crossings_and_exact_boundary(self):
        # 0..480: 1/2s; 480..960: 1s; 960..1440: 1/4s.
        report = analyze(make_snapshot(
            [(0, "set_tempo", {"tempo": 500000}), (480, "set_tempo", {"tempo": 1000000}),
             (960, "set_tempo", {"tempo": 250000}), eot(1440)],
            [on(240), off(1440), eot(1440)],
        ))
        note = report["notes"][0]
        self.assertEqual((fraction(note["start_seconds"]), fraction(note["end_seconds"]), fraction(note["duration_seconds"])),
                         (Fraction(1, 4), Fraction(7, 4), Fraction(3, 2)))
        self.assertEqual([fraction(segment["start_seconds"]) for segment in report["tempo_map"]],
                         [Fraction(0), Fraction(1, 2), Fraction(3, 2)])
        self.assertEqual(fraction(report["events"][1]["seconds"]), Fraction(1, 2))
        self.assertEqual(fraction(report["events"][2]["seconds"]), Fraction(3, 2))
        self.assertEqual(report["notes"][0]["start_event"], 0)
        self.assertEqual(report["notes"][0]["end_event"], 1)

    def test_last_tempo_at_same_tick_retains_every_source_event(self):
        report = analyze(make_snapshot(
            [(0, "set_tempo", {"tempo": 600000}), (0, "set_tempo", {"tempo": 900000}),
             (480, "set_tempo", {"tempo": 300000}), (480, "set_tempo", {"tempo": 1200000}), eot(960)],
            [on(0), off(960), eot(960)],
        ))
        self.assertEqual(len(report["events"]), 8)
        self.assertEqual(report["summary"]["tempo_changes"], 4)
        self.assertEqual(len(report["tempo_map"]), 2)
        self.assertFalse(report["tempo_map"][0]["default"])
        self.assertEqual([item["source_event"] for item in report["tempo_map"]],
                         [{"track": 0, "index": 1}, {"track": 0, "index": 3}])
        self.assertEqual(fraction(report["notes"][0]["end_seconds"]), Fraction(21, 10))

    def test_fifo_overlap_zero_velocity_and_zero_duration(self):
        report = analyze(make_snapshot([on(0), on(120, velocity=99), off(240, velocity=17),
                                        on(360, velocity=0), on(480, note=64), off(480, note=64), eot(480)]))
        first, second, zero = report["notes"]
        self.assertEqual([(n["start_event"], n["end_event"]) for n in report["notes"]], [(0, 2), (1, 3), (4, 5)])
        self.assertTrue(first["ambiguous_pairing"])
        self.assertTrue(second["ambiguous_pairing"])
        self.assertFalse(zero["ambiguous_pairing"])
        self.assertEqual(first["release_velocity"], 17)
        self.assertEqual(second["release_velocity"], 0)
        self.assertEqual(second["off_kind"], "note_on_zero")
        self.assertEqual(fraction(zero["duration_seconds"]), 0)
        self.assertEqual(report["summary"]["overlapping_note_ons"], 1)
        self.assertEqual(report["summary"]["completed_notes"], 3)

    def test_open_orphan_controllers_and_raw_programs(self):
        report = analyze(make_snapshot([
            (0, "program_change", {"program": 0, "channel": 4}), on(0, channel=4),
            (120, "control_change", {"control": 64, "value": 127, "channel": 4}),
            (240, "control_change", {"control": 66, "value": 127, "channel": 4}),
            (300, "control_change", {"control": 123, "value": 0, "channel": 4}),
            on(360, note=65, velocity=0, channel=4), eot(960),
        ]))
        note = report["notes"][0]
        for key in ("end_event", "end_tick", "end_seconds", "duration_seconds", "release_velocity", "off_kind"):
            self.assertIsNone(note[key], key)
        self.assertEqual(report["summary"]["open_notes"], 1)
        self.assertEqual(report["summary"]["unmatched_note_offs"], 1)
        self.assertEqual(report["summary"]["control_changes"], {"total": 3, "by_control": {"64": 1, "66": 1, "123": 1}})
        self.assertEqual(report["tracks"][0]["programs"], [{"tick": 0, "index": 0, "port": None, "channel": 4, "program": 0}])
        self.assertEqual(report["tracks"][0]["channels"], [4])
        self.assertEqual([(d["code"], d["index"]) for d in report["diagnostics"]], [("open_note", 1), ("unmatched_note_off", 5)])

    def test_track_port_and_channel_are_separate_pairing_domains(self):
        report = analyze(make_snapshot(
            [on(0), (10, "midi_port", {"port": 0}), off(20), on(30, note=65, channel=1), off(40, note=65, channel=2), eot(50)],
            [off(0), on(5, note=70), off(45, note=70), eot(50)],
        ))
        self.assertEqual(report["summary"]["note_count"], 3)
        self.assertEqual(report["summary"]["open_notes"], 2)
        self.assertEqual(report["summary"]["unmatched_note_offs"], 3)
        self.assertEqual(report["notes"][0]["port"], None)
        self.assertEqual(report["notes"][1]["port"], 0)
        self.assertEqual(report["events"][1]["port"], None)
        self.assertEqual(report["events"][2]["port"], 0)
        shared = [d for d in report["diagnostics"] if d["code"] == "shared_channel_across_tracks"]
        self.assertEqual(shared, [{"code": "shared_channel_across_tracks", "track": None, "index": None,
                                   "tick": None, "port": None, "channel": 0, "note": None}])
        self.assertEqual(report["summary"]["shared_channels"], 1)
        self.assertEqual(report["diagnostics"][0]["code"], "shared_channel_across_tracks")

    def test_shared_channels_count_voice_without_notes(self):
        report = analyze(make_snapshot(
            [(0, "program_change", {"channel": 3, "program": 9}), eot(0)],
            [(0, "pitchwheel", {"channel": 3, "pitch": -400}), eot(0)],
            [(0, "midi_port", {"port": 0}), (0, "aftertouch", {"channel": 3, "value": 5}), eot(0)],
        ))
        self.assertEqual(report["summary"]["shared_channels"], 1)
        self.assertEqual(report["summary"]["note_count"], 0)
        self.assertEqual(report["tracks"][1]["channels"], [3])

    def test_source_frozen_and_result_cannot_mutate_it(self):
        snapshot = make_snapshot([(0, "track_name", {"name": "x\x00\n$Nome$"}), on(0), off(480), eot(480)])
        before = deepcopy(snapshot)
        result = analyze(snapshot)
        self.assertEqual(snapshot, before)
        with self.assertRaises(FrozenInstanceError):
            snapshot.ppqn = 96
        result["events"][0]["fields"]["name"] = "changed"
        result["tracks"][0]["name"] = "changed"
        result["notes"][0]["start_tick"] = 123
        self.assertEqual(snapshot, before)
        fresh = analyze(snapshot)
        self.assertEqual(fresh["events"][0]["fields"]["name"], "x\x00\n$Nome$")
        self.assertEqual(json.loads(json.dumps(fresh, ensure_ascii=False)), fresh)
        self.assertEqual(analyze(snapshot), fresh)

    def test_exact_decimal_half_even_is_context_independent(self):
        self.assertEqual(_seconds(Fraction(1, 2_000_000_000))["decimal"], "0.000000000")
        self.assertEqual(_seconds(Fraction(3, 2_000_000_000))["decimal"], "0.000000002")
        self.assertEqual(_seconds(Fraction(5, 2_000_000_000))["decimal"], "0.000000002")
        self.assertEqual(_seconds(Fraction(1, 3))["decimal"], "0.333333333")
        self.assertEqual(_seconds(Fraction(9007199254740991, 3))["numerator"], "9007199254740991")
        self.assertEqual(_seconds(Fraction(9007199254740991, 3))["decimal"], "3002399751580330.333333333")

    def test_large_tick_and_non_binary_tempo_stay_exact(self):
        # Deliberately above the range where double stores every integer.
        tick = 9007199254740991
        report = analyze(make_snapshot([(0, "set_tempo", {"tempo": 500001}), on(0), off(tick), eot(tick)], ppqn=32767))
        self.assertEqual(fraction(report["notes"][0]["duration_seconds"]), Fraction(tick * 500001, 32767000000))

    def test_limits_reject_instead_of_truncating(self):
        snapshot = make_snapshot([on(0), on(1, note=61), eot(2)])
        with self.assertRaises(MidiError) as raised:
            analyze(snapshot, Limits(max_notes=1))
        self.assertEqual(raised.exception.code, "note_limit")
        with self.assertRaises(MidiError) as raised:
            analyze(snapshot, Limits(max_diagnostics=1))
        self.assertEqual(raised.exception.code, "diagnostic_limit")
        with self.assertRaises(MidiError) as raised:
            analyze(snapshot, Limits(max_events=True))
        self.assertEqual(raised.exception.code, "invalid_limits")

    def test_reject_mutable_or_forged_snapshot(self):
        snapshot = make_snapshot([on(0), off(1), eot(1)])
        for forged in (replace(snapshot, events=list(snapshot.events)), replace(snapshot, ppqn=True),
                       replace(snapshot, events=(replace(snapshot.events[0], tick=2), *snapshot.events[1:]))):
            with self.subTest(snapshot=forged), self.assertRaises(MidiError):
                analyze(forged)


if __name__ == "__main__":
    unittest.main()
