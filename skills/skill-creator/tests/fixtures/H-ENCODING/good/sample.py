# H-ENCODING good fixture: none of these should be flagged.
import os
from pathlib import Path


def read_it(p: Path) -> bytes:
    text = p.read_text(encoding="utf-8")            # ok: encoding given
    with open("notes.txt", encoding="utf-8") as f:  # ok: encoding given
        text += f.read()
    with open("blob.bin", "rb") as b:               # ok: binary mode
        data = b.read()
    fd = os.open("x", os.O_RDONLY)                   # ok: os.open is fd-level
    os.close(fd)
    Path("out.txt").write_text(text, encoding="utf-8")  # ok: encoding given
    return data
