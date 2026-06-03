"""
STAGE 3 — Keyword Pre-filter
"""

import re

STAGE_TO_FUNNEL = {
    "acquisition": ["awareness", "consideration"],
    "activation": ["activation"],
    "monetization": ["conversion"],
    "retention": ["retention"],
    "expansion": ["expansion"],
    "resurrection": ["winback"],
}

STAGE_KEYWORDS = {
    "acquisition": ["cold traffic", "ad copy", "hero", "first visit", "landing page"],
    "activation": ["onboarding", "activation", "first value", "aha moment", "day 1"],
    "monetization": ["upgrade", "free to paid", "trial to paid", "pricing", "checkout", "freemium", "upgrade prompt", "willingness to pay", "paid plan"],
    "retention": ["churn", "retention", "renewal", "cancel", "win back", "loyalty"],
    "expansion": ["upsell", "expansion", "seat", "power user", "account growth"],
    "resurrection": ["win back", "reactivate", "lapsed", "churned", "re-engage"],
}

EMOTION_KEYWORDS = {
    "trust": ["trust", "credibility", "social proof", "authority", "verification"],
    "uncertainty": ["risk reversal", "guarantee", "clarity", "reassurance", "objection"],
    "effort": ["friction", "cognitive load", "form", "simplification", "ease"],
    "loss": ["loss aversion", "scarcity", "urgency", "fomo", "cost of inaction"],
    "identity": ["identity", "status", "community", "belonging", "social"],
    "inertia": ["commitment", "trigger", "nudge", "upgrade prompt", "activation"],
    "overwhelm": ["cognitive load", "simplification", "clarity", "focus", "hierarchy"],
    "anxiety": ["risk reversal", "trust", "security", "guarantee", "transparency"],
}

def _overlap_score(query_values: list, principle_values: list) -> int:
    if not query_values or not principle_values:
        return 0
    q_lower = [v.lower() for v in query_values]
    p_lower = [v.lower() for v in principle_values]
    return sum(1 for q in q_lower if any(q in p or p in q for p in p_lower))

def _keyword_text_match(normalized_text: str, principle: dict) -> int:
    tags = principle.get("metadata_tags", {})
    use_case_keywords = tags.get("use_case_keywords", [])
    text_lower = normalized_text.lower()
    score = 0
    for kw in use_case_keywords:
        if re.search(r"\b" + re.escape(kw.lower()) + r"\b", text_lower):
            score += 2
    return score

def _business_stage_score(principle: dict, business_stages: list) -> int:
    if not business_stages:
        return 0

    tags = principle.get("metadata_tags", {})
    p_funnel = [v.lower() for v in tags.get("funnel_stages", [])]
    p_keywords = [v.lower() for v in tags.get("use_case_keywords", [])]

    score = 0
    for i, stage in enumerate(business_stages[:3]):
        weight = 4 if i == 0 else 2

        target_funnels = STAGE_TO_FUNNEL.get(stage, [])
        for tf in target_funnels:
            if any(tf in pf for pf in p_funnel):
                score += weight

        stage_kws = STAGE_KEYWORDS.get(stage, [])
        for skw in stage_kws:
            if any(skw in pk for pk in p_keywords):
                score += weight

    return score

def _emotional_mechanism_score(principle: dict, emotional_mechs: list) -> int:
    if not emotional_mechs:
        return 0

    tags = principle.get("metadata_tags", {})
    p_keywords = [v.lower() for v in tags.get("use_case_keywords", [])]
    p_text = (
        principle.get("principle_name", "") + " " +
        principle.get("one_liner", "") + " " +
        principle.get("human_fear_or_desire", "")
    ).lower()

    score = 0

    for i, mech in enumerate(emotional_mechs[:3]):
        weight = 3 if i == 0 else 1

        mech_kws = EMOTION_KEYWORDS.get(mech, [])
        for mkw in mech_kws:
            if mkw in p_text or any(mkw in pk for pk in p_keywords):
                score += weight
                break

    return score

def score_principle(principle: dict, intent: dict, normalized_text: str) -> int:
    tags = principle.get("metadata_tags", {})
    score = 0

    score += _overlap_score(intent.get("goals", []), tags.get("goals", []))
    score += _overlap_score(intent.get("page_types", []), tags.get("page_types", []))
    score += _overlap_score(intent.get("funnel_stages", []), tags.get("funnel_stages", []))
    score += _overlap_score(intent.get("audiences", []), tags.get("audiences", []))
    score += _overlap_score(intent.get("tone_fit", []), tags.get("tone_fit", []))

    score += _keyword_text_match(normalized_text, principle)
    score += _business_stage_score(principle, intent.get("business_stages", []))
    score += _emotional_mechanism_score(principle, intent.get("emotional_mechanisms", []))

    name = principle.get("principle_name", "").lower()
    one_liner = principle.get("one_liner", "").lower()
    text_lower = normalized_text.lower()
    if name and name in text_lower:
        score += 3
    if one_liner:
        first_words = " ".join(one_liner.split()[:4])
        if first_words in text_lower:
            score += 2

    return score

def prefilter(dataset: list, intent: dict, normalized_text: str, top_n: int = 20) -> list:
    scored = []
    for principle in dataset:
        s = score_principle(principle, intent, normalized_text)
        scored.append((s, principle))

    scored.sort(key=lambda x: x[0], reverse=True)
    has_matches = any(s > 0 for s, _ in scored)

    if not has_matches:
        return dataset

    return [p for s, p in scored[:top_n]]

def get_score_summary(dataset: list, intent: dict, normalized_text: str) -> list:
    scored = []
    for principle in dataset:
        s = score_principle(principle, intent, normalized_text)
        scored.append({
            "id": principle.get("id"),
            "name": principle.get("principle_name"),
            "score": s,
            "pillar": principle.get("pillar_code"),
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:20]
