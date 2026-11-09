"""Build the pinned independent C consumer outside the source tree (Linux/macOS)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import urllib.request

URL = "https://www.fourmilab.ch/webtools/midicsv/midicsv-1.1.tar.gz"
SHA256 = "7c5a749ab5c4ebac4bd7361df0af65892f380245be57c838e08ec6e4ac9870ef"
OLD = b"        char    *index();\n"


def build(destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=False)
    with urllib.request.urlopen(URL, timeout=60) as response:
        data = response.read(4 * 1024 * 1024 + 1)
    if len(data) > 4 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != SHA256:
        raise RuntimeError("Independent consumer archive size or SHA-256 mismatch")
    archive = destination / "midicsv-1.1.tar.gz"
    archive.write_bytes(data)
    # No extractall, links, devices, absolute paths or parent traversal.
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        if sum(member.size for member in members) > 16 * 1024 * 1024:
            raise RuntimeError("Unexpected consumer source size")
        for member in members:
            parts = Path(member.name).parts
            if not parts or parts[0] != "midicsv-1.1" or ".." in parts or Path(member.name).is_absolute():
                raise RuntimeError("Unexpected archive path")
            target = destination.joinpath(*parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as stream:
                    target.write_bytes(stream.read())
            else:
                raise RuntimeError("Unexpected archive member type")
    source_dir = destination / "midicsv-1.1"
    getopt = source_dir / "getopt.c"
    original = getopt.read_bytes()
    if original.count(OLD) != 1:
        raise RuntimeError("Portability patch anchor changed")
    # Unused pre-ANSI declaration conflicts with glibc's index prototype.
    # Remove that declaration only; no parsing or encoding logic is changed.
    patched = original.replace(OLD, b"")
    getopt.write_bytes(patched)
    process = subprocess.run(["make", "-C", str(source_dir), "all"], capture_output=True, timeout=120)
    (destination / "build.log").write_bytes(process.stdout + process.stderr)
    process.check_returncode()
    info = {
        "source_url": URL, "source_sha256": SHA256,
        "version": "1.1 (January 2008)",
        "portability_patch": {
            "file": "getopt.c", "change": "Remove unused char *index(); declaration only",
            "before_sha256": hashlib.sha256(original).hexdigest(),
            "after_sha256": hashlib.sha256(patched).hexdigest(),
        },
        "executables": {},
    }
    for name in ("midicsv", "csvmidi"):
        executable = source_dir / name
        version = subprocess.run([str(executable), "-u"], capture_output=True, timeout=10, check=True)
        if b"Version 1.1 (January 2008)" not in version.stdout + version.stderr:
            raise RuntimeError("Unexpected consumer identity")
        info["executables"][name] = {
            "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "size_bytes": executable.stat().st_size,
        }
    (destination / "build.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    return info


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destino", type=Path, required=True, help="New directory outside this repository")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    destination = args.destino.resolve()
    if destination == project or project in destination.parents:
        parser.error("Use a new directory outside this repository")
    build(destination)
    print(destination / "midicsv-1.1")


if __name__ == "__main__":
    main()
