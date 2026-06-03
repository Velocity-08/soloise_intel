"""
STAGE 1 — Format Detection & Normalization
"""

import json
import csv
import io
import re

def detect_format(raw_input: str) -> str:
    stripped = raw_input.strip()

    if (stripped.startswith("{") and stripped.endswith("}")) or \
       (stripped.startswith("[") and stripped.endswith("]")):
        try:
            json.loads(stripped)
            return "json"
        except json.JSONDecodeError:
            pass

    lines = stripped.splitlines()
    if len(lines) >= 2:
        first_line = lines[0]
        comma_count = first_line.count(",")
        if comma_count >= 1:
            try:
                reader = csv.reader(io.StringIO(stripped))
                rows = list(reader)
                if len(rows) >= 2 and len(rows[0]) > 1:
                    return "csv"
            except Exception:
                pass

    return "text"

def flatten_json(obj, prefix="") -> list:
    parts = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            parts.extend(flatten_json(v, prefix=f"{k}"))
    elif isinstance(obj, list):
        for item in obj:
            parts.extend(flatten_json(item, prefix=prefix))
    else:
        val = str(obj).strip()
        if val and val.lower() not in ("none", "null", ""):
            if prefix:
                parts.append(f"{prefix}: {val}")
            else:
                parts.append(val)
    return parts

def normalize_json(raw: str) -> str:
    parsed = json.loads(raw.strip())
    parts = flatten_json(parsed)
    return ". ".join(parts)

def normalize_csv(raw: str) -> str:
    reader = csv.DictReader(io.StringIO(raw.strip()))
    sentences = []
    for row in reader:
        parts = [f"{k.strip()}: {v.strip()}" for k, v in row.items() if v.strip()]
        if parts:
            sentences.append(", ".join(parts))
    return ". ".join(sentences)

def normalize_text(raw: str) -> str:
    lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
    if len(lines) <= 5:
        return " ".join(lines)

    action_verbs = r"\b(increase|reduce|improve|fix|convert|grow|retain|onboard|signup|cancel|churn|engage|activate|launch|test|optimize|write|build|design)\b"
    key_lines = [lines[0]]
    if lines[-1] != lines[0]:
        key_lines.append(lines[-1])

    for line in lines[1:-1]:
        if "?" in line or re.search(action_verbs, line, re.IGNORECASE):
            key_lines.append(line)
        if len(key_lines) >= 7:
            break

    return " ".join(key_lines)

def normalize(raw_input: str) -> dict:
    if not raw_input or not raw_input.strip():
        raise ValueError("Empty input received.")

    fmt = detect_format(raw_input)

    if fmt == "json":
        text = normalize_json(raw_input)
    elif fmt == "csv":
        text = normalize_csv(raw_input)
    else:
        text = normalize_text(raw_input)

    text = re.sub(r"\s+", " ", text).strip()

    return {"normalized_text": text, "detected_format": fmt}
