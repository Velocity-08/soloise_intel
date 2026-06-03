"""
Pipeline Orchestrator — token-minimized Kimi rerank
"""

from stages.dataset_loader import load_dataset
from stages.stage1_normalizer import normalize
from stages.stage2_intent import extract_intent
from stages.stage3_prefilter import prefilter
from stages.stage4_rerank import rerank
from stages.stage5_extractor import extract


def run_pipeline(raw_input: str, top_n: int = 5, debug: bool = False) -> list:
    dataset = load_dataset()

    stage1 = normalize(raw_input)
    normalized_text = stage1["normalized_text"]
    detected_format = stage1["detected_format"]

    if debug:
        print(f"\n[S1] Format: {detected_format}")
        print(f"[S1] Text:   {normalized_text[:300]}")

    intent = extract_intent(normalized_text)

    if debug:
        print("\n[S2] Intent:")
        for k, v in intent.items():
            print(f"     {k}: {v}")

    candidates = prefilter(dataset, intent, normalized_text, top_n=16)

    if debug:
        print(f"\n[S3] Candidates: {len(candidates)}")

    stage4 = rerank(
        normalized_text=normalized_text,
        candidates=candidates,
        dataset=dataset,
        top_n=top_n,
    )

    if debug:
        print(f"\n[S4] Model: {stage4['model']} | Tokens: {stage4['usage']}")

    stage5 = extract(
        raw_kimi_output=stage4["raw_output"],
        dataset=dataset,
        top_n=top_n,
    )

    if debug:
        print(f"\n[S5] Principles: {stage5['count']}")

    return stage5["principles"]
