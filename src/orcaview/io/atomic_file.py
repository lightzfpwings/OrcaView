"""Replace a named file only after every output byte has been written."""

from pathlib import Path
from tempfile import NamedTemporaryFile


def write_bytes(path, data):
    destination = Path(path)
    stream = NamedTemporaryFile(dir=destination.parent, prefix=".orcaview-", delete=False)
    temp = Path(stream.name)
    try:
        with stream:
            stream.write(data)
        temp.replace(destination)
    finally:
        temp.unlink(missing_ok=True)
