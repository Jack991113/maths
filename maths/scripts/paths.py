"""Portable locations; importing this module never creates or overwrites data."""
import os
import json
from pathlib import Path


def codex_home():
    installed = Path(__file__).resolve().parent.parent
    fallback = installed.parent.parent if installed.parent.name == "skills" else Path.home() / ".codex"
    return Path(os.environ.get("CODEX_HOME") or fallback).expanduser().resolve()


def data_root():
    if os.environ.get("MATHS_DATA_DIR"):
        return Path(os.environ["MATHS_DATA_DIR"]).expanduser().resolve()
    mapping = codex_home() / "maths-runtime" / "data-location.json"
    if mapping.exists():
        return Path(json.loads(mapping.read_text(encoding="utf-8"))["data_dir"]).expanduser().resolve()
    return (codex_home() / "maths-data").resolve()


if __name__ == "__main__":
    print(data_root())
