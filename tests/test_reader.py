"""Fixtures binárias originais: framing, limites e captura do leitor."""

from dataclasses import fields, replace
import hashlib
from io import BytesIO
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import mido

from mapa_midi import Event, Limits, MidiError, Snapshot, Track, read_bytes, read_path
from mapa_midi.models import validate_limits, validate_snapshot
from mapa_midi import reader


def vlq(value):
    result = [value & 127]
    while value >> 7:
        value >>= 7
        result.append((value & 127) | 128)
    return bytes(reversed(result))


def ev(delta, message):
    return vlq(delta) + message


def meta(kind, payload=b"", delta=0):
    return ev(delta, bytes([255, kind]) + vlq(len(payload)) + payload)


EOT = meta(0x2F)


def smf(*tracks, midi_format=0, ppqn=480, extra=b""):
    return (b"MThd" + struct.pack(">IHHH", 6 + len(extra), midi_format, len(tracks), ppqn)
            + extra + b"".join(b"MTrk" + struct.pack(">I", len(t)) + t for t in tracks))


class ReaderTests(unittest.TestCase):
    def assert_error(self, code, function, *args, **kwargs):
        with self.assertRaises(MidiError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_original_bytes_hash_and_mido_fields(self):
        data = smf(ev(0, b"\x93\x3c\x64") + ev(480, b"\x83\x3c\x11") + EOT)
        snapshot = read_bytes(data)
        self.assertEqual(snapshot.sha256, hashlib.sha256(data).hexdigest())
        self.assertEqual(snapshot.size_bytes, len(data))
        self.assertEqual((snapshot.format, snapshot.ppqn, snapshot.charset), (0, 480, "latin1"))
        self.assertEqual(snapshot.tracks, (Track(0, None, 480, 3),))
        self.assertEqual([(e.index, e.tick, e.channel) for e in snapshot.events], [(0, 0, 3), (1, 480, 3), (2, 480, None)])
        self.assertEqual(dict(snapshot.events[1].fields), {"note": 60, "velocity": 17})

    def test_mido_is_central_decoder_of_same_snapshot(self):
        data = smf(ev(0, b"\x90\x3c\x64") + EOT)
        original = mido.MidiFile
        captures = []
        def decoding(*args, **kwargs):
            captures.append((kwargs["file"].getvalue(), kwargs["clip"], kwargs["charset"]))
            midi = original(*args, **kwargs)
            midi.tracks[0][0].velocity = 42
            return midi
        with patch.object(reader.mido, "MidiFile", side_effect=decoding):
            result = read_bytes(data)
        self.assertEqual(captures, [(data, False, "latin1")])
        self.assertEqual(dict(result.events[0].fields)["velocity"], 42)

    def test_decoder_coverage_requires_count_and_deltas(self):
        data = smf(ev(0, b"\x90\x3c\x64") + ev(7, b"\x80\x3c\x00") + EOT)
        for mutation in ("count", "delta", "type", "channel"):
            midi = mido.MidiFile(file=BytesIO(data))
            if mutation == "count":
                midi.tracks[0].pop()
            elif mutation == "delta":
                midi.tracks[0][1].time = 6
            elif mutation == "type":
                midi.tracks[0][0] = mido.Message("note_off", note=60, velocity=100)
            else:
                midi.tracks[0][0].channel = 1
            with self.subTest(mutation=mutation), patch.object(reader.mido, "MidiFile", return_value=midi):
                self.assert_error("decoder_coverage", read_bytes, data)

    def test_tracks_are_not_merged_and_keep_first_track_name(self):
        data = smf(meta(3, b"") + meta(3, b"segundo") + meta(0x51, b"\x07\xa1\x20") + EOT,
                   ev(0, b"\x91\x40\x7f") + ev(12, b"\x81\x40\x03") + EOT,
                   midi_format=1)
        snapshot = read_bytes(data)
        self.assertEqual(snapshot.tracks[0].name, "")
        self.assertEqual([dict(e.fields)["name"] for e in snapshot.events if e.type == "track_name"], ["", "segundo"])
        self.assertEqual([e.track for e in snapshot.events], [0, 0, 0, 0, 1, 1, 1])
        self.assertEqual(snapshot.events[-1].tick, 12)

    def test_port_context_is_local_and_changes_for_following_events(self):
        data = smf(meta(0x21, b"\x00") + ev(0, b"\x90\x3c\x01")
                   + meta(0x21, b"\x02") + ev(1, b"\x80\x3c\x00") + EOT,
                   ev(0, b"\x90\x3c\x01") + EOT, midi_format=1)
        snapshot = read_bytes(data)
        self.assertEqual([e.port for e in snapshot.events], [None, 0, 0, 2, 2, None, None])

    def test_valid_channel_running_status(self):
        snapshot = read_bytes(smf(ev(0, b"\x92\x3c\x7f") + ev(2, b"\x3e\x40")
                                  + ev(3, b"\x3e\x00") + EOT))
        self.assertEqual([(e.type, e.channel, e.tick) for e in snapshot.events[:3]],
                         [("note_on", 2, 0), ("note_on", 2, 2), ("note_on", 2, 5)])

    def test_smf_meta_and_sysex_cancel_running_status(self):
        for separator in (meta(1, b"x"), ev(0, b"\xf0\x02\x01\xf7"), ev(0, b"\xf7\x01\x01")):
            invalid = smf(ev(0, b"\x90\x3c\x01") + separator + ev(0, b"\x3e\x01") + EOT)
            with self.subTest(separator=separator), patch.object(reader.mido, "MidiFile") as decoder:
                self.assert_error("invalid_running_status", read_bytes, invalid)
                decoder.assert_not_called()
            # An explicit channel status starts a fresh valid sequence.
            read_bytes(smf(ev(0, b"\x90\x3c\x01") + separator + ev(0, b"\x90\x3e\x01") + EOT))

    def test_opaque_payloads_are_raw_digests_not_bytes(self):
        sysex = b"\x01\x02\xf7"
        unknown = b"\x00\xff\x80"
        proprietary = b"\x00\x81\xff"
        snapshot = read_bytes(smf(ev(0, b"\xf0" + vlq(len(sysex)) + sysex)
                                 + meta(0x75, unknown) + meta(0x7F, proprietary) + EOT))
        for event, payload in zip(snapshot.events, (sysex, unknown, proprietary)):
            f = dict(event.fields)
            self.assertEqual(f["payload_bytes"], len(payload))
            self.assertEqual(f["payload_sha256"], hashlib.sha256(payload).hexdigest())
            self.assertNotIn("data", f)
        self.assertEqual(dict(snapshot.events[0].fields)["status_byte"], 240)
        self.assertEqual(dict(snapshot.events[1].fields)["type_byte"], 0x75)

    def test_f7_origin_is_distinguished_from_f0(self):
        snapshot = read_bytes(smf(ev(0, b"\xf7\x02\x01\xf7") + EOT))
        self.assertEqual(dict(snapshot.events[0].fields)["status_byte"], 247)
        self.assertEqual(dict(snapshot.events[0].fields)["payload_bytes"], 2)

    def test_small_payload_limit_does_not_reject_derived_digest(self):
        snapshot = read_bytes(smf(ev(0, b"\xf0\x01\x01") + meta(0x75, b"x") + EOT),
                              limits=Limits(max_payload_bytes=1))
        self.assertEqual([dict(e.fields)["payload_bytes"] for e in snapshot.events[:2]], [1, 1])
        self.assertEqual(len(dict(snapshot.events[0].fields)["payload_sha256"]), 64)

    def test_encoding_is_explicit_and_controls_preserved(self):
        data = smf(meta(1, b"\xff\x00\r\n") + EOT)
        self.assertEqual(dict(read_bytes(data).events[0].fields)["text"], "ÿ\x00\r\n")
        self.assert_error("invalid_text_encoding", read_bytes, data, charset="utf-8")
        text = "ação\x00\x01\n"
        data = smf(meta(3, text.encode("utf-8")) + EOT)
        self.assertEqual(read_bytes(data, charset="utf-8").tracks[0].name, text)
        for charset in ("auto", "UTF-8", None, True):
            self.assert_error("invalid_charset", read_bytes, data, charset=charset)

    def test_smpte_offset_metadata_is_text_not_timing_division(self):
        snapshot = read_bytes(smf(meta(0x54, bytes([0x40, 0, 0, 0, 0])) + EOT))
        self.assertEqual(dict(snapshot.events[0].fields)["frame_rate"], "29.97")
        self.assertEqual(snapshot.ppqn, 480)

    def test_empty_port_cannot_invent_a_note_pairing_domain(self):
        # Original regression: Mido synthesizes port=0 for FF 21 00, separating
        # the positive onset (undeclared port) from its later explicit off.
        data = bytes.fromhex("4d546864000000060000000101e04d54726b0000001100903c4000ff21008360803c0000ff2f00")
        with patch.object(reader.mido, "MidiFile") as decoder:
            self.assert_error("incomplete_metadata", read_bytes, data)
            decoder.assert_not_called()

    def test_fixed_metadata_requires_observed_minimum_prefix(self):
        prefixes = {0x00: b"\x00\x01", 0x20: b"\x03", 0x21: b"\x04",
                    0x51: b"\x07\xa1\x20", 0x54: b"\x00\x00\x00\x00\x00",
                    0x58: b"\x04\x02\x18\x08", 0x59: b"\x00\x00"}
        for kind, prefix in prefixes.items():
            for length in range(len(prefix)):
                with self.subTest(kind=kind, length=length), patch.object(reader.mido, "MidiFile") as decoder:
                    self.assert_error("incomplete_metadata", read_bytes, smf(meta(kind, prefix[:length]) + EOT))
                    decoder.assert_not_called()

    def test_fixed_metadata_extensions_preserve_prefix_and_fresh_status(self):
        prefixes = {0x00: b"\x00\x01", 0x20: b"\x03", 0x21: b"\x04",
                    0x51: b"\x07\xa1\x20", 0x54: b"\x00\x00\x00\x00\x00",
                    0x58: b"\x04\x02\x18\x08", 0x59: b"\x00\x00"}
        for kind, prefix in prefixes.items():
            # Real SMF extension tails are ignored by the known Mido decoder;
            # they must not be mistaken for another event or a strict-length
            # validation failure. Channel status is explicit after every meta.
            with self.subTest(kind=kind):
                plain = read_bytes(smf(meta(kind, prefix) + ev(0, b"\x90\x3c\x40") + EOT))
                extended = read_bytes(smf(meta(kind, prefix + b"\xfe\x80\x00") + ev(0, b"\x90\x3c\x40") + EOT))
                self.assertEqual(extended.events, plain.events)
                self.assertNotEqual(extended.sha256, plain.sha256)
                self.assertEqual(extended.size_bytes, plain.size_bytes + 3)
                self.assertEqual(extended.events[1].channel, 0)
                self.assertEqual(extended.events[1].port, 4 if kind == 0x21 else None)

    def test_header_extra_is_bounded_counted_and_hashed(self):
        data = smf(EOT, extra=b"x" * 1018)
        snapshot = read_bytes(data)
        self.assertEqual(snapshot.header_extra_bytes, 1018)
        self.assertEqual(snapshot.sha256, hashlib.sha256(data).hexdigest())
        self.assert_error("invalid_smf", read_bytes, smf(EOT, extra=b"x" * 1019))

    def test_unsupported_profile_is_explicit(self):
        self.assert_error("unsupported_format", read_bytes, smf(EOT, midi_format=2))
        for division in (0, 0xE728):
            self.assert_error("unsupported_division", read_bytes, smf(EOT, ppqn=division))
        self.assert_error("tempo_zero", read_bytes, smf(meta(0x51, b"\x00\x00\x00") + EOT))
        self.assert_error("tempo_track", read_bytes, smf(EOT, meta(0x51, b"\x07\xa1\x20") + EOT, midi_format=1))
        for status in (b"\xf1\x00", b"\xf2\x00\x00", b"\xf8", b"\xfe"):
            self.assert_error("unsupported_status", read_bytes, smf(ev(0, status) + EOT))

    def test_chunks_eot_and_trailing_bytes_require_full_coverage(self):
        valid = smf(EOT)
        cases = [b"", valid[:-1], valid + b"ignored", smf(b""), smf(EOT + EOT),
                 smf(meta(0x2F, b"\x00")), smf(ev(0, b"\x90\x3c\x01")),
                 smf(EOT, EOT), valid.replace(b"MTrk", b"JUNK"),
                 valid[:18] + struct.pack(">I", 0xFFFFFFFF) + valid[22:],
                 valid[:10] + b"\x00\x00" + valid[12:]]
        for data in cases:
            with self.subTest(data=data), patch.object(reader.mido, "MidiFile") as decoder:
                self.assert_error("invalid_smf", read_bytes, data)
                decoder.assert_not_called()

    def test_vlq_limit_for_delta_and_payload_before_mido(self):
        for track in (b"\x81\x80\x80\x80\x00\xff\x2f\x00",
                      b"\x00\xff\x01\x80\x80\x80\x80\x00" + EOT):
            with self.subTest(track=track), patch.object(reader.mido, "MidiFile") as decoder:
                self.assert_error("vlq_limit", read_bytes, smf(track))
                decoder.assert_not_called()
        self.assert_error("invalid_smf", read_bytes, smf(b"\x80"))

    def test_predecoder_limits_block_allocation(self):
        cases = [(smf(EOT), Limits(max_file_bytes=2), "file_limit"),
                 (smf(EOT, EOT, midi_format=1), Limits(max_tracks=1), "track_limit"),
                 (smf(meta(1, b"x") + EOT), Limits(max_events=1), "event_limit"),
                 (smf(meta(1, b"xx") + EOT), Limits(max_payload_bytes=1), "payload_limit"),
                 (smf(ev(2, b"\x90\x3c\x01") + EOT), Limits(max_ticks=1), "tick_limit")]
        for data, limits, code in cases:
            with self.subTest(code=code), patch.object(reader.mido, "MidiFile") as decoder:
                self.assert_error(code, read_bytes, data, limits=limits)
                decoder.assert_not_called()

    def test_note_limit_covers_positive_onsets(self):
        data = smf(ev(0, b"\x90\x3c\x01") + ev(0, b"\x90\x3c\x00")
                   + ev(0, b"\x90\x40\x01") + EOT)
        self.assert_error("note_limit", read_bytes, data, limits=Limits(max_notes=1))

    def test_channel_data_rejection_uses_mido_without_leaking_contents(self):
        self.assert_error("decode_error", read_bytes, smf(ev(0, b"\x90\xff\x01") + EOT))
        with patch.object(reader.mido, "MidiFile", side_effect=ValueError("PRIVATE_SECRET")):
            error = self.assert_error("decode_error", read_bytes, smf(EOT))
        self.assertNotIn("PRIVATE_SECRET", str(error))

    def test_bytes_api_rejects_mutable_and_other_inputs(self):
        for data in (bytearray(smf(EOT)), memoryview(smf(EOT)), "midi", None):
            self.assert_error("invalid_bytes", read_bytes, data)

    def test_path_captures_readonly_regular_file_once(self):
        data = smf(EOT)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "original.mid"
            path.write_bytes(data)
            before = path.stat()
            actual_open = reader.os.open
            actual_fstat = reader.os.fstat
            with patch.object(reader.os, "open", wraps=actual_open) as opened, patch.object(reader.os, "fstat", wraps=actual_fstat) as stated:
                snapshot = read_path(path)
            after = path.stat()
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual((before.st_size, before.st_mtime_ns), (after.st_size, after.st_mtime_ns))
            self.assertEqual(snapshot.sha256, hashlib.sha256(data).hexdigest())
            self.assertEqual(opened.call_count, 1)
            flags = opened.call_args.args[1]
            self.assertFalse(flags & (os.O_WRONLY | os.O_RDWR))
            if hasattr(os, "O_NONBLOCK"):
                self.assertTrue(flags & os.O_NONBLOCK)
            self.assertEqual(stated.call_count, 2)
            self.assertEqual(stated.call_args_list[0].args, stated.call_args_list[1].args)

    def test_path_detects_mutation_during_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "changing.mid"
            path.write_bytes(smf(EOT))
            original_read = reader.os.read
            modified = False
            def changing_read(descriptor, size):
                nonlocal modified
                chunk = original_read(descriptor, size)
                if not modified:
                    with path.open("ab") as output:
                        output.write(b"new")
                    modified = True
                return chunk
            with patch.object(reader.os, "read", side_effect=changing_read):
                self.assert_error("input_changed", read_path, path)

    def test_path_read_is_bounded_even_when_file_grows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "growing.mid"
            data = smf(EOT)
            path.write_bytes(data)
            original_read = reader.os.read
            modified = False
            requests = []
            def growing_read(descriptor, size):
                nonlocal modified
                requests.append(size)
                if not modified:
                    with path.open("ab") as output:
                        output.write(b"x" * 100)
                    modified = True
                return original_read(descriptor, size)
            with patch.object(reader.os, "read", side_effect=growing_read):
                self.assert_error("file_limit", read_path, path, limits=Limits(max_file_bytes=len(data)))
            self.assertEqual(sum(requests), len(data) + 1)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO indisponível nesta plataforma")
    def test_fifo_is_rejected_without_waiting_for_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pipe"
            os.mkfifo(path)
            self.assert_error("not_regular_file", read_path, path)

    def test_directory_missing_file_and_path_errors_are_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assert_error("not_regular_file" if os.name != "nt" else "input_read_error", read_path, directory)
            private = Path(directory) / "private_customer_name.mid"
            error = self.assert_error("input_read_error", read_path, private)
            self.assertNotIn(str(private), str(error))
        with patch.object(reader.os, "open", side_effect=PermissionError("SECRET_PRIVATE_PATH")):
            error = self.assert_error("input_read_error", read_path, "ignored")
        self.assertNotIn("SECRET_PRIVATE_PATH", str(error))


class ModelValidationTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = read_bytes(smf(ev(0, b"\x90\x3c\x64") + ev(1, b"\x80\x3c\x00") + EOT))

    def reject(self, snapshot):
        with self.assertRaises(MidiError) as caught:
            validate_snapshot(snapshot)
        self.assertEqual(caught.exception.code, "invalid_snapshot")

    def test_limits_reject_every_bool_zero_float_and_mutable_shape(self):
        for field in fields(Limits):
            for value in (True, 0, -1, 1.0, "1", []):
                with self.subTest(field=field.name, value=value), self.assertRaises(MidiError):
                    validate_limits(replace(Limits(), **{field.name: value}))
        with self.assertRaises(MidiError):
            validate_limits(object())

    def test_forged_missing_dataclass_attributes_are_public_errors(self):
        self.reject(object.__new__(Snapshot))
        self.reject(replace(self.snapshot, events=(object.__new__(Event),) + self.snapshot.events[1:]))

    def test_snapshot_rejects_mutable_shapes_and_forged_scalars(self):
        for altered in (replace(self.snapshot, tracks=list(self.snapshot.tracks)),
                        replace(self.snapshot, events=list(self.snapshot.events)),
                        replace(self.snapshot, ppqn=True), replace(self.snapshot, sha256="G" * 64),
                        replace(self.snapshot, size_bytes=False), replace(self.snapshot, charset="auto"),
                        replace(self.snapshot, tracks=(replace(self.snapshot.tracks[0], name="\ud800"),))):
            with self.subTest(altered=type(altered)):
                self.reject(altered)

    def test_event_ranges_schema_and_provenance(self):
        first = self.snapshot.events[0]
        invalid = [replace(first, tick=True), replace(first, channel=16), replace(first, port=256),
                   replace(first, index=1), replace(first, track=1), replace(first, is_meta=1),
                   replace(first, fields=(("note", 128), ("velocity", 100))),
                   replace(first, fields=(("note", 60), ("velocity", True))),
                   replace(first, fields=(("velocity", 100), ("note", 60))),
                   replace(first, fields=(("note", 60), ("note", 60), ("velocity", 100))),
                   replace(first, fields=[["note", 60], ["velocity", 100]]),
                   replace(first, fields=(("note", 60), ("velocity", [100]))),
                   replace(first, fields=(("note", 60), ("time", 0), ("velocity", 100)))]
        for event in invalid:
            with self.subTest(event=event):
                self.reject(replace(self.snapshot, events=(event,) + self.snapshot.events[1:]))

    def test_eot_tick_order_counts_names_and_ports_are_validated(self):
        events = self.snapshot.events
        invalid = [replace(self.snapshot, events=events[:-1]),
                   replace(self.snapshot, events=(events[0], replace(events[1], tick=2), events[2])),
                   replace(self.snapshot, events=(events[0], replace(events[1], type="end_of_track", is_meta=True, channel=None, fields=()), events[2])),
                   replace(self.snapshot, tracks=(replace(self.snapshot.tracks[0], end_tick=2),)),
                   replace(self.snapshot, tracks=(replace(self.snapshot.tracks[0], event_count=4),)),
                   replace(self.snapshot, tracks=(replace(self.snapshot.tracks[0], name="invented"),)),
                   replace(self.snapshot, events=(replace(events[0], port=0),) + events[1:])]
        for snapshot in invalid:
            self.reject(snapshot)

    def test_meta_and_payload_typed_ranges(self):
        snapshot = read_bytes(smf(meta(0x51, b"\x07\xa1\x20") + meta(0x75, b"secret") + EOT))
        self.reject(replace(snapshot, events=(replace(snapshot.events[0], fields=(("tempo", 0),)),) + snapshot.events[1:]))
        invalid_payload = replace(snapshot.events[1], fields=(("payload_bytes", 6), ("payload_sha256", "not-a-digest"), ("type_byte", 117)))
        self.reject(replace(snapshot, events=(snapshot.events[0], invalid_payload, snapshot.events[2])))

    def test_forged_text_field_respects_payload_bound(self):
        snapshot = read_bytes(smf(meta(1, b"x") + EOT))
        altered = replace(snapshot, events=(replace(snapshot.events[0], fields=(("text", "x" * 65),)), snapshot.events[1]))
        with self.assertRaises(MidiError):
            validate_snapshot(altered, Limits(max_payload_bytes=64))


if __name__ == "__main__":
    unittest.main()
