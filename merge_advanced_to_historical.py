#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_advanced_to_historical.py

Merge advanced features con dataset storico per training ML.

Usage:
    python3 merge_advanced_to_historical.py
"""

import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Paths
HIST_OU_PATH = ROOT / "data" / "historical_dataset.csv"
HIST_1X2_PATH = ROOT / "data" / "historical_1x2.csv"
ADV_FEATURES_PATH = ROOT / "data" / "advanced_features.csv"

# Output paths
HIST_OU_MERGED = ROOT / "data" / "historical_dataset_enhanced.csv"
HIST_1X2_MERGED = ROOT / "data" / "historical_1x2_enhanced.csv"


def merge_advanced_features():
    """Merge advanced features con dataset storici."""

    # Check se advanced features esistono
    if not ADV_FEATURES_PATH.exists():
        print(f"[WARN] {ADV_FEATURES_PATH} non trovato")
        print("[INFO] Esegui prima: python3 populate_advanced_features.py --all")
        return

    # Load advanced features
    print(f"[INFO] Caricamento advanced features da {ADV_FEATURES_PATH}")
    adv_df = pd.read_csv(ADV_FEATURES_PATH)
    print(f"[INFO] Caricate {len(adv_df)} righe con {len(adv_df.columns)} colonne")

    # Advanced features da aggiungere (exclude metadata)
    metadata_cols = ['match_id', 'date', 'league', 'home_team', 'away_team']
    adv_feature_cols = [c for c in adv_df.columns if c not in metadata_cols]
    print(f"[INFO] Advanced features: {len(adv_feature_cols)} colonne")
    print(f"[SAMPLE] {adv_feature_cols[:10]}")

    # Process OU dataset
    if HIST_OU_PATH.exists():
        print(f"\n[INFO] Processing {HIST_OU_PATH}")
        ou_df = pd.read_csv(HIST_OU_PATH)
        print(f"[INFO] Dataset OU: {len(ou_df)} righe, {len(ou_df.columns)} colonne")

        # Merge on match_id
        if 'match_id' in ou_df.columns:
            merged_ou = pd.merge(
                ou_df,
                adv_df[['match_id'] + adv_feature_cols],
                on='match_id',
                how='left'
            )
            print(f"[INFO] Merged OU: {len(merged_ou)} righe, {len(merged_ou.columns)} colonne")

            # Save
            merged_ou.to_csv(HIST_OU_MERGED, index=False)
            print(f"[SUCCESS] Saved to {HIST_OU_MERGED}")

            # Stats
            merged_count = merged_ou[adv_feature_cols[0]].notna().sum()
            print(f"[STATS] {merged_count}/{len(merged_ou)} ({merged_count/len(merged_ou)*100:.1f}%) partite con advanced features")
        else:
            print("[WARN] Colonna 'match_id' non trovata in OU dataset")

    # Process 1X2 dataset
    if HIST_1X2_PATH.exists():
        print(f"\n[INFO] Processing {HIST_1X2_PATH}")
        x2_df = pd.read_csv(HIST_1X2_PATH)
        print(f"[INFO] Dataset 1X2: {len(x2_df)} righe, {len(x2_df.columns)} colonne")

        # Merge on match_id
        if 'match_id' in x2_df.columns:
            merged_x2 = pd.merge(
                x2_df,
                adv_df[['match_id'] + adv_feature_cols],
                on='match_id',
                how='left'
            )
            print(f"[INFO] Merged 1X2: {len(merged_x2)} righe, {len(merged_x2.columns)} colonne")

            # Save
            merged_x2.to_csv(HIST_1X2_MERGED, index=False)
            print(f"[SUCCESS] Saved to {HIST_1X2_MERGED}")

            # Stats
            merged_count = merged_x2[adv_feature_cols[0]].notna().sum()
            print(f"[STATS] {merged_count}/{len(merged_x2)} ({merged_count/len(merged_x2)*100:.1f}%) partite con advanced features")
        else:
            print("[WARN] Colonna 'match_id' non trovata in 1X2 dataset")

    # Print lista feature da aggiungere a model_pipeline.py
    print("\n" + "="*80)
    print("ISTRUZIONI PER model_pipeline.py:")
    print("="*80)
    print("\nAggiungi queste feature a FEATURES_BASE in model_pipeline.py:")
    print("\nFEATURES_ADVANCED = [")
    for feat in adv_feature_cols:
        print(f'    "{feat}",')
    print("]\n")
    print("FEATURES_BASE: List[str] = [")
    print("    # xG base features")
    print('    "xg_for_home",')
    print('    "xg_against_home",')
    print('    "xg_for_away",')
    print('    "xg_against_away",')
    print('    "rest_days_home",')
    print('    "rest_days_away",')
    print('    # ... altre features esistenti ...')
    print("] + FEATURES_ADVANCED")
    print("\nE aggiorna i path:")
    print(f'HIST_OU_PATH = ROOT / "data" / "historical_dataset_enhanced.csv"')
    print(f'HIST_1X2_PATH = ROOT / "data" / "historical_1x2_enhanced.csv"')


if __name__ == "__main__":
    merge_advanced_features()
