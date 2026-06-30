import os
import uuid

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from audit_log import append_entry, get_entries
from confidence import compute_confidence
from signals.cognitive_signal import get_cognitive_signal
from signals.llm_signal import get_llm_signal

load_dotenv()

app = Flask(__name__)


def classify_attribution(confidence):
    if confidence < 0.35:
        return "likely_ai"
    if confidence > 0.70:
        return "likely_human"
    return "uncertain"


@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json(silent=True) or {}
    text = data.get("text")
    creator_id = data.get("creator_id")

    if not text or not creator_id:
        return jsonify({"error": "text and creator_id are required"}), 400

    content_id = str(uuid.uuid4())
    signal1 = get_llm_signal(text)
    signal2 = get_cognitive_signal(text)

    confidence = compute_confidence(
        signal1["llm_human_score"], signal2["cognitive_pattern_score"], signal1["doc_type"]
    )
    attribution = classify_attribution(confidence)
    status = "classified"

    append_entry(
        {
            "event_type": "classification_created",
            "content_id": content_id,
            "creator_id": creator_id,
            "attribution": attribution,
            "confidence": confidence,
            "llm_human_score": signal1["llm_human_score"],
            "cognitive_pattern_score": signal2["cognitive_pattern_score"],
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
            "label": f"[placeholder label] attribution={attribution}",
            "signals": {
                "llm_human_score": signal1["llm_human_score"],
                "cognitive_pattern_score": signal2["cognitive_pattern_score"],
                "doc_type": signal1["doc_type"],
            },
            "status": status,
        }
    )


@app.route("/log", methods=["GET"])
def log():
    return jsonify({"entries": get_entries()})


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
