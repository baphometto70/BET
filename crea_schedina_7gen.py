#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crea schedine concrete per il 7 gennaio 2026
Basandosi sui dati xG e analisi precedenti
"""

from database import SessionLocal
from models import Fixture
from datetime import date
import pandas as pd

db = SessionLocal()

# Carica partite 7 gennaio
fixtures = db.query(Fixture).filter(
    Fixture.date == date(2026, 1, 7)
).all()

print("=" * 100)
print("🎯 SCHEDINE CONSIGLIATE PER 7 GENNAIO 2026")
print("=" * 100)
print(f"\nPartite disponibili: {len(fixtures)}\n")

# Analizza ogni partita
schedine = []

for fix in fixtures:
    # Controlla se ha features
    if not fix.feature:
        continue

    feat = fix.feature
    if not all([feat.xg_for_home, feat.xg_against_home, feat.xg_for_away, feat.xg_against_away]):
        continue

    # Calcola lambda (gol attesi)
    lambda_home = (feat.xg_for_home + feat.xg_against_away) / 2
    lambda_away = (feat.xg_for_away + feat.xg_against_home) / 2
    lambda_total = lambda_home + lambda_away

    # Calcola probabilità Over 1.5 (formula Poisson)
    from scipy.stats import poisson

    # P(Over 1.5) = 1 - P(0-0) - P(1-0) - P(0-1) - P(1-1)
    p_00 = poisson.pmf(0, lambda_home) * poisson.pmf(0, lambda_away)
    p_10 = poisson.pmf(1, lambda_home) * poisson.pmf(0, lambda_away)
    p_01 = poisson.pmf(0, lambda_home) * poisson.pmf(1, lambda_away)
    p_11 = poisson.pmf(1, lambda_home) * poisson.pmf(1, lambda_away)
    p_over_15 = 1 - (p_00 + p_10 + p_01 + p_11)

    # P(Over 2.5)
    p_under_25 = sum(
        poisson.pmf(i, lambda_home) * poisson.pmf(j, lambda_away)
        for i in range(3) for j in range(3) if i + j <= 2
    )
    p_over_25 = 1 - p_under_25

    # Calcola probabilità 1X2 (approssimata con Poisson)
    # P(Home Win)
    p_home = sum(
        poisson.pmf(i, lambda_home) * poisson.pmf(j, lambda_away)
        for i in range(10) for j in range(i)
    )

    # P(Draw)
    p_draw = sum(
        poisson.pmf(i, lambda_home) * poisson.pmf(i, lambda_away)
        for i in range(10)
    )

    # P(Away Win)
    p_away = 1 - p_home - p_draw

    # Calcola Doppia Chance
    p_1x = p_home + p_draw
    p_x2 = p_draw + p_away
    p_12 = p_home + p_away

    # Identificapicks ad alta probabilità (>70%)
    picks = []

    if p_over_15 > 0.75:
        picks.append(("Over 1.5", p_over_15, "⭐⭐⭐"))
    elif p_over_15 > 0.70:
        picks.append(("Over 1.5", p_over_15, "⭐⭐"))

    if p_over_25 > 0.65:
        picks.append(("Over 2.5", p_over_25, "⭐⭐"))
    elif p_over_25 > 0.60:
        picks.append(("Over 2.5", p_over_25, "⭐"))

    if p_1x > 0.70:
        picks.append(("1X (Home or Draw)", p_1x, "⭐⭐"))
    if p_x2 > 0.70:
        picks.append(("X2 (Draw or Away)", p_x2, "⭐⭐"))
    if p_12 > 0.70:
        picks.append(("12 (Home or Away)", p_12, "⭐⭐"))

    if picks:
        schedine.append({
            'fixture': fix,
            'lambda_home': lambda_home,
            'lambda_away': lambda_away,
            'lambda_total': lambda_total,
            'picks': picks,
            'p_home': p_home,
            'p_draw': p_draw,
            'p_away': p_away,
            'p_over_15': p_over_15,
            'p_over_25': p_over_25
        })

# Ordina per numero di picks + probabilità totale
schedine.sort(key=lambda x: (len(x['picks']), sum(p[1] for p in x['picks'])), reverse=True)

print("\n📋 PARTITE CON PICKS AD ALTA PROBABILITÀ:\n")

for i, s in enumerate(schedine[:10], 1):  # Top 10
    fix = s['fixture']
    print(f"{i}. {fix.home} vs {fix.away}")
    print(f"   🏆 {fix.league} | ⏰ {fix.time}")
    print(f"   📊 xG previsti: {s['lambda_home']:.2f} - {s['lambda_away']:.2f} (Tot: {s['lambda_total']:.2f})")
    print(f"   📈 1X2: Home {s['p_home']*100:.1f}% | Draw {s['p_draw']*100:.1f}% | Away {s['p_away']*100:.1f}%")
    print(f"   🎯 PICKS:")
    for pick, prob, stars in s['picks']:
        print(f"      {stars} {pick}: {prob*100:.1f}%")
    print()

# CREA SCHEDINE COMBO
print("\n" + "=" * 100)
print("🎲 SCHEDINE COMBO CONSIGLIATE")
print("=" * 100)

# Schedina 1: SOLO OVER 1.5 (le più sicure)
print("\n📌 SCHEDINA 1: MULTIPLA OVER 1.5 (Alta Sicurezza)")
print("-" * 100)
over_15_picks = [(s['fixture'], s['p_over_15']) for s in schedine if s['p_over_15'] > 0.75]
over_15_picks.sort(key=lambda x: x[1], reverse=True)

if over_15_picks:
    print("Partite selezionate:")
    quota_totale = 1.0
    prob_combo = 1.0
    for fix, prob in over_15_picks[:5]:  # Top 5
        # Quota stimata: 1 / probabilità (approssimazione conservativa)
        quota_stimata = 1 / prob * 1.1  # +10% margine bookmaker
        quota_totale *= quota_stimata
        prob_combo *= prob
        print(f"   ✅ {fix.home} vs {fix.away} - Over 1.5 ({prob*100:.1f}%) [Quota ~{quota_stimata:.2f}]")

    print(f"\n   💰 Quota totale stimata: ~{quota_totale:.2f}")
    print(f"   📊 Probabilità combo: {prob_combo*100:.1f}%")
    print(f"   🎯 Consiglio: {'✅ OTTIMA' if prob_combo > 0.50 else '⚠️ RISCHIOSA' if prob_combo > 0.30 else '❌ TROPPO RISCHIOSA'}")
else:
    print("   ⚠️ Nessuna partita con Over 1.5 > 75%")

# Schedina 2: COMBO DOPPIA CHANCE + OVER 1.5
print("\n📌 SCHEDINA 2: COMBO MISTA (Sicurezza Media)")
print("-" * 100)
combo_picks = []
for s in schedine:
    # Trova la migliore doppia chance
    best_dc = None
    best_dc_prob = 0
    if s['p_home'] + s['p_draw'] > best_dc_prob:
        best_dc = "1X"
        best_dc_prob = s['p_home'] + s['p_draw']
    if s['p_draw'] + s['p_away'] > best_dc_prob:
        best_dc = "X2"
        best_dc_prob = s['p_draw'] + s['p_away']

    if best_dc_prob > 0.70 and s['p_over_15'] > 0.70:
        combo_picks.append((s['fixture'], best_dc, best_dc_prob, s['p_over_15']))

combo_picks.sort(key=lambda x: x[2] * x[3], reverse=True)

if combo_picks:
    print("Partite selezionate:")
    quota_totale = 1.0
    prob_combo = 1.0
    for fix, dc, prob_dc, prob_over in combo_picks[:3]:  # Top 3
        # Quota combo: doppia chance (~1.3-1.5) + over 1.5 (~1.3-1.4)
        quota_dc = 1 / prob_dc * 1.15
        quota_over = 1 / prob_over * 1.15
        quota_combinata = quota_dc * quota_over
        quota_totale *= quota_combinata
        prob_comb = prob_dc * prob_over
        prob_combo *= prob_comb
        print(f"   ✅ {fix.home} vs {fix.away}")
        print(f"      - {dc} ({prob_dc*100:.1f}%) + Over 1.5 ({prob_over*100:.1f}%)")
        print(f"      - Probabilità combo: {prob_comb*100:.1f}% [Quota ~{quota_combinata:.2f}]")

    print(f"\n   💰 Quota totale stimata: ~{quota_totale:.2f}")
    print(f"   📊 Probabilità combo: {prob_combo*100:.1f}%")
    print(f"   🎯 Consiglio: {'✅ BUONA' if prob_combo > 0.40 else '⚠️ RISCHIOSA' if prob_combo > 0.25 else '❌ TROPPO RISCHIOSA'}")
else:
    print("   ⚠️ Nessuna combo adatta trovata")

# Schedina 3: SINGOLE AD ALTA QUOTA
print("\n📌 SCHEDINA 3: SINGOLE SICURE (Stake Singolo)")
print("-" * 100)
print("Le 3 scommesse singole più sicure:\n")

for i, s in enumerate(schedine[:3], 1):
    fix = s['fixture']
    best_pick = max(s['picks'], key=lambda x: x[1])
    pick_name, pick_prob, stars = best_pick
    quota_stimata = 1 / pick_prob * 1.1

    print(f"{i}. {fix.home} vs {fix.away}")
    print(f"   🎯 Pick: {pick_name}")
    print(f"   📊 Probabilità: {pick_prob*100:.1f}%")
    print(f"   💰 Quota stimata: ~{quota_stimata:.2f}")
    print(f"   🏆 {fix.league} | ⏰ {fix.time}")
    print()

db.close()

print("\n" + "=" * 100)
print("⚠️ DISCLAIMER:")
print("Queste sono predizioni basate su modelli statistici e xG.")
print("Le probabilità sono stimate e le quote sono approssimative.")
print("Gioca responsabilmente e verifica sempre le quote reali prima di scommettere.")
print("=" * 100)
