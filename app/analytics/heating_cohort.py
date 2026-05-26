"""
Kış kombi / ısıtma ideal sıcaklık aralığı (anket seçeneği) için:

1) **Kohort çoğunluğu**: Aynı yaş dilimi + cinsiyet + şehirdeki katılımcıların modu (en sık seçilen aralık).
2) **Random Forest**: Aynı hedef değişkenle eğitilmiş sınıflandırıcı — tek kullanıcı profili için olasılıklar.

Beklenti: «Bu yaşta, bu cinsiyette, bu şehirde çoğunluk hangi aralığı seçmiş?» → kullanıcıyı o «en yakın grup» ile hizala.

Kullanım:
    python -m app.analytics.heating_cohort --age 24 --gender Erkek --city İzmir --height 192 --weight 95
    python -m app.analytics.heating_cohort --from-url  # veriyi URL'den çeker
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from app.analytics.preprocess import (
    GOOGLE_FORMS_CONFIG,
    GOOGLE_FORMS_DEFAULT_EXPORT_URL,
    preprocess_survey,
    run_preprocess_from_url,
)
from app.analytics.random_forest_train import predict_rf_row, train_random_forest_classifier

# Anket sütunu (Google Form)
WINTER_HEATING_COL = (
    "Kışın ısınmak için klima/kombi kullanıyorsanız ideal sıcaklığınız kaçtır? (Örn: 35C)"
)

CITY_COL = "Şu an yaşadığınız şehir:"
GENDER_COL = "Cinsiyetiniz"
AGE_COL = "Yaşınız:"
AGE_BIN_COL = "Yaş_grubu"


def normalize_tr_city(s: object) -> str:
    """Şehir eşlemesi: birleşik İ/i noktalarını kaldır + casefold (CLI/CSV uyumu)."""
    if pd.isna(s):
        return ""
    x = str(s).strip()
    x = unicodedata.normalize("NFKC", x)
    x = "".join(
        ch for ch in unicodedata.normalize("NFKD", x) if unicodedata.category(ch) != "Mn"
    )
    x = x.casefold()
    x = re.sub(r"\s+", " ", x)
    for sep in (",", "("):
        if sep in x:
            x = x.split(sep)[0].strip()
    return x


def normalize_gender(s: object) -> str:
    if pd.isna(s):
        return ""
    return str(s).strip().lower()


def age_to_bin_label(age: int) -> str:
    """preprocess.bin_age ile aynı kesitler."""
    a = float(age)
    if a <= 25:
        return "18-25"
    if a <= 35:
        return "26-35"
    if a <= 45:
        return "36-45"
    return "45+"


@dataclass
class CohortResult:
    """Önce dar filtre (yaş + cinsiyet + şehir); yetersizse genişletilmiş kohort."""

    strict_n: int
    strict_mode: str | None
    strict_distribution: pd.Series
    strict_desc: str
    relaxed_n: int
    relaxed_mode: str | None
    relaxed_distribution: pd.Series
    relaxed_desc: str
    used_relaxed: bool

    @property
    def cohort_size(self) -> int:
        return self.relaxed_n if self.used_relaxed else self.strict_n

    @property
    def mode_setting(self) -> str | None:
        return self.relaxed_mode if self.used_relaxed else self.strict_mode

    @property
    def distribution(self) -> pd.Series:
        return self.relaxed_distribution if self.used_relaxed else self.strict_distribution

    @property
    def filters_desc(self) -> str:
        return self.relaxed_desc if self.used_relaxed else self.strict_desc


def filter_cohort_mask(
    processed: pd.DataFrame,
    *,
    age: int,
    gender: str,
    city: str,
    relax_city: bool = False,
    relax_age: bool = False,
) -> tuple[pd.Series, str]:
    """Boolean maske + insan okunur filtre açıklaması."""
    g = normalize_gender(gender)
    c = normalize_tr_city(city)

    if AGE_BIN_COL in processed.columns and not relax_age:
        want = age_to_bin_label(age)
        m_age = processed[AGE_BIN_COL].astype(str).str.strip() == want
        age_desc = f"{AGE_BIN_COL}={want}"
    else:
        a = pd.to_numeric(processed[AGE_COL], errors="coerce")
        m_age = a.notna() & (a >= 18) & (a <= 80)
        age_desc = "yaş (geniş)"

    m_gen = processed[GENDER_COL].map(normalize_gender) == g

    if CITY_COL in processed.columns and not relax_city:
        m_city = processed[CITY_COL].map(normalize_tr_city) == c
        city_desc = f"sehir={city.strip()}"
    else:
        m_city = pd.Series(True, index=processed.index)
        city_desc = "şehir (tümü)"

    mask = m_age & m_gen & m_city
    desc = f"{age_desc}, cinsiyet={gender}, {city_desc}"
    return mask, desc


def _series_mode(vc: pd.Series) -> str | None:
    return str(vc.index[0]) if len(vc) else None


def cohort_winter_mode(
    processed: pd.DataFrame,
    *,
    age: int,
    gender: str,
    city: str,
    min_cohort: int = 3,
) -> CohortResult:
    """Önce yaş+cinsiyet+şehir; ``n < min_cohort`` ise şehir, sonra yaş gevşetilir."""
    if WINTER_HEATING_COL not in processed.columns:
        raise KeyError(f"Eksik sütun: {WINTER_HEATING_COL}")

    mask_s, desc_s = filter_cohort_mask(
        processed, age=age, gender=gender, city=city, relax_city=False, relax_age=False
    )
    sub_s = processed.loc[mask_s, WINTER_HEATING_COL].dropna()
    sub_s = sub_s[sub_s.astype(str).str.strip() != ""]
    vc_s = sub_s.value_counts()

    if int(vc_s.sum()) >= min_cohort:
        return CohortResult(
            strict_n=int(vc_s.sum()),
            strict_mode=_series_mode(vc_s),
            strict_distribution=vc_s,
            strict_desc=desc_s,
            relaxed_n=int(vc_s.sum()),
            relaxed_mode=_series_mode(vc_s),
            relaxed_distribution=vc_s,
            relaxed_desc=desc_s,
            used_relaxed=False,
        )

    for relax_city, relax_age in ((True, False), (True, True)):
        mask, desc = filter_cohort_mask(
            processed,
            age=age,
            gender=gender,
            city=city,
            relax_city=relax_city,
            relax_age=relax_age,
        )
        sub = processed.loc[mask, WINTER_HEATING_COL].dropna()
        sub = sub[sub.astype(str).str.strip() != ""]
        vc = sub.value_counts()
        n = int(vc.sum())
        if n >= min_cohort or (relax_city and relax_age):
            return CohortResult(
                strict_n=int(vc_s.sum()),
                strict_mode=_series_mode(vc_s),
                strict_distribution=vc_s,
                strict_desc=desc_s,
                relaxed_n=n,
                relaxed_mode=_series_mode(vc),
                relaxed_distribution=vc,
                relaxed_desc=desc,
                used_relaxed=True,
            )

    vc = sub_s.value_counts()
    return CohortResult(
        strict_n=int(vc.sum()),
        strict_mode=_series_mode(vc),
        strict_distribution=vc,
        strict_desc=desc_s,
        relaxed_n=int(vc.sum()),
        relaxed_mode=_series_mode(vc),
        relaxed_distribution=vc,
        relaxed_desc=desc_s,
        used_relaxed=False,
    )


def build_minimal_user_raw_row(
    *,
    age: int,
    gender: str,
    city: str,
    height_cm: float | None = None,
    weight_kg: float | None = None,
) -> pd.DataFrame:
    """Ön işleme sokulacak tek satırlık ham anket satırı (diğer sorular boş)."""
    row: dict[str, Any] = {
        AGE_COL: age,
        GENDER_COL: gender,
        CITY_COL: city,
    }
    if height_cm is not None:
        row["Boyunuz (cm):"] = height_cm
    if weight_kg is not None:
        row["Kilonuz (kg):"] = weight_kg
    return pd.DataFrame([row])


def run_heating_recommendation(
    processed: pd.DataFrame,
    *,
    age: int,
    gender: str,
    city: str,
    height_cm: float | None,
    weight_kg: float | None,
    train_rf: bool = True,
) -> dict[str, Any]:
    co = cohort_winter_mode(processed, age=age, gender=gender, city=city)

    if co.used_relaxed:
        interp = (
            f"Dar kohort ({co.strict_desc}): n={co.strict_n}, "
            f"mod={co.strict_mode!r}. "
            f"En az {3} kişi olmadığı için genişletilmiş kohort ({co.relaxed_desc}): "
            f"n={co.relaxed_n}, mod={co.relaxed_mode!r} (bu gruba hizalama önerisi)."
        )
    else:
        interp = (
            f"Kohort ({co.strict_desc}): n={co.strict_n}, "
            f"en sık seçilen ideal sıcaklık aralığı: {co.strict_mode!r}."
        )

    out: dict[str, Any] = {"cohort": co, "interpretation": interp}

    if train_rf:
        try:
            clf, le, feats, acc, _ = train_random_forest_classifier(
                processed,
                target_col=WINTER_HEATING_COL,
                lifestyle_only=True,
                min_samples=8,
                n_estimators=400,
                max_depth=16,
            )
            user_raw = build_minimal_user_raw_row(
                age=age,
                gender=gender,
                city=city,
                height_cm=height_cm,
                weight_kg=weight_kg,
            )
            user_p = preprocess_survey(user_raw, GOOGLE_FORMS_CONFIG, google_mode=True)
            row = user_p.iloc[0]
            rf_label, rf_probs = predict_rf_row(clf, le, feats, row)
            out["random_forest"] = {
                "predicted_setting": rf_label,
                "class_probabilities": rf_probs,
                "holdout_accuracy": acc,
            }
            out["interpretation_rf"] = (
                f"Random Forest (lifestyle-only ozellikler, hold-out dogruluk ~ {acc:.2f}): "
                f"tahmin edilen aralik {rf_label!r}."
            )
        except Exception as exc:
            out["random_forest_error"] = str(exc)
            out["interpretation_rf"] = f"Random Forest çalıştırılamadı: {exc}"
    return out


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
    p = argparse.ArgumentParser(description="Kış ısıtma aralığı — kohort modu + RF")
    p.add_argument("--age", type=int, default=24)
    p.add_argument("--gender", default="Erkek")
    p.add_argument(
        "--city",
        default="izmir",
        help="Kucuk harf ASCII onerilir (Windows konsol kodlamasi); Izmir/IZMIR eslenir.",
    )
    p.add_argument("--height", type=float, default=192.0)
    p.add_argument("--weight", type=float, default=95.0)
    p.add_argument("--processed", type=Path, default=None, help="İşlenmiş CSV yolu")
    p.add_argument("--from-url", type=str, default=None, help="Ham CSV URL (varsayılan: Google export)")
    p.add_argument("--no-rf", action="store_true", help="Sadece kohort modu")
    return p


def main() -> None:
    args = _arg_parser().parse_args()
    proc = _load_processed_csv(args)

    res = run_heating_recommendation(
        proc,
        age=args.age,
        gender=args.gender,
        city=args.city,
        height_cm=args.height,
        weight_kg=args.weight,
        train_rf=not args.no_rf,
    )
    print(res["interpretation"])
    if res.get("interpretation_rf"):
        print(res["interpretation_rf"])
    print("\nDagilim (kullanilan kohort, ust 10):")
    print(res["cohort"].distribution.head(10).to_string())
    if "random_forest" in res:
        print("\nRF olasılıkları:")
        for k, v in sorted(res["random_forest"]["class_probabilities"].items(), key=lambda x: -x[1])[:8]:
            print(f"  {k}: {v:.3f}")


if __name__ == "__main__":
    main()
