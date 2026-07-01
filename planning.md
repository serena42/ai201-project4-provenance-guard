# Provenance Guard - Planning (Phase Scaffold)

Status: Draft skeleton only. Details intentionally left blank for phased completion.

## Scope and Goals

- Project objective (1-2 sentences): Build a backend attribution service that evaluates submitted writing using multiple independent signals, returns a calibrated confidence score, and shows a plain-language transparency label. The system should prioritize trust and fairness by representing uncertainty honestly and providing a clear appeal path for creators.
- Primary user/stakeholder: Primary stakeholders are creators who submit content and need fair attribution outcomes, plus platform moderators who need structured logs to review decisions and appeals.
- Success criteria for this project: A submission returns attribution, confidence, and label in a structured response; all decisions are logged with signal-level detail; appeals move content to under_review and are auditable; and rate limiting prevents obvious abuse while allowing normal creator usage.

## Architecture

### System Flow Narrative (2-3 sentences)

When a creator submits text to POST /submit, the system generates a content_id, evaluates the text with two independent signals, combines those outputs into a single confidence score, maps the score to a transparency label, and returns the classification response. The same submission event is written to a structured audit log with attribution, confidence, and per-signal scores so decisions are traceable later. If a creator disputes a result through POST /appeal, the system records the creator_reasoning, updates status to under_review for that content_id, and appends the appeal event to the audit log for moderator review.

### Architecture Diagram

```text
Submission Flow
---------------
[Client]
  |
  | POST /submit {text, creator_id}
  v
[Ingest + content_id]
  |-------------------------------> [Signal 1: LLM Classifier]
  |                                     |\
  |                                     | \ llm_human_score
  |                                     |  +---------------------------> [Confidence Scoring]
  |                                     |
  |                                     +--> doc_type_classification (essay/blog/poem/etc.)
  |                                                  |\
  |                                                  | \ doc_type
  |                                                  |  +--------> [Signal 2: Cognitive Pattern Signals]
  |                                                  |
  +---------------- raw_text (original text) --------+--------> [Signal 2: Cognitive Pattern Signals]
                                                                 |
                                                                 | signal2_human_score
                                                                 +---------------------> [Confidence Scoring]

[Signal 1: LLM Classifier] --- doc_type -------------------------> [Confidence Scoring]
[Confidence Scoring] --- confidence + attribution ---------------> [Transparency Label Mapper]
[Transparency Label Mapper] --- label_text ----------------------> [Audit Log]
[Confidence Scoring] ----------- confidence + attribution --------> [Audit Log]
[Audit Log] ------------------------------------------------------> [POST /submit Response]


Appeal Flow
-----------
[Client]
  |
  | POST /appeal {content_id, creator_reasoning}
  v
[Appeal Handler]
  |
  | status = under_review
  v
[Audit Log: append appeal event + reasoning + timestamp]
  |
  +--> [POST /appeal Response]
```

## API Surface (Contract First)

### Endpoint: POST /submit

- Purpose: Accept creator-submitted text, run both detection signals, combine into a confidence score, map to a transparency label, persist an audit entry, and return the classification result.
- Request body (minimum):
	- text: Required string. Raw user content to analyze (poem, story excerpt, blog-style text).
	- creator_id: Required string. Platform/user identifier for the submitter.
- Response fields (minimum):
	- content_id: UUID string generated at submission time.
	- attribution: Enum string: likely_ai | uncertain | likely_human.
	- confidence: Float in the range 0.0-1.0, where higher means more likely human-authored.
	- label: Plain-language transparency label text shown to end users.
	- signal details (if included): Object with per-signal outputs (for example, llm_score and cognitive_pattern_score).
- Expected status codes:
	- 200 OK on successful classification.
	- 400 Bad Request for missing/invalid text or creator_id.
	- 429 Too Many Requests when rate limit is exceeded.
- Example response shape:
```json
{
  "content_id": "b8f2b513-9d2b-4c84-a87b-03c4f06457e9",
  "creator_id": "test-user-1",
  "attribution": "likely_human",
  "confidence": 0.82,
  "label": "This content is likely human-written. Confidence: high.",
  "signals": {
    "llm_score": 0.79,
    "cognitive_pattern_score": 0.85
  },
  "status": "classified"
}
```

### Endpoint: POST /appeal

- Purpose: Allow the creator to contest a classification decision and move the content item into manual review status.
- Request body (minimum):
	- content_id: Required UUID string from a prior POST /submit response.
	- creator_reasoning: Required non-empty string explaining why the creator believes the result is incorrect.
- Behavior:
	- Update status to under_review: Find the matching content record and set status from classified to under_review.
	- Log appeal with original decision context: Append a structured audit event containing content_id, prior attribution/confidence, appeal_reasoning, and timestamp.
- Response fields:
	- content_id: The appealed item ID.
	- status: under_review.
	- message: Confirmation text that appeal was received.
	- appeal_logged_at: UTC timestamp.
- Expected status codes:
	- 200 OK on successful appeal creation.
	- 400 Bad Request for missing/invalid fields.
	- 404 Not Found if content_id does not exist.
- Example response shape:
```json
{
  "content_id": "b8f2b513-9d2b-4c84-a87b-03c4f06457e9",
  "status": "under_review",
  "message": "Appeal received and queued for review.",
  "appeal_logged_at": "2026-06-30T20:14:52Z"
}
```

### Endpoint: GET /log

- Purpose: Return recent structured audit entries so classification and appeal history can be inspected and documented.
- Response shape: JSON object with an entries array ordered newest-first. Each entry includes timestamp, content_id, attribution, confidence, signal scores, status, and optional appeal_reasoning.
- Notes on visibility/auth for this class project: Open/no-auth for local grading visibility; production systems would require authentication and access controls.
- Expected status codes:
	- 200 OK when log is available.
- Example response shape:
```json
{
  "entries": [
    {
      "timestamp": "2026-06-30T20:12:10Z",
      "content_id": "b8f2b513-9d2b-4c84-a87b-03c4f06457e9",
      "creator_id": "test-user-1",
      "attribution": "likely_human",
      "confidence": 0.82,
      "llm_score": 0.79,
      "cognitive_pattern_score": 0.85,
      "status": "under_review",
      "appeal_reasoning": "I wrote this from personal experience."
    }
  ]
}
```

## Detection Signals (Required: 2+)

### Signal 1

- Name: Groq-based classification
- What it measures: Holistic semantic and stylistic coherence.
- Why this differs for human vs AI writing: Human coherence tends to be more varied. For example, if you ask someone to back up a claim, they make assumptions about how much to emphasize each point. Their experience across topics leads them to use expert vocabulary in some areas and journeyman or amateur vocabulary in others. AI is usually more uniform and does not vary as much across those nuances.
- Blind spots / failure modes: If a human writes in a style the model associates with AI coherence, the text may simply be highly edited according to what the model values. To reduce that risk, I use prompt guidance that distinguishes polished writing from overly uniform writing.
- Output format: 0.0-1.0 score, where 0.0 is certainly AI and 1.0 is certainly human.

### Signal 2

- Name: Cognitive Pattern Signals
- What it measures: Constraint awareness, self-reference, and implicit context assumptions.
- Why this differs for human vs AI writing: These are small but meaningful signs of human authorship. Human writers are often more aware of constraints that could weaken a claim, may preface a point with why they are mentioning it when it feels slightly off-topic, and may use phrases that assume shared experience (for example, "as usual").
- Blind spots / failure modes: Deliberately dry or highly edited writing may fail these human-pattern checks. I can add a step during the LLM pass to classify document style and reduce this signal's weight for styles like legal briefs, academic abstracts, and grant proposals.
- Output format: 0.0-1.0 score, where 0.0 is certainly AI and 1.0 is certainly human.

### Signal Combination Strategy

- Normalization approach: Both signals already return 0.0-1.0 human-likelihood scores, so each value is clamped to [0.0, 1.0] to prevent overflow. The LLM output is parsed as llm_human_score, and Signal 2 produces cognitive_pattern_score after averaging its sub-metrics and clamping to [0.0, 1.0].
- Weighting or voting approach: Weighted average with dynamic weighting by document type. Baseline weights are w1=0.55 (LLM) and w2=0.45 (Signal 2). For document types that can suppress cognitive-pattern cues (legal_brief, academic_abstract, grant_proposal), adjust to w1=0.70 and w2=0.30.
- Combined confidence formula (clear + implementation-ready): Let s1 = llm_human_score, s2 = cognitive_pattern_score, and (w1, w2) be selected by doc_type where w1 + w2 = 1.0. Compute raw_confidence = (w1 * s1) + (w2 * s2). Apply light uncertainty compression toward center to avoid overconfident outputs: confidence = 0.5 + 0.85 * (raw_confidence - 0.5). Final step: clamp confidence to [0.0, 1.0].

## Uncertainty Representation

- What a confidence score means in this system: Confidence is the estimated probability that a submission is human-authored after combining the LLM signal and cognitive-pattern signal. A score near 0.50 indicates ambiguous evidence, while scores near 0.0 or 1.0 indicate stronger agreement across signals.
- Score calibration approach: Start with weighted combination plus center compression (defined above), then calibrate thresholds using a small curated test set (clear AI, clear human, and borderline samples). If borderline content clusters too far from 0.50, reduce the compression factor or tighten thresholds until uncertain cases consistently land in the middle band.
- Threshold ranges:
  - likely_ai: confidence < 0.35
  - uncertain: 0.35 <= confidence <= 0.70
  - likely_human: confidence > 0.70
- False-positive risk handling strategy (human mislabeled as AI): The uncertain band is intentionally wider than the AI-positive band to reduce false positives against human creators. For style classes that naturally suppress cognitive-pattern cues (for example, legal or academic text), Signal 2 weight is reduced via doc_type so the model does not over-penalize formal writing.

## Transparency Label Design (Write Exact Text)

### Variant A: High-confidence AI

- Trigger range: confidence < 0.35
- Exact label text shown to users: "This content appears likely AI-generated. Confidence in this assessment is high. If you created this yourself, you can submit an appeal for human review."

### Variant B: Uncertain

- Trigger range: 0.35 <= confidence <= 0.70
- Exact label text shown to users: "We could not determine authorship with high confidence. This content may include human writing, AI assistance, or both."

### Variant C: High-confidence Human

- Trigger range: confidence > 0.70
- Exact label text shown to users: "This content appears likely human-written. Confidence in this assessment is high, but automated attribution is not perfect."

## Appeals Workflow

- Who can appeal: The original creator of the submitted content (identified by creator_id) can appeal a result associated with their content_id.
- Required appeal input fields: content_id (required), creator_reasoning (required), and optional creator_id for ownership validation.
- State transition on appeal: If content_id exists, status changes from classified to under_review. If already under_review, the endpoint returns a no-op confirmation and appends the new reasoning as an additional appeal note.
- What gets logged on appeal: timestamp, content_id, creator_id (if provided), prior attribution, prior confidence, prior signal scores, status_before, status_after, creator_reasoning, and appeal_event_type="appeal_submitted".
- What a reviewer should see in queue/context: content_id, full submitted text, latest attribution label, confidence score, both signal scores, doc_type classification, creator_reasoning, submission timestamp, appeal timestamp, and current status (under_review).

## Audit Log Design

- Storage choice (JSON file vs SQLite): Structured JSON log file for simplicity and grading visibility in this milestone-based project. Each event is appended as one JSON object to an in-memory list and persisted to disk as a JSON array.
- Structured entry schema (minimum fields):
  - timestamp: UTC timestamp for when the event is written.
  - content_id: UUID for the submission this event refers to.
  - creator_id: Submitter identifier (or appellant identifier when present).
  - attribution: likely_ai | uncertain | likely_human at time of decision.
  - confidence: Combined 0.0-1.0 confidence score.
  - llm_score: Signal 1 human-likelihood score.
  - cognitive_pattern_score: Signal 2 human-likelihood score.
  - doc_type: LLM-derived document type used for weighting.
  - status: classified | under_review.
  - event_type: classification_created | appeal_submitted.
  - appeal_reasoning (if present): Free-text creator explanation for appeal.
  - status_before (appeal events): Prior state before transition.
  - status_after (appeal events): State after transition (typically under_review).
- Retrieval strategy for GET /log: Return JSON in newest-first order with optional limit parameter (default 50) so README evidence is easy to capture. Response shape: {"entries": [...]} with full structured fields for both classification and appeal events.

## Rate Limiting Plan

- Target route(s): POST /submit (primary), with POST /appeal left unthrottled or given a much looser limit so creators can contest decisions without friction.
- Chosen limits (minute/day): 5 submissions per minute and 50 submissions per day per client IP.
- Rationale tied to realistic writer behavior + abuse prevention: A normal creator is unlikely to submit more than a few drafts in a short span, so 5 per minute gives room for normal use while staying well below Groq's published per-minute request ceiling for the model I plan to use. The daily cap prevents scripted flooding or repeated mass-submission attacks while reducing the chance that my own class-project traffic runs into the Groq free tier first.
- Evidence plan (how to capture 429 behavior for README): Run a short loop that sends 7 POST /submit requests in quick succession and capture the output showing the first 5 requests returning 200 and the excess requests returning 429. Also note in the implementation that Groq 429 responses should be handled with `retry-after` backoff so the app does not hammer the API when the upstream limit is reached.

## Anticipated Edge Cases (At Least 2 Specific Cases)

1. A highly polished human essay or academic abstract may score as AI-like because it lacks the casual phrasing, self-references, and other cognitive-pattern cues the second signal expects.
2. A short poem, slogan, or very brief social post may not provide enough text for stable signal scoring, so the LLM output and cognitive-pattern score may both become noisy or overconfident.
3. Repetitive AI-assisted writing that has been lightly edited by a human may land in the uncertain band because the LLM can detect strong coherence while the cognitive-pattern signal still sees some human-style context markers.

## Testing Plan (Phase-Oriented)

### Confidence Tests

- High-confidence AI sample: "Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment."
- High-confidence human sample: "ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after. my friend got the spicy version and said it was better. probably won't go back unless someone drags me there"
- Borderline sample 1: "The relationship between monetary policy and asset price inflation has been extensively studied in the literature. Central banks face a fundamental tension between their mandate for price stability and the unintended consequences of prolonged low interest rates on equity and real estate valuations."
- Borderline sample 2: "I've been thinking a lot about remote work lately. There are genuine tradeoffs — flexibility and no commute on one side, isolation and blurred work-life boundaries on the other. Studies show productivity varies widely by individual and role type." (Although I think this is AI just because it's hard to believe someone would be sophisticated enough use an em-dash but still bother to write to say nothing.)
- Expected score/label behavior: The AI sample should land below 0.35 and produce the high-confidence AI label. The human sample should land above 0.70 and produce the high-confidence human label. The two borderline samples should land in or near the uncertain band so the uncertain label is exercised, and the exact scores should not all cluster at the same value.

### Endpoint Tests

- POST /submit returns required fields: Send a sample text and creator_id, then verify the JSON response includes content_id, attribution, confidence, label, llm_score, cognitive_pattern_score, doc_type, and status.
- POST /appeal updates status + logs reasoning: Submit an appeal with content_id and creator_reasoning, then verify the response confirms under_review, the original record changes to under_review, and the log records the appeal_reasoning plus prior decision context.
- GET /log returns structured entries (>=3): After at least three submissions and one appeal, request GET /log and verify the response is structured JSON with at least three entries, newest-first ordering, timestamps, content_id values, attribution, confidence, and appeal fields where applicable.
- Rate limit test produces 429 after threshold: Send 7 rapid POST /submit requests and verify that the first 5 succeed while the excess requests return 429. Also confirm the app surfaces or logs the upstream Groq retry-after behavior if Groq rate limiting is triggered during testing.

## AI Tool Plan

### M3: Submission Endpoint + First Signal

- Spec sections to provide to AI tool: Architecture section, API Surface for POST /submit, and the first signal description from Detection Signals.
- Ask AI tool to generate: A Flask app skeleton with a POST /submit route stub plus the first signal function that returns a 0.0-1.0 human-likelihood score and a doc_type classification.
- Verification steps before accepting output: Check that the route accepts text and creator_id, that the function signature matches the spec, and that direct test calls to the first signal return sensible scores before wiring it into the endpoint.

### M4: Second Signal + Confidence Scoring

- Spec sections to provide to AI tool: Architecture section, Detection Signals, and Uncertainty Representation.
- Ask AI tool to generate: The second signal function (cognitive-pattern scoring) plus the confidence scoring logic that combines llm_human_score, cognitive_pattern_score, and doc_type-based weighting into a single calibrated confidence value.
- Verification steps before accepting output: Confirm the combined score uses the correct weighting by doc_type, lands in the threshold ranges defined in the spec, and produces noticeably different outputs for clearly human, clearly AI, and borderline test inputs.

### M5: Production Layer (Labels + Appeals + Safety)

- Spec sections to provide to AI tool: Transparency Label Design, Appeals Workflow, Audit Log Design, Rate Limiting Plan, and the Architecture diagram.
- Ask AI tool to generate: Label generation logic that maps confidence to the exact label text, the POST /appeal endpoint, audit-log updates for appeals, and Flask-Limiter configuration for POST /submit.
- Verification steps before accepting output: Confirm that all three label variants are reachable, that an appeal changes status to under_review and is logged, and that the submit endpoint returns 429 after the configured limit while preserving a readable retry-after path for upstream Groq errors.

## Phase Checklist

- [ ] Phase 1: Finalize architecture narrative + diagram
- [ ] Phase 2: Finalize signals + uncertainty + thresholds
- [ ] Phase 3: Finalize exact label text variants
- [ ] Phase 4: Finalize appeals, audit log schema, and rate limits
- [ ] Phase 5: Lock AI tool prompts/verification plan
- [ ] Phase 6: Reconcile this plan with README evidence checklist

## Stretch Feature: Ensemble Detection (planned before implementation)

- Third signal: Stylometric heuristics (`signals/stylometric_signal.py`), pure Python, no external libraries. Averages three sub-metrics into `stylometric_score` (0.0-1.0, human-likelihood):
  - Sentence-length variance: coefficient of variation of word-count-per-sentence, scaled against a typical-human CV of ~0.6. AI text tends toward more uniform sentence lengths; human text is more variable.
  - Type-token ratio (vocabulary diversity): unique words / total words, scored highest inside a "typical human" band of 0.4-0.7 and penalized outside it in either direction (extreme repetition or extreme lexical uniqueness are both atypical of casual human writing).
  - Punctuation variety: how many distinct punctuation styles (`!`, `?`, `...`, em dash, `;`, `:`, quotes) appear at all, as a rough proxy for expressive/informal variation.
  - Blind spots: all three sub-metrics are length-sensitive and can be noisy on very short submissions (few sentences), and formal human prose (which is itself low-variance and low-punctuation-variety) can score AI-like on this signal alone — the same failure mode as Signal 2, for a related reason.
- Combination update: `compute_confidence()` now takes all three scores (`llm_human_score`, `cognitive_pattern_score`, `stylometric_score`) plus `doc_type`. Baseline weights become `llm=0.45, cognitive=0.30, stylometric=0.25`; for `doc_type in {legal_brief, academic_abstract, grant_proposal}` (where the cognitive signal is least reliable), weights shift to `llm=0.55, cognitive=0.15, stylometric=0.30`.
- Conflict resolution (voting): each signal "votes" human (score >= 0.5) or AI (score < 0.5). A unanimous 3-0 vote uses the weights as-is. A 2-1 split halves the lone dissenting signal's weight and renormalizes the remaining weights to sum to 1.0 before computing the weighted average — so no single signal can override two that agree, but a genuine minority signal still contributes at reduced influence rather than being discarded outright. The same center-compression step (`confidence = 0.5 + 0.85 * (raw - 0.5)`) is applied afterward.
- Verification plan: re-run the four Milestone 4 test samples through the three-signal pipeline and confirm each still lands in its expected band; additionally construct one deliberate 2-1 split case (one signal disagreeing with the other two) and confirm the outlier's weight is visibly reduced in the resulting confidence value versus a plain unweighted average.

## Stretch Feature: Analytics Dashboard (planned before implementation)

- Endpoint: `GET /analytics` (`analytics.py`), following the same no-auth/JSON-for-grading-visibility pattern as `GET /log`.
- Metric 1 - detection pattern: count and percentage of `classification_created` entries in each of `likely_ai` / `uncertain` / `likely_human`.
- Metric 2 - appeal rate: distinct appealed `content_id`s divided by total classifications, so a content item appealed more than once is only counted once.
- Metric 3 (chosen) - signal disagreement rate: the fraction of classifications where the three per-signal votes (score >= 0.5 = human) were not unanimous. This reuses the same vote definition as `compute_confidence()`'s conflict-resolution logic (see Ensemble Detection above), so it directly measures how often the 2-1 outlier-dampening path is actually exercised in practice, rather than being an arbitrary extra metric.
- Data source: `audit_log.get_all_entries()` (unfiltered, unlimited) rather than the paginated `get_entries()` used by `GET /log`, so analytics reflect the full history, not just the most recent 50 entries.
- Verification plan: submit a mix of clear-AI, clear-human, and one deliberately 2-1-split sample, appeal one of them, and confirm `/analytics` reports the correct counts/percentages for all three metrics against that known input set.

## Notes and Open Questions

- Open questions to resolve before coding:
  - Should doc_type remain an internal weighting feature only, or should it also appear in the final API response and audit log as a first-class field?
  - Should the confidence thresholds stay at 0.35 / 0.70, or should I tighten them after a few manual test runs if borderline content lands in the wrong band?
  - Should POST /appeal accept creator_id for ownership validation, or keep the required payload minimal and trust content_id plus creator_reasoning only?
  - Should GET /log support a query limit parameter in the final implementation, and if so, what default window should it return?
  - If Groq returns 429 during testing, should the app surface that error directly, retry after a delay, or degrade gracefully to the uncertain label and a warning message?
- Assumptions to validate:
  - The two-signal design remains strong enough for the rubric without adding a third signal or splitting Signal 2 into separate tracked signals.
  - A JSON log file will be sufficient for grading visibility and easier to inspect than SQLite for this project.
  - The class-project environment will allow enough Groq calls to test the scoring flow without hitting the organization-level quota too quickly.
