#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
append_db_to_history.py
-----------------------
Appends finished matches from the local database (bet.db) to the historical datasets
(data/historical_dataset.csv and data/historical_1x2.csv).
This ensures that the latest results (fetched via results_fetcher.py) are included
in the training set without re-running the full historical build.
"""

import sys
import pandas as pd
from datetime import datetime
from database import SessionLocal
from models import Fixture, Feature, Odds
import numpy as np

HISTORICAL_CSV = "data/historical_dataset.csv"
HISTORICAL_1X2_CSV = "data/historical_1x2.csv"

def append_matches():
    db = SessionLocal()
    try:
        # Load existing history to check for duplicates
        try:
            existing_df = pd.read_csv(HISTORICAL_CSV)
            existing_ids = set(existing_df['match_id'].astype(str))
            print(f"Existing history has {len(existing_df)} rows.")
        except FileNotFoundError:
            print(f"Warning: {HISTORICAL_CSV} not found. Starting fresh.")
            existing_df = pd.DataFrame()
            existing_ids = set()

        # Query DB for finished matches with features
        # We want matches that have a result (goals not None)
        # and have features populated.
        
        matches = db.query(Fixture).join(Feature).outerjoin(Odds).filter(
            Fixture.result_home_goals != None,
            Fixture.result_away_goals != None
        ).all()
        
        print(f"Found {len(matches)} finished matches in DB.")
        
        new_rows = []
        
        for m in matches:
            if m.match_id in existing_ids:
                continue
                
            # Get features
            f = db.query(Feature).filter(Feature.match_id == m.match_id).first()
            if not f:
                continue # Should be covered by join, but safe check
            
            # Get odds (optional)
            o = db.query(Odds).filter(Odds.match_id == m.match_id).first()
            
            # Prepare row
            row = {
                "match_id": m.match_id,
                "date": str(m.date), # m.date is Date object
                "time_local": m.time_local or "15:00",
                "league": m.league,
                "home": m.home,
                "away": m.away,
                "ft_home_goals": m.result_home_goals,
                "ft_away_goals": m.result_away_goals,
                
                # Odds
                "odds_1": o.odds_1 if o else None,
                "odds_x": o.odds_x if o else None,
                "odds_2": o.odds_2 if o else None,
                
                # Features
                "xg_for_home": f.xg_for_home,
                "xg_against_home": f.xg_against_home,
                "xg_for_away": f.xg_for_away,
                "xg_against_away": f.xg_against_away,
                "rest_days_home": f.rest_days_home,
                "rest_days_away": f.rest_days_away,
                "derby_flag": f.derby_flag,
                "europe_flag_home": f.europe_flag_home,
                "europe_flag_away": f.europe_flag_away,
                "meteo_flag": f.meteo_flag,
                "style_ppda_home": f.style_ppda_home,
                "style_ppda_away": f.style_ppda_away,
                "travel_km_away": f.travel_km_away,
            }
            
            # Calculate targets
            hg = m.result_home_goals
            ag = m.result_away_goals
            
            if hg is None or ag is None:
                continue
                
            row["target_ou25"] = 1 if (hg + ag) > 2.5 else 0
            row["target_btts"] = 1 if (hg > 0 and ag > 0) else 0
            
            # 1X2 Target: 1=Home, 1=Draw, 2=Away (Wait, logic in historical_builder was: Equal->1, Home<Away->2, else 0??)
            # Let's check historical_builder again correctly.
            # Line 610: base["target_1x2"] = 0 (Default)
            # Line 611: == -> 1
            # Line 612: Home < Away -> 2
            # So HomeWins -> 0. Draw -> 1. AwayWins -> 2.
            
            if hg > ag:
                row["target_1x2"] = 0
            elif hg == ag:
                row["target_1x2"] = 1
            else:
                row["target_1x2"] = 2
            
            new_rows.append(row)

        if not new_rows:
            print("No new matches to append.")
            return

        print(f"Appending {len(new_rows)} new matches.")
        
        # Check target_1x2 convention in historical_builder
        # Line 610: base["target_1x2"] = pd.Series(0, index=base.index) -> Defaults to 0 (Home?)
        # Line 611: base.loc[base["ft_home_goals"] == base["ft_away_goals"], "target_1x2"] = 1 -> Draw
        # Line 612: base.loc[base["ft_home_goals"] < base["ft_away_goals"], "target_1x2"] = 2 -> Away
        # So: 0=Home, 1=Draw, 2=Away.
        
        # Adjust target_1x2 for new_rows
        for r in new_rows:
            hg = r["ft_home_goals"]
            ag = r["ft_away_goals"]
            if hg > ag:
                r["target_1x2"] = 0
            elif hg == ag:
                r["target_1x2"] = 1
            else:
                r["target_1x2"] = 2

        new_df = pd.DataFrame(new_rows)
        
        # Ensure column order matches
        if not existing_df.empty:
            # Add missing cols to new_df
            for c in existing_df.columns:
                if c not in new_df.columns:
                    new_df[c] = ""
            # Reorder
            new_df = new_df[existing_df.columns]
        
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        
        # Save
        combined_df.to_csv(HISTORICAL_CSV, index=False)
        combined_df.to_csv(HISTORICAL_1X2_CSV, index=False)
        
        print(f"Updated {HISTORICAL_CSV} with total {len(combined_df)} rows.")

    finally:
        db.close()

if __name__ == "__main__":
    append_matches()
