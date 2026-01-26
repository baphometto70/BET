#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crea SCHEDINA OTTIMIZZATA per 7 gennaio 2026
Usando le predizioni ML + xG per massimizzare probabilità di vincita
"""

import pandas as pd
from itertools import combinations

# Carica extended predictions
df = pd.read_csv('extended_predictions.csv')

# Filtra solo HIGH confidence (>70%)
high_conf = df[df['confidence'] == 'high'].copy()

print("🎯 SCHEDINA OTTIMIZZATA 7 GENNAIO 2026")
print("=" * 100)
print(f"\nPredizioni high confidence: {len(high_conf)}")

# Raggruppa per partita
matches = high_conf.groupby('match_id').agg({
    'home': 'first',
    'away': 'first',
    'league': 'first',
    'kickoff_time': 'first'
}).reset_index()

print(f"Partite con almeno 1 pick high confidence: {len(matches)}\n")

# Per ogni partita, trova il pick con probabilità più alta
best_picks = []

for match_id in high_conf['match_id'].unique():
    match_preds = high_conf[high_conf['match_id'] == match_id]
    best = match_preds.nlargest(1, 'probability').iloc[0]

    best_picks.append({
        'match_id': match_id,
        'home': best['home'],
        'away': best['away'],
        'league': best['league'],
        'time': best['kickoff_time'],
        'market': best['market_name'],
        'probability': best['probability'],
        'category': best['category']
    })

# Ordina per probabilità decrescente
best_picks_df = pd.DataFrame(best_picks).sort_values('probability', ascending=False)

print("=" * 100)
print("TOP 10 PICK SINGOLI AD ALTA PROBABILITÀ")
print("=" * 100)

for i, pick in enumerate(best_picks_df.head(10).itertuples(), 1):
    quota = 1 / pick.probability
    print(f"{i}. {pick.home} vs {pick.away}")
    print(f"   🎯 {pick.market}")
    print(f"   📊 Probabilità: {pick.probability*100:.1f}%")
    print(f"   💰 Quota stimata: ~{quota:.2f}")
    print(f"   🏆 {pick.league} | ⏰ {pick.time}")
    print()

# SCHEDINA #1: TRIPLA SUPER SICURA (top 3 probabilità)
print("\n" + "=" * 100)
print("📋 SCHEDINA #1: TRIPLA SUPER SICURA")
print("=" * 100)

top3 = best_picks_df.head(3)
prob_combo = 1.0
quota_combo = 1.0

for i, pick in enumerate(top3.itertuples(), 1):
    prob_combo *= pick.probability
    quota_combo *= (1 / pick.probability)
    print(f"{i}. {pick.home} vs {pick.away} | ⏰ {pick.time}")
    print(f"   → {pick.market}")
    print(f"   📊 Prob: {pick.probability*100:.1f}%")

print(f"\n💡 Probabilità combinata: {prob_combo*100:.1f}%")
print(f"💰 Quota stimata totale: ~{quota_combo:.2f}")
print(f"🎲 Con 10€: potenziale vincita ~{quota_combo*10:.2f}€")

# SCHEDINA #2: QUINTUPLA VALUE
print("\n" + "=" * 100)
print("📋 SCHEDINA #2: QUINTUPLA VALUE (Più Rischiosa, Quote Alte)")
print("=" * 100)

top5 = best_picks_df.head(5)
prob_combo = 1.0
quota_combo = 1.0

for i, pick in enumerate(top5.itertuples(), 1):
    prob_combo *= pick.probability
    quota_combo *= (1 / pick.probability)
    print(f"{i}. {pick.home} vs {pick.away} | ⏰ {pick.time}")
    print(f"   → {pick.market}")
    print(f"   📊 Prob: {pick.probability*100:.1f}%")

print(f"\n💡 Probabilità combinata: {prob_combo*100:.1f}%")
print(f"💰 Quota stimata totale: ~{quota_combo:.2f}")
print(f"🎲 Con 5€: potenziale vincita ~{quota_combo*5:.2f}€")

# SCHEDINA #3: DOPPIA CHANCE MIX
print("\n" + "=" * 100)
print("📋 SCHEDINA #3: SPECIALIZZATA DOPPIA CHANCE")
print("=" * 100)

dc_picks = high_conf[high_conf['category'] == 'Doppia Chance'].nlargest(4, 'probability')
prob_combo = 1.0
quota_combo = 1.0

for i, pick in enumerate(dc_picks.itertuples(), 1):
    prob_combo *= pick.probability
    quota_combo *= (1 / pick.probability)
    print(f"{i}. {pick.home} vs {pick.away} | ⏰ {pick.kickoff_time}")
    print(f"   → {pick.market_name}")
    print(f"   📊 Prob: {pick.probability*100:.1f}%")

print(f"\n💡 Probabilità combinata: {prob_combo*100:.1f}%")
print(f"💰 Quota stimata totale: ~{quota_combo:.2f}")
print(f"🎲 Con 10€: potenziale vincita ~{quota_combo*10:.2f}€")

# SCHEDINA #4: OVER/UNDER MIX
print("\n" + "=" * 100)
print("📋 SCHEDINA #4: SPECIALIZZATA OVER/UNDER")
print("=" * 100)

ou_picks = high_conf[high_conf['category'] == 'Over/Under'].nlargest(4, 'probability')
prob_combo = 1.0
quota_combo = 1.0

for i, pick in enumerate(ou_picks.itertuples(), 1):
    prob_combo *= pick.probability
    quota_combo *= (1 / pick.probability)
    print(f"{i}. {pick.home} vs {pick.away} | ⏰ {pick.kickoff_time}")
    print(f"   → {pick.market_name}")
    print(f"   📊 Prob: {pick.probability*100:.1f}%")

print(f"\n💡 Probabilità combinata: {prob_combo*100:.1f}%")
print(f"💰 Quota stimata totale: ~{quota_combo:.2f}")
print(f"🎲 Con 10€: potenziale vincita ~{quota_combo*10:.2f}€")

# RIEPILOGO FINALE
print("\n" + "=" * 100)
print("💰 STRATEGIA BANKROLL CONSIGLIATA (Budget 50€)")
print("=" * 100)
print("""
CONSERVATIVA (Massima Sicurezza):
- 20€ su Schedina #1 (Tripla)
- 20€ divisi in 2 doppie dalle top 4
- 10€ riserva

BILANCIATA (Rischio Medio):
- 15€ su Schedina #1 (Tripla)
- 10€ su Schedina #3 (DC)
- 10€ su Schedina #4 (O/U)
- 10€ su 2 singole top
- 5€ riserva

AGGRESSIVA (Rischio Alto, Quote Alte):
- 10€ su Schedina #1 (Tripla)
- 15€ su Schedina #2 (Quintupla)
- 15€ su Schedina #3 (DC)
- 10€ riserva
""")

print("=" * 100)
print("⚠️  DISCLAIMER")
print("=" * 100)
print("""
- Queste predizioni sono basate su modelli ML + xG
- Le quote sono stimate e vanno verificate sul bookmaker
- Gioca responsabilmente
- Il gioco può causare dipendenza
- Vietato ai minori di 18 anni
""")
print("=" * 100)
