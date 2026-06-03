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
        print(f"\n[STAGE 1] Format detected : {detected_format}")
        print(f"[STAGE 1] Normalized text : {normalized_text[:300]}{'...' if len(normalized_text) > 300 else ''}")

    intent = extract_intent(normalized_text)

    if debug:
        print("\n[STAGE 2] Intent extracted:")
        for k, v in intent.items():
            print(f"          {k}: {v}")

    candidates = prefilter(dataset, intent, normalized_text, top_n=16)

    if debug:
        print(f"\n[STAGE 3] Candidates after pre-filter: {len(candidates)}")
        for c in candidates[:5]:
            print(f"          {c['id']} — {c['principle_name']}")
        if len(candidates) > 5:
            print(f"          ... and {len(candidates) - 5} more")

    stage4 = rerank(
        normalized_text=normalized_text,
        candidates=candidates,
        dataset=dataset,
        top_n=top_n,
    )

    if debug:
        print(f"\n[STAGE 4] Model used      : {stage4['model']}")
        print(f"[STAGE 4] Candidates sent : {stage4['candidates_sent']}")
        print(f"[STAGE 4] Output tokens   : {stage4['usage'].get('completion_tokens')}")

    stage5 = extract(
        raw_kimi_output=stage4["raw_output"],
        dataset=dataset,
        top_n=top_n,
    )

    if debug:
        print(f"\n[STAGE 5] IDs extracted   : {stage5['ids_extracted']}")
        print(f"[STAGE 5] Principles found: {stage5['count']}")
        print()

    return stage5["principles"]
