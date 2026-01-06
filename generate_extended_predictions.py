#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_extended_predictions.py

Genera predizioni estese su tutti i mercati disponibili:
- Doppia Chance (1X, X2, 12)
- Multigol
- Goal/No Goal
- Over/Under altre linee
- Combo markets

Usage:
    python3 generate_extended_predictions.py --date 2026-01-04
    python3 generate_extended_predictions.py --date 2026-01-04 --top 20
"""

import argparse
import sys
from pathlib import Path
import pandas as pd
import numpy as np

from database import SessionLocal
from models import Fixture, Feature, Odds
from extended_markets import (
    calculate_extended_markets,
    find_best_bets,
    format_market_name
)

ROOT = Path(__file__).resolve().parent


def generate_extended_predictions(
    date_str: str,
    top_n: int = 15,
    min_prob: float = 0.55,
    min_value: float = 0.03
):
    """
    Genera predizioni estese per una data specifica.

    Args:
        date_str: Data in formato YYYY-MM-DD
        top_n: Numero massimo di bet per partita
        min_prob: Probabilità minima per considerare una scommessa
        min_value: Value minimo richiesto
    """
    from datetime import datetime

    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except:
        print(f"[ERROR] Data non valida: {date_str}. Usa formato YYYY-MM-DD")
        sys.exit(1)

    db = SessionLocal()

    # Load predictions from model_pipeline
    pred_path = ROOT / "predictions.csv"
    if not pred_path.exists():
        print(f"[ERROR] predictions.csv non trovato. Esegui prima:")
        print(f"  python3 model_pipeline.py --predict --date {date_str}")
        sys.exit(1)

    preds_df = pd.read_csv(pred_path)
    preds_df = preds_df[preds_df['date'] == date_str].copy()

    if len(preds_df) == 0:
        print(f"[WARN] Nessuna predizione trovata per {date_str}")
        sys.exit(0)

    print(f"\n{'='*100}")
    print(f"PREDIZIONI ESTESE - {date_str}")
    print(f"{'='*100}\n")

    all_extended_bets = []
    from datetime import datetime

    for _, pred in preds_df.iterrows():
        match_id = pred['match_id']
        home = pred['home']
        away = pred['away']
        league = pred['league']

        # Get fixture to check kickoff time
        fixture_obj = db.query(Fixture).filter(Fixture.match_id == match_id).first()

        if not fixture_obj:
            print(f"[WARN] Fixture non trovata per {match_id}, skip")
            continue

        # Filter already played matches
        # time è in formato HH:MM string, date è un Date object
        match_time_str = fixture_obj.time
        match_date = fixture_obj.date

        # Combina data e ora per confronto
        if match_time_str and match_date:
            try:
                hour, minute = map(int, match_time_str.split(':'))
                match_datetime = datetime.combine(match_date, datetime.min.time().replace(hour=hour, minute=minute))
                now = datetime.now()

                if match_datetime < now:
                    print(f"[SKIP] {home} - {away} già giocata alle {match_time_str}")
                    continue
            except:
                pass  # Se errore parsing, continua comunque

        # Format kickoff time for display
        kickoff_str = match_time_str if match_time_str else 'N/A'

        # Get ML probabilities
        p1 = pred.get('p1', np.nan)
        px = pred.get('px', np.nan)
        p2 = pred.get('p2', np.nan)
        p_over = pred.get('p_over_2_5', np.nan)
        p_under = pred.get('p_under_2_5', np.nan)

        # Get feature object from DB to calculate lambdas
        feature_obj = db.query(Feature).filter(Feature.match_id == match_id).first()

        if not feature_obj:
            print(f"[WARN] Features non trovate per {match_id}, skip")
            continue

        # Calculate Poisson lambdas from xG
        xg_home = feature_obj.xg_for_home or 1.3
        xg_away = feature_obj.xg_for_away or 1.3

        # Adjust lambdas based on xG against
        xga_home = feature_obj.xg_against_home or 1.3
        xga_away = feature_obj.xg_against_away or 1.3

        # Blended lambda: offesa squadra vs difesa avversaria
        lambda_home = (xg_home + xga_away) / 2
        lambda_away = (xg_away + xga_home) / 2

        # Get odds if available
        odds_obj = db.query(Odds).filter(Odds.match_id == match_id).first()
        odds_map = {}
        if odds_obj:
            # Map basic odds (we don't have extended odds yet, but structure is ready)
            if odds_obj.odds_1:
                odds_map['1'] = float(odds_obj.odds_1)
            if odds_obj.odds_x:
                odds_map['X'] = float(odds_obj.odds_x)
            if odds_obj.odds_2:
                odds_map['2'] = float(odds_obj.odds_2)
            if odds_obj.odds_ou25_over:
                odds_map['over_2.5'] = float(odds_obj.odds_ou25_over)
            if odds_obj.odds_ou25_under:
                odds_map['under_2.5'] = float(odds_obj.odds_ou25_under)

        # Calculate extended markets
        markets = calculate_extended_markets(
            lambda_home,
            lambda_away,
            p1_ml=p1 if not np.isnan(p1) else None,
            px_ml=px if not np.isnan(px) else None,
            p2_ml=p2 if not np.isnan(p2) else None
        )

        # Find best bets for this match
        best_bets = find_best_bets(
            markets,
            odds_map=odds_map if odds_map else None,
            min_probability=min_prob,
            min_value=0.00,  # CAMBIATO: più permissivo
            kelly_fraction=0.20,  # Conservative Kelly
            diversify=True  # NUOVO: forza diversificazione
        )

        # Print match header with kickoff time
        print(f"\n[{league}] {home} vs {away} - ⏰ {kickoff_str}")
        print(f"  λ: {lambda_home:.2f} - {lambda_away:.2f} | xG: {xg_home:.2f} - {xg_away:.2f}")
        print(f"  ML Probs: {p1:.1%} - {px:.1%} - {p2:.1%}" if not np.isnan(p1) else "")

        if len(best_bets) == 0:
            print(f"  [!] Nessuna scommessa trovata con i criteri specificati")
            continue

        print(f"\n  TOP {min(top_n, len(best_bets))} BETS:")

        for i, bet in enumerate(best_bets[:top_n], 1):
            market_name = format_market_name(bet['market'])
            prob_str = f"{bet['probability']:.1%}"
            value_str = f"{bet['value']:+.1%}" if bet['value'] is not None else "N/A"
            kelly_str = f"{bet['kelly']:.1%}" if bet['kelly'] > 0 else ""

            conf_emoji = "🔥" if bet['confidence'] == 'high' else "✓" if bet['confidence'] == 'medium' else "○"

            # Add percentage to market name (es. "Over 2.5 (65%)")
            bet_line = f"  {i:2d}. {conf_emoji} {market_name:<35} ({prob_str}) | V={value_str}"

            if bet['odds']:
                bet_line += f" | Q={bet['odds']:.2f}"
            if kelly_str:
                bet_line += f" | K={kelly_str}"

            print(bet_line)

            # Save to all bets list for summary
            all_extended_bets.append({
                'match_id': match_id,
                'home': home,
                'away': away,
                'league': league,
                'kickoff_time': kickoff_str,
                'market': bet['market'],
                'market_name': market_name,
                'probability': bet['probability'],
                'value': bet['value'],
                'odds': bet['odds'],
                'kelly': bet['kelly'],
                'confidence': bet['confidence'],
                'category': bet['category']
            })

    db.close()

    # Save extended bets to CSV
    if all_extended_bets:
        extended_df = pd.DataFrame(all_extended_bets)
        output_path = ROOT / "extended_predictions.csv"
        extended_df.to_csv(output_path, index=False)

        print(f"\n{'='*100}")
        print(f"[SUCCESS] {len(all_extended_bets)} scommesse salvate in {output_path}")

        # Summary by category
        print(f"\n=== RIEPILOGO PER CATEGORIA ===")
        category_counts = extended_df['category'].value_counts()
        for cat, count in category_counts.items():
            avg_prob = extended_df[extended_df['category'] == cat]['probability'].mean()
            print(f"  {cat:<20}: {count:3d} scommesse (Prob media: {avg_prob:.1%})")

        # Top 10 overall bets
        print(f"\n=== TOP 10 SCOMMESSE COMPLESSIVE (per valore) ===")
        top_10 = extended_df.nlargest(10, 'value')
        for i, row in top_10.iterrows():
            print(f"  {row['home'][:20]} - {row['away'][:20]}")
            print(f"    → {row['market_name']}")
            print(f"    P={row['probability']:.1%} | V={row['value']:+.1%} | {row['confidence'].upper()}")
            print()

        print(f"{'='*100}\n")

    else:
        print(f"\n[WARN] Nessuna scommessa generata per {date_str}")


def main():
    parser = argparse.ArgumentParser(
        description="Genera predizioni estese su tutti i mercati"
    )
    parser.add_argument(
        "--date",
        type=str,
        required=True,
        help="Data in formato YYYY-MM-DD"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=15,
        help="Numero massimo di bet per partita (default: 15)"
    )
    parser.add_argument(
        "--min-prob",
        type=float,
        default=0.55,
        help="Probabilità minima (default: 0.55 = 55%%)"
    )
    parser.add_argument(
        "--min-value",
        type=float,
        default=0.03,
        help="Value minimo richiesto (default: 0.03 = 3%%)"
    )

    args = parser.parse_args()

    generate_extended_predictions(
        args.date,
        top_n=args.top,
        min_prob=args.min_prob,
        min_value=args.min_value
    )


if __name__ == "__main__":
    main()
