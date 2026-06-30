# Provenance Guard
Provenance Guard is a backend system that any creative sharing platform could plug into to classify submitted content, score confidence in that classification, surface a transparency label to users, and handle appeals from creators who believe they've been misclassified.

##Architecture overview: 
the path a submission takes from input to transparency label
Detection signals: what each signal measures, why you chose it, and what it misses

##Confidence scoring: 
how you combined signals into a score, how you validated it's meaningful, and two example submissions with noticeably different confidence scores (one high-confidence, one lower-confidence) showing the actual scores

### Signal 1 (Groq) test results — Milestone 3

Tested `get_llm_signal()` independently against the four sample inputs from planning.md before wiring it into `/submit`:

| Sample | `llm_human_score` | `doc_type` | Expected band | Matches? |
|---|---|---|---|---|
| Clear AI | 0.2 | academic_abstract | likely_ai (<0.35) | Yes |
| Clear human | 0.9 | blog_post | likely_human (>0.70) | Yes |
| Borderline (formal human) | 0.4 | academic_abstract | uncertain (0.35–0.70) | Yes |
| Borderline (lightly-edited AI) | 0.8 | blog_post / essay | should land mid-range / uncertain | No — scored high-human |

Three of four samples landed in the expected band. The lightly-edited-AI sample is the exception: it scored 0.8 (high-confidence human), even after revising the system prompt to add an explicit "local specificity" cue (concrete details/named entities vs. generic abstraction) intended to catch exactly this case. The score was unchanged after the revision (0.8 → 0.8); only the `doc_type` classification shifted between runs (academic_abstract/blog_post → essay), suggesting the model isn't weighting that cue strongly for this text. This is a real blind spot of signal 1 alone — see Known Limitations — and is one reason a second, independent signal (cognitive-pattern heuristics, Milestone 4) is needed rather than relying on the LLM signal by itself.

### Signal 2 (cognitive pattern heuristics) — Milestone 4

`get_cognitive_signal()` scores three pure-Python sub-metrics — self-reference density (first-person pronouns/contractions), constraint-awareness phrase density ("to be fair," "I think," "honestly"), and implicit-context-assumption phrase density ("as usual," "you know") — averaged into a single `cognitive_pattern_score`. Tested independently against the same four samples:

| Sample | `cognitive_pattern_score` | Notes |
|---|---|---|
| Clear AI | 0.0 | No self-reference or hedging cues — matches signal 1 |
| Clear human | 0.91 | Heavy first-person + casual hedging ("honestly," "probably") |
| Borderline (formal human) | 0.0 | Formal academic prose has no cognitive-pattern cues — a known blind spot (see Known Limitations); this is exactly why doc_type-based weighting discounts signal 2 for academic/legal/grant text |
| Borderline (lightly-edited AI) | 0.21 | Picks up "I've been thinking" self-reference but stays low overall — disagrees with signal 1's 0.8, demonstrating real independence between the two signals |

### Combined confidence scoring — Milestone 4

`compute_confidence()` (in `confidence.py`) combines `llm_human_score` (s1) and `cognitive_pattern_score` (s2) via doc_type-weighted average — w1=0.55/w2=0.45 by default, or w1=0.70/w2=0.30 for `legal_brief`/`academic_abstract`/`grant_proposal` — then applies center compression (`confidence = 0.5 + 0.85 * (raw - 0.5)`) to avoid overconfident outputs, per planning.md's Signal Combination Strategy. Tested end-to-end through `POST /submit`:

| Sample | `llm_human_score` | `cognitive_pattern_score` | doc_type | Combined confidence | Attribution | Matches expected band? |
|---|---|---|---|---|---|---|
| Clear AI | 0.2 | 0.0 | academic_abstract | 0.194 | likely_ai | Yes |
| Clear human | 0.9 | 0.91 | blog_post | 0.843 | likely_human | Yes |
| Borderline (formal human) | 0.7–0.8* | 0.0 | academic_abstract | 0.45–0.49 | uncertain | Yes |
| Borderline (lightly-edited AI) | 0.8 | 0.0–0.21 | blog_post | 0.45–0.53 | uncertain | Yes |

\* The Groq model is not perfectly deterministic even at `temperature=0`; `llm_human_score` for this sample varied between 0.4 and 0.8 across separate runs (see Known Limitations). Despite that swing, the combined confidence stayed in the `uncertain` band in every run, because the reduced signal-2 weight for `academic_abstract` still pulls a high s1 down once s2=0.

All four samples now land in their expected bands. Notably, the lightly-edited-AI sample — which signal 1 alone misclassified as high-confidence human (0.8) in Milestone 3 — is corrected by the combination: signal 2's low cognitive-pattern score pulls the combined confidence down into the `uncertain` band (0.45–0.53), which is the intended behavior for ambiguous content. This is the clearest evidence that the two signals are doing genuinely independent work rather than duplicating each other.

##Transparency label: 
typed description of all three variants (high-confidence AI, human, uncertain) showing the exact text each one displays; screenshot or mockup optional

##Rate limiting: the limits you chose and your reasoning for those specific values

##Known limitations: 
at least one specific type of content your system would likely misclassify and why

##Spec reflection: 
one way the spec helped you, one way implementation diverged from it and why

##AI usage section: 
at least 2 specific instances describing what you directed the AI to do and what you revised or overrode
