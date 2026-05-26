"""
Anket verisini Random Forest ve cold-start segmentasyonu için ön işler.

Kullanım:
    python -m app.analytics.preprocess --input veri/anket.csv
    python -m app.analytics.preprocess --from-url "https://docs.google.com/.../export?format=csv"
    python -m app.analytics.preprocess --input indirilen.csv --google

Sütun adları anket dışa aktarımına göre farklı olabilir; SurveyColumnConfig üzerinden güncelleyin.
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import IO
from urllib.error import URLError
from urllib.request import urlopen

import numpy as np
import pandas as pd

from app.analytics.time_utils import apply_cyclic_time_encoding

# ---------------------------------------------------------------------------
# Yapılandırma — anket CSV başlıklarınızla eşleştirin
# ---------------------------------------------------------------------------


@dataclass
class SurveyColumnConfig:
    """Ham anket dosyasındaki sütun adları."""

    height_cm: str = "Boy"
    weight_kg: str = "Kilo"
    age: str = "Yaş"
    city: str = "Yaşanılan Şehir"
    gender: str = "Cinsiyet"
    # Çoklu seçim (metin içinde ayraçla ayrılmış seçenekler)
    multiselect_devices: str = "Kullanılan/İstenen Cihazlar"
    multiselect_vacuum_sensitivity: str = "Süpürge Hassasiyeti"
    # Zaman (örn. "22:00")
    light_on_time: str = "Işık açma saati"
    bedtime: str = "Yatış saati"
    # Ordinal metin
    daily_activity: str = "Hala hareketliliği"
    light_brightness: str = "Işık parlaklığı"

    # Ek çoklu seçim sütunları (isteğe bağlı)
    extra_multiselect: tuple[str, ...] = field(default_factory=tuple)
    # Google Form uzantıları (varsayılan boş)
    light_work: str | None = None
    household: str | None = None


DEFAULT_CONFIG = SurveyColumnConfig()


@dataclass
class GoogleFormsSurveyConfig(SurveyColumnConfig):
    """Google Sheets CSV dışa aktarımı (Synapse anketi)."""

    height_cm: str = "Boyunuz (cm):"
    weight_kg: str = "Kilonuz (kg):"
    age: str = "Yaşınız:"
    city: str = "Şu an yaşadığınız şehir:"
    gender: str = "Cinsiyetiniz"
    multiselect_devices: str = (
        "Evinizde internete bağlanabilen veya telefondan kontrol edilebilen hangi cihazlar var "
        "ya da hangilerini kullanmak istersiniz? (Birden fazla seçebilirsiniz)"
    )
    multiselect_vacuum_sensitivity: str = (
        "Süpürgenin çalışması sizi ne zaman rahatsız eder? (Birden fazla seçebilirsiniz)"
    )
    light_on_time: str = (
        "Bu aylarda (Şubat-Mart-Nisan) ışıkları genellikle saat kaçta açarsınız?"
    )
    bedtime: str = "Yatmadan önce tüm ışıkları kapatma saatiniz genellikle kaçtır?"
    daily_activity: str = "Günlük hareketliliğinizi nasıl tanımlarsınız?"
    light_brightness: str = "Kitap okurken ışığının nasıl olmasını istersiniz?"
    light_work: str | None = "Çalışırken ortam ışığının nasıl olmasını istersiniz?"
    household: str | None = "Evde kaç kişi yaşıyorsunuz?"


GOOGLE_FORMS_CONFIG = GoogleFormsSurveyConfig()

GOOGLE_FORMS_DEFAULT_EXPORT_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "14txb7jxbjDVtDa7HskwT6HHVlgPQak5Ib5U0HLl1uGE/export?format=csv"
)


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def _slug_token(s: str) -> str:
    """Sütun adı için güvenli kısa etiket."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^aA-zZ0-9]+", "_", s).strip("_").lower()
    return s or "opt"


def _split_multiselect_cell(value: object, separators: str = r"[,;|/]+") -> list[str]:
    if pd.isna(value) or value is None:
        return []
    parts = re.split(separators, str(value).strip())
    return [p.strip() for p in parts if p and str(p).strip()]


def parse_height_to_cm(value: object) -> float:
    """
    Google Form karmaşık girişleri: 192, 1.79 (m), 1m65cm, 1/65 (165 cm), 1 59, 1-68.
    """
    if pd.isna(value) or value is None or str(value).strip() == "":
        return np.nan
    s_raw = str(value).strip().lower().replace(",", ".")
    s = re.sub(r"\s+", " ", s_raw)

    m_mcm = re.match(r"^(\d)\s*m\s*(\d{1,2})\s*cm", s)
    if m_mcm:
        return float(m_mcm.group(1)) * 100.0 + float(m_mcm.group(2))

    frac = re.match(r"^(\d)\s*/\s*(\d{2,3})$", s)
    if frac:
        a, b = int(frac.group(1)), int(frac.group(2))
        if a <= 2 and 50 <= b <= 99:
            return float(a * 100 + b)

    if re.search(r"cm|santim", s):
        nums = re.findall(r"\d+(?:\.\d+)?", s)
        if nums:
            return float(nums[0])

    sp = re.match(r"^(\d)\s+(\d{2})$", s.replace(".", ""))
    if sp:
        return float(sp.group(1)) * 100.0 + float(sp.group(2))

    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if not nums:
        return np.nan
    x = float(nums[0])
    if len(nums) >= 2 and x < 3:
        return float(nums[0]) * 100.0 + float(nums[1])
    if x < 2.6:
        return x * 100.0
    if 80.0 <= x <= 250.0:
        return x
    if 2.6 <= x < 80.0:
        return np.nan
    return x


def parse_weight_to_kg(value: object) -> float:
    if pd.isna(value) or value is None or str(value).strip() == "":
        return np.nan
    s = str(value).strip().lower().replace(",", ".")
    s = re.sub(r"kg\.?", "", s).strip()
    nums = re.findall(r"\d+(?:\.\d+)?", s.replace(" ", ""))
    if not nums:
        return np.nan
    return float(nums[0])


def map_activity_ordinal_google(text: object) -> float:
    if pd.isna(text) or str(text).strip() == "":
        return np.nan
    t = str(text).lower()
    if "çok hareketli" in t:
        return 3.0
    if "orta hall" in t:
        return 2.0
    if "çok hareketsiz" in t or "hareketsiz" in t:
        return 1.0
    return np.nan


def map_light_ordinal_google(text: object) -> float:
    """Loş / Orta / Çok parlak — Google tam cümle cevapları."""
    if pd.isna(text) or str(text).strip() == "":
        return np.nan
    t = str(text).lower()
    if "çok parlak" in t or "yüksek odak" in t:
        return 3.0
    if "orta (" in t or t.startswith("orta "):
        return 2.0
    if "loş" in t:
        return 1.0
    return np.nan


def parse_household_count(value: object) -> float:
    if pd.isna(value) or str(value).strip() == "":
        return np.nan
    s = str(value).strip().lower()
    if "4" in s and "fazla" in s:
        return 5.0
    m = re.match(r"^(\d+)", s)
    if m:
        return float(m.group(1))
    return np.nan


def drop_junk_sheet_columns(df: pd.DataFrame) -> pd.DataFrame:
    bad: list[str] = []
    for c in df.columns:
        cs = str(c).strip()
        if cs.startswith("Unnamed") or "27." in cs or cs == "":
            bad.append(c)
    return df.drop(columns=bad, errors="ignore")


def read_survey_csv(source: str | Path | IO[str], encoding: str = "utf-8-sig") -> pd.DataFrame:
    """Yerel dosya, URL veya metin akışından CSV okur."""
    if isinstance(source, str | Path):
        s = str(source)
        if s.startswith("http://") or s.startswith("https://"):
            try:
                with urlopen(s, timeout=60) as resp:
                    raw = resp.read().decode(encoding, errors="replace")
            except URLError as e:
                raise RuntimeError(f"URL okunamadı: {s}") from e
            return pd.read_csv(StringIO(raw), encoding=encoding)
        return pd.read_csv(s, encoding=encoding)
    return pd.read_csv(source, encoding=encoding)


def compute_bmi_kg_m2(height_cm: pd.Series, weight_kg: pd.Series) -> pd.Series:
    """BMI = kg / (m^2), boy cm cinsinden."""
    h_m = pd.to_numeric(height_cm, errors="coerce") / 100.0
    w = pd.to_numeric(weight_kg, errors="coerce")
    bmi = w / (h_m**2)
    bmi = bmi.replace([np.inf, -np.inf], np.nan)
    return bmi


def categorize_bmi(bmi: pd.Series) -> pd.Series:
    """Zayıf / Normal / Kilolu / Obez (WHO eşikleri, yetişkin)."""
    out = pd.Series(np.nan, index=bmi.index, dtype=object)

    mask = bmi.notna()
    out.loc[mask & (bmi < 18.5)] = "Zayıf"
    out.loc[mask & (bmi >= 18.5) & (bmi < 25)] = "Normal"
    out.loc[mask & (bmi >= 25) & (bmi < 30)] = "Kilolu"
    out.loc[mask & (bmi >= 30)] = "Obez"
    return out


def bin_age(age: pd.Series) -> pd.Series:
    """18-25, 26-35, 36-45, 45+ (uçlar pd.cut ile)."""
    a = pd.to_numeric(age, errors="coerce")
    bins = [17, 25, 35, 45, np.inf]
    labels = ["18-25", "26-35", "36-45", "45+"]
    return pd.cut(a, bins=bins, labels=labels, right=True)


def parse_time_to_decimal_hours(value: object) -> float:
    """
    Metin zamanı hesaplanabilir saat cinsinden float'a çevirir (örn. 22:30 -> 22.5).
    """
    if pd.isna(value) or value is None or str(value).strip() == "":
        return np.nan
    if isinstance(value, int | float | np.floating) and not isinstance(value, bool):
        return float(value)
    s = str(value).strip().lower().replace(".", ":")
    # Tek sayı "22" gibi
    if re.fullmatch(r"\d{1,2}", s):
        return float(s)
    m = re.match(r"^(\d{1,2})\s*:\s*(\d{1,2})(?:\s*:\s*(\d{1,2}))?", s)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        return h + mi / 60.0
    # Son çare: pandas to_datetime
    try:
        ts = pd.to_datetime(s, errors="coerce")
        if pd.isna(ts):
            return np.nan
        return ts.hour + ts.minute / 60.0 + ts.second / 3600.0
    except Exception:
        return np.nan


def normalize_time_columns(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            continue
        new_name = f"{col}_saat_decimal"
        out[new_name] = out[col].map(parse_time_to_decimal_hours)
        out = apply_cyclic_time_encoding(out, col, output_prefix=f"{col}_saat")
    return out


def multiselect_columns_to_binary(
    df: pd.DataFrame,
    source_columns: Iterable[str],
    prefix: str | None = None,
    separators: str = r"[,;|/]+",
) -> pd.DataFrame:
    """
    Her kaynak sütun için, görülen tüm seçeneklere karşılık 0/1 sütunları üretir.
    Sütun adı: ms_{kaynak_slug}__{seçenek_slug}
    """
    out = df.copy()
    for col in source_columns:
        if col not in out.columns:
            continue
        base = _slug_token(col) if prefix is None else prefix
        all_tokens: set[str] = set()
        for cell in out[col]:
            for tok in _split_multiselect_cell(cell, separators):
                all_tokens.add(tok)
        for tok in sorted(all_tokens):
            flag_col = f"ms_{base}__{_slug_token(tok)}"
            out[flag_col] = out[col].map(
                lambda v, t=tok: int(t in _split_multiselect_cell(v, separators))
            ).astype(np.int8)
    return out


def map_ordinal_columns(df: pd.DataFrame, mappings: dict[str, dict[str, int]]) -> pd.DataFrame:
    """Her sütun için metin -> tamsayı (küçük harf normalize)."""
    out = df.copy()
    for col, label_to_int in mappings.items():
        if col not in out.columns:
            continue
        norm_map = {k.strip().lower(): v for k, v in label_to_int.items()}

        def _map_one(x: object) -> float:
            if pd.isna(x) or x is None or str(x).strip() == "":
                return np.nan
            key = str(x).strip().lower()
            return float(norm_map[key]) if key in norm_map else np.nan

        out[f"{col}_ordinal"] = out[col].map(_map_one)
    return out


def _safe_feature_name(prefix: str, category: str) -> str:
    """CSV/ML araçları için okunabilir, boşluksuz sütun adı."""
    cat = re.sub(r"\s+", "_", str(category).strip())
    cat = re.sub(r"[^\w\-]", "", cat, flags=re.UNICODE)
    return f"{prefix}__{cat}" if cat else f"{prefix}__bos"


def encode_city_onehot(df: pd.DataFrame, city_col: str) -> pd.DataFrame:
    if city_col not in df.columns:
        return df
    out = df.copy()
    cities = out[city_col].fillna("Bilinmiyor").astype(str)
    uniques = pd.unique(cities)
    blocks: dict[str, pd.Series] = {}
    for u in uniques:
        col = _safe_feature_name("sehir", u)
        blocks[col] = (cities == u).astype(np.int8)
    dummies = pd.DataFrame(blocks, index=out.index)
    return pd.concat([out, dummies], axis=1)


def encode_gender_label(df: pd.DataFrame, gender_col: str) -> pd.DataFrame:
    """Cinsiyet -> tamsayı etiket (sıra: alfabetik benzersiz değer)."""
    if gender_col not in df.columns:
        return df
    out = df.copy()
    cats = pd.Series(out[gender_col]).dropna().astype(str).unique()
    cats_sorted = sorted(cats)
    mapping = {v: i for i, v in enumerate(cats_sorted)}
    out["cinsiyet_label"] = out[gender_col].map(lambda x: mapping.get(str(x).strip(), np.nan))
    return out


def assign_cold_start_group(df: pd.DataFrame) -> pd.DataFrame:
    """
    Demografik + BMI grubu birleşiminden cold-start segmenti (string kimlik).
    Modelde kategorik özellik veya train/test ayrımı için kullanılabilir.
    """
    out = df.copy()
    parts = []
    for candidate in ["Yaş_grubu", "BMI_kategori", "cinsiyet_label"]:
        if candidate in out.columns:
            parts.append(out[candidate].astype(str))
    if not parts:
        out["cold_start_group"] = "unknown"
        return out
    out["cold_start_group"] = parts[0]
    for p in parts[1:]:
        out["cold_start_group"] = out["cold_start_group"] + "_" + p
    return out


# ---------------------------------------------------------------------------
# Ana boru hattı
# ---------------------------------------------------------------------------


def preprocess_survey(
    df: pd.DataFrame,
    config: SurveyColumnConfig = DEFAULT_CONFIG,
    *,
    google_mode: bool = False,
) -> pd.DataFrame:
    """Tüm adımları sırayla uygular. ``google_mode=True`` Google Form CSV için temizlik + bulanık ordinal kullanır."""
    processed = drop_junk_sheet_columns(df.copy())

    if google_mode:
        h_col, w_col = config.height_cm, config.weight_kg
        h_use = h_col
        w_use = w_col
        if h_col in processed.columns:
            h_clean = f"{h_col}_clean_cm"
            processed[h_clean] = processed[h_col].map(parse_height_to_cm)
            h_use = h_clean
        if w_col in processed.columns:
            w_clean = f"{w_col}_clean_kg"
            processed[w_clean] = processed[w_col].map(parse_weight_to_kg)
            w_use = w_clean
    else:
        h_use, w_use = config.height_cm, config.weight_kg

    # BMI
    if h_use in processed.columns and w_use in processed.columns:
        processed["BMI"] = compute_bmi_kg_m2(processed[h_use], processed[w_use])
        processed["BMI_kategori"] = categorize_bmi(processed["BMI"])

    # Yaş grupları + sayısal yaş (ML özellikleri için)
    if config.age in processed.columns:
        processed["Yaş_grubu"] = bin_age(processed[config.age])
        processed["yas_sayi"] = pd.to_numeric(processed[config.age], errors="coerce")

    # Hane sayısı (Google)
    if google_mode and config.household and config.household in processed.columns:
        processed["evde_kisi_sayisi"] = processed[config.household].map(parse_household_count)

    # Zaman sütunları
    time_cols = [c for c in (config.light_on_time, config.bedtime) if c in processed.columns]
    processed = normalize_time_columns(processed, time_cols)

    # Ordinal
    if google_mode:
        if config.daily_activity in processed.columns:
            processed[f"{config.daily_activity}_ordinal"] = processed[config.daily_activity].map(
                map_activity_ordinal_google
            )
        if config.light_brightness in processed.columns:
            processed[f"{config.light_brightness}_ordinal"] = processed[config.light_brightness].map(
                map_light_ordinal_google
            )
        lw = config.light_work
        if lw and lw in processed.columns:
            processed[f"{lw}_ordinal"] = processed[lw].map(map_light_ordinal_google)
    else:
        ordinal_maps = {
            config.daily_activity: {
                "Hareketsiz": 1,
                "Orta": 2,
                "Hareketli": 3,
            },
            config.light_brightness: {
                "Loş": 1,
                "Orta": 2,
                "Parlak": 3,
            },
        }
        processed = map_ordinal_columns(processed, ordinal_maps)

    # Çoklu seçim -> binary
    multi_cols = [
        config.multiselect_devices,
        config.multiselect_vacuum_sensitivity,
        *config.extra_multiselect,
    ]
    multi_cols = [c for c in multi_cols if c in processed.columns]
    processed = multiselect_columns_to_binary(processed, multi_cols)

    # Şehir OHE, cinsiyet label
    processed = encode_city_onehot(processed, config.city)
    processed = encode_gender_label(processed, config.gender)

    processed = assign_cold_start_group(processed)

    return processed


def run_preprocess(
    input_path: str | Path,
    output_path: str | Path | None = None,
    config: SurveyColumnConfig | None = None,
    *,
    google_mode: bool = False,
) -> Path:
    cfg = config or DEFAULT_CONFIG
    input_path = Path(input_path)
    if not input_path.is_file():
        raise FileNotFoundError(f"Girdi dosyası bulunamadı: {input_path}")

    if output_path is None:
        output_path = Path(__file__).resolve().parent / "processed_synapse_data.csv"
    else:
        output_path = Path(output_path)

    df = read_survey_csv(input_path)
    processed = preprocess_survey(df, cfg, google_mode=google_mode)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    processed.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def run_preprocess_from_url(
    url: str,
    output_path: str | Path | None = None,
    config: SurveyColumnConfig | None = None,
    *,
    google_mode: bool = True,
) -> Path:
    """Google Sheets ``export?format=csv`` bağlantısından indirip işler."""
    cfg = config or GOOGLE_FORMS_CONFIG
    if output_path is None:
        output_path = Path(__file__).resolve().parent / "processed_synapse_data.csv"
    else:
        output_path = Path(output_path)
    df = read_survey_csv(url)
    processed = preprocess_survey(df, cfg, google_mode=google_mode)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    processed.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Synapse anket verisi ön işleme")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", "-i", type=Path, help="Ham anket CSV yolu")
    src.add_argument(
        "--from-url",
        type=str,
        default=None,
        help="CSV URL (ör. Google Sheets export?format=csv)",
    )
    p.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Çıktı CSV (varsayılan: app/analytics/processed_synapse_data.csv)",
    )
    p.add_argument(
        "--google",
        action="store_true",
        help="Yerel dosya için Google Form sütun adları + boy/kilo temizliği + bulanık ordinal",
    )
    return p


def main() -> None:
    args = _build_arg_parser().parse_args()
    if args.from_url:
        out = run_preprocess_from_url(args.from_url, args.output, google_mode=True)
    else:
        cfg = GOOGLE_FORMS_CONFIG if args.google else DEFAULT_CONFIG
        out = run_preprocess(args.input, args.output, cfg, google_mode=args.google)
    print(f"Kaydedildi: {out}")


if __name__ == "__main__":
    main()
