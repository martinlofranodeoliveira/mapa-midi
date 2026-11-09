"""Compare complete event facts to recorded MIDICSV output and manual oracles.

--offline verifies durable recordings only. --live invokes the independent tools
again in a new output directory, then validates those new bytes. Neither mode
sends MIDI to a device or claims the C consumer validates malformed files.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import csv
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mapa_midi.analysis import analyze
from mapa_midi.errors import MidiError
from mapa_midi.reader import read_bytes

VALID = ("exemplo", "edgecases", "shared", "metadata", "running")
PERMISSIVE = ("status-after-meta", "status-after-sysex")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_text(text: str) -> str:
    """MIDICSV's documented Latin-1 octal/escaped-backslash notation."""
    result = bytearray()
    index = 0
    while index < len(text):
        char = text[index]
        if char != "\\":
            result.extend(char.encode("latin1"))
            index += 1
        elif text[index:index + 2] == "\\\\":
            result.append(92)
            index += 2
        elif len(text[index + 1:index + 4]) == 3 and all(c in "01234567" for c in text[index + 1:index + 4]):
            result.append(int(text[index + 1:index + 4], 8))
            index += 4
        else:
            raise AssertionError("Unexpected MIDICSV string escape")
    return result.decode("utf-8", errors="strict")


def decoded_facts(data: bytes) -> tuple[dict, list[dict]]:
    rows = list(csv.reader(io.StringIO(data.decode("latin1")), skipinitialspace=True))
    header = rows[0]
    assert header[:3] == ["0", "0", "Header"]
    source = dict(zip(("format", "track_count", "ppqn"), map(int, header[3:])))
    events = []
    indices = {}
    ports = {}
    text_types = {
        "Title_t": ("track_name", "name"), "Text_t": ("text", "text"),
        "Copyright_t": ("copyright", "text"), "Marker_t": ("marker", "text"),
    }
    voices = {
        "Note_on_c": ("note_on", ("note", "velocity")),
        "Note_off_c": ("note_off", ("note", "velocity")),
        "Control_c": ("control_change", ("control", "value")),
        "Program_c": ("program_change", ("program",)),
        "Channel_aftertouch_c": ("aftertouch", ("value",)),
        "Poly_aftertouch_c": ("polytouch", ("note", "value")),
    }
    for row in rows[1:]:
        track, tick, kind = int(row[0]) - 1, int(row[1]), row[2]
        if kind in ("Start_track", "End_of_file"):
            continue
        fields = {}
        is_meta = True
        channel = None
        port = ports.get(track)
        if kind in text_types:
            event_type, field = text_types[kind]
            fields[field] = decode_text(row[3])
        elif kind in voices:
            event_type, keys = voices[kind]
            is_meta = False
            channel = int(row[3])
            fields = dict(zip(keys, map(int, row[4:])))
        elif kind == "Pitch_bend_c":
            event_type, is_meta, channel = "pitchwheel", False, int(row[3])
            fields["pitch"] = int(row[4]) - 8192
        elif kind == "End_track":
            event_type = "end_of_track"
        elif kind == "Tempo":
            event_type, fields = "set_tempo", {"tempo": int(row[3])}
        elif kind == "MIDI_port":
            event_type, fields = "midi_port", {"port": int(row[3])}
            ports[track] = int(row[3])
        elif kind == "Channel_prefix":
            event_type, fields = "channel_prefix", {"channel": int(row[3])}
        elif kind == "Sequence_number":
            event_type, fields = "sequence_number", {"number": int(row[3])}
        elif kind == "Time_signature":
            event_type = "time_signature"
            fields = dict(zip(("numerator", "denominator", "clocks_per_click", "notated_32nd_notes_per_beat"),
                              (int(row[3]), 2 ** int(row[4]), int(row[5]), int(row[6]))))
        elif kind == "Key_signature":
            # Fixture's known independent semantic expectation: -3 minor = Cm.
            assert row[3:] == ["-3", "minor"]
            event_type, fields = "key_signature", {"key": "Cm"}
        elif kind in ("System_exclusive", "System_exclusive_packet", "Sequencer_specific", "Unknown_meta_event"):
            if kind.startswith("System_exclusive"):
                event_type, is_meta = "sysex", False
                offset = 3
                fields["status_byte"] = 240 if kind == "System_exclusive" else 247
            elif kind == "Sequencer_specific":
                event_type, offset = "sequencer_specific", 3
            else:
                event_type, offset = "unknown_meta", 4
                fields["type_byte"] = int(row[3])
            size = int(row[offset])
            payload = bytes(map(int, row[offset + 1:]))
            assert len(payload) == size
            fields.update(payload_bytes=size, payload_sha256=digest(payload))
        else:
            raise AssertionError(f"Unaccounted independent event type: {kind}")
        index = indices.get(track, 0)
        indices[track] = index + 1
        events.append({"track": track, "index": index, "tick": tick,
                       "type": event_type, "is_meta": is_meta, "port": port,
                       "channel": channel, "fields": fields})
    assert rows[-1] == ["0", "0", "End_of_file"]
    return source, events


def rational(value: dict | None) -> Fraction | None:
    return None if value is None else Fraction(int(value["numerator"]), int(value["denominator"]))


def check_manual(name: str, report: dict, oracles: dict) -> None:
    wanted = oracles[name]
    for key, value in wanted["summary"].items():
        assert report["summary"][key] == value, (name, "summary", key)
    assert rational(report["summary"]["duration_seconds"]) == Fraction(wanted["duration_seconds"]), name
    actual_notes = []
    for note in report["notes"]:
        actual_notes.append({
            key: note[key] for key in ("track", "port", "channel", "note", "start_tick", "end_tick", "off_kind", "ambiguous_pairing", "start_event", "end_event", "velocity", "release_velocity")
        } | {"start_seconds": str(rational(note["start_seconds"])),
             "duration_seconds": None if note["duration_seconds"] is None else str(rational(note["duration_seconds"])),
             "end_seconds": None if note["end_seconds"] is None else str(rational(note["end_seconds"]))})
    assert actual_notes == wanted["notes"], (name, "manual note pairing/time oracle")
    if "tempo_map" in wanted:
        actual = [[segment["tick"], segment["tempo_us_per_quarter"], str(rational(segment["start_seconds"]))]
                  for segment in report["tempo_map"]]
        assert actual == wanted["tempo_map"], (name, "manual tempo oracle")


def check_recordings(directory: Path) -> dict:
    records = json.loads((directory / "records.json").read_text(encoding="utf-8"))
    oracles = json.loads((directory / "oracles.json").read_text(encoding="utf-8"))
    for name, expected in records["files"].items():
        data = (directory / name).read_bytes()
        assert len(data) == expected["size_bytes"] and digest(data) == expected["sha256"], (name, "recording checksum")
    results = {}
    for name in VALID:
        raw = (directory / f"{name}.mid").read_bytes()
        source, independent = decoded_facts((directory / f"{name}.decoded.csv").read_bytes())
        report = analyze(read_bytes(raw, charset="utf-8"))
        assert report["source"]["sha256"] == digest(raw)
        assert report["source"]["format"] == source["format"]
        assert report["source"]["ppqn"] == source["ppqn"]
        assert report["summary"]["track_count"] == source["track_count"]
        facts = [{key: value for key, value in event.items() if key != "seconds"} for event in report["events"]]
        assert facts == independent, (name, "complete independent event facts")
        check_manual(name, report, oracles)
        results[name] = {"events": len(facts), "notes": len(report["notes"]), "sha256": digest(raw)}
    # Deliberately show the consumer's permissiveness rather than treating it as
    # a validator: well-framed but nonconforming running status is accepted by C.
    for name in PERMISSIVE:
        _, decoded = decoded_facts((directory / f"{name}.decoded.csv").read_bytes())
        assert sum(event["type"] == "note_on" for event in decoded) == 2
        try:
            read_bytes((directory / f"{name}.mid").read_bytes())
        except MidiError as error:
            assert error.code == "invalid_running_status", (name, error.code)
        else:
            raise AssertionError("Nonconforming running status unexpectedly accepted")
    return {"valid_cases": results, "recorded_nonconforming_consumer_acceptance": list(PERMISSIVE)}


def live(tool_dir: Path, output: Path) -> dict:
    fixtures = ROOT / "fixtures" / "midicsv"
    check_recordings(fixtures)
    output.mkdir(parents=True, exist_ok=False)
    identities = {}
    for tool in ("csvmidi", "midicsv"):
        executable = (tool_dir / tool).resolve()
        banner = subprocess.run([str(executable), "-u"], capture_output=True, timeout=10, check=True)
        text = (banner.stdout + banner.stderr).decode("ascii", errors="replace")
        assert "Version 1.1 (January 2008)" in text
        identities[tool] = {"sha256": digest(executable.read_bytes()), "version": "1.1 (January 2008)"}
    records = json.loads((fixtures / "records.json").read_text())
    for name in VALID:
        source = fixtures / f"{name}.csv"
        midi = output / f"{name}.mid"
        args = [str((tool_dir / "csvmidi").resolve()), "-z"]
        if name != "running":
            args.append("-x")
        subprocess.run(args + [str(source), str(midi)], timeout=20, check=True, capture_output=True)
        subprocess.run([str((tool_dir / "midicsv").resolve()), str(midi), str(output / f"{name}.decoded.csv")],
                       timeout=20, check=True, capture_output=True)
        assert midi.read_bytes() == (fixtures / f"{name}.mid").read_bytes(), (name, "independent encoder reproducibility")
        assert (output / f"{name}.decoded.csv").read_bytes() == (fixtures / f"{name}.decoded.csv").read_bytes()
    for name in PERMISSIVE:
        (output / f"{name}.mid").write_bytes((fixtures / f"{name}.mid").read_bytes())
        subprocess.run([str((tool_dir / "midicsv").resolve()), str(output / f"{name}.mid"), str(output / f"{name}.decoded.csv")],
                       timeout=20, check=True, capture_output=True)
        assert (output / f"{name}.decoded.csv").read_bytes() == (fixtures / f"{name}.decoded.csv").read_bytes()
    # Check the newly emitted files with the same complete-facts and oracle gate.
    for name in records["files"]:
        if not (output / name).exists():
            (output / name).write_bytes((fixtures / name).read_bytes())
    (output / "records.json").write_bytes((fixtures / "records.json").read_bytes())
    result = check_recordings(output)
    (output / "live-run.json").write_text(json.dumps({
        "mode": "live_external_consumer",
        "actual_external_run_utc": datetime.now(timezone.utc).isoformat(),
        "executables": identities, "checked": result,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--tool-dir", type=Path)
    parser.add_argument("--saida", type=Path)
    args = parser.parse_args()
    if args.live:
        if args.tool_dir is None or args.saida is None:
            parser.error("--live requires --tool-dir and --saida (new directory)")
        result = live(args.tool_dir, args.saida)
        result["mode"] = "live_external_consumer"
    else:
        result = check_recordings(ROOT / "fixtures" / "midicsv")
        result["mode"] = "offline_recordings_only"
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("Run this evidence checker without Python -O")
    main()
