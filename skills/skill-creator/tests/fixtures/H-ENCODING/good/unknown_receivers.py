from pathlib import Path


class Custom:
    def read_text(self):
        return "text"

    def write_text(self, text):
        return text

    def open(self):
        return self


custom = Custom()
custom.read_text()
custom.write_text("text")
custom.open()


def read_it(mode, other, **options):
    open("notes.txt", mode)
    open("notes.txt", mode=mode)
    open("notes.txt", "invalid")
    open("notes.txt", **options)
    Path("notes.txt").open(mode)
    Path("notes.txt").open("rb")
    Path.open(Path("notes.txt"), "rb")
    other.read_text()


def shadowed(open, Path):
    open("anything")
    Path("anything").read_text()


def rebound():
    Path = Custom
    Path().read_text()
