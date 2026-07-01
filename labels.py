LABEL_LIKELY_AI = (
    "This content appears likely AI-generated. Confidence in this assessment is high. "
    "If you created this yourself, you can submit an appeal for human review."
)

LABEL_UNCERTAIN = (
    "We could not determine authorship with high confidence. This content may include "
    "human writing, AI assistance, or both."
)

LABEL_LIKELY_HUMAN = (
    "This content appears likely human-written. Confidence in this assessment is high, "
    "but automated attribution is not perfect."
)


def get_label(attribution):
    if attribution == "likely_ai":
        return LABEL_LIKELY_AI
    if attribution == "likely_human":
        return LABEL_LIKELY_HUMAN
    return LABEL_UNCERTAIN
