#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "fixtures.csv"
FEA = ROOT / "features.csv"
OUT_DIR = ROOT / "data"
OUT_DIR.mkdir(exist_ok=True)


def main():
    if not FIX.exists() or not FEA.exists():
        print("[ERR] fixtures.csv o features.csv mancanti.")
        return

    fix = pd.read_csv(FIX)
    fea = pd.read_csv(FEA)

    print(f"[INFO] fixtures: {len(fix)} righe, features: {len(fea)} righe")

    if "match_id" not in fix.columns or "match_id" not in fea.columns:
        print("[ERR] Colonna 'match_id' mancante in uno dei due CSV.")
        print(f"fixtures cols: {list(fix.columns)}")
        print(f"features cols: {list(fea.columns)}")
        return

    # conteggio per data/lega (se presenti)
    for name, df in [("fixtures", fix), ("features", fea)]:
        cols = [c for c in ["date", "league", "league_code"] if c in df.columns]
        if cols:
            grp = df.groupby(cols).size().reset_index(name="n")
            print(f"\n[{name.upper()}] distribuzione per {cols}:")
            print(grp.to_string(index=False))

    # join e anti-join
    merged = pd.merge(
        fix[["match_id", "date", "league", "home", "away"]],
        fea[["match_id"]],
        on="match_id",
        how="inner",
    )
    print(f"\n[JOIN] righe dopo INNER JOIN su match_id: {len(merged)}")

    only_fix = fix.loc[~fix["match_id"].isin(fea["match_id"])]
    only_fea = fea.loc[~fea["match_id"].isin(fix["match_id"])]

    (OUT_DIR / "_debug_only_fixtures.csv").write_text(
        only_fix.to_csv(index=False), encoding="utf-8"
    )
    (OUT_DIR / "_debug_only_features.csv").write_text(
        only_fea.to_csv(index=False), encoding="utf-8"
    )
    (OUT_DIR / "_debug_join_ok.csv").write_text(
        merged.to_csv(index=False), encoding="utf-8"
    )

    print(f"[DIAG] Solo in fixtures: {len(only_fix)}  → data/_debug_only_fixtures.csv")
    print(f"[DIAG] Solo in features: {len(only_fea)} → data/_debug_only_features.csv")
    print(f"[DIAG] Join OK: {len(merged)}           → data/_debug_join_ok.csv")


if __name__ == "__main__":
    main()
