"""
Dataset Loader — loads Soloise_Intel_Master_v1.json once into memory.
On Vercel the JSON must be bundled inside api/ (committed to repo).
"""

import json
import os

_dataset_cache = None


def load_dataset(path: str = None) -> list:
    global _dataset_cache
    if _dataset_cache is not None:
        return _dataset_cache

    if path is None:
        # Look for the JSON next to this file (api/stages/) or one level up (api/)
        here = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(here, "Soloise_Intel_Master_v1.json"),
            os.path.join(here, "..", "Soloise_Intel_Master_v1.json"),
            os.path.join(here, "..", "..", "Soloise_Intel_Master_v1.json"),
        ]
        for p in candidates:
            if os.path.exists(p):
                path = p
                break

    if not path or not os.path.exists(path):
        raise FileNotFoundError(
            "Dataset not found. Place Soloise_Intel_Master_v1.json inside api/ before deploying."
        )

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    principles = raw.get("dataset", [])
    if not principles:
        raise ValueError("Dataset loaded but 'dataset' key is empty.")

    _dataset_cache = principles
    return _dataset_cache


def get_dataset_stats() -> dict:
    data = load_dataset()
    pillars: dict = {}
    for p in data:
        pillar = p.get("pillar", "Unknown")
        pillars[pillar] = pillars.get(pillar, 0) + 1
    return {"total_principles": len(data), "pillars": pillars}
