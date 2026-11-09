"""Instala o wheel fora do checkout e verifica uma inspeção completa."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import venv
import xml.etree.ElementTree as ET
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", required=True)
    args = parser.parse_args()
    wheel = Path(args.wheel).resolve()
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONUTF8"] = env["PYTHONNOUSERSITE"] = "1"
    with tempfile.TemporaryDirectory(prefix="mapa-midi-installed-") as directory:
        root = Path(directory)
        venv.EnvBuilder(with_pip=True, symlinks=os.name != "nt").create(root / "venv")
        python = root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        command = root / "venv" / ("Scripts/mapa-midi.exe" if os.name == "nt" else "bin/mapa-midi")

        def run(arguments, code=0, entrypoint=False):
            result = subprocess.run([str(command if entrypoint else python), *arguments], cwd=root, env=env,
                                    capture_output=True, encoding="utf-8", timeout=240)
            assert result.returncode == code, (result.stdout, result.stderr)
            return result

        run(["-m", "pip", "--disable-pip-version-check", "install", str(wheel)])
        result = run(["-I", "-c", "import mapa_midi; print(mapa_midi.__file__)"])
        assert str(root / "venv") in result.stdout
        run(["exemplo", "--saida", "demo.zip"], entrypoint=True)
        with zipfile.ZipFile(root / "demo.zip") as archive:
            manifest = json.loads(archive.read("manifesto.json"))
            assert set(archive.namelist()) == set(manifest["members"]) | {"manifesto.json"}
            for name, record in manifest["members"].items():
                data = archive.read(name)
                assert len(data) == record["size_bytes"] and hashlib.sha256(data).hexdigest() == record["sha256"]
            source = archive.read("exemplo.mid")
            report = json.loads(archive.read("resumo.json"))
            assert hashlib.sha256(source).hexdigest() == report["source"]["sha256"]
            s = report["summary"]
            assert (s["track_count"], s["event_count"], s["note_count"], s["completed_notes"]) == (3, 42, 13, 13)
            assert s["duration_seconds"]["numerator"] == "41" and s["duration_seconds"]["denominator"] == "10"
            long_note = next(n for n in report["notes"] if n["track"] == 1 and n["note"] == 60)
            assert (long_note["duration_seconds"]["numerator"], long_note["duration_seconds"]["denominator"]) == ("7", "4")
            rows = list(csv.DictReader(io.StringIO(archive.read("notas.csv").decode("utf-8-sig"))))
            assert len(rows) == 13
            png = archive.read("rolo.png")
            assert png.startswith(b"\x89PNG\r\n\x1a\n") and struct.unpack(">II", png[16:24]) == (1440, 960)
            svg = ET.fromstring(archive.read("rolo.svg"))
            assert not list(svg.iter("{http://www.w3.org/2000/svg}image"))
            assert any(e.get("id") == "note-t1-e3" for e in svg.iter())
            (root / "exemplo.mid").write_bytes(source)
        run(["-I", "-m", "mapa_midi", "inspecionar", "exemplo.mid", "--charset", "utf-8", "--saida", "result.json", "--formato", "json"])
        original = (root / "result.json").read_bytes()
        assert json.loads(original) == report
        run(["-I", "-m", "mapa_midi", "inspecionar", "exemplo.mid", "--saida", "result.json", "--formato", "json"], code=2)
        assert (root / "result.json").read_bytes() == original and (root / "exemplo.mid").read_bytes() == source
        print("Wheel instalado fora do checkout: CLI, 13 intervalos, tempo 7/4 s, gráficos e saída preservada.")


if __name__ == "__main__":
    main()
