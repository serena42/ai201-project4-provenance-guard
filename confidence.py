REDUCED_WEIGHT_DOC_TYPES = {"legal_brief", "academic_abstract", "grant_proposal"}

DEFAULT_WEIGHTS = {"llm": 0.45, "cognitive": 0.30, "stylometric": 0.25}
REDUCED_WEIGHTS = {"llm": 0.55, "cognitive": 0.15, "stylometric": 0.30}

OUTLIER_DAMPENING_FACTOR = 0.5


def get_weights(doc_type):
    if doc_type in REDUCED_WEIGHT_DOC_TYPES:
        return dict(REDUCED_WEIGHTS)
    return dict(DEFAULT_WEIGHTS)


def _resolve_conflicts(scores, weights):
    """Dampens a lone dissenting signal's weight before renormalizing.

    All three signals "vote" human (>=0.5) or AI (<0.5). A unanimous vote (3-0)
    needs no adjustment. A 2-1 split halves the outlier's weight and
    redistributes the rest proportionally, so one signal can't single-handedly
    override two that agree.
    """
    votes = {name: score >= 0.5 for name, score in scores.items()}
    human_votes = sum(votes.values())

    if human_votes in (0, 3):
        return weights

    majority = human_votes == 2
    outlier = next(name for name, vote in votes.items() if vote != majority)

    adjusted = dict(weights)
    adjusted[outlier] *= OUTLIER_DAMPENING_FACTOR
    total = sum(adjusted.values())
    return {name: weight / total for name, weight in adjusted.items()}


def compute_confidence(llm_human_score, cognitive_pattern_score, stylometric_score, doc_type):
    scores = {
        "llm": llm_human_score,
        "cognitive": cognitive_pattern_score,
        "stylometric": stylometric_score,
    }
    weights = _resolve_conflicts(scores, get_weights(doc_type))

    raw_confidence = sum(scores[name] * weights[name] for name in scores)
    confidence = 0.5 + 0.85 * (raw_confidence - 0.5)
    return max(0.0, min(1.0, confidence))
