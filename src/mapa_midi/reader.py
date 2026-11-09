"""Captura limitada de SMF e decodificação central pelo Mido.

O preflight verifica apenas framing e limites. Os campos musicais vêm dos
objetos Mido, comparados com a cobertura de eventos da mesma captura de bytes.
"""

from dataclasses import dataclass
import hashlib
from io import BytesIO
import os
import stat
import struct

import mido

from .errors import MidiError
from .models import Event, Limits, Snapshot, Track, validate_limits, validate_snapshot


# Required observed prefixes for the fixed-field metadata supported here. SMF
# readers must tolerate extension tails; this is deliberately a minimum, not an
# equality test. In particular, Mido 1.3.3 fabricates defaults for empty port and
# sequence-number payloads, which cannot establish observed facts in this tool.
_META_MIN_PAYLOAD = {0x00: 2, 0x20: 1, 0x21: 1, 0x51: 3, 0x54: 5, 0x58: 4, 0x59: 2}


@dataclass(frozen=True, slots=True)
class _Frame:
    delta: int
    tick: int
    status: int
    meta_type: int | None = None
    payload_start: int = 0
    payload_length: int = 0


@dataclass(frozen=True, slots=True)
class _Framing:
    format: int
    ppqn: int
    header_extra_bytes: int
    tracks: tuple[tuple[_Frame, ...], ...]


def _bad_framing() -> None:
    raise MidiError("invalid_smf", "O framing do arquivo MIDI é inválido ou está incompleto.")


def _validate_charset(charset: str) -> None:
    if type(charset) is not str or charset not in ("latin1", "utf-8"):
        raise MidiError("invalid_charset", "Escolha explicitamente latin1 ou utf-8.")


def _vlq(data: bytes, position: int, end: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if position >= end:
            _bad_framing()
        byte = data[position]
        position += 1
        value = (value << 7) | (byte & 0x7F)
        if byte < 0x80:
            return value, position
    raise MidiError("vlq_limit", "Uma quantidade variável excede os quatro bytes do SMF.")


def _preflight(data: bytes, limits: Limits) -> _Framing:
    if len(data) < 14 or data[:4] != b"MThd":
        _bad_framing()
    header_length = int.from_bytes(data[4:8], "big")
    if not 6 <= header_length <= 1024 or 8 + header_length > len(data):
        _bad_framing()
    midi_format, track_count, division = struct.unpack_from(">HHH", data, 8)
    if midi_format not in (0, 1):
        raise MidiError("unsupported_format", "Somente arquivos MIDI dos tipos 0 e 1 são suportados.")
    if division == 0 or division & 0x8000:
        raise MidiError("unsupported_division", "A divisão precisa ser PPQN positiva; SMPTE não é suportado.")
    if track_count == 0 or (midi_format == 0 and track_count != 1):
        _bad_framing()
    if track_count > limits.max_tracks:
        raise MidiError("track_limit", "A quantidade de trilhas excede o limite configurado.")
    position = 8 + header_length
    tracks = []
    total_events = 0
    for track_index in range(track_count):
        if position + 8 > len(data) or data[position:position + 4] != b"MTrk":
            _bad_framing()
        chunk_length = int.from_bytes(data[position + 4:position + 8], "big")
        position += 8
        end = position + chunk_length
        if end > len(data):
            _bad_framing()
        frames = []
        tick = 0
        running_status = None
        ended = False
        while position < end:
            if ended:
                _bad_framing()
            delta, position = _vlq(data, position, end)
            tick += delta
            if tick > limits.max_ticks:
                raise MidiError("tick_limit", "A posição em ticks excede o limite configurado.")
            total_events += 1
            if total_events > limits.max_events:
                raise MidiError("event_limit", "A quantidade de eventos excede o limite configurado.")
            if position >= end:
                _bad_framing()
            first = data[position]
            if first < 0x80:
                if running_status is None:
                    raise MidiError("invalid_running_status", "Running status sem mensagem de canal anterior válida.")
                status = running_status
            else:
                status = first
                position += 1
            if 0x80 <= status <= 0xEF:
                running_status = status
                length = 1 if status >> 4 in (0xC, 0xD) else 2
                if position + length > end:
                    _bad_framing()
                # Mido remains responsible for channel data and field decoding.
                position += length
                frame = _Frame(delta, tick, status)
            elif status in (0xFF, 0xF0, 0xF7):
                # SMF 1.0: both meta and SysEx cancel running status. Mido
                # 1.3.3 permissively keeps it across meta; this guard does not.
                running_status = None
                meta_type = None
                if status == 0xFF:
                    if position >= end or data[position] >= 0x80:
                        _bad_framing()
                    meta_type = data[position]
                    position += 1
                payload_length, position = _vlq(data, position, end)
                if payload_length > limits.max_payload_bytes:
                    raise MidiError("payload_limit", "Um payload MIDI excede o limite configurado.")
                if position + payload_length > end:
                    _bad_framing()
                if payload_length < _META_MIN_PAYLOAD.get(meta_type, 0):
                    raise MidiError("incomplete_metadata", "Metadado MIDI fixo incompleto não é suportado neste perfil.")
                frame = _Frame(delta, tick, status, meta_type, position, payload_length)
                if meta_type == 0x2F:
                    if payload_length != 0 or position != end:
                        _bad_framing()
                    ended = True
                if meta_type == 0x51:
                    if midi_format == 1 and track_index != 0:
                        raise MidiError("tempo_track", "Andamento fora da trilha condutora não é suportado no tipo 1.")
                    if payload_length >= 3 and data[position:position + 3] == b"\x00\x00\x00":
                        raise MidiError("tempo_zero", "Andamento zero não é suportado.")
                position += payload_length
            else:
                raise MidiError("unsupported_status", "Mensagem de sistema fora do perfil SMF suportado.")
            frames.append(frame)
        if not ended:
            _bad_framing()
        tracks.append(tuple(frames))
    if position != len(data):
        _bad_framing()
    return _Framing(midi_format, division, header_length - 6, tuple(tracks))


_VOICE_STATUS_TYPES = {
    0x8: "note_off", 0x9: "note_on", 0xA: "polytouch", 0xB: "control_change",
    0xC: "program_change", 0xD: "aftertouch", 0xE: "pitchwheel",
}


def _coverage_error() -> None:
    raise MidiError("decoder_coverage", "O decoder não cobriu os eventos da captura de forma consistente.")


def read_bytes(data: bytes, limits: Limits = Limits(), charset: str = "latin1") -> Snapshot:
    """Lê somente bytes imutáveis, sem tocar portas ou regravar a entrada."""
    validate_limits(limits)
    _validate_charset(charset)
    if type(data) is not bytes:
        raise MidiError("invalid_bytes", "A entrada da API deve ser bytes imutáveis.")
    if len(data) > limits.max_file_bytes:
        raise MidiError("file_limit", "O arquivo excede o limite configurado.")
    framing = _preflight(data, limits)
    try:
        midi = mido.MidiFile(file=BytesIO(data), clip=False, charset=charset)
    except UnicodeError:
        raise MidiError("invalid_text_encoding", "Um texto MIDI não é válido no charset escolhido.") from None
    except Exception:
        raise MidiError("decode_error", "O Mido não conseguiu decodificar esta entrada no perfil suportado.") from None
    if (midi.type != framing.format or midi.ticks_per_beat != framing.ppqn
            or len(midi.tracks) != len(framing.tracks)):
        _coverage_error()
    events = []
    tracks = []
    for track_index, (messages, raw_frames) in enumerate(zip(midi.tracks, framing.tracks)):
        if len(messages) != len(raw_frames):
            _coverage_error()
        tick = 0
        port = None
        name = None
        for index, (message, frame) in enumerate(zip(messages, raw_frames)):
            if type(message.time) is not int or message.time != frame.delta:
                _coverage_error()
            tick += message.time
            if tick != frame.tick:
                _coverage_error()
            if frame.status < 0xF0:
                if (message.is_meta or message.type != _VOICE_STATUS_TYPES[frame.status >> 4]
                        or message.channel != frame.status & 0xF):
                    _coverage_error()
            elif frame.status in (0xF0, 0xF7):
                if message.is_meta or message.type != "sysex":
                    _coverage_error()
            elif not message.is_meta:
                _coverage_error()
            fields = message.dict()
            fields.pop("type")
            fields.pop("time")
            channel = fields.pop("channel") if not message.is_meta and "channel" in fields else None
            if message.type in ("sysex", "unknown_meta", "sequencer_specific"):
                # Hash the actual length-delimited payload, including framing
                # bytes Mido may normalize away inside SysEx (e.g. final F7).
                payload = memoryview(data)[frame.payload_start:frame.payload_start + frame.payload_length]
                fields = {"payload_bytes": len(payload), "payload_sha256": hashlib.sha256(payload).hexdigest()}
                if message.type == "sysex":
                    fields["status_byte"] = frame.status
                elif message.type == "unknown_meta":
                    fields["type_byte"] = message.type_byte
            normalized = {}
            for key, value in fields.items():
                if type(value) is float:
                    value = str(value)
                elif type(value) is list:
                    value = tuple(value)
                normalized[key] = value
            event = Event(track_index, index, tick, message.type, message.is_meta,
                          port, channel, tuple(sorted(normalized.items())))
            events.append(event)
            if message.type == "track_name" and name is None:
                name = message.name
            if message.type == "midi_port":
                port = message.port
        tracks.append(Track(track_index, name, tick, len(messages)))
    snapshot = Snapshot(hashlib.sha256(data).hexdigest(), len(data), framing.format,
                        framing.ppqn, charset, framing.header_extra_bytes,
                        tuple(tracks), tuple(events))
    validate_snapshot(snapshot, limits)
    return snapshot


def _stat_identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_path(path, limits: Limits = Limits(), charset: str = "latin1") -> Snapshot:
    """Captura uma vez um arquivo regular, com limite e fstat antes/depois.

    O hash identifica os bytes capturados; não promete que o caminho permanecerá
    associado ao mesmo arquivo depois da captura.
    """
    validate_limits(limits)
    _validate_charset(charset)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = None
    try:
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise MidiError("not_regular_file", "A entrada precisa ser um arquivo regular.")
        if before.st_size > limits.max_file_bytes:
            raise MidiError("file_limit", "O arquivo excede o limite configurado.")
        chunks = []
        captured = 0
        while captured <= limits.max_file_bytes:
            chunk = os.read(descriptor, min(65536, limits.max_file_bytes + 1 - captured))
            if not chunk:
                break
            captured += len(chunk)
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if captured > limits.max_file_bytes:
            raise MidiError("file_limit", "O arquivo excede o limite configurado.")
        if _stat_identity(before) != _stat_identity(after) or captured != before.st_size:
            raise MidiError("input_changed", "O arquivo mudou durante a captura; tente novamente com uma cópia estável.")
        data = b"".join(chunks)
    except MidiError:
        raise
    except (OSError, TypeError, ValueError):
        raise MidiError("input_read_error", "Não foi possível capturar o arquivo de entrada.") from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                raise MidiError("input_read_error", "Não foi possível concluir a captura do arquivo de entrada.") from None
    return read_bytes(data, limits=limits, charset=charset)
