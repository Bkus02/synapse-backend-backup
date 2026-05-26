"""
Chapter 6: Tests — rapor tablolari uretici.

Calistirma:
    python -m tests.chapter6_report_tables
    pytest tests/ -q --tb=no
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run_pytest() -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _latency_table() -> str:
    from tests.test_habit_latency_benchmark import (
        BENCHMARK_ITERATIONS,
        LOG_COUNT,
        _synthetic_behavior_logs,
        benchmark_habit_matrix_read,
        benchmark_runtime_mining,
    )
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine

    import app.core.models  # noqa: F401 — metadata'ya tum tablolar
    from app.models.habit_matrix import HabitMatrix  # noqa: F401

    logs = _synthetic_behavior_logs(LOG_COUNT)
    runtime = benchmark_runtime_mining(logs, iterations=BENCHMARK_ITERATIONS)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        matrix = benchmark_habit_matrix_read(session, logs, iterations=BENCHMARK_ITERATIONS)

    speedup = runtime["median_ms"] / matrix["median_ms"] if matrix["median_ms"] else 0.0
    lines = [
        "### Tablo 6.1 — Habit Engine gecikme karsilastirmasi (canli mining vs Habit Matrix)",
        "",
        "| Yol | Orta gecikme (ms) | P95 (ms) | Aday kural |",
        "|-----|-------------------|----------|------------|",
        f"| Canli sequence mining (RUNTIME) | {runtime['median_ms']:.3f} | {runtime['p95_ms']:.3f} | {int(runtime['candidates'])} |",
        f"| Habit Matrix okuma (MATRIX) | {matrix['median_ms']:.3f} | {matrix['p95_ms']:.3f} | {int(matrix['candidates'])} |",
        f"| Hizlanma (runtime/matrix) | {speedup:.2f}x | — | — |",
        "",
        f"_Olcum: {BENCHMARK_ITERATIONS} iterasyon, {LOG_COUNT} davranis logu, SQLite in-memory._",
    ]
    return "\n".join(lines)


def _test_summary_table(exit_code: int, output: str) -> str:
    passed = output.count(" passed")
    failed = "FAILED" in output or exit_code != 0
    status = "Basarili" if not failed else "Basarisiz"
    lines = [
        "### Tablo 6.2 — Test paketi ozeti",
        "",
        "| Kategori | Test dosyasi | Durum |",
        "|----------|--------------|-------|",
        "| Anomaly Detection (k=2, AnomalyDetected event) | `test_anomaly_detection.py` | " + ("Gecti" if not failed else "Kontrol") + " |",
        "| Habit latency benchmark | `test_habit_latency_benchmark.py` | " + ("Gecti" if not failed else "Kontrol") + " |",
        "| Cold-start kullanici provisioning | `test_cold_start_user_provisioning.py` | " + ("Gecti" if not failed else "Kontrol") + " |",
        "| Decision engine kurallari | `test_decision_engine_rules.py` | " + ("Gecti" if not failed else "Kontrol") + " |",
        "| Cold-start motoru | `test_cold_start.py` | " + ("Gecti" if not failed else "Kontrol") + " |",
        "",
        f"_pytest cikis kodu: {exit_code}. Ozet: {output.strip().splitlines()[-1] if output.strip() else '—'}_",
    ]
    return "\n".join(lines)


def _anomaly_table() -> str:
    from app.core.domain.anomaly_detection import evaluate_duration_anomaly

    cases = [
        ("Normal (21 dk, ort. 11 dk)", 21.0, [10.0, 12.0, 11.0], False),
        ("Anomali (25 dk, ort. 11 dk, k=2)", 25.0, [10.0, 12.0, 11.0], True),
        ("Sinir (22 dk, ort. 11 dk, k=2)", 22.0, [10.0, 12.0, 11.0], True),
    ]
    rows = ["### Tablo 6.3 — Anomaly Detection (k=2 esik)", "", "| Senaryo | Sure (dk) | Ortalama (dk) | Event? |", "|---------|-----------|---------------|--------|"]
    for label, cur, hist, expected in cases:
        detected, avg = evaluate_duration_anomaly(cur, hist, k=2.0)
        rows.append(f"| {label} | {cur:.0f} | {avg:.1f} | {'Evet' if detected else 'Hayir'} |")
        assert detected == expected
    rows.append("")
    rows.append("_Domain: `evaluate_duration_anomaly`; uygulama katmani `AnomalyDetected` event yayinlar._")
    return "\n".join(rows)


def _cold_start_table() -> str:
    from pathlib import Path as P

    if not P(CSV_PATH := "app/analytics/processed_synapse_data.csv").is_file():
        return "### Tablo 6.4 — Cold-start varsayilan oneriler\n\n_CSV bulunamadi._"

    from app.analytics.cold_start_engine import ColdStartEngine

    user = {"age": 22, "city": "İzmir", "gender": "Erkek", "height": 180, "weight": 75}
    catalog = ColdStartEngine(csv_path=CSV_PATH).generate_initial_catalog(user)
    rows = [
        "### Tablo 6.4 — Cold-start demografik varsayilan oneriler (ornek kullanici)",
        "",
        "| Soru (context) | Onerilen varsayilan |",
        "|----------------|---------------------|",
    ]
    for q, a in list(catalog.items())[:8]:
        rows.append(f"| {q[:60]}{'…' if len(q) > 60 else ''} | {a} |")
    if len(catalog) > 8:
        rows.append(f"| _… ve {len(catalog) - 8} alan daha_ | — |")
    rows.append("")
    rows.append(f"_Toplam {len(catalog)} varsayilan oneri uretildi._")
    return "\n".join(rows)


def main() -> None:
    print("# Chapter 6: Tests — Sonuc Tablolari\n")
    print(_latency_table())
    print()
    print(_anomaly_table())
    print()
    print(_cold_start_table())
    print()
    code, out = _run_pytest()
    print(_test_summary_table(code, out))
    if code != 0:
        print("\n```\n" + out[-2000:] + "\n```")
        sys.exit(code)


if __name__ == "__main__":
    main()
