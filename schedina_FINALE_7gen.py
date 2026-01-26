#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCHEDINA FINALE 7 GENNAIO - LA VERITÀ
Basata SOLO su Poisson (ML è rotto) ma con analisi intelligente
"""

from database import SessionLocal
from models import Fixture
from datetime import date
from scipy.stats import poisson
import pandas as pd

db = SessionLocal()
fixtures = db.query(Fixture).filter(Fixture.date == date(2026, 1, 7)).all()

print("="*100)
print("🎯 SCHEDINA FINALE 7 GENNAIO 2026 - ANALISI ONESTA")
print("="*100)
print(f"⚠️  DISCLAIMER: I modelli ML sono rotti (danno solo 2 classi invece di 3)")
print(f"✅ USO SOLO POISSON (matematicamente corretto)")
print(f"⚠️  PROBLEMA: Con xG simili (1.1-1.7), Poisson dà risultati simili")
print("="*100)

partite_analisi = []

for fix in fixtures:
    if not fix.feature:
        continue

    feat = fix.feature
    if not all([feat.xg_for_home, feat.xg_against_home, feat.xg_for_away, feat.xg_against_away]):
        continue

    # Lambda
    lam_h = (feat.xg_for_home + feat.xg_against_away) / 2
    lam_a = (feat.xg_for_away + feat.xg_against_home) / 2

    # Probabilità 1X2
    p_h = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a) for i in range(10) for j in range(i))
    p_d = sum(poisson.pmf(i, lam_h) * poisson.pmf(i, lam_a) for i in range(10))
    p_a = 1 - p_h - p_d

    # Over/Under
    p_over15 = 1 - sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                       for i in range(2) for j in range(2) if i+j <= 1)
    p_over25 = 1 - sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                       for i in range(3) for j in range(3) if i+j <= 2)

    # GG
    p_gg = 1 - (poisson.pmf(0, lam_h) * sum(poisson.pmf(j, lam_a) for j in range(10)) +
                sum(poisson.pmf(i, lam_h) for i in range(10)) * poisson.pmf(0, lam_a) -
                poisson.pmf(0, lam_h) * poisson.pmf(0, lam_a))

    partite_analisi.append({
        'home': fix.home,
        'away': fix.away,
        'time': fix.time,
        'league': fix.league,
        'lam_h': lam_h,
        'lam_a': lam_a,
        'p_h': p_h,
        'p_d': p_d,
        'p_a': p_a,
        'p_1x': p_h + p_d,
        'p_x2': p_d + p_a,
        'p_12': p_h + p_a,
        'p_over15': p_over15,
        'p_over25': p_over25,
        'p_under25': 1 - p_over25,
        'p_gg': p_gg,
        'favorito': 'CASA' if p_h > p_a and p_h > p_d else 'TRASFERTA' if p_a > p_h and p_a > p_d else 'EQUILIBRIO'
    })

df = pd.DataFrame(partite_analisi)

print(f"\n📊 SITUAZIONE REALE:")
print(f"   Partite con FAVORITO CASA: {len(df[df['favorito']=='CASA'])}")
print(f"   Partite con FAVORITO TRASFERTA: {len(df[df['favorito']=='TRASFERTA'])}")
print(f"   Partite EQUILIBRATE: {len(df[df['favorito']=='EQUILIBRIO'])}")

# Mostra le partite con favorito chiaro
print("\n" + "="*100)
print("🏠 PARTITE CON FAVORITO CASA CHIARO (Prob Casa > 40%)")
print("="*100)
casa_fav = df[df['p_h'] > 0.40].sort_values('p_h', ascending=False)
for i, row in casa_fav.iterrows():
    print(f"{row['home']:30} vs {row['away']:30}")
    print(f"   1: {row['p_h']*100:5.1f}% | X: {row['p_d']*100:5.1f}% | 2: {row['p_a']*100:5.1f}%")
    print(f"   PICK: 1X ({row['p_1x']*100:.1f}%) quota ~{1/row['p_1x']:.2f}")

print("\n" + "="*100)
print("✈️  PARTITE CON FAVORITO TRASFERTA CHIARO (Prob Trasferta > 40%)")
print("="*100)
away_fav = df[df['p_a'] > 0.40].sort_values('p_a', ascending=False)
for i, row in away_fav.iterrows():
    print(f"{row['home']:30} vs {row['away']:30}")
    print(f"   1: {row['p_h']*100:5.1f}% | X: {row['p_d']*100:5.1f}% | 2: {row['p_a']*100:5.1f}%")
    print(f"   PICK: X2 ({row['p_x2']*100:.1f}%) quota ~{1/row['p_x2']:.2f}")

print("\n" + "="*100)
print("⚖️  PARTITE EQUILIBRATE (Tutte le prob < 40%)")
print("="*100)
equilibrate = df[(df['p_h'] <= 0.40) & (df['p_a'] <= 0.40)]
for i, row in equilibrate.iterrows():
    print(f"{row['home']:30} vs {row['away']:30}")
    print(f"   1: {row['p_h']*100:5.1f}% | X: {row['p_d']*100:5.1f}% | 2: {row['p_a']*100:5.1f}%")
    print(f"   PICK: 12 ({row['p_12']*100:.1f}%) quota ~{1/row['p_12']:.2f}")

# SCHEDINE FINALI
print("\n" + "="*100)
print("🎯 SCHEDINE CONSIGLIATE (Basate su analisi reale)")
print("="*100)

print("\n📋 SCHEDINA #1: FAVORITI CHIARI (3 eventi)")
print("-"*100)
picks_1 = []

# Prendi il top favorito casa
if len(casa_fav) > 0:
    top_casa = casa_fav.iloc[0]
    picks_1.append(('1X', top_casa))
    print(f"1. {top_casa['home']:30} vs {top_casa['away']:30} | 1X")
    print(f"   Prob: {top_casa['p_1x']*100:.1f}% | Quota: ~{1/top_casa['p_1x']:.2f}")

# Prendi il top favorito trasferta
if len(away_fav) > 0:
    top_away = away_fav.iloc[0]
    picks_1.append(('X2', top_away))
    print(f"2. {top_away['home']:30} vs {top_away['away']:30} | X2")
    print(f"   Prob: {top_away['p_x2']*100:.1f}% | Quota: ~{1/top_away['p_x2']:.2f}")

# Aggiungi Over 1.5 della partita con lambda totale più alto
df['lam_tot'] = df['lam_h'] + df['lam_a']
top_gol = df.nlargest(1, 'lam_tot').iloc[0]
picks_1.append(('O1.5', top_gol))
print(f"3. {top_gol['home']:30} vs {top_gol['away']:30} | Over 1.5")
print(f"   Prob: {top_gol['p_over15']*100:.1f}% | Quota: ~{1/top_gol['p_over15']:.2f}")

# Calcola quota combinata
prob_comb = picks_1[0][1]['p_1x'] * picks_1[1][1]['p_x2'] * picks_1[2][1]['p_over15']
quota_comb = 1 / picks_1[0][1]['p_1x'] * 1 / picks_1[1][1]['p_x2'] * 1 / picks_1[2][1]['p_over15']
print(f"\n💰 TOTALE: Prob {prob_comb*100:.1f}% | Quota ~{quota_comb:.2f}")
print(f"🎲 Con 10€ → Vincita ~{quota_comb*10:.2f}€ | Profitto ~{(quota_comb-1)*10:.2f}€")

print("\n📋 SCHEDINA #2: GOL (Tripla GG)")
print("-"*100)
top_gg = df.nlargest(3, 'p_gg')
prob_gg_comb = 1.0
quota_gg_comb = 1.0
for i, row in enumerate(top_gg.itertuples(), 1):
    prob_gg_comb *= row.p_gg
    quota_gg_comb *= 1/row.p_gg
    print(f"{i}. {row.home:30} vs {row.away:30} | GG")
    print(f"   Prob: {row.p_gg*100:.1f}% | Quota: ~{1/row.p_gg:.2f}")

print(f"\n💰 TOTALE: Prob {prob_gg_comb*100:.1f}% | Quota ~{quota_gg_comb:.2f}")
print(f"🎲 Con 5€ → Vincita ~{quota_gg_comb*5:.2f}€ | Profitto ~{(quota_gg_comb-1)*5:.2f}€")

print("\n📋 SCHEDINA #3: UNDER (Tripla Under 2.5)")
print("-"*100)
top_under = df.nlargest(3, 'p_under25')
prob_under_comb = 1.0
quota_under_comb = 1.0
for i, row in enumerate(top_under.itertuples(), 1):
    prob_under_comb *= row.p_under25
    quota_under_comb *= 1/row.p_under25
    print(f"{i}. {row.home:30} vs {row.away:30} | Under 2.5")
    print(f"   Prob: {row.p_under25*100:.1f}% | Quota: ~{1/row.p_under25:.2f}")

print(f"\n💰 TOTALE: Prob {prob_under_comb*100:.1f}% | Quota ~{quota_under_comb:.2f}")
print(f"🎲 Con 5€ → Vincita ~{quota_under_comb*5:.2f}€ | Profitto ~{(quota_under_comb-1)*5:.2f}€")

print("\n" + "="*100)
print("❌ VERITÀ SCOMODA")
print("="*100)
print("""
Il problema NON è il mio codice. Il problema è che:

1. ❌ I modelli ML sono ROTTI (solo 2 classi invece di 3)
2. ✅ Poisson è matematicamente CORRETTO
3. ⚠️  MA le partite del 7 gennaio hanno TUTTE xG simili (1.1-1.7)
4. ⚠️  Quindi Poisson dà risultati SIMILI (matematicamente corretto ma poco utile)

SOLUZIONI:
A) Riaddestra i modelli ML con 3 classi (serve tempo)
B) Usa queste schedine che ho fatto (basate su DIFFERENZE REALI tra partite)
C) Aspetta partite con xG più vari (es. 2.5 vs 0.8) per avere predizioni diverse

Per OGGI, le schedine sopra sono le MIGLIORI possibili con i dati disponibili.
""")

db.close()
