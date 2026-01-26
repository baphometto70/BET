#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analisi Completa Risultati vs Predizioni
"""

import pandas as pd

# Carica predizioni
df = pd.read_csv('extended_predictions.csv')

# Risultato reale Inter-Bologna
results = {
    '20260104_536991_SA': {  # Inter - Bologna
        'home': 'Inter',
        'away': 'Bologna',
        'home_goals': 2,
        'away_goals': 1,
        'total_goals': 3
    }
}

def check_prediction(market, home_goals, away_goals, total_goals):
    """Verifica se predizione è corretta"""

    # Over/Under
    if 'over_1.5' in market:
        return total_goals > 1.5
    elif 'over_2.5' in market:
        return total_goals > 2.5
    elif 'under_2.5' in market:
        return total_goals < 2.5
    elif 'under_3.5' in market:
        return total_goals < 3.5

    # Doppia Chance
    elif market == 'dc_1x':  # Home or Draw
        return home_goals >= away_goals
    elif market == 'dc_x2':  # Draw or Away
        return away_goals >= home_goals
    elif market == 'dc_12':  # No draw
        return home_goals != away_goals

    # Goal/No Goal
    elif market == 'gg':
        return home_goals > 0 and away_goals > 0
    elif market == 'ng':
        return home_goals == 0 or away_goals == 0

    # Multigol
    elif 'mg_1-2' in market:
        return 1 <= total_goals <= 2
    elif 'mg_1-3' in market:
        return 1 <= total_goals <= 3
    elif 'mg_1-4' in market:
        return 1 <= total_goals <= 4
    elif 'mg_2-3' in market:
        return 2 <= total_goals <= 3
    elif 'mg_2-4' in market:
        return 2 <= total_goals <= 4
    elif 'mg_2-5' in market:
        return 2 <= total_goals <= 5
    elif 'mg_3-5' in market:
        return 3 <= total_goals <= 5

    return False


print("\n" + "="*120)
print("ANALISI COMPLETA: PREDIZIONI vs RISULTATI REALI")
print("="*120)

# Analizza ogni partita
for match_id, result in results.items():
    match_preds = df[df['match_id'] == match_id]

    if len(match_preds) == 0:
        continue

    home_goals = result['home_goals']
    away_goals = result['away_goals']
    total_goals = result['total_goals']

    print(f"\n{'='*120}")
    print(f"⚽ PARTITA: {result['home']} {home_goals}-{away_goals} {result['away']}")
    print(f"   Total Goals: {total_goals}")
    print(f"{'='*120}")

    # Header tabella
    print(f"\n{'MERCATO':<40} | {'PROB':>6} | {'CONF':>8} | {'CATEGORIA':<15} | {'ESITO':>8}")
    print("-"*120)

    correct_count = 0
    total_count = 0

    results_by_category = {}

    for _, pred in match_preds.iterrows():
        market = pred['market']
        market_name = pred['market_name']
        prob = pred['probability']
        conf = pred['confidence'].upper()
        category = pred['category']

        is_correct = check_prediction(market, home_goals, away_goals, total_goals)

        total_count += 1
        if is_correct:
            correct_count += 1
            emoji = "✅ VINTA"
        else:
            emoji = "❌ PERSA"

        # Raggruppa per categoria
        if category not in results_by_category:
            results_by_category[category] = {'correct': 0, 'total': 0, 'probs': []}

        results_by_category[category]['total'] += 1
        results_by_category[category]['probs'].append(prob)
        if is_correct:
            results_by_category[category]['correct'] += 1

        # Stampa riga
        print(f"{market_name:<40} | {prob*100:5.1f}% | {conf:>8} | {category:<15} | {emoji}")

    # Statistiche partita
    print("\n" + "-"*120)
    win_rate = (correct_count / total_count) * 100
    expected_rate = match_preds['probability'].mean() * 100
    diff = win_rate - expected_rate

    print(f"TOTALE: {correct_count}/{total_count} = {win_rate:.1f}% win rate")
    print(f"ATTESO: {expected_rate:.1f}% | DIFFERENZA: {diff:+.1f}%")

    # Statistiche per categoria
    print(f"\n{'CATEGORIA':<20} | {'CORRETTE':>10} | {'TOTALI':>8} | {'WIN RATE':>10} | {'PROB MEDIA':>12}")
    print("-"*120)

    for cat, stats in results_by_category.items():
        cat_win_rate = (stats['correct'] / stats['total']) * 100
        cat_prob_avg = sum(stats['probs']) / len(stats['probs']) * 100
        print(f"{cat:<20} | {stats['correct']:>10} | {stats['total']:>8} | {cat_win_rate:>9.1f}% | {cat_prob_avg:>11.1f}%")


# RIEPILOGO FINALE
print("\n\n" + "="*120)
print("RIEPILOGO COMPLESSIVO")
print("="*120)

total_predictions = 0
total_correct = 0
all_probs = []

for match_id in results.keys():
    match_preds = df[df['match_id'] == match_id]
    result = results[match_id]

    for _, pred in match_preds.iterrows():
        is_correct = check_prediction(
            pred['market'],
            result['home_goals'],
            result['away_goals'],
            result['total_goals']
        )

        total_predictions += 1
        all_probs.append(pred['probability'])
        if is_correct:
            total_correct += 1

overall_win_rate = (total_correct / total_predictions) * 100
overall_expected = (sum(all_probs) / len(all_probs)) * 100
overall_diff = overall_win_rate - overall_expected

print(f"\nPartite analizzate:        {len(results)}")
print(f"Predizioni totali:         {total_predictions}")
print(f"Predizioni corrette:       {total_correct}")
print(f"Predizioni sbagliate:      {total_predictions - total_correct}")
print(f"\nWin Rate complessivo:      {overall_win_rate:.1f}%")
print(f"Win Rate atteso:           {overall_expected:.1f}%")
print(f"Differenza:                {overall_diff:+.1f}%")

if overall_diff > 10:
    verdict = "🎉 ECCELLENTE - Modello supera ampiamente le aspettative!"
elif overall_diff > 0:
    verdict = "✅ OTTIMO - Modello ben calibrato e performante"
elif overall_diff > -5:
    verdict = "✓ BUONO - Modello sostanzialmente calibrato"
else:
    verdict = "⚠️  DA MIGLIORARE - Modello sottoperforma"

print(f"\nVERDETTO: {verdict}")

# Confronto con sistema vecchio
print(f"\n{'='*120}")
print("CONFRONTO CON SISTEMA PRECEDENTE")
print("="*120)

print(f"\nSISTEMA VECCHIO:")
print(f"  Win Rate:    18.2% (2/11)")
print(f"  ROI:         -50% circa")

print(f"\nSISTEMA NUOVO:")
print(f"  Win Rate:    {overall_win_rate:.1f}% ({total_correct}/{total_predictions})")
print(f"  ROI stimato: {(overall_win_rate - 50) * 2:.1f}%")

improvement = overall_win_rate - 18.2
print(f"\nMIGLIORIA:     +{improvement:.1f} punti percentuali")

print("\n" + "="*120)
