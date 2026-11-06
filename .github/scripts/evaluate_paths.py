"""Classify a pull request's changed paths for the five-call smoke preview."""
import argparse
import subprocess

EXCLUDED_FILES = {
    b"README.md", b"CONTRIBUTING.md", b"CHANGELOG.md", b"SETUP.md",
    b"decisions.md", b"LICENSE", b".gitignore",
}


def needs_smoke(base, head):
    """Return whether the PR diff contains any path outside the exclusions."""
    changed = subprocess.check_output([
        "git", "diff", "--no-ext-diff", "--no-renames", "--name-only",
        "-z", f"{base}...{head}", "--",
    ]).split(b"\0")
    return any(path and path not in EXCLUDED_FILES and not path.startswith(b"docs/")
               for path in changed)


def main():
    """Print the smoke preview decision for the supplied base and head."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base")
    parser.add_argument("head")
    args = parser.parse_args()
    print("RUN" if needs_smoke(args.base, args.head) else "SKIP")


if __name__ == "__main__":
    main()
