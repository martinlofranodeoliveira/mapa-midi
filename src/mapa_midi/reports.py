"""Relatórios locais com proveniência, limites e apresentação explícita."""
from __future__ import annotations

from dataclasses import replace

import csv
import hashlib
import html
import io
import json
import zipfile

from .errors import MidiError
from .models import Limits, validate_limits


def _limit() -> None:
    raise MidiError("report_limit", "O relatório completo excede o limite de saída; nenhum arquivo foi publicado.")


def _bounded(data: bytes, maximum: int) -> bytes:
    if len(data) > maximum:
        _limit()
    return data


def json_bytes(value, maximum: int) -> bytes:
    buffer = io.BytesIO()
    for chunk in json.JSONEncoder(ensure_ascii=False, allow_nan=False, indent=2).iterencode(value):
        encoded = chunk.encode("utf-8")
        if buffer.tell() + len(encoded) + 1 > maximum:
            _limit()
        buffer.write(encoded)
    buffer.write(b"\n")
    return buffer.getvalue()


def _cell(value) -> str:
    if value is None:
        return ""
    if type(value) is bool:
        return "true" if value else "false"
    text = str(value)
    # Prefixo de apóstrofo é apresentação para planilhas, não altera o JSON.
    leading = text.lstrip("".join(chr(i) for i in range(33)))
    if leading.startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        text = "'" + text
    return text


def _csv_bytes(header, rows, maximum: int) -> bytes:
    buffer = io.BytesIO(b"\xef\xbb\xbf")
    buffer.seek(3)
    row_buffer = io.StringIO(newline="")
    writer = csv.writer(row_buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow([_cell(v) for v in header])
    first = row_buffer.getvalue().encode("utf-8")
    buffer.write(_bounded(first, maximum - 3))
    for row in rows:
        row_buffer.seek(0)
        row_buffer.truncate()
        writer.writerow([_cell(v) for v in row])
        encoded = row_buffer.getvalue().encode("utf-8")
        if buffer.tell() + len(encoded) > maximum:
            _limit()
        buffer.write(encoded)
    return _bounded(buffer.getvalue(), maximum)


def _time_cells(value):
    return [None, None, None] if value is None else [value[k] for k in ("numerator", "denominator", "decimal")]


def events_csv(report: dict, maximum: int) -> bytes:
    header = ["track", "track_name", "index", "tick", "type", "is_meta", "port", "channel",
              "seconds_numerator", "seconds_denominator", "seconds_decimal", "fields_json"]
    names = {track["index"]: track["name"] for track in report["tracks"]}
    return _csv_bytes(header, (
        [e["track"], names[e["track"]], e["index"], e["tick"], e["type"], e["is_meta"], e["port"], e["channel"]]
        + _time_cells(e["seconds"])
        + [json.dumps(e["fields"], ensure_ascii=False, allow_nan=False, sort_keys=True)]
        for e in report["events"]
    ), maximum)


def notes_csv(report: dict, maximum: int) -> bytes:
    fields = ["track", "port", "channel", "note", "note_name", "start_event", "end_event", "start_tick", "end_tick"]
    times = ["start_seconds", "end_seconds", "duration_seconds"]
    extra = ["velocity", "release_velocity", "off_kind", "ambiguous_pairing"]
    header = fields + [f"{name}_{part}" for name in times for part in ("numerator", "denominator", "decimal")] + extra
    return _csv_bytes(header, (
        [note[name] for name in fields]
        + [cell for name in times for cell in _time_cells(note[name])]
        + [note[name] for name in extra]
        for note in report["notes"]
    ), maximum)


def _md(value) -> str:
    if value is None:
        return "—"
    text = str(value)
    text = "".join(f"\\u{ord(c):04x}" if ord(c) < 32 or ord(c) == 127 else c for c in text)
    text = html.escape(text, quote=True)
    for char in "\\`*_{}[]()#+-.!|":
        text = text.replace(char, "\\" + char)
    return text


def _time_text(value) -> str:
    if value is None:
        return "aberta"
    return f"{value['numerator']}/{value['denominator']} s ({value['decimal']} s)"


def markdown_bytes(report: dict, maximum: int) -> bytes:
    output = io.BytesIO()

    def line(text=""):
        data = (text + "\n").encode("utf-8")
        if output.tell() + len(data) > maximum:
            _limit()
        output.write(data)

    def table(header, rows):
        line("| " + " | ".join(_md(v) for v in header) + " |")
        line("| " + " | ".join("---" for _ in header) + " |")
        for row in rows:
            line("| " + " | ".join(_md(v) for v in row) + " |")
        line()

    s = report["summary"]
    source = report["source"]
    line("# Mapa MIDI · relatório de mensagens")
    line()
    line(f"SHA-256 da captura: `{source['sha256']}`. Formato {source['format']}; {source['ppqn']} ticks por semínima; charset {source['charset']}.")
    line()
    line(f"{s['track_count']} trilhas · {s['event_count']} eventos · {s['note_count']} note-ons positivos · {s['completed_notes']} intervalos completos · {s['open_notes']} abertos.")
    line(f"Fim das trilhas: {_time_text(s['duration_seconds'])}; {s['duration_ticks']} ticks.")
    line()
    line("## Como ler")
    line()
    for text in report["scope"].values():
        line(_md(text))
    line()
    line("Os numeradores e denominadores são os tempos exatos; os decimais têm nove casas, arredondamento para o par. Trilhas, canais e índices começam em zero. Campos textuais são escapados nesta apresentação; o JSON preserva os dados.")
    line()
    line("## Trilhas e programas observados")
    line()
    table(["Trilha", "Nome", "Eventos", "Fim", "Canais", "Programas observados"], (
        [t["index"], t["name"], t["event_count"], _time_text(t["end_seconds"]), t["channels"], json.dumps(t["programs"], ensure_ascii=False)]
        for t in report["tracks"]
    ))
    line("## Mapa de andamento")
    line()
    table(["Tick", "µs por semínima", "Início", "Evento de origem", "Padrão"], (
        [t["tick"], t["tempo_us_per_quarter"], _time_text(t["start_seconds"]), t["source_event"], t["default"]]
        for t in report["tempo_map"]
    ))
    line("## Intervalos entre mensagens de nota")
    line()
    table(["Trilha", "Porta", "Canal", "Nota", "Eventos início/fim", "Ticks início/fim", "Início", "Fim", "Duração", "Velocidade", "Release", "Off", "Ambíguo"], (
        [n["track"], n["port"], n["channel"], n["note_name"], f"{n['start_event']}/{n['end_event']}", f"{n['start_tick']}/{n['end_tick']}",
         _time_text(n["start_seconds"]), _time_text(n["end_seconds"]), _time_text(n["duration_seconds"]), n["velocity"], n["release_velocity"], n["off_kind"], n["ambiguous_pairing"]]
        for n in report["notes"]
    ))
    line("## Diagnósticos")
    line()
    if report["diagnostics"]:
        keys = ["code", "track", "index", "tick", "port", "channel", "note"]
        table(keys, ([d[k] for k in keys] for d in report["diagnostics"]))
    else:
        line("Nenhum dos diagnósticos implementados foi observado. Isso não comprova conformidade MIDI completa.")
        line()
    line("## Todos os eventos")
    line()
    table(["Trilha", "Índice", "Tick", "Segundos", "Tipo", "Porta", "Canal", "Campos"], (
        [e["track"], e["index"], e["tick"], _time_text(e["seconds"]), e["type"], e["port"], e["channel"], json.dumps(e["fields"], ensure_ascii=False)]
        for e in report["events"]
    ))
    return output.getvalue()


def _archive(members: dict[str, bytes], report: dict, maximum: int) -> bytes:
    if sum(map(len, members.values())) > maximum:
        _limit()
    manifest = {"schema_version": 1, "application": "mapa-midi", "application_version": "1.0.0",
                "source_sha256": report["source"]["sha256"],
                "members": {name: {"size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                            for name, data in sorted(members.items())}}
    prepared = dict(members)
    prepared["manifesto.json"] = json_bytes(manifest, maximum)
    if sum(map(len, prepared.values())) > maximum:
        _limit()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(prepared.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            archive.writestr(info, data)
    return _bounded(stream.getvalue(), maximum)


def prepare_output(report: dict, output_format: str = "bundle", *, sample: bytes | None = None, limits: Limits = Limits()) -> bytes:
    """Recebe exclusivamente o relatório de analyze; prepara tudo antes de publicar."""
    validate_limits(limits)
    maximum = limits.max_report_bytes
    if output_format not in ("bundle", "json", "csv", "markdown"):
        raise MidiError("invalid_format", "Formato de saída não suportado.")
    if sample is not None and (output_format != "bundle" or type(sample) is not bytes
                               or hashlib.sha256(sample).hexdigest() != report["source"]["sha256"]):
        raise MidiError("invalid_sample", "O exemplo não corresponde à captura analisada.")
    if output_format == "json":
        return json_bytes(report, maximum)
    if output_format == "markdown":
        return markdown_bytes(report, maximum)
    members = {}
    remaining = maximum

    def add(name, data):
        nonlocal remaining
        if len(data) > remaining:
            _limit()
        members[name] = data
        remaining -= len(data)

    def budget():
        if remaining <= 0:
            _limit()
        return remaining

    add("eventos.csv", events_csv(report, budget()))
    add("notas.csv", notes_csv(report, budget()))
    if output_format == "bundle":
        from .plot import render_plot
        add("resumo.json", json_bytes(report, budget()))
        add("resumo.md", markdown_bytes(report, budget()))
        for name, data in render_plot(report, limits=replace(limits, max_report_bytes=budget())).items():
            add(name, data)
        if sample is not None:
            add("exemplo.mid", sample)
    return _archive(members, report, maximum)
