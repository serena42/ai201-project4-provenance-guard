import re

SELF_REFERENCE_WORDS = {"i", "me", "my", "mine", "myself"}

CONSTRAINT_AWARENESS_PHRASES = [
    "to be fair",
    "granted",
    "admittedly",
    "i might be wrong",
    "i could be wrong",
    "i'm not sure",
    "im not sure",
    "i think",
    "i guess",
    "honestly",
    "though",
    "that said",
    "in fairness",
    "feel free to correct me",
    "correct me if i'm wrong",
    "probably",
    "i'm no expert",
    "im no expert",
]

IMPLICIT_CONTEXT_PHRASES = [
    "as usual",
    "like always",
    "you know",
    "obviously",
    "right?",
    "anyway",
    "anyways",
    "honestly",
    "lol",
    "tbh",
    "ngl",
]


CONTRACTION_PREFIXES = ("i've", "i'm", "i'd", "i'll")


def _tokenize(text):
    words = re.findall(r"[a-zA-Z']+", text.lower())
    return [w if w not in CONTRACTION_PREFIXES else "i" for w in words]


def _split_sentences(text):
    sentences = re.split(r"[.!?]+", text)
    return [s.strip() for s in sentences if s.strip()]


def _phrase_density(text_lower, phrases, word_count):
    if word_count == 0:
        return 0.0
    hits = sum(text_lower.count(phrase) for phrase in phrases)
    return hits / word_count


def get_cognitive_signal(text):
    """Scores constraint awareness, self-reference, and implicit context assumptions.

    Returns:
        dict with:
            cognitive_pattern_score: float in [0.0, 1.0], 0.0 = certainly AI, 1.0 = certainly human
    """
    words = _tokenize(text)
    word_count = len(words)
    text_lower = text.lower()

    if word_count == 0:
        return {"cognitive_pattern_score": 0.5}

    self_reference_hits = sum(1 for w in words if w in SELF_REFERENCE_WORDS)
    self_reference_density = self_reference_hits / word_count
    self_reference_score = min(1.0, self_reference_density * 25)

    constraint_density = _phrase_density(text_lower, CONSTRAINT_AWARENESS_PHRASES, word_count)
    constraint_score = min(1.0, constraint_density * 40)

    implicit_density = _phrase_density(text_lower, IMPLICIT_CONTEXT_PHRASES, word_count)
    implicit_score = min(1.0, implicit_density * 40)

    cognitive_pattern_score = (self_reference_score + constraint_score + implicit_score) / 3
    cognitive_pattern_score = max(0.0, min(1.0, cognitive_pattern_score))

    return {"cognitive_pattern_score": cognitive_pattern_score}
