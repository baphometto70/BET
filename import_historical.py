#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
import_historical.py
Importa gli storici (historical_dataset.csv / historical_1x2.csv) nel DB
tabella historical_matches per il training ML.
"""
import argparse
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd

from database import SessionLocal, engine
from models import HistoricalMatch, Base

ROOT = Path(__file__).resolve().parent
HIST_DATASET = ROOT / "data" / "historical_dataset.csv"
HIST_1X2 = ROOT / "data" / "historical_1x2.csv"

RENAME_MAP = {
    "xG_for_5_home": "xg_for_home",
    "xG_against_5_home": "xg_against_home",
    "xG_for_5_away": "xg_for_away",
    "xG_against_5_away": "xg_against_away",
}


def _standardize_cols(df: pd.DataFrame) -> pd.DataFrame:
    ren = {k: v for k, v in RENAME_MAP.items() if k in df.columns}
    if ren:
        df = df.rename(columns=ren)
    return df


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
        return _standardize_cols(df)
    except Exception as exc:
        print(f"[ERR] lettura {path}: {exc}", file=sys.stderr)
        return pd.DataFrame()


def import_historical(limit: int = 0):
    Base.metadata.create_all(bind=engine, tables=[HistoricalMatch.__table__])

    df_main = _load_csv(HIST_DATASET)
    df_alt = _load_csv(HIST_1X2)
    if df_alt is not None and not df_alt.empty:
        df_main = pd.concat([df_main, df_alt], ignore_index=True)

    if df_main.empty:
        print("[WARN] Nessun dato storico trovato.")
        return

    df_main.drop_duplicates(subset=["match_id"], inplace=True)
    if limit > 0:
        df_main = df_main.head(limit)

    required_cols = {"match_id", "date", "home", "away"}
    missing = required_cols - set(df_main.columns)
    if missing:
        print(f"[ERR] Colonne obbligatorie mancanti: {missing}", file=sys.stderr)
        return

    # Conversioni leggere
    def _to_date(val):
        try:
            return datetime.fromisoformat(str(val)[:10]).date()
        except Exception:
            return None

    db = SessionLocal()
    inserted = 0
    try:
        for _, row in df_main.iterrows():
            obj = HistoricalMatch(
                match_id=str(row.get("match_id")),
                date=_to_date(row.get("date")),
                time_local=str(row.get("time_local")) if not pd.isna(row.get("time_local")) else None,
                league=row.get("league"),
                home=row.get("home"),
                away=row.get("away"),
                ft_home_goals=row.get("ft_home_goals"),
                ft_away_goals=row.get("ft_away_goals"),
                odds_1=row.get("odds_1"),
                odds_x=row.get("odds_x"),
                odds_2=row.get("odds_2"),
                xg_for_home=row.get("xg_for_home"),
                xg_against_home=row.get("xg_against_home"),
                xg_for_away=row.get("xg_for_away"),
                xg_against_away=row.get("xg_against_away"),
                rest_days_home=row.get("rest_days_home"),
                rest_days_away=row.get("rest_days_away"),
                derby_flag=row.get("derby_flag"),
                europe_flag_home=row.get("europe_flag_home"),
                europe_flag_away=row.get("europe_flag_away"),
                meteo_flag=row.get("meteo_flag"),
                style_ppda_home=row.get("style_ppda_home"),
                style_ppda_away=row.get("style_ppda_away"),
                travel_km_away=row.get("travel_km_away"),
                target_ou25=row.get("target_ou25"),
                target_btts=row.get("target_btts"),
                target_1x2=row.get("target_1x2"),
            )
            db.merge(obj)
            inserted += 1
        db.commit()
        print(f"[OK] Inserite/aggiornate {inserted} righe in historical_matches.")
    except Exception as exc:
        db.rollback()
        print(f"[ERR] Inserimento fallito: {exc}", file=sys.stderr)
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="Limita il numero di record importati (0 = tutti)")
    args = ap.parse_args()
    import_historical(limit=args.limit)
