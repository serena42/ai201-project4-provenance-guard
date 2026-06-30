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

##Transparency label: 
typed description of all three variants (high-confidence AI, human, uncertain) showing the exact text each one displays; screenshot or mockup optional

##Rate limiting: the limits you chose and your reasoning for those specific values

##Known limitations: 
at least one specific type of content your system would likely misclassify and why

##Spec reflection: 
one way the spec helped you, one way implementation diverged from it and why

##AI usage section: 
at least 2 specific instances describing what you directed the AI to do and what you revised or overrode
