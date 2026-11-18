"""Load the repository's private .env without executing shell code."""
import os
import re
import shlex
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def load_env(path=None):
    path = Path(path) if path is not None else ENV_PATH
    if not path.exists():
        return
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        parts = shlex.split(line, comments=True)
        if parts[:1] == ["export"]:
            parts = parts[1:]
        if not parts:
            continue
        if len(parts) != 1 or "=" not in parts[0]:
            raise ValueError("Invalid .env assignment at line {}".format(number))
        key, value = parts[0].split("=", 1)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError("Invalid .env variable at line {}".format(number))
        os.environ.setdefault(key, value)
