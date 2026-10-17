# H-SWALLOW bad fixture: a handler whose only body is pass, with no reason.
import json


def load(path):
    try:
        return json.loads(open(path, encoding="utf-8").read())
    except (json.JSONDecodeError, OSError):
        pass  # swallows the error silently
