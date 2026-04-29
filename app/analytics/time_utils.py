from __future__ import annotations

import numpy as np
import pandas as pd


def apply_cyclic_time_encoding(
    df: pd.DataFrame,
    time_column: str,
    *,
    output_prefix: str | None = None,
) -> pd.DataFrame:
    """
    Verilen zaman sütununu (HH:MM / HH:MM:SS / datetime) döngüsel sin-cos bileşenlerine çevirir.

    Varsayılan çıktı adları:
      - ``time_sin``
      - ``time_cos``

    ``output_prefix`` verilirse:
      - ``{output_prefix}_sin``
      - ``{output_prefix}_cos``
    """
    if time_column not in df.columns:
        return df

    out = df.copy()
    parsed = pd.to_datetime(out[time_column], format="%H:%M:%S", errors="coerce")
    fallback_mask = parsed.isna()
    if fallback_mask.any():
        parsed.loc[fallback_mask] = pd.to_datetime(
            out.loc[fallback_mask, time_column],
            format="%H:%M",
            errors="coerce",
        )
    minutes_passed = parsed.dt.hour * 60 + parsed.dt.minute + parsed.dt.second / 60.0
    total_minutes = 24.0 * 60.0
    angles = 2.0 * np.pi * minutes_passed / total_minutes

    if output_prefix:
        sin_col = f"{output_prefix}_sin"
        cos_col = f"{output_prefix}_cos"
    else:
        sin_col = "time_sin"
        cos_col = "time_cos"

    out[sin_col] = np.sin(angles)
    out[cos_col] = np.cos(angles)
    return out


def encode_time_cyclic(
    df: pd.DataFrame,
    time_column: str,
    *,
    output_prefix: str | None = None,
) -> pd.DataFrame:
    """apply_cyclic_time_encoding icin geriye donuk isimlendirme."""
    return apply_cyclic_time_encoding(df, time_column, output_prefix=output_prefix)

