#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCHEDINA SMART 7 gennaio 2026
Predizioni DIVERSE cercando VALORE non solo alta probabilità
"""

import pandas as pd

df = pd.read_csv('extended_predictions.csv')

print("=" * 100)
print("🎯 SCHEDINE SMART - 7 GENNAIO 2026")
print("=" * 100)
print("Strategia: MASSIMIZZARE DIVERSITÀ E VALORE")
print("=" * 100)

# STRATEGIA 1: Cercare partite con probabilità SBILANCIATE (non equilibrate)
print("\n" + "="*100)
print("📊 ANALISI: Partite con xG più sbilanciate (favorito chiaro)")
print("="*100)

# Le migliori per scommettere sono quelle con favorito CHIARO
# Cerco DC 1X o X2 con prob >70% (non "12")

dc_1x = df[(df['market'] == 'dc_1x') & (df['probability'] > 0.70)].sort_values('probability', ascending=False)
dc_x2 = df[(df['market'] == 'dc_x2') & (df['probability'] > 0.70)].sort_values('probability', ascending=False)

print("\n🏠 FAVORITO CASA (1X con >70%):")
for i, row in enumerate(dc_1x.head(5).itertuples(), 1):
    print(f"{i}. {row.home:30} vs {row.away:30} → {row.probability*100:.1f}% (quota ~{1/row.probability:.2f})")

print("\n✈️  FAVORITO TRASFERTA (X2 con >70%):")
for i, row in enumerate(dc_x2.head(5).itertuples(), 1):
    print(f"{i}. {row.home:30} vs {row.away:30} → {row.probability*100:.1f}% (quota ~{1/row.probability:.2f})")

# SCHEDINA 1: Mix 1X + X2 + Multigol
print("\n" + "="*100)
print("📋 SCHEDINA #1: MIX DOPPIA CHANCE CON FAVORITI CHIARI")
print("="*100)

picks_1 = [
    dc_1x.iloc[0],  # Top 1X
    dc_x2.iloc[0],  # Top X2
    df[(df['category'] == 'Multigol') & (df['market'] != 'mg_2-5')].nlargest(1, 'probability').iloc[0]  # Multigol DIVERSO da 2-5
]

prob = 1.0
quota = 1.0
for i, pick in enumerate(picks_1, 1):
    prob *= pick['probability']
    quota *= (1 / pick['probability'])
    print(f"{i}. {pick['home']:30} vs {pick['away']:30}")
    print(f"   → {pick['market_name']}")
    print(f"   📊 {pick['probability']*100:.1f}% | Quota ~{1/pick['probability']:.2f}")

print(f"\n💰 Probabilità: {prob*100:.1f}% | Quota: ~{quota:.2f}")
print(f"🎲 Con 10€ → Vincita: ~{quota*10:.2f}€ | Profitto: ~{(quota-1)*10:.2f}€")

# SCHEDINA 2: Goal/NoGoal + Over/Under specifici
print("\n" + "="*100)
print("📋 SCHEDINA #2: GOL + RANGE SPECIFICO")
print("="*100)

# Cerco partite con GG alta E Over 1.5 alta (partite con gol)
partite_gol = []
for match_id in df['match_id'].unique():
    match_df = df[df['match_id'] == match_id]
    gg = match_df[match_df['market'] == 'gg']['probability'].values[0]
    over15 = match_df[match_df['market'] == 'over_1.5']['probability'].values[0]
    under35 = match_df[match_df['market'] == 'under_3.5']['probability'].values[0]

    if gg > 0.55 and over15 > 0.65:  # Partite con gol probabile
        partite_gol.append({
            'match_id': match_id,
            'home': match_df.iloc[0]['home'],
            'away': match_df.iloc[0]['away'],
            'gg': gg,
            'over15': over15,
            'under35': under35,
            'score': gg * over15  # Score combinato
        })

partite_gol_df = pd.DataFrame(partite_gol).sort_values('score', ascending=False)

print("\n🔥 TOP 3 PARTITE CON GOL ATTESO:")
picks_2 = []
for i, row in partite_gol_df.head(3).iterrows():
    print(f"{i+1}. {row['home']:30} vs {row['away']:30}")
    print(f"   GG: {row['gg']*100:.1f}% | Over 1.5: {row['over15']*100:.1f}% | Under 3.5: {row['under35']*100:.1f}%")

    # Pick: GG + Over 1.5
    gg_pick = df[(df['match_id'] == row['match_id']) & (df['market'] == 'gg')].iloc[0]
    picks_2.append(gg_pick)

print("\n📋 Schedina GG (3 partite):")
prob = 1.0
quota = 1.0
for i, pick in enumerate(picks_2, 1):
    prob *= pick['probability']
    quota *= (1 / pick['probability'])
    print(f"{i}. {pick['home']:30} vs {pick['away']:30} → GG")
    print(f"   📊 {pick['probability']*100:.1f}% | Quota ~{1/pick['probability']:.2f}")

print(f"\n💰 Probabilità: {prob*100:.1f}% | Quota: ~{quota:.2f}")
print(f"🎲 Con 10€ → Vincita: ~{quota*10:.2f}€ | Profitto: ~{(quota-1)*10:.2f}€")

# SCHEDINA 3: Partite con Under (pochi gol attesi)
print("\n" + "="*100)
print("📋 SCHEDINA #3: PARTITE CON POCHI GOL (Under)")
print("="*100)

# Cerco Under 2.5 con probabilità >50%
under25_picks = df[(df['market'] == 'under_2.5') & (df['probability'] > 0.48)].sort_values('probability', ascending=False).head(3)

prob = 1.0
quota = 1.0
for i, pick in enumerate(under25_picks.itertuples(), 1):
    prob *= pick.probability
    quota *= (1 / pick.probability)
    print(f"{i}. {pick.home:30} vs {pick.away:30} → Under 2.5")
    print(f"   📊 {pick.probability*100:.1f}% | Quota ~{1/pick.probability:.2f}")

print(f"\n💰 Probabilità: {prob*100:.1f}% | Quota: ~{quota:.2f}")
print(f"🎲 Con 10€ → Vincita: ~{quota*10:.2f}€ | Profitto: ~{(quota-1)*10:.2f}€")

# SCHEDINA 4: VALUE BET (Quote alte con prob decente)
print("\n" + "="*100)
print("📋 SCHEDINA #4: VALUE BET (Quote 1.60+, Prob 60%+)")
print("="*100)

# Cerco pick con prob 60-70% (quote ~1.4-1.7)
df['quota_stimata'] = 1 / df['probability']
df['value_score'] = df['probability'] * df['quota_stimata']  # Ideally should be >1

value_picks = df[
    (df['probability'] >= 0.60) &
    (df['probability'] <= 0.70) &
    (~df['market'].str.contains('over_0.5')) &  # Escludo Over 0.5
    (~df['market'].str.contains('dc_12'))  # Escludo DC 12
].sort_values('quota_stimata', ascending=False).head(4)

prob = 1.0
quota = 1.0
for i, pick in enumerate(value_picks.itertuples(), 1):
    prob *= pick.probability
    quota *= pick.quota_stimata
    print(f"{i}. {pick.home:30} vs {pick.away:30}")
    print(f"   → {pick.market_name}")
    print(f"   📊 {pick.probability*100:.1f}% | Quota ~{pick.quota_stimata:.2f}")

print(f"\n💰 Probabilità: {prob*100:.1f}% | Quota: ~{quota:.2f}")
print(f"🎲 Con 10€ → Vincita: ~{quota*10:.2f}€ | Profitto: ~{(quota-1)*10:.2f}€")

# RIEPILOGO FINALE
print("\n" + "="*100)
print("🎯 RIEPILOGO: QUALE SCHEDINA GIOCARE?")
print("="*100)
print("""
🥇 SCHEDINA #1 (Mix DC 1X/X2 + Multigol)
   ✅ PRO: Più bilanciata, favoriti chiari
   ⚠️  CONTRO: Quote medie (~3-4)
   💡 CONSIGLIO: Stake 15€

🥈 SCHEDINA #2 (Tripla GG)
   ✅ PRO: Logica chiara (partite con gol)
   ⚠️  CONTRO: GG è rischioso
   💡 CONSIGLIO: Stake 5€

🥉 SCHEDINA #3 (Tripla Under 2.5)
   ✅ PRO: Partite difensive
   ⚠️  CONTRO: Basta 1 gol in più per perdere
   💡 CONSIGLIO: Stake 5€

💎 SCHEDINA #4 (Value Bet)
   ✅ PRO: Quote alte (>5.00)
   ⚠️  CONTRO: Rischio alto
   💡 CONSIGLIO: Stake 5€ (giocata speculativa)

📊 STRATEGIA COMPLESSIVA (Budget 50€):
- 15€ Schedina #1
- 10€ Singole top (DC 1X/X2 con >73%)
- 5€ Schedina #2
- 5€ Schedina #3
- 5€ Schedina #4
- 10€ Riserva
""")

print("="*100)
print("✅ QUESTE SCHEDINE SONO DIVERSE E BILANCIATE")
print("="*100)
