"""Inspeção local de arquivos MIDI, sem reprodução ou dispositivos."""

from .errors import MidiError
from .models import Event, Limits, Snapshot, Track, validate_limits, validate_snapshot

__version__ = "1.0.0"

__all__ = ["Event", "Limits", "MidiError", "Snapshot", "Track", "validate_limits", "validate_snapshot", "read_bytes", "read_path"]


def read_bytes(data: bytes, limits: Limits = Limits(), charset: str = "latin1") -> Snapshot:
    from .reader import read_bytes as implementation
    return implementation(data, limits=limits, charset=charset)


def read_path(path, limits: Limits = Limits(), charset: str = "latin1") -> Snapshot:
    from .reader import read_path as implementation
    return implementation(path, limits=limits, charset=charset)
