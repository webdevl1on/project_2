import json
from pathlib import Path

def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)
    