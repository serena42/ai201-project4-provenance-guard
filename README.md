# Provenance Guard
Provenance Guard is a backend system that any creative sharing platform could plug into to classify submitted content, score confidence in that classification, surface a transparency label to users, and handle appeals from creators who believe they've been misclassified.

## Architecture overview

A creator submits text and a `creator_id` to `POST /submit`. The app generates a `content_id`, runs the text through two independent detection signals (an LLM-based judge and a set of cognitive-pattern heuristics), combines their outputs into a single confidence score via doc-type-weighted averaging, maps that score to an attribution label (`likely_ai` / `uncertain` / `likely_human`) and a plain-language transparency label, and writes a structured entry to the audit log before returning the result. If a creator disagrees, `POST /appeal` records their reasoning, flips the content's status to `under_review`, and logs the appeal alongside the original decision so a moderator can review both together via `GET /log`.

**Detection signals:**
- **Signal 1 — Groq-based LLM classifier:** measures holistic semantic/stylistic coherence and returns a 0.0–1.0 human-likelihood score plus a `doc_type` classification. Chosen because it captures broad, high-level stylistic uniformity that's hard to express as hand-written heuristics. Misses: can mistake highly polished human writing for AI-like uniformity, and is not perfectly deterministic even at `temperature=0`.
- **Signal 2 — cognitive-pattern heuristics:** measures self-reference density, constraint-awareness hedging ("I think," "honestly"), and implicit-context-assumption phrases ("as usual") as a pure-Python 0.0–1.0 score. Chosen because it's a cheap, deterministic, independent check that doesn't rely on the LLM's own judgment. Misses: formal/edited registers (academic, legal, grant writing) suppress these cues even when the author is human — see Known Limitations.

## Confidence scoring

`compute_confidence()` combines `llm_human_score` (s1) and `cognitive_pattern_score` (s2) via a doc-type-selected weighted average (`w1=0.55/w2=0.45` normally, `w1=0.70/w2=0.30` for formal doc types), then applies center compression (`confidence = 0.5 + 0.85 * (raw - 0.5)`) so the system doesn't overstate certainty. Validated by running the four curated samples from `planning.md` (clear AI, clear human, two borderline cases) through the signals independently and then end-to-end through `/submit` — see the Milestone 3/4 tables below — and by checking that the two signals disagree on at least one sample (the lightly-edited-AI case) to confirm they're contributing independent information rather than duplicating each other.

Two example submissions with different confidence, both captured from a live `/submit` call:
- High confidence: casual first-person restaurant review → `confidence = 0.87825`, `attribution = "likely_human"`.
- Low confidence: formal AI-generated paragraph on AI ethics → `confidence = 0.194`, `attribution = "likely_ai"`.

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

## Transparency label

`labels.py` maps the `attribution` value returned by `classify_attribution()` to one of three exact strings, all in plain language (no "classifier output," "logit," or score jargon):

| Attribution | Trigger | Exact label text |
|---|---|---|
| `likely_ai` | confidence < 0.35 | "This content appears likely AI-generated. Confidence in this assessment is high. If you created this yourself, you can submit an appeal for human review." |
| `uncertain` | 0.35 ≤ confidence ≤ 0.70 | "We could not determine authorship with high confidence. This content may include human writing, AI assistance, or both." |
| `likely_human` | confidence > 0.70 | "This content appears likely human-written. Confidence in this assessment is high, but automated attribution is not perfect." |

Live evidence from `POST /submit` — the label text visibly differs between the high- and low-confidence cases below, not just the number:

- Human sample (confidence 0.878): `"attribution": "likely_human"`, label = *"This content appears likely human-written. Confidence in this assessment is high, but automated attribution is not perfect."*
- AI sample (confidence 0.194): `"attribution": "likely_ai"`, label = *"This content appears likely AI-generated. Confidence in this assessment is high. If you created this yourself, you can submit an appeal for human review."*

## Appeals workflow

`POST /appeal` takes `content_id` and `creator_reasoning`, looks up the most recent audit entry for that `content_id`, flips `status` from `classified` to `under_review`, and appends a new `appeal_submitted` event that preserves the original attribution/confidence/signal scores alongside the appeal text.

Demo — appealing the human-sample submission above:

Request:
```json
POST /appeal
{"content_id": "fccdb33b-3a78-4a0c-b938-5f13c74ae542", "creator_reasoning": "I wrote this myself from personal experience, it was not AI generated."}
```

Response:
```json
{
  "content_id": "fccdb33b-3a78-4a0c-b938-5f13c74ae542",
  "status": "under_review",
  "message": "Appeal received and queued for review.",
  "appeal_logged_at": "2026-07-01T00:03:26.850334+00:00"
}
```

The resulting audit log (`GET /log`) shows both the original classification and the appeal for the same `content_id`, with `status_before`/`status_after` and the creator's reasoning preserved:

```json
{
  "event_type": "appeal_submitted",
  "content_id": "fccdb33b-3a78-4a0c-b938-5f13c74ae542",
  "creator_id": "test-user-1",
  "attribution": "likely_human",
  "confidence": 0.87825,
  "status": "under_review",
  "status_before": "classified",
  "status_after": "under_review",
  "appeal_reasoning": "I wrote this myself from personal experience, it was not AI generated.",
  "timestamp": "2026-07-01T00:03:26.850377+00:00"
}
```

## Rate limiting

`POST /submit` is limited to **5 requests per minute and 50 per day, per client IP** (Flask-Limiter, in-memory storage). `POST /appeal` and `GET /log` are left unthrottled so creators can always contest a decision and reviewers can always inspect the log.

Reasoning: a real creator submitting drafts for review is unlikely to fire more than a handful of requests in a given minute — 5/minute leaves comfortable headroom for normal iterative use (submit, revise, resubmit) while blocking scripted flooding. The 50/day ceiling caps sustained abuse across a session without affecting a legitimate writer who submits a few pieces a day, and it also protects the project's Groq API quota from being exhausted by a single client during grading/demo traffic.

Demo — 7 rapid `POST /submit` calls from the same client, with 2 prior submissions already counted against the same window:

```
request 1 -> 200
request 2 -> 200
request 3 -> 200
request 4 -> 429
request 5 -> 429
request 6 -> 429
request 7 -> 429
```

The first 3 succeed (bringing the window total to 5, since 2 requests had already been made earlier in the same minute), and every request past the limit returns `429 Too Many Requests`.

## Known limitations

Formal, heavily-edited human writing (academic abstracts, legal briefs, grant proposals) is the content type most likely to be misclassified. Signal 2 (cognitive-pattern heuristics) looks for first-person self-reference and casual hedging phrases ("I think," "honestly," "as usual") — cues that formal registers deliberately avoid — so a genuinely human-written abstract can score `cognitive_pattern_score = 0.0`, the same as AI-generated text. `compute_confidence()` partially compensates by lowering Signal 2's weight for `doc_type in {academic_abstract, legal_brief, grant_proposal}` (0.30 instead of 0.45), but this only dampens the effect; it doesn't eliminate it, since Signal 1 (the LLM judge) was also observed to be non-deterministic on formal borderline text (see the "Borderline (formal human)" row in Milestone 4 above, where `llm_human_score` swung from 0.4 to 0.8 across runs at `temperature=0`). A formal human writer is therefore at real risk of landing in the `uncertain` band even when the LLM signal alone would have scored them as human.

## Spec reflection

The spec helped most by forcing exact label text and exact threshold ranges to be written down in `planning.md` *before* any code existed — this made `classify_attribution()` and `labels.py` nearly copy-paste from the plan, and it caught the inconsistency between the two files early rather than at grading time.

Where implementation diverged: the plan's appeal schema (`## Appeals Workflow` in `planning.md`) describes a no-op path for re-appealing already-`under_review` content ("appends the new reasoning as an additional appeal note"). The actual implementation doesn't special-case this — `POST /appeal` always looks up the latest entry, always sets `status_after = "under_review"`, and always appends a new `appeal_submitted` event. In practice this produces the same observable behavior (another appeal event is logged, status stays `under_review`) without needing a separate branch, so the simpler unconditional path was kept and the plan's distinction was dropped as unnecessary complexity rather than implemented literally.

## Stretch feature: Ensemble detection

Added a third, independent detection signal — **stylometric heuristics** (`signals/stylometric_signal.py`, pure Python) — bringing the pipeline to 3 distinct signals:

1. **Signal 1 — Groq LLM classifier:** holistic semantic/stylistic coherence (see above).
2. **Signal 2 — cognitive-pattern heuristics:** self-reference, hedging, implicit-context phrases (see above).
3. **Signal 3 — stylometric heuristics:** averages three sub-metrics into a single `stylometric_score` — sentence-length variance (coefficient of variation, scaled against a ~0.6 "typical human" value; AI text tends toward uniform sentence lengths), type-token ratio / vocabulary diversity (scored highest in a 0.4-0.7 "typical human" band, penalized outside it in either direction), and punctuation variety (how many distinct punctuation styles appear at all, as a rough proxy for expressive variation). Chosen because it's a second fully independent, deterministic signal that measures *structure* rather than semantics or self-reference. Misses: noisy on very short text, and formal human prose can score AI-like on this signal too, for the same reason it does on Signal 2.

**Weighting and conflict resolution:** `compute_confidence()` (in `confidence.py`) takes all three scores plus `doc_type`. Baseline weights are `llm=0.45, cognitive=0.30, stylometric=0.25`; for formal doc types (`legal_brief`, `academic_abstract`, `grant_proposal`) weights shift to `llm=0.55, cognitive=0.15, stylometric=0.30` since the cognitive signal is least reliable there. Each signal casts a vote (human if score ≥ 0.5, else AI). A unanimous 3-0 vote uses the weights unchanged; a 2-1 split halves the lone dissenting signal's weight and renormalizes the rest, so a single outlier signal can't override two that agree, but it still contributes at reduced influence rather than being dropped entirely.

Live demo showing all three individual signal scores alongside the combined result:

- Casual human review → `llm_human_score=0.9`, `cognitive_pattern_score=1.0`, `stylometric_score=0.512` → combined `confidence=0.783`, `attribution=likely_human`.
- Formal AI-generated paragraph → `llm_human_score=0.2`, `cognitive_pattern_score=0.0`, `stylometric_score=0.387` → combined `confidence=0.267`, `attribution=likely_ai`.

Conflict-resolution check (constructed 2-1 split, not from live traffic): `compute_confidence(llm=0.9, cognitive=0.2, stylometric=0.3, doc_type="blog_post")` → the LLM signal votes human while the other two vote AI, so the LLM's weight is halved and renormalized before averaging, producing `confidence=0.445` (`uncertain`) — noticeably pulled toward the two-signal majority rather than sitting at the unweighted average of all three raw scores.

## AI usage

1. **Milestone 4 (second signal + confidence scoring):** I gave the AI tool the Architecture, Detection Signals, and Uncertainty Representation sections of `planning.md` and asked it to generate `get_cognitive_signal()` plus `compute_confidence()`. The generated `compute_confidence()` initially used a flat 0.5/0.5 weighting regardless of `doc_type`; I overrode this to add the doc-type-conditional weighting (0.55/0.45 baseline vs. 0.70/0.30 for `academic_abstract`/`legal_brief`/`grant_proposal`) specified in the plan, since the flat version would have let Signal 2 drag down clearly-human formal writing.
2. **Milestone 5 (labels + appeals + rate limiting):** I gave the AI tool the Transparency Label Design, Appeals Workflow, Audit Log Design, and Rate Limiting Plan sections and asked it to generate `labels.py`, the `POST /appeal` route, and the Flask-Limiter setup. The first draft of `POST /appeal` searched the audit log for an entry by `content_id` without restricting to the *latest* one, so if content had already been appealed once, a second appeal could read stale prior-decision fields. I revised `audit_log.py` to add `get_latest_entry_by_content_id()` (using the last match instead of the first) and updated the route to use it, so repeated appeals always reflect the most recent status.
3. **Stretch (ensemble detection):** I asked the AI tool to extend `compute_confidence()` from a two-signal weighted average to three signals with a documented conflict-resolution rule, given the new Stretch Feature section of `planning.md`. Its first version detected a "2-1 split" but only ever dropped the outlier's weight to 0 instead of halving and renormalizing it, which meant a single dissenting signal was discarded entirely rather than contributing at reduced influence — a stronger override than the plan called for. I rewrote `_resolve_conflicts()` to halve the outlier's weight and renormalize the remaining weights to sum to 1.0, matching the "reduced influence, not discarded" behavior specified in planning.md.
