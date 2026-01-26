#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCHEDINE 10 GENNAIO 2026 - RISULTATI QUASI CERTI
Seleziona i migliori eventi con alta probabilità da tutti i campionati
"""

from database import SessionLocal
from models import Fixture
from datetime import date
from scipy.stats import poisson

db = SessionLocal()

# Query per tutte le partite del 10 gennaio 2026
fixtures = db.query(Fixture).filter(Fixture.date == date(2026, 1, 10)).all()

print("=" * 100)
print("🎯 SCHEDINE 10 GENNAIO 2026 - EVENTI QUASI CERTI")
print("=" * 100)
print(f"Partite disponibili: {len(fixtures)}\n")

# Calcola tutte le probabilità per ogni partita
tutti_eventi = []

for fix in fixtures:
    if not fix.feature:
        continue

    feat = fix.feature
    if not all([feat.xg_for_home, feat.xg_against_home, feat.xg_for_away, feat.xg_against_away]):
        continue

    # Lambda (gol attesi)
    lam_h = (feat.xg_for_home + feat.xg_against_away) / 2
    lam_a = (feat.xg_for_away + feat.xg_against_home) / 2

    # Probabilità 1X2
    p_h = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a) for i in range(10) for j in range(i))
    p_d = sum(poisson.pmf(i, lam_h) * poisson.pmf(i, lam_a) for i in range(10))
    p_a = 1 - p_h - p_d

    # Doppia Chance
    p_1x = p_h + p_d
    p_x2 = p_d + p_a
    p_12 = p_h + p_a

    # Over/Under
    p_over05 = 1 - poisson.pmf(0, lam_h) * poisson.pmf(0, lam_a)
    p_over15 = 1 - sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                       for i in range(2) for j in range(2) if i+j <= 1)
    p_over25 = 1 - sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                       for i in range(3) for j in range(3) if i+j <= 2)
    p_over35 = 1 - sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                       for i in range(4) for j in range(4) if i+j <= 3)
    p_under25 = 1 - p_over25
    p_under35 = 1 - p_over35

    # Goal/No Goal
    p_gg = 1 - (poisson.pmf(0, lam_h) * sum(poisson.pmf(j, lam_a) for j in range(10)) +
                sum(poisson.pmf(i, lam_h) for i in range(10)) * poisson.pmf(0, lam_a) -
                poisson.pmf(0, lam_h) * poisson.pmf(0, lam_a))
    p_ng = 1 - p_gg

    # Multigol
    p_mg_13 = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                  for i in range(10) for j in range(10) if 1 <= i+j <= 3)
    p_mg_24 = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                  for i in range(10) for j in range(10) if 2 <= i+j <= 4)
    p_mg_25 = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                  for i in range(10) for j in range(10) if 2 <= i+j <= 5)

    # Crea lista di tutti gli eventi con probabilità >= 70%
    # ESCLUDI Over 0.5 perché troppo banale (vogliamo eventi più interessanti)
    eventi_partita = [
        ('1', p_h), ('X', p_d), ('2', p_a),
        ('1X', p_1x), ('X2', p_x2), ('12', p_12),
        ('Over 1.5', p_over15), ('Over 2.5', p_over25),
        ('Under 2.5', p_under25), ('Under 3.5', p_under35),
        ('GG', p_gg), ('NG', p_ng),
        ('MG 1-3', p_mg_13), ('MG 2-4', p_mg_24), ('MG 2-5', p_mg_25),
    ]

    for mercato, prob in eventi_partita:
        if prob >= 0.70:  # Solo eventi con prob >= 70%
            tutti_eventi.append({
                'partita': f"{fix.home} vs {fix.away}",
                'lega': fix.league_code,
                'ora': fix.time_local or fix.time,
                'mercato': mercato,
                'prob': prob,
                'quota_fair': 1 / prob,
            })

# Ordina per probabilità decrescente
tutti_eventi_sorted = sorted(tutti_eventi, key=lambda x: x['prob'], reverse=True)

print(f"Eventi con probabilità >= 70%: {len(tutti_eventi_sorted)}\n")

# ========================================
# SCHEDINA #1: TOP 10 EVENTI PIÙ SICURI
# ========================================
print("=" * 100)
print("📋 SCHEDINA #1: TOP 10 EVENTI PIÙ SICURI (Massima Probabilità)")
print("=" * 100)

schedina_1 = tutti_eventi_sorted[:10]
prob_totale_1 = 1.0
quota_totale_1 = 1.0

for i, ev in enumerate(schedina_1, 1):
    prob_totale_1 *= ev['prob']
    quota_totale_1 *= ev['quota_fair']

    print(f"\n{i}. {ev['partita']}")
    print(f"   🏆 {ev['lega']} | ⏰ {ev['ora']}")
    print(f"   🎯 {ev['mercato']:15} → {ev['prob']*100:.1f}% (Quota ~{ev['quota_fair']:.2f})")

print(f"\n{'─' * 100}")
print(f"📊 PROBABILITÀ TOTALE: {prob_totale_1*100:.2f}%")
print(f"💰 QUOTA TOTALE: {quota_totale_1:.2f}")
print(f"{'─' * 100}")

# ========================================
# SCHEDINA #2: EVENTI ULTRA SICURI (≥ 75%)
# ========================================
print("\n\n" + "=" * 100)
print("📋 SCHEDINA #2: ULTRA SICURI (Solo probabilità ≥ 75%)")
print("=" * 100)

schedina_2 = [ev for ev in tutti_eventi_sorted if ev['prob'] >= 0.75][:12]
prob_totale_2 = 1.0
quota_totale_2 = 1.0

for i, ev in enumerate(schedina_2, 1):
    prob_totale_2 *= ev['prob']
    quota_totale_2 *= ev['quota_fair']

    print(f"\n{i}. {ev['partita']}")
    print(f"   🏆 {ev['lega']} | ⏰ {ev['ora']}")
    print(f"   🎯 {ev['mercato']:15} → {ev['prob']*100:.1f}% (Quota ~{ev['quota_fair']:.2f})")

print(f"\n{'─' * 100}")
print(f"📊 PROBABILITÀ TOTALE: {prob_totale_2*100:.2f}%")
print(f"💰 QUOTA TOTALE: {quota_totale_2:.2f}")
print(f"{'─' * 100}")

# ========================================
# SCHEDINA #3: FOCUS OVER/UNDER
# ========================================
print("\n\n" + "=" * 100)
print("📋 SCHEDINA #3: FOCUS OVER/UNDER (Solo mercati O/U)")
print("=" * 100)

schedina_3 = [ev for ev in tutti_eventi_sorted
              if any(x in ev['mercato'] for x in ['Over', 'Under'])][:10]
prob_totale_3 = 1.0
quota_totale_3 = 1.0

for i, ev in enumerate(schedina_3, 1):
    prob_totale_3 *= ev['prob']
    quota_totale_3 *= ev['quota_fair']

    print(f"\n{i}. {ev['partita']}")
    print(f"   🏆 {ev['lega']} | ⏰ {ev['ora']}")
    print(f"   🎯 {ev['mercato']:15} → {ev['prob']*100:.1f}% (Quota ~{ev['quota_fair']:.2f})")

print(f"\n{'─' * 100}")
print(f"📊 PROBABILITÀ TOTALE: {prob_totale_3*100:.2f}%")
print(f"💰 QUOTA TOTALE: {quota_totale_3:.2f}")
print(f"{'─' * 100}")

# ========================================
# SCHEDINA #4: MULTI-LEGA BILANCIATA
# ========================================
print("\n\n" + "=" * 100)
print("📋 SCHEDINA #4: MULTI-LEGA BILANCIATA (Mix Serie A, Bundesliga, Premier, etc.)")
print("=" * 100)

# Seleziona 2-3 eventi per lega
leghe_uniche = list(set([ev['lega'] for ev in tutti_eventi_sorted]))
schedina_4 = []

for lega in leghe_uniche:
    eventi_lega = [ev for ev in tutti_eventi_sorted if ev['lega'] == lega][:2]
    schedina_4.extend(eventi_lega)

schedina_4 = sorted(schedina_4, key=lambda x: x['prob'], reverse=True)[:12]
prob_totale_4 = 1.0
quota_totale_4 = 1.0

for i, ev in enumerate(schedina_4, 1):
    prob_totale_4 *= ev['prob']
    quota_totale_4 *= ev['quota_fair']

    print(f"\n{i}. {ev['partita']}")
    print(f"   🏆 {ev['lega']} | ⏰ {ev['ora']}")
    print(f"   🎯 {ev['mercato']:15} → {ev['prob']*100:.1f}% (Quota ~{ev['quota_fair']:.2f})")

print(f"\n{'─' * 100}")
print(f"📊 PROBABILITÀ TOTALE: {prob_totale_4*100:.2f}%")
print(f"💰 QUOTA TOTALE: {quota_totale_4:.2f}")
print(f"{'─' * 100}")

# ========================================
# SCHEDINA #5: GOAL/NO GOAL SPECIALIST
# ========================================
print("\n\n" + "=" * 100)
print("📋 SCHEDINA #5: GOAL/NO GOAL SPECIALIST")
print("=" * 100)

schedina_5 = [ev for ev in tutti_eventi_sorted
              if ev['mercato'] in ['GG', 'NG']][:10]
prob_totale_5 = 1.0
quota_totale_5 = 1.0

for i, ev in enumerate(schedina_5, 1):
    prob_totale_5 *= ev['prob']
    quota_totale_5 *= ev['quota_fair']

    print(f"\n{i}. {ev['partita']}")
    print(f"   🏆 {ev['lega']} | ⏰ {ev['ora']}")
    print(f"   🎯 {ev['mercato']:15} → {ev['prob']*100:.1f}% (Quota ~{ev['quota_fair']:.2f})")

print(f"\n{'─' * 100}")
print(f"📊 PROBABILITÀ TOTALE: {prob_totale_5*100:.2f}%")
print(f"💰 QUOTA TOTALE: {quota_totale_5:.2f}")
print(f"{'─' * 100}")

# ========================================
# RIEPILOGO FINALE
# ========================================
print("\n\n" + "=" * 100)
print("📊 RIEPILOGO SCHEDINE")
print("=" * 100)

schedine_riepilogo = [
    ("SCHEDINA #1: Top 10 Più Sicuri", len(schedina_1), prob_totale_1, quota_totale_1),
    ("SCHEDINA #2: Ultra Sicuri (≥75%)", len(schedina_2), prob_totale_2, quota_totale_2),
    ("SCHEDINA #3: Over/Under Focus", len(schedina_3), prob_totale_3, quota_totale_3),
    ("SCHEDINA #4: Multi-Lega", len(schedina_4), prob_totale_4, quota_totale_4),
    ("SCHEDINA #5: GG/NG Specialist", len(schedina_5), prob_totale_5, quota_totale_5),
]

for nome, num_eventi, prob, quota in schedine_riepilogo:
    print(f"\n{nome}")
    print(f"  Eventi: {num_eventi} | Probabilità: {prob*100:.2f}% | Quota: {quota:.2f}")

print("\n" + "=" * 100)
print("💡 CONSIGLI:")
print("=" * 100)
print("""
1. SCHEDINA #2 (Ultra Sicuri): Massima affidabilità, quota più bassa
2. SCHEDINA #1 (Top 10): Bilanciamento ottimale tra sicurezza e quota
3. SCHEDINA #4 (Multi-Lega): Diversificazione per ridurre rischio concentrato
4. SCHEDINA #3 e #5: Specializzate per chi preferisce specifici mercati

⚠️ NOTA: Queste quote sono calcolate matematicamente (fair odds).
   Le quote reali del bookmaker saranno più basse a causa del margine.
   Verifica sempre le quote effettive prima di puntare.
""")

db.close()
