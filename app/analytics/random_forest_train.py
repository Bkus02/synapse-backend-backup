"""
Ön işlenmiş anket verisi üzerinde Random Forest sınıflandırıcı eğitimi.

Varsayılan hedef: ``BMI_kategori`` (Yaşam alışkanlığı + ortam tercihlerinden BMI sınıfı — tezde yorum gerektirir).

Kullanım:
    python -m app.analytics.random_forest_train
    python -m app.analytics.random_forest_train --input yerel.csv --no-google
    python -m app.analytics.random_forest_train --target BMI_kategori --save-model
"""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from app.analytics.preprocess import (
    DEFAULT_CONFIG,
    GOOGLE_FORMS_CONFIG,
    GOOGLE_FORMS_DEFAULT_EXPORT_URL,
    preprocess_survey,
    read_survey_csv,
    run_preprocess_from_url,
)


def _drop_pii_and_text_columns(columns: list[str]) -> set[str]:
    out: set[str] = set()
    needles = (
        "e-posta",
        "email",
        "kvkk",
        "zaman damgası",
        "onaylıyorum",
        "adresi",
    )
    for c in columns:
        cl = str(c).lower()
        if any(n in cl for n in needles):
            out.add(c)
    return out


def _numeric_bool_columns(df: pd.DataFrame) -> list[str]:
    out: list[str] = []
    for c in df.columns:
        if pd.api.types.is_bool_dtype(df[c]):
            out.append(c)
        elif pd.api.types.is_numeric_dtype(df[c]):
            out.append(c)
    return out


def build_xy(
    processed: pd.DataFrame,
    target_col: str,
    *,
    lifestyle_only: bool = False,
) -> tuple[pd.DataFrame, np.ndarray, LabelEncoder]:
    if target_col not in processed.columns:
        raise KeyError(f"Hedef sütun yok: {target_col}")

    y_raw = processed[target_col]
    mask = y_raw.notna() & (y_raw.astype(str).str.strip() != "")
    df = processed.loc[mask].copy()
    y_raw = df[target_col]

    drop_exact = {target_col}
    if target_col == "BMI_kategori":
        drop_exact.add("BMI")

    drop_exact |= _drop_pii_and_text_columns(list(df.columns))

    X = df.drop(columns=[c for c in drop_exact if c in df.columns], errors="ignore")

    if lifestyle_only:
        for c in list(X.columns):
            cs = str(c).lower()
            if any(
                k in cs
                for k in (
                    "kilo",
                    "boy",
                    "clean_kg",
                    "clean_cm",
                    "weight",
                    "height",
                )
            ):
                X = X.drop(columns=[c], errors="ignore")

    num_cols = _numeric_bool_columns(X)
    X = X[num_cols].copy()
    for col in X.columns:
        if pd.api.types.is_bool_dtype(X[col]):
            X[col] = X[col].astype(np.float64)

    X = X.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    le = LabelEncoder()
    y = le.fit_transform(y_raw.astype(str))

    return X, y, le


def align_feature_row_to_model(
    row: pd.Series, feature_names: list[str]
) -> pd.DataFrame:
    """Tek kullanıcı satırını eğitimdeki özellik sırası ve boyuta hizalar (eksik → 0)."""
    data: dict[str, float] = {}
    for f in feature_names:
        v = row[f] if f in row.index else 0.0
        if pd.isna(v):
            v = 0.0
        data[f] = float(v)
    return pd.DataFrame([data])


def predict_rf_row(
    clf: RandomForestClassifier,
    le: LabelEncoder,
    feature_names: list[str],
    row: pd.Series,
) -> tuple[str, dict[str, float]]:
    """Sınıf etiketi ve sınıf olasılıkları (ham kategori adları)."""
    X = align_feature_row_to_model(row, feature_names)
    idx = clf.predict(X).ravel()[0]
    label = str(le.inverse_transform([idx])[0])
    probs = clf.predict_proba(X)[0]
    dist = {str(c): float(p) for c, p in zip(le.classes_, probs, strict=False)}
    return label, dist


def train_random_forest_classifier(
    processed: pd.DataFrame,
    target_col: str = "BMI_kategori",
    test_size: float = 0.25,
    random_state: int = 42,
    n_estimators: int = 300,
    max_depth: int | None = 12,
    *,
    lifestyle_only: bool = False,
    min_samples: int = 10,
) -> tuple[RandomForestClassifier, LabelEncoder, list[str], float, str]:
    X, y, le = build_xy(processed, target_col, lifestyle_only=lifestyle_only)
    if len(X) < min_samples:
        raise ValueError(f"Çok az örnek: n={len(X)} (min {min_samples}).")
    if X.shape[1] == 0:
        raise ValueError("Özellik matrisi boş — tüm sütunlar nesne tipinde veya çıkarıldı.")

    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y
        )
    except ValueError:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state
        )

    clf = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=random_state,
        class_weight="balanced_subsample",
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)
    pred = clf.predict(X_test)
    acc = float(accuracy_score(y_test, pred))
    report = classification_report(
        y_test, pred, target_names=le.classes_.tolist(), zero_division=0
    )
    feature_names = X.columns.tolist()
    return clf, le, feature_names, acc, report


def run_full_pipeline(
    source: str | Path,
    *,
    from_url: bool,
    google_mode: bool,
    processed_csv: Path | None,
    target_col: str,
    save_model: bool,
    model_path: Path,
    lifestyle_only: bool = False,
) -> None:
    cfg = GOOGLE_FORMS_CONFIG if google_mode else DEFAULT_CONFIG

    if from_url:
        url = str(source)
        if processed_csv:
            run_preprocess_from_url(url, processed_csv, google_mode=True)
            processed = pd.read_csv(processed_csv, encoding="utf-8-sig")
        else:
            df = read_survey_csv(url)
            processed = preprocess_survey(df, cfg, google_mode=True)
    else:
        df = read_survey_csv(source)
        processed = preprocess_survey(df, cfg, google_mode=google_mode)
        if processed_csv:
            processed_csv.parent.mkdir(parents=True, exist_ok=True)
            processed.to_csv(processed_csv, index=False, encoding="utf-8-sig")

    clf, le, feats, acc, report = train_random_forest_classifier(
        processed, target_col=target_col, lifestyle_only=lifestyle_only
    )
    print(f"Random Forest — hedef: {target_col}")
    print(f"Doğruluk (hold-out): {acc:.4f}")
    print(report)

    imp = pd.Series(clf.feature_importances_, index=feats).sort_values(ascending=False).head(15)
    print("Önem (top 15):\n", imp.to_string())

    if save_model:
        model_path.parent.mkdir(parents=True, exist_ok=True)
        bundle = {
            "model": clf,
            "label_encoder": le,
            "feature_columns": feats,
            "target": target_col,
        }
        joblib.dump(bundle, model_path)
        print(f"Model kaydedildi: {model_path}")


def _arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Synapse anket → RF sınıflandırıcı")
    src = p.add_mutually_exclusive_group(required=False)
    src.add_argument(
        "--url",
        default=GOOGLE_FORMS_DEFAULT_EXPORT_URL,
        help="Google Sheets CSV URL",
    )
    src.add_argument("--input", "-i", type=Path, help="Yerel ham CSV")
    p.add_argument(
        "--no-google",
        action="store_true",
        help="Yerel dosyada varsayılan (kısa) sütun adları kullan",
    )
    p.add_argument(
        "--processed-out",
        type=Path,
        default=None,
        help="İşlenmiş CSV kaydı (varsayılan: URL ile app/analytics/processed_synapse_data.csv)",
    )
    p.add_argument(
        "--target",
        default="BMI_kategori",
        help="Tahmin hedefi sütunu (varsayılan: BMI_kategori)",
    )
    p.add_argument("--save-model", action="store_true")
    p.add_argument(
        "--model-path",
        type=Path,
        default=Path(__file__).resolve().parent / "rf_bmi_category.joblib",
    )
    p.add_argument(
        "--lifestyle-only",
        action="store_true",
        help="Boy/kilo (ve türetilmiş clean) sütunlarını özelliklerden çıkar — BMI sınıfı için daha zor ama daha anlamlı senaryo",
    )
    return p


def main() -> None:
    args = _arg_parser().parse_args()
    google_mode = not args.no_google
    if args.input is not None:
        proc_out = args.processed_out or (Path(__file__).resolve().parent / "processed_synapse_data.csv")
        run_full_pipeline(
            args.input,
            from_url=False,
            google_mode=google_mode,
            processed_csv=proc_out,
            target_col=args.target,
            save_model=args.save_model,
            model_path=args.model_path,
            lifestyle_only=args.lifestyle_only,
        )
    else:
        proc_out = args.processed_out or (Path(__file__).resolve().parent / "processed_synapse_data.csv")
        run_full_pipeline(
            args.url,
            from_url=True,
            google_mode=True,
            processed_csv=proc_out,
            target_col=args.target,
            save_model=args.save_model,
            model_path=args.model_path,
            lifestyle_only=args.lifestyle_only,
        )


if __name__ == "__main__":
    main()
