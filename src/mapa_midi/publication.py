"""Publica uma saída pronta sem substituir qualquer entrada do diretório."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile

from .errors import MidiError


def publish_bytes(destination: str | os.PathLike, data: bytes) -> None:
    if type(data) is not bytes:
        raise MidiError("invalid_output", "Prepare a saída completa antes de publicar.")
    path = Path(destination)
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".mapa-midi-", suffix=".tmp", dir=path.parent)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # Exclusivo inclusive para symlink quebrado; não há check-then-replace.
        os.link(temporary, path, follow_symlinks=False)
    except FileExistsError:
        raise MidiError("output_exists", "O destino já existe. Escolha outro arquivo; nada foi sobrescrito.") from None
    except OSError:
        raise MidiError("output_failed", "Não foi possível criar a saída. Use uma pasta gravável que permita links locais.") from None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
