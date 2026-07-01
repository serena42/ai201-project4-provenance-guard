import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from analytics import compute_analytics
from audit_log import append_entry, get_all_entries, get_entries, get_latest_entry_by_content_id
from confidence import compute_confidence
from labels import get_label
from signals.cognitive_signal import get_cognitive_signal
from signals.llm_signal import get_llm_signal
from signals.stylometric_signal import get_stylometric_signal
from verification import (
    CERTIFICATE_LABEL,
    VERIFICATION_CONFIDENCE_THRESHOLD,
    VERIFICATION_MIN_WORD_COUNT,
    get_verification,
    is_verified,
    mark_verified,
)

load_dotenv()

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)


def classify_attribution(confidence):
    if confidence < 0.35:
        return "likely_ai"
    if confidence > 0.70:
        return "likely_human"
    return "uncertain"


def run_detection_pipeline(text):
    signal1 = get_llm_signal(text)
    signal2 = get_cognitive_signal(text)
    signal3 = get_stylometric_signal(text)

    confidence = compute_confidence(
        signal1["llm_human_score"],
        signal2["cognitive_pattern_score"],
        signal3["stylometric_score"],
        signal1["doc_type"],
    )

    return {
        "llm_human_score": signal1["llm_human_score"],
        "cognitive_pattern_score": signal2["cognitive_pattern_score"],
        "stylometric_score": signal3["stylometric_score"],
        "doc_type": signal1["doc_type"],
        "confidence": confidence,
    }


@app.route("/submit", methods=["POST"])
@limiter.limit("5 per minute;50 per day")
def submit():
    data = request.get_json(silent=True) or {}
    text = data.get("text")
    creator_id = data.get("creator_id")

    if not text or not creator_id:
        return jsonify({"error": "text and creator_id are required"}), 400

    content_id = str(uuid.uuid4())
    result = run_detection_pipeline(text)
    confidence = result["confidence"]
    attribution = classify_attribution(confidence)
    status = "classified"
    label = get_label(attribution)
    verification = get_verification(creator_id)

    append_entry(
        {
            "event_type": "classification_created",
            "content_id": content_id,
            "creator_id": creator_id,
            "attribution": attribution,
            "confidence": confidence,
            "llm_human_score": result["llm_human_score"],
            "cognitive_pattern_score": result["cognitive_pattern_score"],
            "stylometric_score": result["stylometric_score"],
            "doc_type": result["doc_type"],
            "status": status,
            "creator_verified": verification is not None,
        }
    )

    response = {
        "content_id": content_id,
        "creator_id": creator_id,
        "attribution": attribution,
        "confidence": confidence,
        "label": label,
        "signals": {
            "llm_human_score": result["llm_human_score"],
            "cognitive_pattern_score": result["cognitive_pattern_score"],
            "stylometric_score": result["stylometric_score"],
            "doc_type": result["doc_type"],
        },
        "status": status,
    }

    if verification is not None:
        response["certificate"] = {
            "type": "verified_human_creator",
            "label": CERTIFICATE_LABEL,
            "verified_at": verification["verified_at"],
        }

    return jsonify(response)


@app.route("/verify", methods=["POST"])
def verify():
    data = request.get_json(silent=True) or {}
    text = data.get("text")
    creator_id = data.get("creator_id")

    if not text or not creator_id:
        return jsonify({"error": "text and creator_id are required"}), 400

    word_count = len(text.split())
    if word_count < VERIFICATION_MIN_WORD_COUNT:
        return jsonify(
            {
                "creator_id": creator_id,
                "verified": False,
                "reason": f"Verification sample must be at least {VERIFICATION_MIN_WORD_COUNT} words "
                f"(got {word_count}). Write a longer, spontaneous sample and try again.",
            }
        ), 400

    result = run_detection_pipeline(text)
    confidence = result["confidence"]
    passed = confidence > VERIFICATION_CONFIDENCE_THRESHOLD

    if not passed:
        return jsonify(
            {
                "creator_id": creator_id,
                "verified": False,
                "confidence": confidence,
                "reason": "Verification sample did not score as high-confidence human "
                f"(needs confidence > {VERIFICATION_CONFIDENCE_THRESHOLD}, got {confidence}). "
                "Try again with a longer, unedited, spontaneous sample.",
            }
        )

    record = mark_verified(creator_id, confidence, word_count)

    append_entry(
        {
            "event_type": "verification_completed",
            "creator_id": creator_id,
            "confidence": confidence,
            "llm_human_score": result["llm_human_score"],
            "cognitive_pattern_score": result["cognitive_pattern_score"],
            "stylometric_score": result["stylometric_score"],
            "doc_type": result["doc_type"],
            "status": "verified",
        }
    )

    return jsonify(
        {
            "creator_id": creator_id,
            "verified": True,
            "confidence": confidence,
            "verified_at": record["verified_at"],
            "certificate_label": CERTIFICATE_LABEL,
        }
    )


@app.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json(silent=True) or {}
    content_id = data.get("content_id")
    creator_reasoning = data.get("creator_reasoning")

    if not content_id or not creator_reasoning:
        return jsonify({"error": "content_id and creator_reasoning are required"}), 400

    prior = get_latest_entry_by_content_id(content_id)
    if prior is None:
        return jsonify({"error": "content_id not found"}), 404

    status_before = prior.get("status")
    status_after = "under_review"
    appeal_logged_at = datetime.now(timezone.utc).isoformat()

    append_entry(
        {
            "event_type": "appeal_submitted",
            "content_id": content_id,
            "creator_id": prior.get("creator_id"),
            "attribution": prior.get("attribution"),
            "confidence": prior.get("confidence"),
            "llm_human_score": prior.get("llm_human_score"),
            "cognitive_pattern_score": prior.get("cognitive_pattern_score"),
            "stylometric_score": prior.get("stylometric_score"),
            "doc_type": prior.get("doc_type"),
            "status": status_after,
            "status_before": status_before,
            "status_after": status_after,
            "appeal_reasoning": creator_reasoning,
        }
    )

    return jsonify(
        {
            "content_id": content_id,
            "status": status_after,
            "message": "Appeal received and queued for review.",
            "appeal_logged_at": appeal_logged_at,
        }
    )


@app.route("/log", methods=["GET"])
def log():
    return jsonify({"entries": get_entries()})


@app.route("/analytics", methods=["GET"])
def analytics():
    return jsonify(compute_analytics(get_all_entries()))


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
