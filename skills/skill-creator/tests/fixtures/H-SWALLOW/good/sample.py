# H-SWALLOW good fixture: neither handler should be flagged.
import json
import sys


def load(path):
    try:
        return json.loads(open(path, encoding="utf-8").read())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: could not read {path}: {exc}", file=sys.stderr)  # reported, not swallowed
        return None


def cleanup(resource):
    try:
        resource.close()
    except OSError:
        pass  # reason: closing an already-closed resource is harmless
