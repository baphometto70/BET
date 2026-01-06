#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_features_ids.py
Allinea features.csv alle match_id di fixtures.csv usando (date, home, away) normalizzati.
- NON tocca fixtures.csv
- Riscrive features.csv con le stesse match_id dei fixtures (ove matchate)
- Logga quante righe sono state riallineate
"""

import re
from pathlib import Path

import pandas as pd
from unidecode import unidecode

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "fixtures.csv"
FEA = ROOT / "features.csv"
OUT_BACKUP = ROOT / "features.csv.bak"

# Token inutili nei nomi delle squadre
DROP_TOKENS = {
    "fc",
    "cf",
    "ac",
    "ssc",
    "as",
    "sc",
    "afc",
    "calcio",
    "bc",
    "sd",
    "ud",
    "de",
    "fk",
    "sk",
    "kv",
    "kk",
    "bk",
    "ik",
    "if",
    "sp",
    "club",
    "real",
    "cd",
}


def norm_team(s: str) -> str:
    if pd.isna(s):
        return ""
    s = unidecode(str(s)).lower().strip()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9\s-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    # tokenizza, rimuovi stopword brevi/club token
    parts = [p for p in s.split() if p not in DROP_TOKENS and len(p) > 1]
    s = " ".join(parts)

    # alias minimi frequenti in coppe
    aliases = {
        "crvena zvezda": "red star belgrade",
        "red star": "red star belgrade",
        "bate borisov": "bate",
        "paok thessaloniki": "paok",
        "real betis balompie": "real betis",
        "young boys bern": "young boys",
        "dinamo zagreb": "dinamo zagreb",
        "dinamo": "dinamo zagreb",
        "feyenoord rotterdam": "feyenoord",
        "porto": "porto",
        "midtjylland": "midtjylland",
        "sturm graz": "sturm graz",
        "paphos": "pafos",
    }
    # applica alias se combacia esattamente
    return aliases.get(s, s)


def norm_row(df: pd.DataFrame, home_col: str, away_col: str):
    df = df.copy()
    df["home_norm"] = df[home_col].apply(norm_team)
    df["away_norm"] = df[away_col].apply(norm_team)
    # data normalizzata (YYYY-MM-DD)
    if "date" in df.columns:
        df["date_norm"] = pd.to_datetime(df["date"], errors="coerce").dt.date.astype(
            str
        )
    else:
        df["date_norm"] = ""
    return df


def main():
    if not FIX.exists():
        print("[ERR] fixtures.csv non trovato.")
        return
    if not FEA.exists():
        print("[ERR] features.csv non trovato.")
        return

    fix = pd.read_csv(FIX)
    fea = pd.read_csv(FEA)

    print(f"[INFO] fixtures: {len(fix)} righe, features: {len(fea)} righe")

    # Normalizza per join su (date_norm, home_norm, away_norm)
    fixN = norm_row(fix, "home", "away")
    feaN = norm_row(fea, "home", "away")
    for c in ("match_id", "time", "time_local"):
        if c not in fixN.columns:
            fixN[c] = ""
    
    # Individua colonne di features (tutte tranne chiavi e duplicati)
    key_cols = {
        "match_id",
        "date",
        "time",
        "time_local",
        "league",
        "league_code",
        "home",
        "away",
    }
    # Explicitly define feature columns to match the model and DB
    fea_cols = [
        "xg_for_home", "xg_against_home", "xg_for_away", "xg_against_away",
        "rest_days_home", "rest_days_away", "injuries_key_home", "injuries_key_away",
        "derby_flag", "europe_flag_home", "europe_flag_away", "meteo_flag",
        "style_ppda_home", "style_ppda_away", "travel_km_away"
    ]

    # Join sinistro: fixtures come master
    merged = fixN.merge(
        feaN[["date_norm", "home_norm", "away_norm", "match_id"] + fea_cols],
        on=["date_norm", "home_norm", "away_norm"],
        how="left",
        suffixes=("", "_fea"),
    )

    # Righe matchate / non matchate
    matched = merged[~merged["match_id_fea"].isna()].copy()
    unmatched = merged[merged["match_id_fea"].isna()].copy()

    # Costruisci nuovo features.csv:
    # - usa le match_id dei fixtures
    # - conserva le colonne di feature provenienti da fea
    out_rows = []
    for _, r in merged.iterrows():
        base = {
            "match_id": r.get("match_id"),  # match_id DEL FIXTURE
            "date": r.get("date"),
            "time": r.get("time_local", r.get("time")),
            "league": r.get("league"),
            "league_code": r.get("league_code"),
            "home": r.get("home"),
            "away": r.get("away"),
        }
        # porta dentro le feature (possono essere NaN se non matchate)
        for c in fea_cols:
            base[c] = r.get(c)
        out_rows.append(base)

    out = pd.DataFrame(out_rows)

    # Backup e scrittura
    FEA.rename(OUT_BACKUP)
    out.to_csv(FEA, index=False)

    print(f"[OK] features riallineate scritto: {FEA}")
    print(f"[INFO] Backup vecchio features: {OUT_BACKUP}")
    print(
        f"[STAT] Matchate: {len(matched)}   Non matchate: {len(unmatched)}   Totale fixture: {len(merged)}"
    )

    if len(unmatched):
        sample = unmatched[["date", "home", "away"]].head(10)
        print("[HINT] Alcune non matchate (prime 10):")
        print(sample.to_string(index=False))


if __name__ == "__main__":
    main()
