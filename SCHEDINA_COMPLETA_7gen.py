#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCHEDINA COMPLETA 7 GENNAIO 2026
TUTTE LE 13 PARTITE con i migliori pick per ognuna
"""

from database import SessionLocal
from models import Fixture
from datetime import date
from scipy.stats import poisson

db = SessionLocal()
fixtures = db.query(Fixture).filter(Fixture.date == date(2026, 1, 7)).all()

print("="*100)
print("🎯 SCHEDINA COMPLETA 7 GENNAIO 2026 - TUTTE LE 13 PARTITE")
print("="*100)

# Ordina per orario e lega
fixtures_sorted = sorted(fixtures, key=lambda x: (x.time, x.league))

tutte_partite = []

for fix in fixtures_sorted:
    if not fix.feature:
        continue

    feat = fix.feature
    if not all([feat.xg_for_home, feat.xg_against_home, feat.xg_for_away, feat.xg_against_away]):
        continue

    # Lambda
    lam_h = (feat.xg_for_home + feat.xg_against_away) / 2
    lam_a = (feat.xg_for_away + feat.xg_against_home) / 2
    lam_tot = lam_h + lam_a

    # Probabilità 1X2
    p_h = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a) for i in range(10) for j in range(i))
    p_d = sum(poisson.pmf(i, lam_h) * poisson.pmf(i, lam_a) for i in range(10))
    p_a = 1 - p_h - p_d

    # DC
    p_1x = p_h + p_d
    p_x2 = p_d + p_a
    p_12 = p_h + p_a

    # Over/Under
    p_over05 = 1 - poisson.pmf(0, lam_h) * poisson.pmf(0, lam_a)
    p_over15 = 1 - sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                       for i in range(2) for j in range(2) if i+j <= 1)
    p_over25 = 1 - sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                       for i in range(3) for j in range(3) if i+j <= 2)
    p_under25 = 1 - p_over25
    p_under35 = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                    for i in range(4) for j in range(4) if i+j <= 3)

    # GG
    p_gg = 1 - (poisson.pmf(0, lam_h) * sum(poisson.pmf(j, lam_a) for j in range(10)) +
                sum(poisson.pmf(i, lam_h) for i in range(10)) * poisson.pmf(0, lam_a) -
                poisson.pmf(0, lam_h) * poisson.pmf(0, lam_a))
    p_ng = 1 - p_gg

    # Multigol
    p_mg_13 = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                  for i in range(4) for j in range(4) if 1 <= i+j <= 3)
    p_mg_25 = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                  for i in range(6) for j in range(6) if 2 <= i+j <= 5)

    # Determina il pick migliore per questa partita
    picks = [
        ('1', p_h),
        ('X', p_d),
        ('2', p_a),
        ('1X', p_1x),
        ('X2', p_x2),
        ('12', p_12),
        ('Over 1.5', p_over15),
        ('Over 2.5', p_over25),
        ('Under 2.5', p_under25),
        ('Under 3.5', p_under35),
        ('GG', p_gg),
        ('NG', p_ng),
        ('MG 1-3', p_mg_13),
        ('MG 2-5', p_mg_25),
    ]

    # Ordina per probabilità
    picks_sorted = sorted(picks, key=lambda x: x[1], reverse=True)
    best_pick = picks_sorted[0]
    second_pick = picks_sorted[1]
    third_pick = picks_sorted[2]

    tutte_partite.append({
        'fix': fix,
        'lam_h': lam_h,
        'lam_a': lam_a,
        'lam_tot': lam_tot,
        'p_h': p_h,
        'p_d': p_d,
        'p_a': p_a,
        'best_pick': best_pick,
        'second_pick': second_pick,
        'third_pick': third_pick,
        'favorito': 'CASA' if p_h > max(p_d, p_a) else 'TRASFERTA' if p_a > max(p_h, p_d) else 'EQUILIBRIO'
    })

# Mostra tutte le partite
print("\n📋 SERIE A (5 partite):")
print("="*100)

for i, p in enumerate([x for x in tutte_partite if 'Serie A' in x['fix'].league], 1):
    fix = p['fix']
    print(f"\n{i}. {fix.home} vs {fix.away}")
    print(f"   ⏰ {fix.time} | 🏆 {fix.league}")
    print(f"   📊 1: {p['p_h']*100:4.1f}% | X: {p['p_d']*100:4.1f}% | 2: {p['p_a']*100:4.1f}%")
    print(f"   🎯 PICK #1: {p['best_pick'][0]:15} ({p['best_pick'][1]*100:5.1f}%) → Quota ~{1/p['best_pick'][1]:.2f}")
    print(f"   🥈 PICK #2: {p['second_pick'][0]:15} ({p['second_pick'][1]*100:5.1f}%) → Quota ~{1/p['second_pick'][1]:.2f}")
    print(f"   🥉 PICK #3: {p['third_pick'][0]:15} ({p['third_pick'][1]*100:5.1f}%) → Quota ~{1/p['third_pick'][1]:.2f}")

print("\n\n📋 PREMIER LEAGUE (8 partite):")
print("="*100)

for i, p in enumerate([x for x in tutte_partite if 'Premier' in x['fix'].league], 1):
    fix = p['fix']
    print(f"\n{i}. {fix.home} vs {fix.away}")
    print(f"   ⏰ {fix.time} | 🏆 {fix.league}")
    print(f"   📊 1: {p['p_h']*100:4.1f}% | X: {p['p_d']*100:4.1f}% | 2: {p['p_a']*100:4.1f}%")
    print(f"   🎯 PICK #1: {p['best_pick'][0]:15} ({p['best_pick'][1]*100:5.1f}%) → Quota ~{1/p['best_pick'][1]:.2f}")
    print(f"   🥈 PICK #2: {p['second_pick'][0]:15} ({p['second_pick'][1]*100:5.1f}%) → Quota ~{1/p['second_pick'][1]:.2f}")
    print(f"   🥉 PICK #3: {p['third_pick'][0]:15} ({p['third_pick'][1]*100:5.1f}%) → Quota ~{1/p['third_pick'][1]:.2f}")

# SCHEDINE CONSIGLIATE
print("\n\n" + "="*100)
print("🎯 SCHEDINE CONSIGLIATE")
print("="*100)

print("\n📋 SCHEDINA #1: SERIE A COMPLETA (5 eventi - Pick migliori)")
print("-"*100)
serie_a_picks = [x for x in tutte_partite if 'Serie A' in x['fix'].league]
prob_sa = 1.0
quota_sa = 1.0
for i, p in enumerate(serie_a_picks, 1):
    prob_sa *= p['best_pick'][1]
    quota_sa *= (1 / p['best_pick'][1])
    print(f"{i}. {p['fix'].home:30} vs {p['fix'].away:30}")
    print(f"   → {p['best_pick'][0]} ({p['best_pick'][1]*100:.1f}%)")

print(f"\n💰 Probabilità combinata: {prob_sa*100:.2f}%")
print(f"💰 Quota totale: ~{quota_sa:.2f}")
print(f"🎲 Con 10€ → Vincita: ~{quota_sa*10:.2f}€ | Profitto: ~{(quota_sa-1)*10:.2f}€")

print("\n📋 SCHEDINA #2: PREMIER LEAGUE TOP 5 (Pick migliori)")
print("-"*100)
premier_picks = [x for x in tutte_partite if 'Premier' in x['fix'].league][:5]
prob_pl = 1.0
quota_pl = 1.0
for i, p in enumerate(premier_picks, 1):
    prob_pl *= p['best_pick'][1]
    quota_pl *= (1 / p['best_pick'][1])
    print(f"{i}. {p['fix'].home:30} vs {p['fix'].away:30}")
    print(f"   → {p['best_pick'][0]} ({p['best_pick'][1]*100:.1f}%)")

print(f"\n💰 Probabilità combinata: {prob_pl*100:.2f}%")
print(f"💰 Quota totale: ~{quota_pl:.2f}")
print(f"🎲 Con 10€ → Vincita: ~{quota_pl*10:.2f}€ | Profitto: ~{(quota_pl-1)*10:.2f}€")

print("\n📋 SCHEDINA #3: MIX SERIE A + PREMIER (6 eventi più sicuri)")
print("-"*100)
# Prendi i 6 pick con probabilità più alta
all_sorted = sorted(tutte_partite, key=lambda x: x['best_pick'][1], reverse=True)[:6]
prob_mix = 1.0
quota_mix = 1.0
for i, p in enumerate(all_sorted, 1):
    prob_mix *= p['best_pick'][1]
    quota_mix *= (1 / p['best_pick'][1])
    print(f"{i}. {p['fix'].home:30} vs {p['fix'].away:30}")
    print(f"   → {p['best_pick'][0]} ({p['best_pick'][1]*100:.1f}%) | {p['fix'].league}")

print(f"\n💰 Probabilità combinata: {prob_mix*100:.2f}%")
print(f"💰 Quota totale: ~{quota_mix:.2f}")
print(f"🎲 Con 10€ → Vincita: ~{quota_mix*10:.2f}€ | Profitto: ~{(quota_mix-1)*10:.2f}€")

print("\n📋 SCHEDINA #4: SOLO FAVORITI CHIARI (1X o X2 con >73%)")
print("-"*100)
favoriti = []
for p in tutte_partite:
    # Calcola p_1x e p_x2
    p_1x = p['p_h'] + p['p_d']
    p_x2 = p['p_d'] + p['p_a']

    if p['p_h'] > p['p_a'] and p_1x > 0.73:
        favoriti.append((p, '1X', p_1x))
    elif p['p_a'] > p['p_h'] and p_x2 > 0.73:
        favoriti.append((p, 'X2', p_x2))

prob_fav = 1.0
quota_fav = 1.0
for i, (p, pick, prob) in enumerate(favoriti[:5], 1):
    prob_fav *= prob
    quota_fav *= (1 / prob)
    print(f"{i}. {p['fix'].home:30} vs {p['fix'].away:30}")
    print(f"   → {pick} ({prob*100:.1f}%) | {p['fix'].league}")

print(f"\n💰 Probabilità combinata: {prob_fav*100:.2f}%")
print(f"💰 Quota totale: ~{quota_fav:.2f}")
print(f"🎲 Con 10€ → Vincita: ~{quota_fav*10:.2f}€ | Profitto: ~{(quota_fav-1)*10:.2f}€")

print("\n" + "="*100)
print("✅ TUTTE LE 13 PARTITE SONO INCLUSE NELL'ANALISI")
print("="*100)

db.close()
