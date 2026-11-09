"""Rolo de piano estático: apresentação, sem reprodução nem inferência de áudio."""

from __future__ import annotations

from fractions import Fraction
from io import BytesIO
import math
import re
import warnings

import matplotlib as mpl
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties, findfont
from matplotlib.ft2font import FT2Font
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

from .analysis import _note_name
from .errors import MidiError
from .models import Limits, validate_limits


_STYLE = {
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "text.usetex": False,
    "text.parse_math": False,
    "svg.fonttype": "none",
    "svg.hashsalt": "mapa-midi-1.0.0",
    "axes.unicode_minus": True,
    "savefig.facecolor": "white",
}
_DIGITS = re.compile(r"(?:0|[1-9][0-9]*)\Z")


def _invalid():
    raise MidiError("invalid_report", "O relatório possui dados inválidos para o gráfico.")


def _integer(value, maximum):
    return type(value) is int and 0 <= value <= maximum


def _fraction(value):
    if type(value) is not dict or set(value) != {"numerator", "denominator", "decimal"}:
        _invalid()
    numerator, denominator = value["numerator"], value["denominator"]
    if any(type(part) is not str or len(part) > 64 or not _DIGITS.fullmatch(part)
           for part in (numerator, denominator)) or denominator == "0" or type(value["decimal"]) is not str:
        _invalid()
    result = Fraction(int(numerator), int(denominator))
    if not math.isfinite(float(result)):
        _invalid()
    return result


def _valid_text(value):
    if type(value) is not str:
        return False
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        return False
    return True


def _plot_data(report, limits):
    validate_limits(limits)
    if type(report) is not dict or type(report.get("notes")) is not list or type(report.get("tracks")) is not list:
        _invalid()
    if len(report["notes"]) > limits.max_plot_notes:
        raise MidiError("plot_note_limit", "Quantidade de notas excede o limite do gráfico; exporte JSON, CSV ou Markdown.")
    if not 1 <= len(report["tracks"]) <= limits.max_tracks:
        _invalid()
    tracks = {}
    for index, track in enumerate(report["tracks"]):
        if type(track) is not dict or type(track.get("index")) is not int or track["index"] != index:
            _invalid()
        name = track.get("name")
        if name is not None and not _valid_text(name):
            _invalid()
        tracks[index] = name
    summary = report.get("summary")
    if type(summary) is not dict or not _integer(summary.get("duration_ticks"), limits.max_ticks):
        _invalid()
    duration = _fraction(summary.get("duration_seconds"))
    notes = []
    sources = set()
    for note in report["notes"]:
        if type(note) is not dict:
            _invalid()
        if (not _integer(note.get("track"), len(tracks) - 1)
                or not _integer(note.get("note"), 127)
                or not _integer(note.get("start_event"), limits.max_events - 1)
                or not _integer(note.get("start_tick"), summary["duration_ticks"])
                or not _integer(note.get("channel"), 15)
                or (note.get("port") is not None and not _integer(note["port"], 255))
                or not _integer(note.get("velocity"), 127) or note["velocity"] == 0
                or type(note.get("ambiguous_pairing")) is not bool):
            _invalid()
        source = note["track"], note["start_event"]
        if source in sources:
            _invalid()
        sources.add(source)
        start = _fraction(note.get("start_seconds"))
        if start > duration:
            _invalid()
        if note.get("end_event") is None:
            if any(note.get(key) is not None for key in ("end_tick", "end_seconds", "duration_seconds", "release_velocity", "off_kind")):
                _invalid()
            length = None
        else:
            if (not _integer(note["end_event"], limits.max_events - 1)
                    or note["end_event"] <= note["start_event"]
                    or not _integer(note.get("end_tick"), summary["duration_ticks"])
                    or note["end_tick"] < note["start_tick"]
                    or not _integer(note.get("release_velocity"), 127)
                    or note.get("off_kind") not in ("note_off", "note_on_zero")):
                _invalid()
            end, length = _fraction(note.get("end_seconds")), _fraction(note.get("duration_seconds"))
            if end < start or end > duration or length != end - start:
                _invalid()
        notes.append((note, start, length))
    active = sorted({note["track"] for note, _, _ in notes})
    if len(active) > limits.max_plot_tracks:
        raise MidiError("plot_track_limit", "Quantidade de trilhas com notas excede o limite do gráfico; exporte JSON, CSV ou Markdown.")
    tempo_map = report.get("tempo_map")
    if type(tempo_map) is not list or not 1 <= len(tempo_map) <= limits.max_events + 1:
        _invalid()
    tempos = []
    last_tick = -1
    for item in tempo_map:
        if (type(item) is not dict or not _integer(item.get("tick"), summary["duration_ticks"])
                or item["tick"] <= last_tick or (last_tick == -1 and item["tick"] != 0)
                or not _integer(item.get("tempo_us_per_quarter"), 16_777_215)
                or item["tempo_us_per_quarter"] == 0 or type(item.get("default")) is not bool):
            _invalid()
        start = _fraction(item.get("start_seconds"))
        if start > duration:
            _invalid()
        if not item["default"]:
            tempos.append(start)
        last_tick = item["tick"]
    return tracks, notes, active, duration, tempos


def _label(value, charmap, maximum=44):
    """Escape controls, invisible formatting and missing glyphs only in the view."""
    import unicodedata

    parts = []
    for character in value:
        codepoint = ord(character)
        category = unicodedata.category(character)
        if category.startswith("C") or codepoint not in charmap:
            parts.append(f"\\u{codepoint:04x}" if codepoint <= 0xFFFF else f"\\U{codepoint:08x}")
        else:
            parts.append(character)
    display = "".join(parts)
    return display if len(display) <= maximum else display[:maximum - 1] + "…"


def _build_figure(report, limits=Limits()):
    """Internal geometry boundary, kept inspectable for numerical verification."""
    tracks, notes, active, duration, tempos = _plot_data(report, limits)
    with mpl.rc_context(_STYLE):
        figure = Figure(figsize=(12, 8), dpi=120, facecolor="white")
        FigureCanvasAgg(figure)
        axes = figure.add_axes((0.085, 0.14, 0.66, 0.72))
        figure.suptitle("Mapa MIDI · intervalos entre mensagens de nota", x=0.085, y=0.96, ha="left", fontsize=15, weight="bold")
        figure.text(0.085, 0.912, "Não representa duração audível. Pedal, sostenuto e modos de canal não prolongam estes intervalos.", fontsize=9)
        figure.text(0.085, 0.045, "C4 = 60 · canais e trilhas numerados a partir de 0 · segundos racionais no JSON; gráfico em ponto flutuante.", fontsize=8, color="#41464c")
        palette = list(mpl.colormaps["tab20"].colors) + list(mpl.colormaps["tab20b"].colors)
        colors = {track: palette[index % len(palette)] for index, track in enumerate(active)}
        for note, start, length in notes:
            suffix = f"t{note['track']}-e{note['start_event']}"
            color = colors[note["track"]]
            x, y = float(start), note["note"]
            if length is None:
                artist = axes.scatter([x], [y], marker=">", s=34, c=[color], edgecolors="#20252b", linewidths=0.5, zorder=4)
                artist.set_gid("open-" + suffix)
            elif length == 0:
                artist = axes.scatter([x], [y], marker="|", s=90, c=[color], linewidths=1.8, zorder=4)
                artist.set_gid("zero-" + suffix)
            else:
                artist = Rectangle((x, y - 0.36), float(length), 0.72,
                                   facecolor=color, edgecolor="#26303a", linewidth=0.45,
                                   hatch="//" if note["ambiguous_pairing"] else None, zorder=3)
                artist.set_gid("note-" + suffix)
                axes.add_patch(artist)
        pitches = [note["note"] for note, _, _ in notes]
        lower, upper = (max(-0.5, min(pitches) - 4), min(127.5, max(pitches) + 4)) if pitches else (47.5, 72.5)
        axes.set_ylim(lower, upper)
        # Collection bounds rendering overhead even for dense tempo maps.
        if tempos:
            lines = LineCollection([[(float(second), lower), (float(second), upper)] for second in tempos],
                                   colors="#6d737a", linewidths=0.65, linestyles="dashed", alpha=0.5, zorder=2)
            lines.set_gid("tempo-changes")
            axes.add_collection(lines)
        right = float(duration)
        padding = max(right * 0.025, 0.025)
        axes.set_xlim(-padding, max(right + padding, 1 if right == 0 else padding))
        ticks = [pitch for pitch in range(0, 128) if lower <= pitch <= upper and pitch % 12 == 0]
        if pitches and len(ticks) < 2:
            ticks = sorted(set(ticks + [min(pitches), max(pitches)]))
        axes.set_yticks(ticks, [f"{pitch} · {_note_name(pitch)}" for pitch in ticks])
        axes.set_xlabel("Tempo (segundos)", labelpad=10)
        axes.set_ylabel("Nota MIDI · convenção C4 = 60", labelpad=12)
        axes.set_axisbelow(True)
        axes.grid(axis="both", color="#dce0e4", linewidth=0.6)
        axes.spines[["top", "right"]].set_visible(False)
        if not notes:
            axes.text(0.5, 0.52, "Nenhuma mensagem note-on com velocidade positiva.", transform=axes.transAxes,
                      ha="center", va="center", fontsize=11, wrap=True,
                      bbox={"facecolor": "white", "edgecolor": "#dce0e4", "pad": 12})
        charmap = FT2Font(findfont(FontProperties(family="DejaVu Sans"))).get_charmap()
        handles = [Patch(facecolor=colors[index], edgecolor="#26303a",
                         label=f"Trilha {index}" + (" · " + _label(tracks[index], charmap) if tracks[index] is not None else ""))
                   for index in active]
        if any(length == 0 for _, _, length in notes):
            handles.append(Line2D([], [], marker="|", linestyle="None", color="#26303a", markersize=9, label="Duração zero"))
        if any(length is None for _, _, length in notes):
            handles.append(Line2D([], [], marker=">", linestyle="None", color="#26303a", markersize=5, label="Aberta · só início observado"))
        if any(note["ambiguous_pairing"] for note, _, _ in notes):
            handles.append(Patch(facecolor="white", edgecolor="#26303a", hatch="//", label="FIFO ambíguo"))
        if tempos:
            handles.append(Line2D([], [], linestyle="dashed", color="#6d737a", linewidth=0.7, label=f"Andamento · {len(tempos)} mudanças"))
        if handles:
            figure.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.765, 0.87),
                          frameon=False, fontsize=7.5, title="Fontes observadas", title_fontsize=9,
                          handlelength=1.6, labelspacing=0.6, borderaxespad=0)
        return figure


class _BoundedBuffer(BytesIO):
    def __init__(self, maximum):
        super().__init__()
        self.maximum = maximum

    def write(self, data):
        if self.tell() + len(data) > self.maximum:
            raise MidiError("report_limit", "O gráfico excede o limite de bytes configurado.")
        return super().write(data)


def render_plot(report, limits=Limits()) -> dict[str, bytes]:
    """Render both bounded, local figures, without opening a GUI or output file."""
    figure = None
    try:
        with warnings.catch_warnings(record=True) as observed, mpl.rc_context(_STYLE):
            warnings.simplefilter("always")
            figure = _build_figure(report, limits)
            svg = _BoundedBuffer(limits.max_report_bytes)
            figure.savefig(svg, format="svg", metadata={"Date": None, "Creator": "Mapa MIDI 1.0.0"})
            svg_bytes = svg.getvalue()
            png = _BoundedBuffer(limits.max_report_bytes - len(svg_bytes))
            figure.savefig(png, format="png", metadata={"Software": "Mapa MIDI 1.0.0"})
            if observed:
                raise MidiError("plot_warning", "O renderizador emitiu um aviso; o gráfico não foi publicado.")
            return {"rolo.svg": svg_bytes, "rolo.png": png.getvalue()}
    except MidiError:
        raise
    except Exception:
        raise MidiError("plot_failed", "Não foi possível renderizar o gráfico local.") from None
    finally:
        if figure is not None:
            figure.clear()
