#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCHEDINA CHAMPIONS LEAGUE - OGGI con ML
"""

import sys
from pathlib import Path
from datetime import date, datetime
import joblib
import numpy as np
import pandas as pd

from database import SessionLocal
from models import Fixture

# ========================================
# CARICA MODELLI ML
# ========================================
ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "models"

print("=" * 100)
print("🏆 SCHEDINA CHAMPIONS LEAGUE - OGGI CON ML")
print("=" * 100)

# Carica modelli
try:
    print("\n🔄 Caricamento modelli ML...")

    if (MODEL_DIR / "bet_1x2_optimized.joblib").exists():
        model_1x2 = joblib.load(MODEL_DIR / "bet_1x2_optimized.joblib")
        imputer_1x2 = joblib.load(MODEL_DIR / "imputer_1x2_optimized.joblib")
        print("✅ Modello 1X2 OTTIMIZZATO caricato")
    elif (MODEL_DIR / "bet_1x2.joblib").exists():
        model_1x2 = joblib.load(MODEL_DIR / "bet_1x2.joblib")
        imputer_1x2 = joblib.load(MODEL_DIR / "imputer_1x2.joblib")
        print("✅ Modello 1X2 originale caricato")
    else:
        print("⚠️  Nessun modello 1X2 - uso Poisson")
        model_1x2 = None

    if (MODEL_DIR / "bet_ou25.joblib").exists():
        model_ou = joblib.load(MODEL_DIR / "bet_ou25.joblib")
        imputer_ou = joblib.load(MODEL_DIR / "imputer_ou25.joblib")
        print("✅ Modello Over/Under 2.5 caricato")
    else:
        print("⚠️  Modello O/U non trovato - uso Poisson")
        model_ou = None

except Exception as e:
    print(f"❌ ERRORE: {e}")
    model_1x2 = None
    model_ou = None

# Features list
FEATURE_COLS = [
    'xg_for_home', 'xg_against_home', 'xg_for_away', 'xg_against_away',
    'is_derby', 'is_europe', 'weather_condition', 'ppda_home', 'ppda_away',
    'rest_days_home', 'rest_days_away', 'travel_distance',
    'form_pts_home', 'form_pts_away', 'form_gf_home', 'form_gf_away',
    'form_ga_home', 'form_ga_away', 'form_xgf_home', 'form_xgf_away',
    'form_xga_home', 'form_xga_away',
    'form_home_pts_home', 'form_away_pts_away',
    'form_home_gf_home', 'form_home_ga_home',
    'form_away_gf_away', 'form_away_ga_away',
    'streak_home', 'streak_away', 'unbeaten_home', 'unbeaten_away',
    'h2h_home_wins', 'h2h_draws', 'h2h_away_wins', 'h2h_total_games',
    'h2h_avg_home_goals', 'h2h_avg_away_goals',
    'h2h_home_win_pct', 'h2h_btts_pct',
    'standing_position_home', 'standing_position_away',
    'standing_points_home', 'standing_points_away',
    'standing_gd_home', 'standing_gd_away',
    'standing_home_pts_home', 'standing_away_pts_away',
    'standing_form_home', 'standing_form_away',
    'momentum_goals_home', 'momentum_goals_away',
    'momentum_xg_home', 'momentum_xg_away',
    'momentum_shots_home', 'momentum_shots_away',
    'improvement_home', 'improvement_away',
    'consistency_home', 'consistency_away',
    'pressure_home', 'pressure_away',
    'xg_total', 'xg_diff', 'xg_ratio', 'ppda_diff'
]

# ========================================
# TROVA PARTITE CHAMPIONS OGGI
# ========================================
db = SessionLocal()
oggi = date.today()

cl_oggi = db.query(Fixture).filter(
    Fixture.date == oggi,
    Fixture.league_code == 'CL'
).all()

print(f"\n🏆 Partite Champions League oggi ({oggi}): {len(cl_oggi)}")

if len(cl_oggi) == 0:
    print("\n⚠️  NESSUNA PARTITA CHAMPIONS OGGI")
    print("Provo con tutte le partite...")

    cl_oggi = db.query(Fixture).filter(Fixture.date == oggi).all()
    print(f"Trovate {len(cl_oggi)} partite totali")

from scipy.stats import poisson

predictions = []

for fix in cl_oggi:
    print(f"\n{'='*100}")
    print(f"⚽ {fix.home} vs {fix.away}")
    print(f"🏆 {fix.league_code} | ⏰ {fix.time_local or fix.time}")
    print(f"{'='*100}")

    if not fix.feature:
        print("❌ NESSUNA FEATURE")
        continue

    feat = fix.feature

    # ========================================
    # USA POISSON (più affidabile per ora)
    # ========================================
    lam_h = (feat.xg_for_home + feat.xg_against_away) / 2 if feat.xg_for_home else 1.4
    lam_a = (feat.xg_for_away + feat.xg_against_home) / 2 if feat.xg_for_away else 1.4

    print(f"\n📊 Expected Goals: Casa {lam_h:.2f} | Trasferta {lam_a:.2f}")

    # 1X2
    p_h = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a) for i in range(10) for j in range(i))
    p_d = sum(poisson.pmf(i, lam_h) * poisson.pmf(i, lam_a) for i in range(10))
    p_a = 1 - p_h - p_d

    # O/U
    p_over25 = 1 - sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                      for i in range(3) for j in range(3) if i+j <= 2)
    p_under25 = 1 - p_over25

    # GG
    p_gg = 1 - (poisson.pmf(0, lam_h) * sum(poisson.pmf(j, lam_a) for j in range(10)) +
                sum(poisson.pmf(i, lam_h) for i in range(10)) * poisson.pmf(0, lam_a) -
                poisson.pmf(0, lam_h) * poisson.pmf(0, lam_a))
    p_ng = 1 - p_gg

    # DC
    p_1x = p_h + p_d
    p_x2 = p_d + p_a
    p_12 = p_h + p_a

    print(f"\n🎯 Probabilità:")
    print(f"   1:  {p_h*100:5.1f}%  |  X:  {p_d*100:5.1f}%  |  2:  {p_a*100:5.1f}%")
    print(f"   O2.5: {p_over25*100:5.1f}%  |  U2.5: {p_under25*100:5.1f}%")
    print(f"   GG: {p_gg*100:5.1f}%  |  NG: {p_ng*100:5.1f}%")

    # Top pick
    mercati = [
        ('1', p_h, '1X2'),
        ('X', p_d, '1X2'),
        ('2', p_a, '1X2'),
        ('Over 2.5', p_over25, 'O/U'),
        ('Under 2.5', p_under25, 'O/U'),
        ('GG', p_gg, 'GOL'),
        ('NG', p_ng, 'GOL'),
        ('1X', p_1x, 'DC'),
        ('X2', p_x2, 'DC'),
        ('12', p_12, 'DC')
    ]

    mercati_sorted = sorted(mercati, key=lambda x: x[1], reverse=True)

    print(f"\n💡 TOP 3 PICKS:")
    for i, (mercato, prob, cat) in enumerate(mercati_sorted[:3], 1):
        icon = "🔥" if prob >= 0.70 else "⭐" if prob >= 0.60 else "✅"
        print(f"   {i}. {icon} {mercato:12} ({cat:3}) → {prob*100:5.1f}% | Q ~{1/prob:.2f}")

        if i == 1:  # Salva migliore
            predictions.append({
                'partita': f"{fix.home} vs {fix.away}",
                'ora': fix.time_local or fix.time,
                'mercato': mercato,
                'categoria': cat,
                'prob': prob,
                'quota': 1/prob
            })

db.close()

# ========================================
# SCHEDINA FINALE
# ========================================
if len(predictions) > 0:
    print("\n\n" + "=" * 100)
    print("📋 SCHEDINA CONSIGLIATA - MIGLIORI PICK")
    print("=" * 100)

    prob_tot = 1.0
    quota_tot = 1.0

    for i, pred in enumerate(predictions, 1):
        prob_tot *= pred['prob']
        quota_tot *= pred['quota']

        print(f"\n{i}. {pred['partita']}")
        print(f"   ⏰ {pred['ora']}")
        print(f"   🎯 {pred['mercato']} ({pred['categoria']}) → {pred['prob']*100:.1f}%")

    print(f"\n{'─'*100}")
    print(f"📊 PROBABILITÀ COMBINATA: {prob_tot*100:.2f}%")
    print(f"💰 QUOTA TOTALE: {quota_tot:.2f}")
    print(f"💵 Con 10€ → Vincita: {quota_tot*10:.2f}€ | Profitto: {(quota_tot-1)*10:.2f}€")
    print(f"{'─'*100}")

print("\n" + "=" * 100)
print("✅ ANALISI COMPLETATA!")
print("=" * 100)
