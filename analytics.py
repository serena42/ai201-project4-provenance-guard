ATTRIBUTIONS = ["likely_ai", "uncertain", "likely_human"]

SIGNAL_FIELDS = ["llm_human_score", "cognitive_pattern_score", "stylometric_score"]


def _round(value, digits=4):
    return round(value, digits) if value is not None else None


def _detection_pattern(classifications):
    total = len(classifications)
    counts = {attribution: 0 for attribution in ATTRIBUTIONS}
    for entry in classifications:
        attribution = entry.get("attribution")
        if attribution in counts:
            counts[attribution] += 1

    return {
        attribution: {
            "count": counts[attribution],
            "pct": _round(counts[attribution] / total) if total else 0.0,
        }
        for attribution in ATTRIBUTIONS
    }


def _appeal_rate(classifications, appeals):
    total = len(classifications)
    appealed_content_ids = {entry.get("content_id") for entry in appeals}
    appealed_count = len(appealed_content_ids)
    return {
        "appealed_count": appealed_count,
        "total_classifications": total,
        "rate": _round(appealed_count / total) if total else 0.0,
    }


def _signal_disagreement_rate(classifications):
    """Fraction of submissions where the 3 signals didn't unanimously agree.

    Mirrors the vote used by compute_confidence()'s conflict resolution: each
    signal votes human if its score is >= 0.5. A 2-1 or 3-0-against-itself
    split counts as disagreement; a unanimous 3-0 vote does not.
    """
    total = 0
    disagreements = 0
    for entry in classifications:
        scores = [entry.get(field) for field in SIGNAL_FIELDS]
        if any(score is None for score in scores):
            continue
        total += 1
        votes = [score >= 0.5 for score in scores]
        if len(set(votes)) > 1:
            disagreements += 1

    return {
        "disagreement_count": disagreements,
        "eligible_count": total,
        "rate": _round(disagreements / total) if total else 0.0,
    }


def compute_analytics(entries):
    classifications = [e for e in entries if e.get("event_type") == "classification_created"]
    appeals = [e for e in entries if e.get("event_type") == "appeal_submitted"]

    return {
        "total_submissions": len(classifications),
        "detection_pattern": _detection_pattern(classifications),
        "appeal_rate": _appeal_rate(classifications, appeals),
        "signal_disagreement_rate": _signal_disagreement_rate(classifications),
    }
