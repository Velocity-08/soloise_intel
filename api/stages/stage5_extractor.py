"""
STAGE 5 — Principle Extractor, Field Filter & Diversity Re-ranker
"""

import re
import json

ALLOWED_FIELDS = [
    "id",
    "pillar",
    "pillar_code",
    "principle_name",
    "one_liner",
    "plain_english",
    "human_fear_or_desire",
    "when_to_use",
    "when_NOT_to_use",
    "saas_example",
    "exact_implementation",
    "example_copy",
    "power_level",
    "ethical_risk",
    "combines_well_with",
]

SIMILARITY_GROUPS = [
    {"P3-008", "P5-001", "P5-013"},
    {"P5-005", "P5-014", "P5-010", "P5-017"},
    {"P2-001", "P2-002", "P2-003", "P2-010"},
    {"P3-009", "P6-012"},
    {"P4-005", "P1-003"},
    {"P4-001", "P4-002", "P4-007"},
]

def extract_ids_from_kimi(raw_output: str, top_n: int) -> list:
    text = raw_output.strip()
    text = re.sub(r"```(?:json)?", "", text).strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and isinstance(parsed.get("ids"), list):
            ids = [str(i) for i in parsed["ids"] if re.match(r"P\d+-\d+", str(i))]
            if ids:
                return ids[:top_n * 2]
        if isinstance(parsed, list):
            ids = [str(i) for i in parsed if re.match(r"P\d+-\d+", str(i))]
            if ids:
                return ids[:top_n * 2]
    except (json.JSONDecodeError, ValueError):
        pass

    final_match = re.search(r'FINAL RANKING[:\s]*(\[.*?\])', text, re.DOTALL | re.IGNORECASE)
    if final_match:
        try:
            parsed = json.loads(final_match.group(1))
            ids = [str(i) for i in parsed if re.match(r'P\d+-\d+', str(i))]
            if ids:
                return ids[:top_n * 2]
        except Exception:
            pass

    tail = text[-1000:]
    tail_ids = _extract_ordered_ids(tail)
    if len(tail_ids) >= top_n:
        return tail_ids[:top_n * 2]

    full_ids = _extract_ordered_ids(text)
    return full_ids[:top_n * 2]

def _extract_ordered_ids(text: str) -> list:
    all_ids = re.findall(r'P\d+-\d+', text)
    seen = []
    for pid in all_ids:
        if pid not in seen:
            seen.append(pid)
    return seen

def apply_diversity_filter(ids: list, dataset: list, top_n: int) -> list:
    id_index = {p["id"]: p for p in dataset}

    selected = []
    selected_groups = set()
    pillar_count = {}

    for pid in ids:
        if len(selected) >= top_n:
            break
        if pid not in id_index:
            continue

        principle = id_index[pid]
        pillar_code = principle.get("pillar_code", "")

        group_blocked = False
        for g_idx, group in enumerate(SIMILARITY_GROUPS):
            if pid in group and g_idx in selected_groups:
                group_blocked = True
                break
        if group_blocked:
            continue

        if pillar_count.get(pillar_code, 0) >= 2:
            continue

        selected.append(pid)
        pillar_count[pillar_code] = pillar_count.get(pillar_code, 0) + 1

        for g_idx, group in enumerate(SIMILARITY_GROUPS):
            if pid in group:
                selected_groups.add(g_idx)

    return selected

def filter_fields(principle: dict) -> dict:
    return {field: principle[field] for field in ALLOWED_FIELDS if field in principle}

def extract(raw_kimi_output: str, dataset: list, top_n: int) -> dict:
    ids = extract_ids_from_kimi(raw_kimi_output, top_n)
    diverse_ids = apply_diversity_filter(ids, dataset, top_n)

    if len(diverse_ids) < top_n:
        for pid in ids:
            if len(diverse_ids) >= top_n:
                break
            if pid not in diverse_ids:
                diverse_ids.append(pid)

    id_index = {p["id"]: p for p in dataset}
    principles = []
    missing = []

    for pid in diverse_ids:
        if pid in id_index:
            principles.append(filter_fields(id_index[pid]))
        else:
            missing.append(pid)

    return {
        "principles": principles,
        "ids_extracted": diverse_ids,
        "count": len(principles),
    }
