import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.analytics.cold_start_engine import ColdStartEngine

CSV_PATH = "app/analytics/processed_synapse_data.csv"
TEST_USER = {
    "age": 22,
    "city": "İzmir",
    "gender": "Erkek",
    "height": 180,
    "weight": 75,
}


def test_generate_initial_catalog_returns_non_empty_dict():
    engine = ColdStartEngine(csv_path=CSV_PATH)
    catalog = engine.generate_initial_catalog(TEST_USER)

    assert isinstance(catalog, dict)
    assert len(catalog) > 0


def test_generate_initial_catalog_contains_light_color_recommendation():
    engine = ColdStartEngine(csv_path=CSV_PATH)
    catalog = engine.generate_initial_catalog(TEST_USER)

    key = "Hangi ışık rengi sizi daha huzurlu hissettirir?"
    assert key in catalog
    assert isinstance(catalog[key], str)
    assert catalog[key].strip() != ""

