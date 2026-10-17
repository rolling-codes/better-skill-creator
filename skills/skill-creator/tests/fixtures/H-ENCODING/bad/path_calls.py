from pathlib import Path as FilePath
import pathlib as paths

path = FilePath("notes.txt")
open("notes.txt", encoding=None)
path.read_text(encoding=None)
path.write_text("text", encoding=None)
path.open()
path.open("w", encoding=None)
FilePath.open(path)
paths.Path("notes.txt").open(mode="rt")


def read_it(path: FilePath):
    return path.read_text()
