from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.analytics.preprocess import compute_bmi_kg_m2
from app.analytics.time_utils import encode_time_cyclic


@dataclass(frozen=True)
class SurveyColumns:
    age: str = "Yaşınız:"
    gender: str = "Cinsiyetiniz"
    city: str = "Şu an yaşadığınız şehir:"
    height_cm: str = "Boyunuz (cm):"
    weight_kg: str = "Kilonuz (kg):"
    bmi: str = "BMI"
    age_group: str = "Yaş_grubu"


@dataclass(frozen=True)
class DistanceWeights:
    age: float = 1.0
    bmi: float = 1.2
    city: float = 2.5
    gender: float = 5.0


@dataclass(frozen=True)
class EngineConfig:
    columns: SurveyColumns = SurveyColumns()
    weights: DistanceWeights = DistanceWeights()
    min_peers: int = 20
    top_k: int = 30
    max_distance: float | None = None
    recommendation_top_n: int = 1


def _normalize_text(value: object) -> str:
    if pd.isna(value) or value is None:
        return ""
    return str(value).strip().casefold()


def _age_to_bin(age: float) -> str:
    if age <= 25:
        return "18-25"
    if age <= 35:
        return "26-35"
    if age <= 45:
        return "36-45"
    return "45+"


def _safe_prefix(col: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", col).strip("_").lower()


def _is_time_like_series(series: pd.Series, min_ratio: float = 0.7) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    sample = series.dropna().astype(str).head(40)
    if sample.empty:
        return False
    parsed = pd.to_datetime(sample, format="%H:%M:%S", errors="coerce")
    fallback = parsed.isna()
    if fallback.any():
        parsed.loc[fallback] = pd.to_datetime(sample.loc[fallback], format="%H:%M", errors="coerce")
    ok_ratio = float(parsed.notna().mean())
    return ok_ratio >= min_ratio


def _candidate_time_columns(df: pd.DataFrame) -> list[str]:
    cols: list[str] = []
    for c in df.columns:
        lc = str(c).casefold()
        if "saat" in lc or "time" in lc:
            cols.append(c)
            continue
        if df[c].dtype == object and _is_time_like_series(df[c]):
            cols.append(c)
    # duplicate guard (order preserved)
    return list(dict.fromkeys(cols))


def load_and_preprocess_data(csv_path: str | Path, config: EngineConfig = EngineConfig()) -> pd.DataFrame:
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    out = df.copy()
    c = config.columns

    if c.bmi not in out.columns and c.height_cm in out.columns and c.weight_kg in out.columns:
        out[c.bmi] = compute_bmi_kg_m2(out[c.height_cm], out[c.weight_kg])

    if c.age_group not in out.columns and c.age in out.columns:
        ages = pd.to_numeric(out[c.age], errors="coerce")
        out[c.age_group] = ages.map(lambda x: _age_to_bin(float(x)) if np.isfinite(x) else np.nan)

    for time_col in _candidate_time_columns(out):
        out = encode_time_cyclic(out, time_col, output_prefix=f"{_safe_prefix(time_col)}_cyc")

    return out


def _standardized_abs_diff(values: pd.Series, query_val: float) -> pd.Series:
    v = pd.to_numeric(values, errors="coerce")
    std = float(v.std(ddof=0))
    if not np.isfinite(std) or std < 1e-6:
        std = 1.0
    return ((v - float(query_val)) / std).abs()


def compute_distance_scores(
    df: pd.DataFrame,
    user_input: dict[str, Any],
    config: EngineConfig = EngineConfig(),
) -> pd.Series:
    c = config.columns
    w = config.weights

    age_q = float(user_input["age"])
    bmi_q = float(user_input["bmi"])
    gender_q = _normalize_text(user_input["gender"])
    city_q = _normalize_text(user_input["city"])

    age_term = _standardized_abs_diff(df[c.age], age_q).fillna(10.0)
    bmi_term = _standardized_abs_diff(df[c.bmi], bmi_q).fillna(10.0)
    gen_match = (df[c.gender].map(_normalize_text) == gender_q).astype(float)
    city_match = (df[c.city].map(_normalize_text) == city_q).astype(float)

    score = (
        w.age * age_term**2
        + w.bmi * bmi_term**2
        + w.gender * (1.0 - gen_match)
        + w.city * (1.0 - city_match)
    )
    return score


def _filter_for_tier(
    df: pd.DataFrame,
    user_input: dict[str, Any],
    *,
    relax_city: bool,
    relax_age_group: bool,
    config: EngineConfig,
) -> pd.Series:
    c = config.columns
    age_group_q = _age_to_bin(float(user_input["age"]))
    gender_q = _normalize_text(user_input["gender"])
    city_q = _normalize_text(user_input["city"])

    m = pd.Series(True, index=df.index)
    m &= df[c.gender].map(_normalize_text) == gender_q
    if not relax_city:
        m &= df[c.city].map(_normalize_text) == city_q
    if not relax_age_group and c.age_group in df.columns:
        m &= df[c.age_group].astype(str) == age_group_q
    return m


def build_peer_group(
    df: pd.DataFrame,
    user_input: dict[str, Any],
    config: EngineConfig = EngineConfig(),
) -> tuple[pd.DataFrame, str]:
    tiers = [
        ("strict(age_group+gender+city)", False, False),
        ("relax_city(age_group+gender)", True, False),
        ("relax_age_group(gender+city)", False, True),
        ("fallback(gender_only)", True, True),
    ]

    distances = compute_distance_scores(df, user_input, config)
    last_name = tiers[-1][0]
    last_peers = df.iloc[0:0]

    for tier_name, relax_city, relax_age_group in tiers:
        mask = _filter_for_tier(
            df,
            user_input,
            relax_city=relax_city,
            relax_age_group=relax_age_group,
            config=config,
        )
        subset = df.loc[mask].copy()
        if subset.empty:
            continue
        subset["distance_score"] = distances.loc[subset.index]
        subset = subset.sort_values("distance_score", ascending=True)
        if config.max_distance is not None:
            subset = subset[subset["distance_score"] <= float(config.max_distance)]

        if len(subset) >= config.min_peers:
            return subset.head(max(config.top_k, config.min_peers)), tier_name
        last_name = tier_name
        last_peers = subset

    if last_peers.empty:
        all_df = df.copy()
        all_df["distance_score"] = distances
        all_df = all_df.sort_values("distance_score", ascending=True)
        return all_df.head(config.min_peers), "global_fallback"
    return last_peers.head(max(config.top_k, config.min_peers)), last_name


def _is_target_column(col: str, config: EngineConfig) -> bool:
    c = config.columns
    excluded = {
        c.age,
        c.gender,
        c.city,
        c.height_cm,
        c.weight_kg,
        c.bmi,
        c.age_group,
        "distance_score",
    }
    if col in excluded:
        return False
    lc = str(col).casefold()
    if lc.startswith("ms_") or lc.startswith("sehir__"):
        return False
    if lc.endswith("_ordinal") or lc.endswith("_saat_decimal"):
        return False
    if lc.endswith("_sin") or lc.endswith("_cos"):
        return False
    if lc.endswith("_clean_cm") or lc.endswith("_clean_kg"):
        return False
    if "zaman damgasi" in lc or "zaman damgası" in lc:
        return False
    if "e-posta" in lc or "kvkk" in lc:
        return False
    return True


def generate_startup_catalog(
    peer_group: pd.DataFrame,
    config: EngineConfig = EngineConfig(),
) -> dict[str, list[dict[str, Any]]]:
    catalog: dict[str, list[dict[str, Any]]] = {}
    for col in peer_group.columns:
        if not _is_target_column(col, config):
            continue
        dtype = peer_group[col].dtype
        is_textual = (
            pd.api.types.is_object_dtype(dtype)
            or pd.api.types.is_string_dtype(dtype)
            or isinstance(dtype, pd.CategoricalDtype)
        )
        if not is_textual:
            continue
        s = peer_group[col].dropna()
        s = s[s.astype(str).str.strip() != ""]
        if s.empty:
            continue
        vc = s.astype(str).value_counts()
        total = float(vc.sum())
        top: list[dict[str, Any]] = []
        for opt, cnt in vc.head(config.recommendation_top_n).items():
            top.append(
                {
                    "option": str(opt),
                    "count": int(cnt),
                    "share": float(cnt) / total,
                }
            )
        catalog[col] = top
    return catalog


def run_cold_start_engine(
    csv_path: str | Path,
    user_input: dict[str, Any],
    config: EngineConfig = EngineConfig(),
) -> dict[str, Any]:
    df = load_and_preprocess_data(csv_path, config)
    peers, tier = build_peer_group(df, user_input, config)
    catalog = generate_startup_catalog(peers, config)
    return {
        "selected_tier": tier,
        "peer_count": int(len(peers)),
        "peer_group": peers,
        "startup_catalog": catalog,
    }


class ColdStartEngine:
    """CSV tabanli cold-start motoru icin basit servis sinifi."""

    def __init__(self, csv_path: str | Path, config: EngineConfig | None = None) -> None:
        self.csv_path = Path(csv_path)
        self.config = config or EngineConfig()
        if not self.csv_path.is_file():
            raise FileNotFoundError(f"CSV bulunamadi: {self.csv_path}")

    def generate_initial_catalog(self, user: dict[str, Any]) -> dict[str, str]:
        if "bmi" in user and user["bmi"] is not None:
            bmi = float(user["bmi"])
        else:
            height = float(user["height"])
            weight = float(user["weight"])
            bmi = weight / ((height / 100.0) ** 2)

        payload = {
            "age": float(user["age"]),
            "gender": user["gender"],
            "city": user["city"],
            "bmi": bmi,
        }
        res = run_cold_start_engine(self.csv_path, payload, self.config)
        catalog = res["startup_catalog"]
        # test/pratik kullanim icin question -> top option
        return {q: opts[0]["option"] for q, opts in catalog.items() if opts}


def _cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Cold-start onerileri (survey_data.csv tabanli)")
    p.add_argument("--input", type=Path, default=Path("survey_data.csv"))
    p.add_argument("--age", type=float, required=True)
    p.add_argument("--gender", type=str, required=True)
    p.add_argument("--city", type=str, required=True)
    p.add_argument("--bmi", type=float, required=True)
    p.add_argument("--min-peers", type=int, default=20)
    p.add_argument("--top-k", type=int, default=30)
    p.add_argument("--top-n", type=int, default=1)
    return p


def main() -> None:
    args = _cli().parse_args()
    cfg = EngineConfig(
        min_peers=args.min_peers,
        top_k=args.top_k,
        recommendation_top_n=args.top_n,
    )
    res = run_cold_start_engine(
        csv_path=args.input,
        user_input={
            "age": args.age,
            "gender": args.gender,
            "city": args.city,
            "bmi": args.bmi,
        },
        config=cfg,
    )
    print(f"tier={res['selected_tier']} peer_count={res['peer_count']}")
    for q, items in res["startup_catalog"].items():
        lead = items[0]
        print(f"- {q}: {lead['option']} ({lead['share']*100:.1f}%)")


if __name__ == "__main__":
    main()

