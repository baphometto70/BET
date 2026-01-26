#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verifica Risultati delle Predizioni

Confronta le predizioni generate con i risultati reali delle partite.
Esegui dopo che i risultati sono stati importati nel database.

Usage:
    python3 verifica_risultati.py --date 2026-01-04
"""

import argparse
import pandas as pd
from database import SessionLocal
from models import Fixture
from datetime import date as date_type

def verify_predictions(date_str: str):
    """
    Verifica le predizioni confrontandole con i risultati reali.

    Args:
        date_str: Data in formato YYYY-MM-DD
    """
    db = SessionLocal()

    # Parse date
    year, month, day = map(int, date_str.split('-'))
    target_date = date_type(year, month, day)

    # Carica predizioni
    try:
        predictions_df = pd.read_csv('extended_predictions.csv')
        # Filtra per data
        predictions_df['match_date'] = predictions_df['match_id'].str[:8]
        target_date_str = date_str.replace('-', '')
        predictions_df = predictions_df[predictions_df['match_date'] == target_date_str]
    except FileNotFoundError:
        print("[ERROR] File extended_predictions.csv non trovato")
        db.close()
        return

    if len(predictions_df) == 0:
        print(f"[WARN] Nessuna predizione trovata per {date_str}")
        db.close()
        return

    # Carica risultati reali
    matches = db.query(Fixture).filter(
        Fixture.date == target_date
    ).all()

    # Crea dizionario match_id -> risultato
    results = {}
    for m in matches:
        if m.result_home_goals is not None:
            results[m.match_id] = {
                'home_goals': m.result_home_goals,
                'away_goals': m.result_away_goals,
                'total_goals': m.result_home_goals + m.result_away_goals,
                'home': m.home,
                'away': m.away,
                'league': m.league,
                'time': m.time
            }

    if len(results) == 0:
        print(f"\n[WARN] Nessun risultato ancora disponibile per {date_str}")
        print("Esegui prima: python3 results_importer.py --date {date_str}")
        db.close()
        return

    print("\n" + "="*100)
    print(f"VERIFICA PREDIZIONI - {date_str}")
    print("="*100)

    # Statistiche per partita
    correct_by_match = {}
    total_by_match = {}

    for match_id in results.keys():
        match_preds = predictions_df[predictions_df['match_id'] == match_id]
        if len(match_preds) == 0:
            continue

        result = results[match_id]
        home_goals = result['home_goals']
        away_goals = result['away_goals']
        total_goals = result['total_goals']

        print(f"\n{'='*100}")
        print(f"⚽ {result['time']} | {result['home']} {home_goals}-{away_goals} {result['away']}")
        print(f"   League: {result['league']} | Total Goals: {total_goals}")
        print(f"   Predizioni: {len(match_preds)}")

        correct = 0
        wrong = 0

        for _, pred in match_preds.iterrows():
            market = pred['market']
            prob = pred['probability']
            market_name = pred['market_name']

            # Verifica se la predizione è corretta
            is_correct = check_prediction(market, home_goals, away_goals, total_goals)

            if is_correct:
                correct += 1
                emoji = "✅"
                status = "VINTA"
            else:
                wrong += 1
                emoji = "❌"
                status = "PERSA"

            print(f"   {emoji} {market_name:40s} | Prob: {prob*100:5.1f}% | {status}")

        correct_by_match[match_id] = correct
        total_by_match[match_id] = len(match_preds)

        win_rate = (correct / len(match_preds)) * 100 if len(match_preds) > 0 else 0
        print(f"\n   📊 Win Rate partita: {correct}/{len(match_preds)} = {win_rate:.1f}%")

    # Statistiche complessive
    print("\n" + "="*100)
    print("📊 STATISTICHE COMPLESSIVE")
    print("="*100)

    total_predictions = sum(total_by_match.values())
    total_correct = sum(correct_by_match.values())
    total_wrong = total_predictions - total_correct
    overall_win_rate = (total_correct / total_predictions) * 100 if total_predictions > 0 else 0

    print(f"\nPartite analizzate:      {len(results)}")
    print(f"Predizioni totali:       {total_predictions}")
    print(f"Predizioni corrette:     {total_correct} ✅")
    print(f"Predizioni sbagliate:    {total_wrong} ❌")
    print(f"Win Rate complessivo:    {overall_win_rate:.1f}%")

    # Confronto con atteso
    expected_win_rate = predictions_df['probability'].mean() * 100
    difference = overall_win_rate - expected_win_rate

    print(f"\nWin Rate atteso:         {expected_win_rate:.1f}%")
    print(f"Differenza:              {difference:+.1f}%")

    if difference > 0:
        print(f"✅ Il modello ha performato MEGLIO del previsto!")
    elif difference < -5:
        print(f"⚠️  Il modello ha performato PEGGIO del previsto")
    else:
        print(f"✅ Il modello è CALIBRATO correttamente")

    # Statistiche per categoria
    print("\n" + "="*100)
    print("📈 PERFORMANCE PER CATEGORIA")
    print("="*100)

    for category in predictions_df['category'].unique():
        cat_preds = predictions_df[predictions_df['category'] == category]
        cat_correct = 0
        cat_total = 0

        for _, pred in cat_preds.iterrows():
            match_id = pred['match_id']
            if match_id not in results:
                continue

            result = results[match_id]
            is_correct = check_prediction(
                pred['market'],
                result['home_goals'],
                result['away_goals'],
                result['total_goals']
            )

            cat_total += 1
            if is_correct:
                cat_correct += 1

        if cat_total > 0:
            cat_win_rate = (cat_correct / cat_total) * 100
            cat_expected = cat_preds['probability'].mean() * 100
            cat_diff = cat_win_rate - cat_expected

            print(f"\n{category:20s}")
            print(f"  Predizioni:    {cat_total}")
            print(f"  Corrette:      {cat_correct}")
            print(f"  Win Rate:      {cat_win_rate:.1f}%")
            print(f"  Atteso:        {cat_expected:.1f}%")
            print(f"  Differenza:    {cat_diff:+.1f}%")

    # Statistiche per confidence
    print("\n" + "="*100)
    print("🎯 PERFORMANCE PER CONFIDENCE LEVEL")
    print("="*100)

    for conf in ['high', 'medium', 'low']:
        conf_preds = predictions_df[predictions_df['confidence'] == conf]
        conf_correct = 0
        conf_total = 0

        for _, pred in conf_preds.iterrows():
            match_id = pred['match_id']
            if match_id not in results:
                continue

            result = results[match_id]
            is_correct = check_prediction(
                pred['market'],
                result['home_goals'],
                result['away_goals'],
                result['total_goals']
            )

            conf_total += 1
            if is_correct:
                conf_correct += 1

        if conf_total > 0:
            conf_win_rate = (conf_correct / conf_total) * 100
            conf_expected = conf_preds['probability'].mean() * 100
            conf_diff = conf_win_rate - conf_expected

            print(f"\n{conf.upper():8s}")
            print(f"  Predizioni:    {conf_total}")
            print(f"  Corrette:      {conf_correct}")
            print(f"  Win Rate:      {conf_win_rate:.1f}%")
            print(f"  Atteso:        {conf_expected:.1f}%")
            print(f"  Differenza:    {conf_diff:+.1f}%")

    print("\n" + "="*100)

    db.close()


def check_prediction(market: str, home_goals: int, away_goals: int, total_goals: int) -> bool:
    """
    Verifica se una predizione è corretta dato il risultato.

    Args:
        market: Nome del mercato (es. 'over_2.5', 'dc_1x')
        home_goals: Gol casa
        away_goals: Gol trasferta
        total_goals: Totale gol

    Returns:
        True se la predizione è corretta, False altrimenti
    """
    # Over/Under
    if 'over_' in market:
        line = float(market.split('_')[1])
        return total_goals > line

    if 'under_' in market:
        line = float(market.split('_')[1])
        return total_goals < line

    # Doppia Chance
    if market == 'dc_1x':  # Home or Draw
        return home_goals >= away_goals

    if market == 'dc_x2':  # Draw or Away
        return away_goals >= home_goals

    if market == 'dc_12':  # Home or Away (no draw)
        return home_goals != away_goals

    # Goal/No Goal
    if market == 'gg':  # Both teams score
        return home_goals > 0 and away_goals > 0

    if market == 'ng':  # At least one doesn't score
        return home_goals == 0 or away_goals == 0

    # Multigol
    if market.startswith('mg_'):
        goals_range = market.split('_')[1]

        if goals_range == '1-2':
            return 1 <= total_goals <= 2
        elif goals_range == '1-3':
            return 1 <= total_goals <= 3
        elif goals_range == '1-4':
            return 1 <= total_goals <= 4
        elif goals_range == '2-3':
            return 2 <= total_goals <= 3
        elif goals_range == '2-4':
            return 2 <= total_goals <= 4
        elif goals_range == '2-5':
            return 2 <= total_goals <= 5
        elif goals_range == '3-5':
            return 3 <= total_goals <= 5

    # Combo markets (DC + GG/NG)
    if market.startswith('combo_'):
        parts = market.split('_')

        # combo_1x_gg
        if len(parts) == 3:
            dc = parts[1]
            gg_ng = parts[2]

            # Check DC
            dc_result = False
            if dc == '1x':
                dc_result = home_goals >= away_goals
            elif dc == 'x2':
                dc_result = away_goals >= home_goals
            elif dc == '12':
                dc_result = home_goals != away_goals

            # Check GG/NG
            gg_ng_result = False
            if gg_ng == 'gg':
                gg_ng_result = home_goals > 0 and away_goals > 0
            elif gg_ng == 'ng':
                gg_ng_result = home_goals == 0 or away_goals == 0
            elif gg_ng.startswith('over'):
                line = float(gg_ng.replace('over', ''))
                gg_ng_result = total_goals > line
            elif gg_ng.startswith('under'):
                line = float(gg_ng.replace('under', ''))
                gg_ng_result = total_goals < line

            return dc_result and gg_ng_result

    # Default: unknown market
    return False


def main():
    parser = argparse.ArgumentParser(description="Verifica risultati predizioni")
    parser.add_argument('--date', type=str, required=True, help="Data in formato YYYY-MM-DD")

    args = parser.parse_args()
    verify_predictions(args.date)


if __name__ == "__main__":
    main()
