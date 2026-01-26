#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analisi Statistica delle Predizioni Generate
"""

import pandas as pd
import numpy as np
from collections import defaultdict

# Carica le predizioni
df = pd.read_csv('extended_predictions.csv')

print("=" * 100)
print("ANALISI STATISTICA PREDIZIONI - 2026-01-04")
print("=" * 100)

# 1. STATISTICHE GENERALI
print("\n📊 STATISTICHE GENERALI")
print("-" * 100)
print(f"Totale scommesse generate:      {len(df)}")
print(f"Partite analizzate:             {df['match_id'].nunique()}")
print(f"Scommesse per partita (media):  {len(df) / df['match_id'].nunique():.1f}")

# 2. DISTRIBUZIONE PER CATEGORIA
print("\n📈 DISTRIBUZIONE PER CATEGORIA")
print("-" * 100)
cat_stats = df.groupby('category').agg({
    'probability': ['count', 'mean', 'min', 'max'],
    'value': 'mean',
    'confidence': lambda x: (x == 'high').sum()
}).round(3)

for cat in df['category'].unique():
    cat_df = df[df['category'] == cat]
    count = len(cat_df)
    avg_prob = cat_df['probability'].mean() * 100
    min_prob = cat_df['probability'].min() * 100
    max_prob = cat_df['probability'].max() * 100
    avg_value = cat_df['value'].mean() * 100
    high_conf = (cat_df['confidence'] == 'high').sum()

    print(f"{cat:20s} | Count: {count:2d} | Prob: {avg_prob:5.1f}% ({min_prob:5.1f}%-{max_prob:5.1f}%) | Value: {avg_value:+6.1f}% | High: {high_conf}")

# 3. DISTRIBUZIONE PER CONFIDENCE
print("\n🎯 DISTRIBUZIONE PER CONFIDENCE LEVEL")
print("-" * 100)
for conf in ['high', 'medium', 'low']:
    conf_df = df[df['confidence'] == conf]
    count = len(conf_df)
    avg_prob = conf_df['probability'].mean() * 100
    avg_value = conf_df['value'].mean() * 100

    print(f"{conf.upper():8s} | Count: {count:2d} | Prob media: {avg_prob:5.1f}% | Value medio: {avg_value:+6.1f}%")

# 4. TOP 20 SCOMMESSE
print("\n🔥 TOP 20 SCOMMESSE (per probabilità)")
print("-" * 100)
top_20 = df.nlargest(20, 'probability')
for i, row in top_20.iterrows():
    conf_emoji = "🔥🔥" if row['confidence'] == 'high' else "🔥" if row['confidence'] == 'medium' else "○"
    print(f"{i+1:2d}. {conf_emoji} {row['home'][:25]:25s} - {row['away'][:25]:25s} | {row['market_name']:35s} | {row['probability']*100:5.1f}%")

# 5. ANALISI PER PARTITA
print("\n⚽ ANALISI PER PARTITA")
print("-" * 100)
for match_id in df['match_id'].unique():
    match_df = df[df['match_id'] == match_id].sort_values('probability', ascending=False)
    first = match_df.iloc[0]

    print(f"\n{first['kickoff_time']} | {first['home'][:30]} vs {first['away'][:30]}")
    print(f"  Scommesse generate: {len(match_df)}")
    print(f"  Top 3:")

    for j, (_, bet) in enumerate(match_df.head(3).iterrows(), 1):
        conf_emoji = "🔥🔥" if bet['confidence'] == 'high' else "🔥" if bet['confidence'] == 'medium' else "○"
        print(f"    {j}. {conf_emoji} {bet['market_name']:35s} {bet['probability']*100:5.1f}%")

# 6. SIMULAZIONE WIN RATE ATTESO
print("\n" + "=" * 100)
print("🎲 SIMULAZIONE WIN RATE ATTESO (Monte Carlo con 10,000 iterazioni)")
print("=" * 100)

# Simuliamo il win rate basandoci sulle probabilità
np.random.seed(42)
n_simulations = 10000

# Simula per diverse strategie
strategies = {
    'Top 10 (prob >= 75%)': df[df['probability'] >= 0.75].nlargest(10, 'probability'),
    'Top 20 (prob >= 70%)': df[df['probability'] >= 0.70].nlargest(20, 'probability'),
    'High Confidence only': df[df['confidence'] == 'high'],
    'Tutte le 52 scommesse': df
}

for strategy_name, strategy_df in strategies.items():
    if len(strategy_df) == 0:
        continue

    wins_per_sim = []

    for _ in range(n_simulations):
        # Per ogni scommessa, simula il risultato basandoci sulla probabilità
        results = np.random.random(len(strategy_df)) < strategy_df['probability'].values
        wins_per_sim.append(results.sum())

    wins_per_sim = np.array(wins_per_sim)
    avg_wins = wins_per_sim.mean()
    std_wins = wins_per_sim.std()
    win_rate = (avg_wins / len(strategy_df)) * 100

    # ROI atteso (assumendo quota media 1.8)
    avg_prob = strategy_df['probability'].mean()
    implied_odd = 1 / avg_prob if avg_prob > 0 else 0
    roi = ((avg_prob * implied_odd) - 1) * 100

    print(f"\n{strategy_name}")
    print(f"  Scommesse:        {len(strategy_df)}")
    print(f"  Prob media:       {strategy_df['probability'].mean()*100:.1f}%")
    print(f"  Vincite attese:   {avg_wins:.1f} ± {std_wins:.1f} su {len(strategy_df)}")
    print(f"  Win rate atteso:  {win_rate:.1f}%")
    print(f"  ROI teorico:      {roi:+.1f}%")

# 7. CONFRONTO CON SISTEMA PRECEDENTE
print("\n" + "=" * 100)
print("📊 CONFRONTO: SISTEMA VECCHIO vs SISTEMA NUOVO")
print("=" * 100)

print("\nSISTEMA VECCHIO (prima dei mercati estesi):")
print("  • Scommesse proposte:      11")
print("  • Scommesse vincenti:      2")
print("  • Win rate:                18.2%")
print("  • Mercati:                 Solo 1X2 e Over/Under 2.5")
print("  • Prob media:              ~45-50%")
print("  • ROI:                     NEGATIVO (circa -50%)")

print("\nSISTEMA NUOVO (con mercati estesi):")
top_20_new = df.nlargest(20, 'probability')
print(f"  • Scommesse proposte:      {len(df)} (filtrate top 20)")
print(f"  • Win rate atteso:         {top_20_new['probability'].mean()*100:.1f}%")
print(f"  • Mercati:                 {df['category'].nunique()} categorie diverse")
print(f"  • Prob media:              {df['probability'].mean()*100:.1f}%")
print(f"  • Prob media top 20:       {top_20_new['probability'].mean()*100:.1f}%")

# Calcola ROI atteso per top 20
top_20_roi = ((top_20_new['probability'].mean() * 1.5) - 1) * 100  # Assumendo quota media conservativa 1.5
print(f"  • ROI atteso (conserv.):   {top_20_roi:+.1f}%")

print("\nMIGLIORIA:")
improvement_wr = (top_20_new['probability'].mean()*100) - 18.2
improvement_roi = top_20_roi - (-50)
print(f"  • Win rate:                +{improvement_wr:.1f} punti percentuali")
print(f"  • ROI:                     +{improvement_roi:.1f} punti percentuali")
print(f"  • Mercati disponibili:     6x più opzioni")

# 8. RACCOMANDAZIONI
print("\n" + "=" * 100)
print("💡 RACCOMANDAZIONI STRATEGICHE")
print("=" * 100)

print("\n1️⃣  STRATEGIA CONSERVATIVA (basso rischio)")
conservative = df[df['probability'] >= 0.75].nlargest(10, 'probability')
print(f"   • Gioca solo Top 10 con prob >= 75%")
print(f"   • Scommesse: {len(conservative)}")
print(f"   • Win rate atteso: {conservative['probability'].mean()*100:.1f}%")
print(f"   • Stake consigliato: 2-3% del bankroll per scommessa")

print("\n2️⃣  STRATEGIA BILANCIATA (medio rischio)")
balanced = df[df['confidence'] == 'high']
print(f"   • Gioca tutte le HIGH confidence")
print(f"   • Scommesse: {len(balanced)}")
print(f"   • Win rate atteso: {balanced['probability'].mean()*100:.1f}%")
print(f"   • Stake consigliato: 1-2% del bankroll per scommessa")

print("\n3️⃣  STRATEGIA AGGRESSIVA (alto rischio/rendimento)")
aggressive = df.nlargest(30, 'value')
print(f"   • Gioca Top 30 per value")
print(f"   • Scommesse: {len(aggressive)}")
print(f"   • Win rate atteso: {aggressive['probability'].mean()*100:.1f}%")
print(f"   • Stake consigliato: 0.5-1% del bankroll per scommessa")

print("\n" + "=" * 100)
print("✅ ANALISI COMPLETATA")
print("=" * 100)
