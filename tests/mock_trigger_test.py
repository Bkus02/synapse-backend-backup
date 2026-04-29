import asyncio
import logging
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.analytics.decision_engine import process_decision


async def _run_scenario(title: str, mock_event: dict):
    print(f"\n=== {title} ===")
    print("--- [SISTEME GIRDI] ---")
    print(
        f"Olay: {mock_event['device_id']} {mock_event['action']} | Saat: {mock_event['timestamp'].strftime('%H:%M')}"
    )
    print("Synapse Karar Motoru calistiriliyor...\n")

    decision = await process_decision(mock_event)

    print("--- [SISTEM CIKTISI] ---")
    if decision:
        print("BILDIRIM TETIKLENDI!")
        print(f"Tip: {decision['type']}")
        print(f"Mesaj: {decision['message']}")
        print(f"Guven Skoru: %{decision['confidence_score'] * 100:.1f}")
        print(f"Baglam: {decision['context']}")
    else:
        print("Karar: Herhangi bir aksiyon gerekmiyor (Dusuk guven veya anlamsiz baglam).")


async def simulate_ac_event():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    # Senaryo-1: Aksam, normal karar (bildirim beklenir)
    evening_event = {
        "device_id": "AC_01",
        "action": "ON",
        "timestamp": datetime.now().replace(hour=20, minute=30, second=0, microsecond=0),
        "user_id": "U001",
        "history_log_count": 38,
        "sequence_rules": [
            {"trigger": "AC_01_ON", "target": "LIGHT_ON", "confidence": 0.86, "context": "Night"}
        ],
        "cold_start_confidence": 0.62,
    }

    # Senaryo-2: Gündüz context-guard (lamba acma engeli beklenir)
    daytime_guard_event = {
        "device_id": "AC_01",
        "action": "ON",
        "timestamp": datetime.now().replace(hour=11, minute=0, second=0, microsecond=0),
        "user_id": "U001",
        "history_log_count": 45,
        "sequence_rules": [
            {"trigger": "AC_01_ON", "target": "LIGHT_ON", "confidence": 0.92, "context": "Morning"}
        ],
        "cold_start_confidence": 0.72,
    }

    # Senaryo-3: Dusuk guven (sessiz kalma beklenir)
    low_conf_event = {
        "device_id": "AC_01",
        "action": "ON",
        "timestamp": datetime.now().replace(hour=21, minute=15, second=0, microsecond=0),
        "user_id": "U001",
        "history_log_count": 5,
        "sequence_rules": [
            {"trigger": "AC_01_ON", "target": "LIGHT_ON", "confidence": 0.20, "context": "Night"}
        ],
        "cold_start_confidence": 0.25,
    }

    await _run_scenario("Senaryo 1 - Aksam Bildirim", evening_event)
    await _run_scenario("Senaryo 2 - Gunduz Context Guard", daytime_guard_event)
    await _run_scenario("Senaryo 3 - Dusuk Guven", low_conf_event)


if __name__ == "__main__":
    asyncio.run(simulate_ac_event())

