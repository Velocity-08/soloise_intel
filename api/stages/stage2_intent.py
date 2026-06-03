"""
STAGE 2 — Intent Extraction
"""

import re

GOAL_SIGNALS = {
    "increase CTR": ["ctr", "click", "click-through", "clickthrough", "clicks"],
    "improve conversion": ["conversion", "convert", "converting", "sales", "purchase"],
    "reduce churn": ["churn", "cancel", "cancellation", "retention", "retain", "winback", "win-back"],
    "reduce friction": ["friction", "drop-off", "dropoff", "abandon", "abandonment", "bounce"],
    "improve completion": ["complete", "completion", "finish", "onboard", "onboarding", "activate", "activation"],
    "create urgency": ["urgency", "urgent", "scarcity", "limited", "deadline", "expire", "fomo"],
    "increase trust": ["trust", "credibility", "proof", "testimonial", "authority", "social proof"],
    "boost engagement": ["engage", "engagement", "sticky", "daily active", "dau", "habit", "notification"],
    "increase revenue": ["revenue", "upsell", "upgrade", "pricing", "monetize", "monetization", "mrr", "arr"],
    "grow signups": ["signup", "sign up", "register", "registration", "trial", "free trial"],
    "improve retention": ["retention", "retain", "churn", "loyal", "loyalty", "renew", "renewal"],
    "increase awareness": ["awareness", "brand", "recall", "impression", "reach"],
}

PAGE_TYPE_SIGNALS = {
    "hero": ["hero", "homepage", "home page", "above the fold", "landing"],
    "pricing": ["pricing", "price", "plan", "tier", "cost", "affordable"],
    "signup": ["signup", "sign up", "register", "registration form", "create account"],
    "onboarding": ["onboarding", "onboard", "setup", "getting started", "welcome", "activate"],
    "email": ["email", "subject line", "newsletter", "drip", "nurture", "campaign", "inbox"],
    "landing page": ["landing page", "ad landing", "paid traffic", "squeeze page"],
    "dashboard": ["dashboard", "app", "product", "in-app", "inside the product"],
    "checkout": ["checkout", "payment", "billing", "upgrade flow", "purchase flow"],
    "cancellation": ["cancel", "cancellation", "churn flow", "offboarding"],
    "testimonial": ["testimonial", "case study", "review", "proof section", "social proof"],
    "ad": ["ad", "advertisement", "creative", "banner", "paid social", "facebook ad", "google ad"],
}

FUNNEL_STAGE_SIGNALS = {
    "awareness": ["awareness", "brand", "reach", "impression", "top of funnel", "tofu", "discovery"],
    "consideration": ["consideration", "compare", "alternative", "research", "evaluate", "shortlist"],
    "conversion": ["conversion", "convert", "buy", "purchase", "close", "sign up", "commit"],
    "activation": ["activation", "activate", "first value", "aha moment", "onboard", "setup"],
    "retention": ["retention", "retain", "keep", "churn", "renew", "loyalty", "habit"],
    "expansion": ["expand", "upsell", "upgrade", "cross-sell", "grow account", "revenue expansion"],
    "winback": ["winback", "win back", "re-engage", "reactivate", "lapsed", "churned"],
}

AUDIENCE_SIGNALS = {
    "B2B buyers": ["b2b", "business to business", "buyer", "procurement", "stakeholder", "decision maker"],
    "enterprise buyer": ["enterprise", "large company", "fortune 500", "big company", "corporate", "cto", "ciso"],
    "founder-led SaaS": ["founder", "startup", "bootstrapped", "indie", "solopreneur", "early stage"],
    "SMB": ["smb", "small business", "small team", "mid-market", "midmarket", "growing company"],
    "B2C": ["b2c", "consumer", "individual user", "end user", "personal"],
    "PLG": ["plg", "product led", "product-led growth", "self-serve", "freemium"],
}

TONE_SIGNALS = {
    "direct": ["direct", "clear", "straightforward", "no-nonsense", "concise"],
    "bold": ["bold", "aggressive", "strong", "powerful", "punchy"],
    "emotional": ["emotional", "empathy", "feeling", "fear", "desire", "pain", "hope"],
    "analytical": ["data", "analytics", "metric", "stats", "numbers", "roi", "analytical"],
    "playful": ["playful", "fun", "humor", "witty", "quirky", "creative"],
    "trustworthy": ["trust", "reliable", "credible", "safe", "secure", "honest"],
}

BUSINESS_STAGE_SIGNALS = {
    "acquisition": [
        "cold traffic", "paid ads", "facebook ad", "google ad", "landing page", "hero section",
        "first visit", "new visitor", "ad creative", "top of funnel", "awareness", "discovery",
        "brand awareness", "reach", "impression", "ctr", "click through"
    ],
    "activation": [
        "onboarding", "activate", "first value", "aha moment", "getting started", "setup",
        "first login", "day one", "day 1", "new user", "first session", "welcome email",
        "never used", "signed up but", "ghost", "not using", "didn't come back"
    ],
    "monetization": [
        "upgrade", "free to paid", "freemium", "won't pay", "won't upgrade", "paid plan",
        "trial to paid", "trial conversion", "pricing page", "upgrade prompt", "upgrade cta",
        "paid tier", "subscription", "payment", "checkout", "willingness to pay",
        "free users", "free plan", "upgrade flow", "convert to paid", "monetize"
    ],
    "retention": [
        "churn", "cancel", "cancellation", "retain", "retention", "renewal", "renew",
        "keeping users", "users leaving", "drop off after", "stop using", "inactive",
        "lapsed", "disengaged", "win back", "reactivate", "loyalty", "long term"
    ],
    "expansion": [
        "upsell", "cross-sell", "expand", "grow account", "increase revenue per user",
        "power user", "heavy user", "seat expansion", "plan upgrade", "enterprise upgrade",
        "add seats", "additional features", "mrr expansion", "account growth"
    ],
    "resurrection": [
        "churned user", "lost customer", "win back", "re-engage", "reactivate",
        "lapsed user", "came back", "return", "re-subscribe", "dormant"
    ],
}

EMOTIONAL_MECHANISM_SIGNALS = {
    "trust": ["trust", "credibility", "skeptical", "skepticism", "doubt", "believe", "safe", "secure", "legitimate", "scam", "fake", "real", "verified"],
    "uncertainty": ["not sure", "unsure", "confused", "confusing", "unclear", "don't know", "hesitant", "hesitation", "risky", "risk", "afraid", "worry", "concerned"],
    "effort": ["too hard", "complicated", "complex", "difficult", "friction", "drop off", "abandon", "give up", "form", "fields", "steps", "long", "tedious"],
    "loss": ["losing", "lose", "lost", "missing out", "leaving money", "cost", "wasting", "waste", "leaking", "leak", "bleeding", "gap", "hole"],
    "identity": ["belong", "like me", "for people like", "status", "brand", "image", "identity", "community", "tribe", "peer", "role", "professional"],
    "inertia": ["stuck", "comfortable", "habit", "routine", "don't want to change", "not motivated", "no urgency", "no reason", "procrastinate", "later", "won't pay", "won't upgrade", "doing nothing", "staying on free"],
    "overwhelm": ["too much", "overwhelmed", "overload", "too many", "too many options", "don't know where to start", "cognitive", "cluttered", "busy", "noisy"],
    "anxiety": ["anxious", "anxiety", "scared", "fear", "panic", "stress", "nervous", "payment", "credit card", "billing", "charge", "cancel", "locked in"],
}

def _match_signals(text_lower: str, signal_map: dict) -> list:
    matched = []
    for category, keywords in signal_map.items():
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                matched.append(category)
                break
    return matched

def _classify_business_stage(text_lower: str) -> list:
    scores = {}
    for stage, keywords in BUSINESS_STAGE_SIGNALS.items():
        score = 0
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                score += 1
        if score > 0:
            scores[stage] = score
    return sorted(scores, key=scores.get, reverse=True)

def _classify_emotional_mechanism(text_lower: str) -> list:
    scores = {}
    for mechanism, keywords in EMOTIONAL_MECHANISM_SIGNALS.items():
        score = 0
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                score += 1
        if score > 0:
            scores[mechanism] = score
    return sorted(scores, key=scores.get, reverse=True)

def extract_intent(normalized_text: str) -> dict:
    text_lower = normalized_text.lower()

    goals = _match_signals(text_lower, GOAL_SIGNALS)
    page_types = _match_signals(text_lower, PAGE_TYPE_SIGNALS)
    funnel = _match_signals(text_lower, FUNNEL_STAGE_SIGNALS)
    audiences = _match_signals(text_lower, AUDIENCE_SIGNALS)
    tones = _match_signals(text_lower, TONE_SIGNALS)
    business_stages = _classify_business_stage(text_lower)
    emotional_mechs = _classify_emotional_mechanism(text_lower)

    return {
        "goals": goals,
        "page_types": page_types,
        "funnel_stages": funnel,
        "audiences": audiences,
        "tone_fit": tones,
        "business_stages": business_stages,
        "emotional_mechanisms": emotional_mechs,
    }
