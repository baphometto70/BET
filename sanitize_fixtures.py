#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path

import pandas as pd
try:
    import tomllib
except ImportError:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent
CFG = ROOT / "config.toml"
FX = ROOT / "fixtures.csv"


def overround(o1, ox, o2):
    try:
        vals = [float(o1), float(ox), float(o2)]
    except Exception:
        return None
    for v in vals:
        if v is None:
            return None
        if isinstance(v, float) and (pd.isna(v) or v <= 0):
            return None
    try:
        inv = sum(1.0 / v for v in vals)
    except Exception:
        return None
    return inv - 1.0


def main():
    if not FX.exists():
        print("[ERR] fixtures.csv non trovato.")
        return
    df = pd.read_csv(FX, dtype=str)
    if df.empty:
        print("[WARN] fixtures.csv vuoto.")
        return

    cfg = tomllib.loads(CFG.read_text(encoding="utf-8"))
    max_or = float(cfg["settings"].get("max_overround", 0.28))

    # assicurati che le colonne esistano
    for c in ["odds_1", "odds_x", "odds_2", "odds_ou25_over", "odds_ou25_under"]:
        if c not in df.columns:
            df[c] = pd.NA

    # calcola overround
    ors = []
    keep = []
    for _, r in df.iterrows():
        orv = overround(r.get("odds_1"), r.get("odds_x"), r.get("odds_2"))
        ors.append(orv)
        keep.append((orv is None) or (0 <= orv <= max_or))
    df["overround"] = ors
    kept = df[keep].copy()
    quarantined = len(df) - len(kept)

    kept.to_csv(FX, index=False)
    print(f"[OK] Sanitize: salvate {len(kept)} righe. Quarantena: {quarantined}")


if __name__ == "__main__":
    main()
