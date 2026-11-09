"""Fatos imutáveis e validação de fronteiras da API pública."""

from dataclasses import dataclass, fields as dataclass_fields
import re

from .errors import MidiError

FieldValue = int | str | bool | None | tuple[int, ...]


@dataclass(frozen=True)
class Limits:
    max_file_bytes: int = 8 * 1024 * 1024
    max_tracks: int = 128
    max_events: int = 200000
    max_payload_bytes: int = 262144
    max_notes: int = 100000
    max_diagnostics: int = 100000
    max_ticks: int = 9007199254740991
    max_plot_notes: int = 20000
    max_plot_tracks: int = 32
    max_report_bytes: int = 64 * 1024 * 1024


@dataclass(frozen=True)
class Event:
    track: int
    index: int
    tick: int
    type: str
    is_meta: bool
    port: int | None
    channel: int | None
    fields: tuple[tuple[str, FieldValue], ...]


@dataclass(frozen=True)
class Track:
    index: int
    name: str | None
    end_tick: int
    event_count: int


@dataclass(frozen=True)
class Snapshot:
    sha256: str
    size_bytes: int
    format: int
    ppqn: int
    charset: str
    header_extra_bytes: int
    tracks: tuple[Track, ...]
    events: tuple[Event, ...]


def _invalid() -> None:
    raise MidiError("invalid_snapshot", "Os fatos MIDI possuem estrutura ou valores inválidos.")


def _integer(value: object, minimum: int, maximum: int | None = None) -> bool:
    return type(value) is int and value >= minimum and (maximum is None or value <= maximum)


def _text(value: object, max_chars: int | None = None) -> bool:
    if type(value) is not str or (max_chars is not None and len(value) > max_chars):
        return False
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        return False
    return True


def _digest(value: object) -> bool:
    return type(value) is str and len(value) == 64 and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def validate_limits(limits: Limits) -> None:
    if type(limits) is not Limits or any(
        not _integer(getattr(limits, field.name, None), 1)
        for field in dataclass_fields(Limits)
    ):
        raise MidiError("invalid_limits", "Os limites devem ser inteiros positivos.")


_VOICE_FIELDS = {
    "note_on": {"note", "velocity"},
    "note_off": {"note", "velocity"},
    "polytouch": {"note", "value"},
    "control_change": {"control", "value"},
    "program_change": {"program"},
    "aftertouch": {"value"},
    "pitchwheel": {"pitch"},
}
_TEXT_FIELDS = {
    "text": "text", "copyright": "text", "track_name": "name",
    "instrument_name": "name", "lyrics": "text", "marker": "text",
    "cue_marker": "text", "device_name": "name",
}
_META_FIELDS = {
    "sequence_number": {"number"}, "channel_prefix": {"channel"},
    "midi_port": {"port"}, "end_of_track": set(), "set_tempo": {"tempo"},
    "smpte_offset": {"frame_rate", "hours", "minutes", "seconds", "frames", "sub_frames"},
    "time_signature": {"numerator", "denominator", "clocks_per_click", "notated_32nd_notes_per_beat"},
    "key_signature": {"key"},
    "sequencer_specific": {"payload_bytes", "payload_sha256"},
    "unknown_meta": {"type_byte", "payload_bytes", "payload_sha256"},
}
_KEYS = {"Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#",
         "Abm", "Ebm", "Bbm", "Fm", "Cm", "Gm", "Dm", "Am", "Em", "Bm", "F#m", "C#m", "G#m", "D#m", "A#m"}


def _validate_event(event: Event, limits: Limits) -> dict:
    if type(event) is not Event or not all(_integer(getattr(event, name, None), 0)
                                          for name in ("track", "index", "tick")):
        _invalid()
    if event.tick > limits.max_ticks:
        raise MidiError("tick_limit", "A posição em ticks excede o limite configurado.")
    if not _text(event.type, 64) or type(event.is_meta) is not bool:
        _invalid()
    if event.port is not None and not _integer(event.port, 0, 255):
        _invalid()
    if event.channel is not None and not _integer(event.channel, 0, 15):
        _invalid()
    if type(event.fields) is not tuple or len(event.fields) > 16:
        _invalid()
    keys = []
    for pair in event.fields:
        if type(pair) is not tuple or len(pair) != 2 or not _text(pair[0], 64):
            _invalid()
        key, value = pair
        if key in {"time", "type"}:
            _invalid()
        if not (value is None or type(value) in (int, bool) or _text(value, max(64, limits.max_payload_bytes))
                or (type(value) is tuple and len(value) <= limits.max_payload_bytes
                    and all(type(v) is int for v in value))):
            _invalid()
        keys.append(key)
    if keys != sorted(set(keys)):
        _invalid()
    f = dict(event.fields)
    if event.type in _VOICE_FIELDS:
        if event.is_meta or event.channel is None or set(f) != _VOICE_FIELDS[event.type]:
            _invalid()
        for key, value in f.items():
            if not _integer(value, -8192 if key == "pitch" else 0, 8191 if key == "pitch" else 127):
                _invalid()
    elif event.type == "sysex":
        if event.is_meta or event.channel is not None or set(f) != {"payload_bytes", "payload_sha256", "status_byte"}:
            _invalid()
        if type(f["status_byte"]) is not int or f["status_byte"] not in (0xF0, 0xF7):
            _invalid()
    else:
        expected = {_TEXT_FIELDS[event.type]} if event.type in _TEXT_FIELDS else _META_FIELDS.get(event.type)
        if not event.is_meta or event.channel is not None or expected is None or set(f) != expected:
            _invalid()
        if event.type in _TEXT_FIELDS and not _text(f[_TEXT_FIELDS[event.type]], limits.max_payload_bytes):
            _invalid()
        for key, maximum in (("number", 65535), ("channel", 255), ("port", 255),
                             ("numerator", 255), ("clocks_per_click", 255),
                             ("notated_32nd_notes_per_beat", 255), ("hours", 31),
                             ("minutes", 59), ("seconds", 59), ("frames", 255),
                             ("sub_frames", 99), ("type_byte", 127)):
            if key in f and not _integer(f[key], 0, maximum):
                _invalid()
        if "tempo" in f and not _integer(f["tempo"], 1, 16777215):
            _invalid()
        if "denominator" in f:
            value = f["denominator"]
            if not _integer(value, 1, 2**255) or value & (value - 1):
                _invalid()
        if "frame_rate" in f and not ((type(f["frame_rate"]) is int and f["frame_rate"] in (24, 25, 30))
                                      or (type(f["frame_rate"]) is str and f["frame_rate"] == "29.97")):
            _invalid()
        if "key" in f and (type(f["key"]) is not str or f["key"] not in _KEYS):
            _invalid()
    if "payload_bytes" in f:
        if not _integer(f["payload_bytes"], 0) or not _digest(f["payload_sha256"]):
            _invalid()
        if f["payload_bytes"] > limits.max_payload_bytes:
            raise MidiError("payload_limit", "Um payload MIDI excede o limite configurado.")
    return f


def _validate_snapshot(snapshot: Snapshot, limits: Limits) -> None:
    if type(snapshot) is not Snapshot:
        _invalid()
    if not _digest(snapshot.sha256) or not _integer(snapshot.size_bytes, 1):
        _invalid()
    if snapshot.size_bytes > limits.max_file_bytes:
        raise MidiError("file_limit", "O arquivo excede o limite configurado.")
    if type(snapshot.format) is not int or snapshot.format not in (0, 1) or not _integer(snapshot.ppqn, 1, 32767):
        _invalid()
    if type(snapshot.charset) is not str or snapshot.charset not in ("latin1", "utf-8"):
        _invalid()
    if not _integer(snapshot.header_extra_bytes, 0, 1018):
        _invalid()
    if type(snapshot.tracks) is not tuple or type(snapshot.events) is not tuple or not snapshot.tracks:
        _invalid()
    if len(snapshot.tracks) > limits.max_tracks:
        raise MidiError("track_limit", "A quantidade de trilhas excede o limite configurado.")
    if len(snapshot.events) > limits.max_events:
        raise MidiError("event_limit", "A quantidade de eventos excede o limite configurado.")
    if snapshot.format == 0 and len(snapshot.tracks) != 1:
        _invalid()
    for index, track in enumerate(snapshot.tracks):
        if type(track) is not Track or type(track.index) is not int or track.index != index:
            _invalid()
        if (track.name is not None and not _text(track.name, limits.max_payload_bytes)) or not _integer(track.end_tick, 0, limits.max_ticks) or not _integer(track.event_count, 1):
            _invalid()
    cursor = 0
    note_count = 0
    for track in snapshot.tracks:
        last_tick = 0
        name = None
        port = None
        for index in range(track.event_count):
            if cursor >= len(snapshot.events):
                _invalid()
            event = snapshot.events[cursor]
            f = _validate_event(event, limits)
            if event.track != track.index or event.index != index or event.tick < last_tick or event.port != port:
                _invalid()
            if (event.type == "end_of_track") != (index == track.event_count - 1):
                _invalid()
            if event.type == "track_name" and name is None:
                name = f["name"]
            if event.type == "midi_port":
                port = f["port"]
            if snapshot.format == 1 and track.index != 0 and event.type == "set_tempo":
                raise MidiError("tempo_track", "Andamento fora da trilha condutora não é suportado no tipo 1.")
            if event.type == "note_on" and f["velocity"] > 0:
                note_count += 1
                if note_count > limits.max_notes:
                    raise MidiError("note_limit", "A quantidade de notas excede o limite configurado.")
            last_tick = event.tick
            cursor += 1
        if track.end_tick != last_tick or track.name != name:
            _invalid()
    if cursor != len(snapshot.events):
        _invalid()


def validate_snapshot(snapshot: Snapshot, limits: Limits = Limits()) -> None:
    """Valida inclusive objetos construídos ou alterados fora do leitor."""
    validate_limits(limits)
    try:
        _validate_snapshot(snapshot, limits)
    except (AttributeError, TypeError, KeyError, ValueError):
        # Frozen dataclasses can still be forged via object.__new__/__setattr__.
        # Those shapes must produce the same public error, not a Python crash.
        _invalid()
