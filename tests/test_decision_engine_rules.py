from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.analytics.decision_engine import process_decision_sync


def test_conflict_filter_keeps_highest_scored_action():
    event = {
        "trigger": "AC_ON",
        "event_time": "2026-04-29 21:00:00",
        "history_log_count": 20,
        "sequence_rules": [
            {"trigger": "AC_ON", "target": "LIGHT_ON", "confidence": 0.90, "context": "Night"},
            {"trigger": "AC_ON", "target": "NIGHT_MODE_ON", "confidence": 0.85, "context": "Night"},
        ],
        "cold_start_confidence": 0.40,
    }
    out = process_decision_sync(event)
    assert out is not None
    assert out["target"] == "LIGHT_ON"
    assert len(out["recommendations"]) == 1


def test_daylight_light_suggestion_is_blocked():
    event = {
        "trigger": "AC_ON",
        "event_time": "2026-04-29 11:00:00",
        "history_log_count": 25,
        "sequence_rules": [
            {"trigger": "AC_ON", "target": "LIGHT_ON", "confidence": 0.95, "context": "Morning"}
        ],
        "cold_start_confidence": 0.85,
    }
    out = process_decision_sync(event)
    assert out is None

