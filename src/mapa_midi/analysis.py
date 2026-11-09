"""Fatos temporais exatos e intervalos entre mensagens de nota.

O pareamento é uma convenção de análise, não uma simulação de sintetizador.
Nenhum controlador altera os intervalos registrados aqui.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import Counter, defaultdict, deque
from fractions import Fraction

from .errors import MidiError
from .models import Limits, Snapshot, validate_snapshot


_PITCH_NAMES = ("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")


def _seconds(value: Fraction) -> dict[str, str]:
    """Round the decimal view with integers; retain authoritative rational facts."""
    scale = 1_000_000_000
    quotient, remainder = divmod(abs(value.numerator) * scale, value.denominator)
    twice = remainder * 2
    if twice > value.denominator or (twice == value.denominator and quotient % 2):
        quotient += 1
    whole, decimal = divmod(quotient, scale)
    sign = "-" if value < 0 and quotient else ""
    return {
        "numerator": str(value.numerator),
        "denominator": str(value.denominator),
        "decimal": f"{sign}{whole}.{decimal:09d}",
    }


def _note_name(note: int) -> str:
    return f"{_PITCH_NAMES[note % 12]}{note // 12 - 1}"


class _TimeMap:
    def __init__(self, snapshot: Snapshot):
        self.ppqn = snapshot.ppqn
        self.segments = [(0, 500_000, Fraction(0), None)]
        for event in snapshot.events:
            if event.type != "set_tempo":
                continue
            tick, tempo, seconds, _ = self.segments[-1]
            start = seconds + Fraction(
                (event.tick - tick) * tempo, self.ppqn * 1_000_000
            )
            segment = (event.tick, dict(event.fields)["tempo"], start, event)
            if event.tick == tick:
                self.segments[-1] = segment
            else:
                self.segments.append(segment)
        self.ticks = [segment[0] for segment in self.segments]

    def at(self, tick: int) -> Fraction:
        start_tick, tempo, seconds, _ = self.segments[bisect_right(self.ticks, tick) - 1]
        return seconds + Fraction((tick - start_tick) * tempo, self.ppqn * 1_000_000)

    def as_json(self) -> list[dict]:
        return [
            {
                "tick": tick,
                "tempo_us_per_quarter": tempo,
                "start_seconds": _seconds(seconds),
                "source_event": None if event is None else {"track": event.track, "index": event.index},
                "default": event is None,
            }
            for tick, tempo, seconds, event in self.segments
        ]


def analyze(snapshot: Snapshot, limits: Limits = Limits()) -> dict:
    """Analyze all captured events, or raise before returning a partial report."""
    validate_snapshot(snapshot, limits)
    clock = _TimeMap(snapshot)
    notes: list[dict] = []
    diagnostics: list[dict] = []
    pending: dict[tuple, deque] = defaultdict(deque)
    shared: dict[tuple, set] = defaultdict(set)
    channels: dict[int, set] = defaultdict(set)
    programs: dict[int, list] = defaultdict(list)
    controls = Counter()
    tempo_changes = 0

    def diagnose(code, *, event=None, port=None, channel=None, note=None):
        if len(diagnostics) >= limits.max_diagnostics:
            raise MidiError("diagnostic_limit", "Quantidade de diagnósticos excede o limite configurado.")
        diagnostics.append({
            "code": code,
            "track": None if event is None else event.track,
            "index": None if event is None else event.index,
            "tick": None if event is None else event.tick,
            "port": port if event is None else event.port,
            "channel": channel if event is None else event.channel,
            "note": note,
        })

    events = []
    for event in snapshot.events:
        fields = dict(event.fields)
        events.append({
            "track": event.track,
            "index": event.index,
            "tick": event.tick,
            "type": event.type,
            "is_meta": event.is_meta,
            "port": event.port,
            "channel": event.channel,
            "fields": {key: list(value) if isinstance(value, tuple) else value for key, value in event.fields},
            "seconds": _seconds(clock.at(event.tick)),
        })
        if event.channel is not None and not event.is_meta:
            shared[(event.port, event.channel)].add(event.track)
            channels[event.track].add(event.channel)
        if event.type == "program_change":
            programs[event.track].append({
                "tick": event.tick, "index": event.index, "port": event.port,
                "channel": event.channel, "program": fields["program"],
            })
        elif event.type == "control_change":
            controls[fields["control"]] += 1
        elif event.type == "set_tempo":
            tempo_changes += 1
        if event.type not in ("note_on", "note_off"):
            continue
        pitch = fields["note"]
        key = (event.track, event.port, event.channel, pitch)
        queue = pending[key]
        if event.type == "note_on" and fields["velocity"] > 0:
            if len(notes) >= limits.max_notes:
                raise MidiError("note_limit", "Quantidade de notas excede o limite configurado.")
            ambiguous = bool(queue)
            if ambiguous:
                diagnose("overlapping_note_on", event=event, note=pitch)
                # A singleton may still be unambiguous. All entries in a
                # larger queue were already marked at their first overlap.
                # This keeps a dense unison stream linear, rather than O(n²).
                queue[0]["ambiguous_pairing"] = True
            note = {
                "track": event.track, "port": event.port, "channel": event.channel,
                "note": pitch, "note_name": _note_name(pitch),
                "start_event": event.index, "end_event": None,
                "start_tick": event.tick, "end_tick": None,
                "start_seconds": _seconds(clock.at(event.tick)),
                "end_seconds": None, "duration_seconds": None,
                "velocity": fields["velocity"], "release_velocity": None,
                "off_kind": None, "ambiguous_pairing": ambiguous,
            }
            notes.append(note)
            queue.append(note)
        elif queue:
            note = queue.popleft()
            note.update({
                "end_event": event.index, "end_tick": event.tick,
                "end_seconds": _seconds(clock.at(event.tick)),
                "duration_seconds": _seconds(clock.at(event.tick) - clock.at(note["start_tick"])),
                "release_velocity": fields["velocity"],
                "off_kind": "note_on_zero" if event.type == "note_on" else "note_off",
            })
        else:
            diagnose("unmatched_note_off", event=event, note=pitch)

    # Open-note diagnostics point to their observed onset; no end is invented.
    track_offsets = []
    cursor = 0
    for track in snapshot.tracks:
        track_offsets.append(cursor)
        cursor += track.event_count
    for note in notes:
        if note["end_event"] is None:
            onset = snapshot.events[track_offsets[note["track"]] + note["start_event"]]
            diagnose("open_note", event=onset, note=note["note"])
    shared_groups = sorted(
        (key for key, tracks in shared.items() if len(tracks) > 1),
        key=lambda key: (-1 if key[0] is None else key[0], key[1]),
    )
    for port, channel in shared_groups:
        diagnose("shared_channel_across_tracks", port=port, channel=channel)
    diagnostics.sort(key=lambda item: tuple(-1 if item[key] is None else item[key] for key in ("tick", "track", "index")) + (item["code"],))
    counts = Counter(item["code"] for item in diagnostics)
    end_tick = max(track.end_tick for track in snapshot.tracks)
    return {
        "schema_version": 1,
        "application_version": "1.0.0",
        "source": {key: getattr(snapshot, key) for key in ("sha256", "size_bytes", "format", "ppqn", "charset", "header_extra_bytes")},
        "scope": {
            "timing": "Segundos racionais exatos; PPQN, andamento explícito ou padrão inicial de 500000 µs/semínima.",
            "pairing": "FIFO por trilha/porta/canal/nota; ordem simultânea entre trilhas não é uma ordem física. C4=60.",
            "not_audio": "Intervalos entre mensagens, não duração audível; pedal, sostenuto e modos de canal não prolongam nem encerram notas.",
            "channel_numbering": "zero_based", "opaque_payloads": "digest_only",
        },
        "tracks": [
            {
                "index": track.index, "name": track.name, "end_tick": track.end_tick,
                "event_count": track.event_count, "end_seconds": _seconds(clock.at(track.end_tick)),
                "channels": sorted(channels[track.index]), "programs": programs[track.index],
            }
            for track in snapshot.tracks
        ],
        "events": events,
        "tempo_map": clock.as_json(),
        "notes": notes,
        "diagnostics": diagnostics,
        "summary": {
            "duration_ticks": end_tick, "duration_seconds": _seconds(clock.at(end_tick)),
            "track_count": len(snapshot.tracks), "event_count": len(snapshot.events),
            "note_count": len(notes), "completed_notes": len(notes) - counts["open_note"],
            "open_notes": counts["open_note"], "unmatched_note_offs": counts["unmatched_note_off"],
            "overlapping_note_ons": counts["overlapping_note_on"], "shared_channels": len(shared_groups),
            "control_changes": {"total": sum(controls.values()), "by_control": {str(control): controls[control] for control in sorted(controls)}},
            "tempo_changes": tempo_changes,
        },
    }
