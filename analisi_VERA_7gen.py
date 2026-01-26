#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ANALISI VERA delle predizioni 7 gennaio
Mostra TUTTE le predizioni diverse per categoria
"""

import pandas as pd

df = pd.read_csv('extended_predictions.csv')

print("=" * 100)
print("ANALISI VERA PREDIZIONI 7 GENNAIO 2026")
print("=" * 100)
print(f"\nTotale predizioni: {len(df)}")
print(f"Partite: {df['match_id'].nunique()}")
print(f"Mercati per partita: {len(df) // df['match_id'].nunique()}")

# Mostra distribuzione probabilità
print("\n" + "=" * 100)
print("DISTRIBUZIONE PROBABILITÀ")
print("=" * 100)
print(df['probability'].describe())

print("\n" + "=" * 100)
print("📊 PREDIZIONI PER CATEGORIA")
print("=" * 100)

for category in df['category'].unique():
    cat_df = df[df['category'] == category].sort_values('probability', ascending=False)

    print(f"\n{'='*100}")
    print(f"🎯 {category.upper()} ({len(cat_df)} predizioni)")
    print(f"{'='*100}")

    # Mostra top 5 e bottom 5
    print(f"\n📈 TOP 5 (Probabilità più alte):")
    for i, row in enumerate(cat_df.head(5).itertuples(), 1):
        print(f"{i}. {row.home[:20]:20} vs {row.away[:20]:20}")
        print(f"   → {row.market_name}")
        print(f"   📊 {row.probability*100:.1f}% | Quota: ~{1/row.probability:.2f}")

    print(f"\n📉 BOTTOM 5 (Probabilità più basse):")
    for i, row in enumerate(cat_df.tail(5).itertuples(), 1):
        print(f"{i}. {row.home[:20]:20} vs {row.away[:20]:20}")
        print(f"   → {row.market_name}")
        print(f"   📊 {row.probability*100:.1f}% | Quota: ~{1/row.probability:.2f}")

    # Statistiche
    print(f"\n📊 Statistiche {category}:")
    print(f"   Min: {cat_df['probability'].min()*100:.1f}%")
    print(f"   Max: {cat_df['probability'].max()*100:.1f}%")
    print(f"   Media: {cat_df['probability'].mean()*100:.1f}%")
    print(f"   Mediana: {cat_df['probability'].median()*100:.1f}%")

# Analisi per singola partita
print("\n" + "=" * 100)
print("🔍 ESEMPIO: Bologna vs Atalanta (Tutte le predizioni)")
print("=" * 100)

bologna = df[df['match_id'] == '20260107_536996_SA'].sort_values('probability', ascending=False)
for i, row in enumerate(bologna.itertuples(), 1):
    conf_icon = "🔥" if row.confidence == 'high' else "⭐" if row.confidence == 'medium' else "💡"
    print(f"{i:2d}. {conf_icon} {row.market_name:35} → {row.probability*100:5.1f}% (quota ~{1/row.probability:.2f})")

# Confronta 2 partite diverse
print("\n" + "=" * 100)
print("⚖️  CONFRONTO: Napoli vs Verona  VS  Fulham vs Chelsea")
print("=" * 100)

napoli = df[df['match_id'] == '20260107_537002_SA']
fulham = df[df['match_id'] == '20260107_537991_PL']

print("\n🔵 Napoli vs Verona (Napoli favorita):")
for row in napoli.nlargest(5, 'probability').itertuples():
    print(f"   {row.market_name:35} → {row.probability*100:5.1f}%")

print("\n🔵 Fulham vs Chelsea (Chelsea favorita):")
for row in fulham.nlargest(5, 'probability').itertuples():
    print(f"   {row.market_name:35} → {row.probability*100:5.1f}%")

# PICKS FINALI INTELLIGENTI
print("\n" + "=" * 100)
print("🎯 PICKS FINALI DIVERSIFICATI (Evito categorie sovrapposte)")
print("=" * 100)

# 1 DC, 1 Multigol, 1 Over/Under (escludo 0.5), 1 GG/NG
dc_best = df[df['category'] == 'Doppia Chance'].nlargest(1, 'probability').iloc[0]
mg_best = df[df['category'] == 'Multigol'].nlargest(1, 'probability').iloc[0]
ou_best = df[(df['category'] == 'Over/Under') & (~df['market'].str.contains('0.5'))].nlargest(1, 'probability').iloc[0]
gg_best = df[df['category'] == 'Goal/No Goal'].nlargest(1, 'probability').iloc[0]

picks = [
    ('DOPPIA CHANCE', dc_best),
    ('MULTIGOL', mg_best),
    ('OVER/UNDER', ou_best),
    ('GOAL/NO GOAL', gg_best)
]

prob_combo = 1.0
quota_combo = 1.0

for tipo, pick in picks:
    prob_combo *= pick['probability']
    quota_combo *= (1 / pick['probability'])
    print(f"\n{tipo}:")
    print(f"   {pick['home']} vs {pick['away']}")
    print(f"   → {pick['market_name']}")
    print(f"   📊 {pick['probability']*100:.1f}% | Quota ~{1/pick['probability']:.2f}")

print(f"\n{'='*100}")
print(f"💡 SCHEDINA QUADRUPLA DIVERSIFICATA")
print(f"{'='*100}")
print(f"Probabilità combinata: {prob_combo*100:.1f}%")
print(f"Quota totale: ~{quota_combo:.2f}")
print(f"Con 10€ → Vincita potenziale: ~{quota_combo*10:.2f}€")
print(f"Profitto: ~{(quota_combo-1)*10:.2f}€")

print("\n" + "=" * 100)
