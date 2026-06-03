"""
Dataset Loader
"""

import json
import os

_dataset_cache = None

def load_dataset(path: str = None) -> list:
    global _dataset_cache
    if _dataset_cache is not None:
        return _dataset_cache

    if path is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base_dir, "Soloise_Intel_Master_v1.json")

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Dataset not found at: {path}\n"
            f"Place Soloise_Intel_Master_v1.json in the project root."
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
    pillars = {}
    for p in data:
        pillar = p.get("pillar", "Unknown")
        pillars[pillar] = pillars.get(pillar, 0) + 1
    return {"total_principles": len(data), "pillars": pillars}
