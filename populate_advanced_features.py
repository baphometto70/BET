#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
populate_advanced_features.py

Popola advanced features per tutte le partite nel database.
Salva in CSV che verrà mergiato con dataset principale durante training ML.

Usage:
    python3 populate_advanced_features.py --all
    python3 populate_advanced_features.py --date 2026-01-02
"""

import argparse
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

from database import SessionLocal
from models import Fixture
from advanced_features import AdvancedFeatureCalculator

ROOT = Path(__file__).resolve().parent
OUTPUT_FILE = ROOT / "data" / "advanced_features.csv"


def populate_advanced_features(
    date_filter: str = None,
    all_matches: bool = False
):
    """
    Popola advanced features per match specificati.

    Args:
        date_filter: Data specifica (YYYY-MM-DD)
        all_matches: Se True, processa TUTTE le partite nel DB
    """
    db = SessionLocal()
    calc = AdvancedFeatureCalculator(db)

    # Query partite da processare
    query = db.query(Fixture)

    if date_filter:
        target_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
        query = query.filter(Fixture.date == target_date)
        print(f"[INFO] Filtrando partite del {date_filter}")
    elif all_matches:
        print(f"[INFO] Processando TUTTE le partite nel database")
    else:
        # Default: partite future
        today = datetime.now().date()
        query = query.filter(Fixture.date >= today)
        print(f"[INFO] Processando partite future (>= {today})")

    fixtures = query.order_by(Fixture.date).all()
    print(f"[INFO] Trovate {len(fixtures)} partite da processare\n")

    if len(fixtures) == 0:
        print("[WARN] Nessuna partita trovata con i filtri specificati")
        db.close()
        return

    # Carica features esistenti se file esiste
    if OUTPUT_FILE.exists():
        existing_df = pd.read_csv(OUTPUT_FILE)
        existing_match_ids = set(existing_df['match_id'].values)
        print(f"[INFO] Caricate {len(existing_df)} features esistenti da {OUTPUT_FILE}")
    else:
        existing_df = pd.DataFrame()
        existing_match_ids = set()

    # Processa partite
    new_features = []
    skipped = 0

    for i, fixture in enumerate(fixtures, 1):
        # Skip se già processata
        if fixture.match_id in existing_match_ids:
            skipped += 1
            continue

        # Progress indicator
        if i % 10 == 0 or i == len(fixtures):
            print(f"[PROGRESS] {i}/{len(fixtures)} partite processate...")

        try:
            features = calc.calculate_all_advanced_features(
                fixture.match_id,
                fixture.home,
                fixture.away,
                fixture.league,
                fixture.date
            )

            # Aggiungi metadati
            features['match_id'] = fixture.match_id
            features['date'] = fixture.date.isoformat()
            features['league'] = fixture.league
            features['home_team'] = fixture.home
            features['away_team'] = fixture.away

            new_features.append(features)

        except Exception as e:
            print(f"\n[ERROR] Match {fixture.match_id}: {e}")
            continue

    db.close()

    # Crea DataFrame con nuove features
    if len(new_features) > 0:
        new_df = pd.DataFrame(new_features)

        # Merge con esistenti
        if len(existing_df) > 0:
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            combined_df = new_df

        # Salva
        OUTPUT_FILE.parent.mkdir(exist_ok=True, parents=True)
        combined_df.to_csv(OUTPUT_FILE, index=False)

        print(f"\n[SUCCESS] Salvate {len(new_features)} nuove features in {OUTPUT_FILE}")
        print(f"[INFO] Totale features nel file: {len(combined_df)}")
        print(f"[INFO] Skipped (già presenti): {skipped}")

        # Mostra esempio features
        print(f"\n[SAMPLE] Prime 5 righe del dataset:")
        print(combined_df[['match_id', 'date', 'home_team', 'away_team', 'home_form_xg_diff', 'away_form_xg_diff', 'form_diff']].head())

    else:
        print(f"\n[INFO] Nessuna nuova feature da salvare (skipped: {skipped})")


def main():
    parser = argparse.ArgumentParser(
        description="Popola advanced features per partite nel database"
    )

    parser.add_argument(
        "--date",
        type=str,
        help="Data specifica (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Processa TUTTE le partite nel database"
    )

    args = parser.parse_args()

    populate_advanced_features(
        date_filter=args.date,
        all_matches=args.all
    )


if __name__ == "__main__":
    main()
