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


@app.route("/submit", methods=["POST"])
@limiter.limit("5 per minute;50 per day")
def submit():
    data = request.get_json(silent=True) or {}
    text = data.get("text")
    creator_id = data.get("creator_id")

    if not text or not creator_id:
        return jsonify({"error": "text and creator_id are required"}), 400

    content_id = str(uuid.uuid4())
    signal1 = get_llm_signal(text)
    signal2 = get_cognitive_signal(text)
    signal3 = get_stylometric_signal(text)

    confidence = compute_confidence(
        signal1["llm_human_score"],
        signal2["cognitive_pattern_score"],
        signal3["stylometric_score"],
        signal1["doc_type"],
    )
    attribution = classify_attribution(confidence)
    status = "classified"
    label = get_label(attribution)

    append_entry(
        {
            "event_type": "classification_created",
            "content_id": content_id,
            "creator_id": creator_id,
            "attribution": attribution,
            "confidence": confidence,
            "llm_human_score": signal1["llm_human_score"],
            "cognitive_pattern_score": signal2["cognitive_pattern_score"],
            "stylometric_score": signal3["stylometric_score"],
            "doc_type": signal1["doc_type"],
            "status": status,
        }
    )

    return jsonify(
        {
            "content_id": content_id,
            "creator_id": creator_id,
            "attribution": attribution,
            "confidence": confidence,
            "label": label,
            "signals": {
                "llm_human_score": signal1["llm_human_score"],
                "cognitive_pattern_score": signal2["cognitive_pattern_score"],
                "stylometric_score": signal3["stylometric_score"],
                "doc_type": signal1["doc_type"],
            },
            "status": status,
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
