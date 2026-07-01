import re
import statistics

PUNCTUATION_MARKS = ["!", "?", "...", "—", ";", ":", '"']

SENTENCE_LENGTH_CV_SCALE = 0.6
TTR_HUMAN_BAND = (0.4, 0.7)
PUNCT_VARIETY_SCALE = 4


def _split_sentences(text):
    sentences = re.split(r"[.!?]+", text)
    return [s.strip() for s in sentences if s.strip()]


def _sentence_length_variance_score(sentences):
    if len(sentences) < 2:
        return 0.5
    lengths = [len(re.findall(r"[a-zA-Z']+", s)) for s in sentences]
    mean_len = statistics.mean(lengths)
    if mean_len == 0:
        return 0.5
    std_len = statistics.stdev(lengths)
    cv = std_len / mean_len
    return max(0.0, min(1.0, cv / SENTENCE_LENGTH_CV_SCALE))


def _type_token_ratio_score(words):
    if not words:
        return 0.5
    ttr = len(set(words)) / len(words)
    low, high = TTR_HUMAN_BAND
    if ttr < low:
        return max(0.0, ttr / low)
    if ttr <= high:
        return 1.0
    return max(0.0, 1.0 - (ttr - high) / (1.0 - high))


def _punctuation_variety_score(text):
    marks_used = sum(1 for mark in PUNCTUATION_MARKS if mark in text)
    return max(0.0, min(1.0, marks_used / PUNCT_VARIETY_SCALE))


def get_stylometric_signal(text):
    """Scores sentence-length variance, vocabulary diversity (TTR), and punctuation variety.

    Returns:
        dict with:
            stylometric_score: float in [0.0, 1.0], 0.0 = certainly AI, 1.0 = certainly human
    """
    sentences = _split_sentences(text)
    words = re.findall(r"[a-zA-Z']+", text.lower())

    variance_score = _sentence_length_variance_score(sentences)
    ttr_score = _type_token_ratio_score(words)
    punct_score = _punctuation_variety_score(text)

    stylometric_score = (variance_score + ttr_score + punct_score) / 3
    stylometric_score = max(0.0, min(1.0, stylometric_score))

    return {"stylometric_score": stylometric_score}
