# H-ENCODING bad fixture: text file ops with no encoding= must all be flagged.
from pathlib import Path


def read_it(p: Path) -> str:
    text = p.read_text()                 # flagged: .read_text() no encoding
    with open("notes.txt") as f:         # flagged: builtin open() text mode
        text += f.read()
    Path("out.txt").write_text(text)     # flagged: .write_text() no encoding
    return text
