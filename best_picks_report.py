#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
best_picks_report.py

Genera report con le migliori scommesse selezionate per massimizzare
le probabilità di vincita.

Criteri di selezione:
- Probabilità alta (>60%)
- Value positivo
- Diversificazione mercati
- Bilanciamento rischio/rendimento

Usage:
    python3 best_picks_report.py
    python3 best_picks_report.py --top 20
    python3 best_picks_report.py --min-prob 0.65 --top 15
"""

import argparse
import pandas as pd
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent


def generate_best_picks_report(
    top_n: int = 15,
    min_prob: float = 0.60,
    max_per_match: int = 3,
    diversify: bool = True
):
    """
    Genera report con le migliori scommesse.

    Args:
        top_n: Numero massimo di scommesse da mostrare
        min_prob: Probabilità minima richiesta
        max_per_match: Max scommesse per singola partita
        diversify: Se True, diversifica tra categorie
    """
    # Load extended predictions
    extended_path = ROOT / "extended_predictions.csv"
    if not extended_path.exists():
        print(f"[ERROR] {extended_path} non trovato.")
        print("Esegui prima: python3 generate_extended_predictions.py --date YYYY-MM-DD")
        return

    df = pd.read_csv(extended_path)

    print(f"\n{'='*100}")
    print(f"BEST PICKS REPORT")
    print(f"{'='*100}\n")
    print(f"Totale scommesse analizzate: {len(df)}")
    print(f"Filtri applicati: Prob >= {min_prob:.0%}, Max {max_per_match}/match")

    # Filter by minimum probability
    df_filtered = df[df['probability'] >= min_prob].copy()
    print(f"Dopo filtro probabilità: {len(df_filtered)} scommesse")

    if len(df_filtered) == 0:
        print("\n[WARN] Nessuna scommessa trovata con i criteri specificati.")
        print("Prova ad abbassare --min-prob")
        return

    # Limit per match
    match_counts = defaultdict(int)
    selected_bets = []

    for _, bet in df_filtered.sort_values('probability', ascending=False).iterrows():
        match_id = bet['match_id']
        if match_counts[match_id] >= max_per_match:
            continue

        selected_bets.append(bet)
        match_counts[match_id] += 1

        if len(selected_bets) >= top_n * 2:  # Get extra for diversification
            break

    df_selected = pd.DataFrame(selected_bets)

    # Diversify by category if requested
    if diversify and len(df_selected) > top_n:
        # Prendi le migliori per categoria
        categories = df_selected['category'].unique()
        per_category = max(1, top_n // len(categories))

        final_picks = []
        for cat in categories:
            cat_bets = df_selected[df_selected['category'] == cat].head(per_category)
            final_picks.extend(cat_bets.to_dict('records'))

        # Fill remaining with highest prob regardless of category
        if len(final_picks) < top_n:
            remaining = top_n - len(final_picks)
            already_selected = {(b['match_id'], b['market']) for b in final_picks}
            for _, bet in df_selected.iterrows():
                if (bet['match_id'], bet['market']) not in already_selected:
                    final_picks.append(bet.to_dict())
                    if len(final_picks) >= top_n:
                        break

        df_final = pd.DataFrame(final_picks)
    else:
        df_final = df_selected.head(top_n)

    # Sort by probability descending
    df_final = df_final.sort_values('probability', ascending=False)

    # Print report
    print(f"\n{'='*100}")
    print(f"TOP {len(df_final)} SCOMMESSE SELEZIONATE")
    print(f"{'='*100}\n")

    total_prob_product = 1.0
    categories_count = df_final['category'].value_counts()

    print("=== Distribuzione per Categoria ===")
    for cat, count in categories_count.items():
        avg_prob = df_final[df_final['category'] == cat]['probability'].mean()
        print(f"  {cat:<25}: {count:2d} scommesse (Prob media: {avg_prob:.1%})")

    print(f"\n{'='*100}")
    print("=== SCOMMESSE CONSIGLIATE ===")
    print(f"{'='*100}\n")

    for i, (_, bet) in enumerate(df_final.iterrows(), 1):
        # Emoji per confidence
        if bet['probability'] >= 0.80:
            emoji = "🔥🔥"
        elif bet['probability'] >= 0.70:
            emoji = "🔥"
        elif bet['probability'] >= 0.60:
            emoji = "✅"
        else:
            emoji = "○"

        # Calculate potential return (esempio stake = 10€)
        stake = 10
        if pd.notna(bet.get('odds')) and bet['odds'] > 0:
            potential_win = stake * bet['odds']
            profit = potential_win - stake
            odds_str = f" | Q={bet['odds']:.2f} (Win: €{profit:.2f})"
        else:
            odds_str = ""

        print(f"{i:2d}. {emoji} {bet['market_name']}")
        print(f"    {bet['home'][:25]} - {bet['away'][:25]}")
        print(f"    P={bet['probability']:.1%} | Value={bet['value']:+.1%} | {bet['confidence'].upper()}{odds_str}")

        # Category tag
        print(f"    [{bet['category']}]")
        print()

        total_prob_product *= bet['probability']

    # Statistics
    print(f"{'='*100}")
    print("=== STATISTICHE COMBO ===")
    print(f"{'='*100}\n")

    avg_prob = df_final['probability'].mean()
    min_prob = df_final['probability'].min()
    max_prob = df_final['probability'].max()

    print(f"Probabilità Media: {avg_prob:.1%}")
    print(f"Probabilità Min: {min_prob:.1%}")
    print(f"Probabilità Max: {max_prob:.1%}")

    # Multiple bet simulation (tutte insieme)
    print(f"\nProbabilità TUTTE vincano (sistema integrale): {total_prob_product:.2%}")

    # Simulate partial systems
    print(f"\n=== SISTEMI PARZIALI (simulazione) ===")

    # At least 80% hit
    prob_80_pct = 1.0
    n_80 = int(len(df_final) * 0.8)
    for prob in df_final.nlargest(n_80, 'probability')['probability']:
        prob_80_pct *= prob
    print(f"Almeno {n_80}/{len(df_final)} vincano (top 80%): {prob_80_pct:.1%}")

    # At least 50% hit
    prob_50_pct = 1.0
    n_50 = int(len(df_final) * 0.5)
    for prob in df_final.nlargest(n_50, 'probability')['probability']:
        prob_50_pct *= prob
    print(f"Almeno {n_50}/{len(df_final)} vincano (top 50%): {prob_50_pct:.1%}")

    # Expected value analysis
    if 'odds' in df_final.columns:
        df_with_odds = df_final[df_final['odds'].notna()].copy()
        if len(df_with_odds) > 0:
            print(f"\n=== ANALISI VALUE (su {len(df_with_odds)} scommesse con quote) ===")

            total_ev = 0
            for _, bet in df_with_odds.iterrows():
                ev = (bet['probability'] * bet['odds']) - 1
                total_ev += ev

            avg_ev = total_ev / len(df_with_odds)
            print(f"Expected Value Medio: {avg_ev:+.1%}")
            print(f"Expected Value Totale: {total_ev:+.1%}")

            # Stake simulation
            total_stake = len(df_with_odds) * 10  # €10 per scommessa
            expected_profit = total_stake * (1 + avg_ev)
            print(f"\nSimulazione stake €10/scommessa:")
            print(f"  Stake totale: €{total_stake:.2f}")
            print(f"  Profitto atteso: €{expected_profit - total_stake:+.2f} ({avg_ev:+.1%})")

    print(f"\n{'='*100}")
    print("[INFO] Le probabilità sono calcolate con modelli ML su 62 features avanzate")
    print("[INFO] Scommettere sempre responsabilmente e solo quanto ci si può permettere di perdere")
    print(f"{'='*100}\n")

    # Save to CSV for easy import
    picks_csv = ROOT / "best_picks.csv"
    df_final.to_csv(picks_csv, index=False)
    print(f"[SAVED] Best picks salvate in {picks_csv}")


def main():
    parser = argparse.ArgumentParser(
        description="Genera report con le migliori scommesse"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=15,
        help="Numero di scommesse da mostrare (default: 15)"
    )
    parser.add_argument(
        "--min-prob",
        type=float,
        default=0.60,
        help="Probabilità minima (default: 0.60 = 60%%)"
    )
    parser.add_argument(
        "--max-per-match",
        type=int,
        default=3,
        help="Max scommesse per partita (default: 3)"
    )
    parser.add_argument(
        "--no-diversify",
        action="store_true",
        help="Disabilita diversificazione categorie"
    )

    args = parser.parse_args()

    generate_best_picks_report(
        top_n=args.top,
        min_prob=args.min_prob,
        max_per_match=args.max_per_match,
        diversify=not args.no_diversify
    )


if __name__ == "__main__":
    main()
