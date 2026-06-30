REDUCED_WEIGHT_DOC_TYPES = {"legal_brief", "academic_abstract", "grant_proposal"}

DEFAULT_WEIGHTS = (0.55, 0.45)
REDUCED_WEIGHTS = (0.70, 0.30)


def get_weights(doc_type):
    if doc_type in REDUCED_WEIGHT_DOC_TYPES:
        return REDUCED_WEIGHTS
    return DEFAULT_WEIGHTS


def compute_confidence(llm_human_score, cognitive_pattern_score, doc_type):
    w1, w2 = get_weights(doc_type)
    raw_confidence = (w1 * llm_human_score) + (w2 * cognitive_pattern_score)
    confidence = 0.5 + 0.85 * (raw_confidence - 0.5)
    return max(0.0, min(1.0, confidence))
