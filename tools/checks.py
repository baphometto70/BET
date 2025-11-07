#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, argparse, os

def check_config():
    # richiede Python 3.11+ per tomllib
    try:
        import tomllib  # type: ignore
    except Exception:
        print("[ERR] Serve Python 3.11+ (tomllib) per leggere config.toml")
        return 2
    if not os.path.exists("config.toml"):
        print("[ERR] config.toml non trovato. Copia config.example.toml in config.toml e inserisci i token.")
        return 2
    with open("config.toml", "rb") as f:
        cfg = tomllib.load(f)
    api = cfg.get("api", {})
    ok1 = bool(str(api.get("THEODDSAPI_KEY","")).strip())
    ok2 = bool(str(api.get("FOOTBALL_DATA_ORG_TOKEN","")).strip())
    if not ok1:
        print("[WARN] THEODDSAPI_KEY assente o vuoto (quote live non disponibili).")
    if not ok2:
        print("[WARN] FOOTBALL_DATA_ORG_TOKEN assente o vuoto (football-data.org non disponibile).")
    if not (ok1 or ok2):
        print("[ERR] Nessun token presente in config.toml.")
        return 2
    print("✅ config.toml ok (almeno un token presente).")
    return 0

def check_fixtures(date_str: str) -> int:
    import pandas as pd
    try:
        df = pd.read_csv("fixtures.csv")
        if "date" not in df.columns:
            return 1
        return 0 if (df["date"] == date_str).any() else 1
    except Exception:
        return 1

def check_odds(date_str: str) -> int:
    import pandas as pd
    try:
        df = pd.read_csv("fixtures.csv")
        df = df[df.get("date", "") == date_str]
        if df.empty:
            return 1
        needed = ["odds_1", "odds_x", "odds_2"]
        if any(c not in df.columns for c in needed):
            return 1
        return 1 if df[needed].isna().sum().sum() > 0 else 0
    except Exception:
        return 1

def check_features(date_str: str) -> int:
    import pandas as pd
    try:
        fix = pd.read_csv("fixtures.csv")
        fea = pd.read_csv("features.csv")
        today = fix[fix.get("date","") == date_str]
        if today.empty:
            return 1
        m = today[["match_id"]].merge(fea, on="match_id", how="left")
        feat_cols = [
            "xG_for_5_home","xG_against_5_home","xG_for_5_away","xG_against_5_away",
            "rest_days_home","rest_days_away","derby_flag","europe_flag_home","europe_flag_away","meteo_flag"
        ]
        for c in feat_cols:
            if c not in m.columns:
                return 1
            if m[c].isna().any() or (m[c] == "").any():
                return 1
        return 0
    except Exception:
        return 1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["config","fixtures","odds","features"])
    ap.add_argument("--date", help="YYYY-MM-DD (per fixtures/odds/features)")
    args = ap.parse_args()

    if args.what == "config":
        code = check_config()
    elif args.what == "fixtures":
        if not args.date: 
            print("[ERR] --date richiesto"); sys.exit(2)
        code = check_fixtures(args.date)
    elif args.what == "odds":
        if not args.date: 
            print("[ERR] --date richiesto"); sys.exit(2)
        code = check_odds(args.date)
    else:  # features
        if not args.date: 
            print("[ERR] --date richiesto"); sys.exit(2)
        code = check_features(args.date)

    sys.exit(code)

if __name__ == "__main__":
    main()
