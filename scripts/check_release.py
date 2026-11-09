"""Verifica conteúdo, recursos e hashes da distribuição construída."""
import base64
import csv
import hashlib
import io
from pathlib import Path, PurePosixPath
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
NAME = "mapa_midi"


def main():
    expected = {p.relative_to(ROOT / "src").as_posix(): p.read_bytes()
                for p in (ROOT / "src" / NAME).rglob("*")
                if p.is_file() and p.suffix in (".py", ".mid") and "__pycache__" not in p.parts}
    assert NAME + "/samples/exemplo.mid" in expected
    wheels = list((ROOT / "dist").glob("*.whl"))
    sdists = list((ROOT / "dist").glob("*.tar.gz"))
    assert len(wheels) == len(sdists) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)) and archive.testzip() is None
        assert {n for n in names if n.startswith(NAME + "/")} == set(expected)
        for name, data in expected.items():
            assert archive.read(name) == data, name
        info = f"{NAME}-{VERSION}.dist-info/"
        allowed = {"METADATA", "WHEEL", "entry_points.txt", "RECORD", "licenses/LICENSE"}
        assert all(n in expected or (n.startswith(info) and n[len(info):] in allowed) for n in names)
        rows = list(csv.reader(io.StringIO(archive.read(info + "RECORD").decode())))
        assert {r[0] for r in rows} == set(names) and len(rows) == len(names)
        for name, digest, size in rows:
            if name == info + "RECORD":
                assert digest == size == ""
                continue
            data = archive.read(name)
            calculated = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            assert digest == "sha256=" + calculated and size == str(len(data))
        assert "mapa-midi = mapa_midi.cli:main" in archive.read(info + "entry_points.txt").decode()
        metadata = archive.read(info + "METADATA").decode()
        assert "mido==1.3.3" in metadata and "matplotlib==3.11.2" in metadata
    with tarfile.open(sdists[0], "r:gz") as archive:
        prefix = f"{NAME}-{VERSION}/"
        paths = set()
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            assert not path.is_absolute() and ".." not in path.parts and member.isfile()
            assert member.name not in paths and member.name.startswith(prefix)
            paths.add(member.name)
            relative = member.name[len(prefix):]
            assert not any(v in path.parts for v in (".venv", "local", "__pycache__", ".env", ".git"))
            if relative != "PKG-INFO":
                source = ROOT / relative
                assert source.is_file() and archive.extractfile(member).read() == source.read_bytes(), relative
        for name in expected:
            assert prefix + "src/" + name in paths
        for name in ("README.md", "LICENSE", "CONTRACT.md", "pyproject.toml", "docs/INTEROPERABILIDADE.md", "docs/VALIDACAO.md", "examples/rolo.png"):
            assert prefix + name in paths
    print(f"Distribuição conferida: {len(expected)} arquivos de execução, exemplo MIDI, sdist e RECORD íntegros.")


if __name__ == "__main__":
    main()
