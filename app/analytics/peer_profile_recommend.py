"""
Yas, cinsiyet, BMI ve sehire gore benzer katilimcilari (k-NN tarzi agirlikli uzaklik)
bulur; diger anket sorularinda kohort cogunlugunu / sik secenekleri onerir.

Mantik:
  1) Once dar kume: ayni yas grubu + cinsiyet + normalize edilmis sehir.
  2) Yetersiz kisi ise siralama: sehri gevset -> yas grubunu gevset (cinsiyet korunur).
  3) Ayni kume icinde uzaklik: |yas - yas_i|, |BMI - BMI_i| (olcekli) + sehir/cinsiyet cezalari.

Kullanim:
    python -m app.analytics.peer_profile_recommend --age 24 --gender Erkek --city izmir --height 180 --weight 80
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.analytics.heating_cohort import (
    AGE_BIN_COL,
    AGE_COL,
    CITY_COL,
    GENDER_COL,
    age_to_bin_label,
    normalize_gender,
    normalize_tr_city,
)
from app.analytics.preprocess import GOOGLE_FORMS_CONFIG, run_preprocess_from_url

GOOGLE_FORMS_DEFAULT_EXPORT_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "14txb7jxbjDVtDa7HskwT6HHVlgPQak5Ib5U0HLl1uGE/export?format=csv"
)

_CFG = GOOGLE_FORMS_CONFIG

# Coklu secim metinleri (virgulle ayrilmis) -> secenek bazli sayim
MULTISELECT_QUESTION_COLS: tuple[str, ...] = (
    _CFG.multiselect_devices,
    _CFG.multiselect_vacuum_sensitivity,
)

_EXCLUDE_NAMES: frozenset[str] = frozenset(
    {
        "Zaman damgası",
        _CFG.age,
        _CFG.gender,
        _CFG.city,
        _CFG.height_cm,
        _CFG.weight_kg,
        "E-posta Adresi",
        "KVKK Aydınlatma Metni ",
        "BMI",
        "BMI_kategori",
        "Yaş_grubu",
        "yas_sayi",
        "evde_kisi_sayisi",
        "cinsiyet_label",
        "cold_start_group",
    }
)


def _split_multiselect_cell(value: object, *, separators: str = r"[,;]+") -> list[str]:
    """Google Form coklu secim: virgul/noktali virgul (slash secenek metninin parcasi olabilir)."""
    if pd.isna(value) or value is None:
        return []
    parts = re.split(separators, str(value).strip())
    return [p.strip() for p in parts if p and str(p).strip()]


def _is_recommendation_column(name: str) -> bool:
    n = str(name).strip()
    if not n or n in _EXCLUDE_NAMES:
        return False
    low = n.casefold()
    if "kvkk" in low:
        return False
    if "e-posta" in low or "eposta" in low.replace("-", ""):
        return False
    if n.startswith("ms_") or n.startswith("sehir__"):
        return False
    for suf in ("_ordinal", "_clean_cm", "_clean_kg", "_saat_decimal"):
        if n.endswith(suf):
            return False
    return True


def list_recommendation_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if _is_recommendation_column(c)]


def compute_bmi_scalar(height_cm: float, weight_kg: float) -> float:
    h = float(height_cm) / 100.0
    return float(weight_kg) / (h * h)


@dataclass
class PeerGroupResult:
    """Benzer kisiler ve hangi filtre katmaninin kullanildigi."""

    peer_indices: np.ndarray
    n_peers: int
    tier_label: str
    distance_weights: dict[str, float] = field(default_factory=dict)


def _standardize_diff(
    series: pd.Series, query_val: float, mask: pd.Series
) -> tuple[float, pd.Series]:
    sub = series.loc[mask]
    std = float(sub.std(ddof=0))
    if not np.isfinite(std) or std < 1e-6:
        std = 1.0
    centered = (series - query_val) / std
    return std, centered.abs()


def _peer_distance_scores(
    df: pd.DataFrame,
    *,
    age: int,
    gender: str,
    city: str,
    user_bmi: float | None,
    mask: pd.Series,
    w_age: float = 1.0,
    w_bmi: float = 1.2,
    w_city_miss: float = 2.5,
    w_gender_miss: float = 5.0,
) -> pd.Series:
    """Dusuk = daha yakin (benzer). Sadece mask True satirlar anlamli."""
    gq = normalize_gender(gender)
    cq = normalize_tr_city(city)

    gen_match = (df[GENDER_COL].map(normalize_gender) == gq).astype(np.float64)
    city_match = (df[CITY_COL].map(normalize_tr_city) == cq).astype(np.float64)

    age_num = pd.to_numeric(df[AGE_COL], errors="coerce")
    _, age_term = _standardize_diff(age_num, float(age), mask)

    if user_bmi is not None and "BMI" in df.columns:
        bmi_s = pd.to_numeric(df["BMI"], errors="coerce")
        _, bmi_term = _standardize_diff(bmi_s, float(user_bmi), mask)
        valid_bmi = mask & bmi_s.notna()
        if valid_bmi.any():
            fillv = float(bmi_term.loc[valid_bmi].max())
            if not np.isfinite(fillv):
                fillv = 3.0
        else:
            fillv = 0.0
        bmi_term = bmi_term.fillna(fillv)
    else:
        bmi_term = pd.Series(0.0, index=df.index)

    d = (
        w_age * age_term**2
        + w_bmi * bmi_term**2
        + w_gender_miss * (1.0 - gen_match)
        + w_city_miss * (1.0 - city_match)
    )
    d = d.where(mask, np.inf)
    return d


def find_peer_group(
    df: pd.DataFrame,
    *,
    age: int,
    gender: str,
    city: str,
    height_cm: float | None,
    weight_kg: float | None,
    bmi: float | None = None,
    k: int = 25,
    min_peers: int = 5,
) -> PeerGroupResult:
    """
    Gevsetmeli filtre + BMI/yas ile ic siralama. En fazla ``k`` komsu.
    """
    user_bmi: float | None
    if bmi is not None:
        user_bmi = float(bmi)
    elif height_cm is not None and weight_kg is not None:
        user_bmi = compute_bmi_scalar(height_cm, weight_kg)
    else:
        user_bmi = None

    gq = normalize_gender(gender)
    cq = normalize_tr_city(city)
    want_bin = age_to_bin_label(age)

    m_age_bin = df[AGE_BIN_COL].astype(str).str.strip() == want_bin if AGE_BIN_COL in df.columns else pd.Series(True, index=df.index)
    m_gen = df[GENDER_COL].map(normalize_gender) == gq
    m_city = df[CITY_COL].map(normalize_tr_city) == cq if CITY_COL in df.columns else pd.Series(True, index=df.index)
    m_age_wide = pd.to_numeric(df[AGE_COL], errors="coerce").between(18, 80, inclusive="both")

    tiers: list[tuple[str, pd.Series]] = [
        ("yas_grubu+cinsiyet+sehir", m_age_bin & m_gen & m_city),
        ("yas_grubu+cinsiyet (sehir tumu)", m_age_bin & m_gen & m_age_wide),
        ("cinsiyet+sehir (yas genis)", m_gen & m_city & m_age_wide),
        ("cinsiyet (yas ve sehir genis)", m_gen & m_age_wide),
    ]

    chosen_mask: pd.Series | None = None
    tier_label = ""

    for label, m in tiers:
        n = int(m.sum())
        if n >= min_peers:
            chosen_mask, tier_label = m, label
            break

    if chosen_mask is None:
        chosen_mask = m_gen & m_age_wide
        tier_label = "cinsiyet (minimum kohort)"

    scores = _peer_distance_scores(
        df,
        age=age,
        gender=gender,
        city=city,
        user_bmi=user_bmi,
        mask=chosen_mask,
    )

    finite = scores.replace([np.inf, -np.inf], np.nan).dropna()
    if finite.empty:
        raise ValueError("Aday kohort bos; veri veya filtreleri kontrol edin.")

    k_eff = min(k, len(finite))
    smallest = finite.nsmallest(k_eff)
    idx = smallest.index.to_numpy()

    return PeerGroupResult(
        peer_indices=idx,
        n_peers=len(idx),
        tier_label=tier_label,
        distance_weights={"w_age": 1.0, "w_bmi": 1.2, "w_city_miss": 2.5, "w_gender_miss": 5.0},
    )


def _aggregate_column(
    series: pd.Series,
    *,
    col_name: str,
    top_n: int,
) -> list[tuple[str, float]]:
    s = series.dropna()
    s = s[s.astype(str).str.strip() != ""]
    if s.empty:
        return []

    if col_name in MULTISELECT_QUESTION_COLS:
        tokens: list[str] = []
        for cell in s:
            tokens.extend(_split_multiselect_cell(cell))
        if not tokens:
            return []
        vc = pd.Series(tokens).value_counts()
        total = float(vc.sum())
        out = [(str(i), float(c) / total) for i, c in vc.head(top_n).items()]
        return out

    vc = s.astype(str).value_counts()
    total = float(vc.sum())
    return [(str(i), float(c) / total) for i, c in vc.head(top_n).items()]


@dataclass
class ColumnRecommendation:
    question: str
    top_options: list[tuple[str, float]]


def recommend_from_peers(
    df: pd.DataFrame,
    peer_indices: np.ndarray,
    *,
    top_n: int = 3,
    columns: list[str] | None = None,
) -> list[ColumnRecommendation]:
    cols = columns if columns is not None else list_recommendation_columns(df)
    sub = df.loc[peer_indices]
    out: list[ColumnRecommendation] = []
    for c in cols:
        if c not in df.columns:
            continue
        opts = _aggregate_column(sub[c], col_name=c, top_n=top_n)
        if opts:
            out.append(ColumnRecommendation(question=c, top_options=opts))
    return out


def run_peer_profile_recommendations(
    df: pd.DataFrame,
    *,
    age: int,
    gender: str,
    city: str,
    height_cm: float | None = None,
    weight_kg: float | None = None,
    bmi: float | None = None,
    k: int = 25,
    min_peers: int = 5,
    top_n: int = 3,
) -> dict[str, Any]:
    peers = find_peer_group(
        df,
        age=age,
        gender=gender,
        city=city,
        height_cm=height_cm,
        weight_kg=weight_kg,
        bmi=bmi,
        k=k,
        min_peers=min_peers,
    )
    recs = recommend_from_peers(df, peers.peer_indices, top_n=top_n)
    return {
        "peer_group": peers,
        "recommendations": recs,
        "profile_summary": {
            "age": age,
            "gender": gender,
            "city": city,
            "bmi": (
                float(bmi)
                if bmi is not None
                else (
                    compute_bmi_scalar(height_cm, weight_kg)
                    if height_cm is not None and weight_kg is not None
                    else None
                )
            ),
        },
    }


def _load_processed_csv(args: argparse.Namespace) -> pd.DataFrame:
    out_csv = Path(__file__).resolve().parent / "processed_synapse_data.csv"
    if args.processed is not None:
        return pd.read_csv(args.processed, encoding="utf-8-sig")
    if args.from_url is not None:
        run_preprocess_from_url(args.from_url, out_csv)
        return pd.read_csv(out_csv, encoding="utf-8-sig")
    if out_csv.is_file():
        return pd.read_csv(out_csv, encoding="utf-8-sig")
    run_preprocess_from_url(GOOGLE_FORMS_DEFAULT_EXPORT_URL, out_csv)
    return pd.read_csv(out_csv, encoding="utf-8-sig")


def _arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Yas/cinsiyet/BMI/sehir ile benzer gruba gore cok sorulu oneri"
    )
    p.add_argument("--age", type=int, required=True)
    p.add_argument("--gender", type=str, required=True)
    p.add_argument("--city", type=str, default="izmir")
    p.add_argument("--height", type=float, default=None, help="cm (BMI icin)")
    p.add_argument("--weight", type=float, default=None, help="kg (BMI icin)")
    p.add_argument("--bmi", type=float, default=None, help="Boy/kilo yerine dogrudan BMI")
    p.add_argument("--k", type=int, default=25, help="En fazla komsu sayisi")
    p.add_argument("--min-peers", type=int, default=5, help="Gevsetme esigi")
    p.add_argument("--top", type=int, default=3, help="Soru basina en cok N secenek")
    p.add_argument("--processed", type=Path, default=None)
    p.add_argument("--from-url", type=str, default=None)
    return p


def main() -> None:
    args = _arg_parser().parse_args()
    if args.bmi is None and (args.height is None or args.weight is None):
        raise SystemExit("BMI icin --height ve --weight veya --bmi verin.")

    df = _load_processed_csv(args)
    res = run_peer_profile_recommendations(
        df,
        age=args.age,
        gender=args.gender,
        city=args.city,
        height_cm=args.height,
        weight_kg=args.weight,
        bmi=args.bmi,
        k=args.k,
        min_peers=args.min_peers,
        top_n=args.top,
    )

    pg: PeerGroupResult = res["peer_group"]
    print(f"Kullanilan benzerlik katmani: {pg.tier_label}")
    print(f"Komsu sayisi (k<={args.k}): {pg.n_peers}")
    if res["profile_summary"]["bmi"] is not None:
        print(f"Profil BMI: {res['profile_summary']['bmi']:.2f}")
    print("")
    for block in res["recommendations"]:
        print(block.question)
        for val, share in block.top_options:
            print(f"  {share*100:5.1f}%  {val}")
        print("")


if __name__ == "__main__":
    main()
