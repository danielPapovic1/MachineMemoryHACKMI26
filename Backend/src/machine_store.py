from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
MACHINES_FILE = DATA_DIR / "machines.json"

REQUIRED_MACHINE_FIELDS = {"machine_id", "name", "type", "zone", "x", "y"}


def load_machines() -> list[dict[str, Any]]:
    raw_data = json.loads(MACHINES_FILE.read_text(encoding="utf-8"))

    if not isinstance(raw_data, list):
        raise ValueError("machines.json must contain a list of machines")

    machines: list[dict[str, Any]] = []
    for index, record in enumerate(raw_data):
        if not isinstance(record, dict):
            raise ValueError(f"Machine record {index} must be an object")

        missing_fields = REQUIRED_MACHINE_FIELDS.difference(record)
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(f"Machine record {index} is missing: {missing}")

        machines.append(record)

    return machines
