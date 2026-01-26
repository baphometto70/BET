#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCHEDINA CHAMPIONS LEAGUE - 21 GENNAIO 2026 con ML
"""

import sys
from pathlib import Path
from datetime import date
import joblib
import numpy as np
import pandas as pd
from scipy.stats import poisson

from database import SessionLocal
from models import Fixture

# ========================================
# CARICA MODELLI ML RIADDESTRATI
# ========================================
ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "models"

print("=" * 100)
print("🏆 SCHEDINA CHAMPIONS LEAGUE - 21 GENNAIO 2026 (ML OTTIMIZZATO)")
print("=" * 100)

try:
    print("\n🔄 Caricamento modelli ML riaddestrati...")
    model_1x2 = joblib.load(MODEL_DIR / "bet_1x2_retrained.joblib")
    imputer_1x2 = joblib.load(MODEL_DIR / "imputer_1x2_retrained.joblib")
    print("✅ Modello 1X2 caricato (Accuracy: 47.88%)")

    model_ou = joblib.load(MODEL_DIR / "bet_ou25_retrained.joblib")
    imputer_ou = joblib.load(MODEL_DIR / "imputer_ou25_retrained.joblib")
    print("✅ Modello O/U caricato (Accuracy: 56.66%)")

except Exception as e:
    print(f"❌ ERRORE: {e}")
    sys.exit(1)

# Features
FEATURES = [
    'xg_for_home', 'xg_against_home', 'xg_for_away', 'xg_against_away',
    'rest_days_home', 'rest_days_away',
    'derby_flag', 'europe_flag_home', 'europe_flag_away',
    'meteo_flag', 'style_ppda_home', 'style_ppda_away',
    'odds_1', 'odds_x', 'odds_2',
    'xg_total', 'xg_diff', 'xg_ratio', 'ppda_diff'
]

# ========================================
# TROVA PARTITE CHAMPIONS 21 GENNAIO
# ========================================
db = SessionLocal()
match_date = date(2026, 1, 21)

cl_oggi = db.query(Fixture).filter(
    Fixture.date == match_date,
    Fixture.league_code == 'CL'
).all()

print(f"\n🏆 Partite Champions League del 21/01/2026: {len(cl_oggi)}")

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
    # PREPARA FEATURES PER ML
    # ========================================
    try:
        X_dict = {
            'xg_for_home': feat.xg_for_home or 1.4,
            'xg_against_home': feat.xg_against_home or 1.4,
            'xg_for_away': feat.xg_for_away or 1.4,
            'xg_against_away': feat.xg_against_away or 1.4,
            'rest_days_home': feat.rest_days_home or 3,
            'rest_days_away': feat.rest_days_away or 3,
            'derby_flag': feat.derby_flag if hasattr(feat, 'derby_flag') else 0,
            'europe_flag_home': 1,  # Champions League
            'europe_flag_away': 1,
            'meteo_flag': feat.meteo_flag if hasattr(feat, 'meteo_flag') else 0,
            'style_ppda_home': feat.style_ppda_home if hasattr(feat, 'style_ppda_home') and feat.style_ppda_home else 10.0,
            'style_ppda_away': feat.style_ppda_away if hasattr(feat, 'style_ppda_away') and feat.style_ppda_away else 10.0,
        }

        # Odds
        if fix.odds:
            X_dict['odds_1'] = fix.odds.odds_1 if fix.odds.odds_1 else 2.5
            X_dict['odds_x'] = fix.odds.odds_x if fix.odds.odds_x else 3.5
            X_dict['odds_2'] = fix.odds.odds_2 if fix.odds.odds_2 else 3.0
        else:
            lam_h_tmp = (X_dict['xg_for_home'] + X_dict['xg_against_away']) / 2
            lam_a_tmp = (X_dict['xg_for_away'] + X_dict['xg_against_home']) / 2
            p_h_tmp = min(0.7, max(0.15, lam_h_tmp / (lam_h_tmp + lam_a_tmp + 0.5)))
            X_dict['odds_1'] = 1 / p_h_tmp if p_h_tmp > 0 else 3.0
            X_dict['odds_x'] = 3.5
            X_dict['odds_2'] = 1 / (1 - p_h_tmp - 0.27) if (1 - p_h_tmp - 0.27) > 0 else 3.5

        # Derived
        X_dict['xg_total'] = X_dict['xg_for_home'] + X_dict['xg_for_away']
        X_dict['xg_diff'] = X_dict['xg_for_home'] - X_dict['xg_for_away']
        X_dict['xg_ratio'] = X_dict['xg_for_home'] / (X_dict['xg_for_away'] + 0.01)
        X_dict['ppda_diff'] = (X_dict['style_ppda_home'] or 10.0) - (X_dict['style_ppda_away'] or 10.0)

        X = pd.DataFrame([X_dict])[FEATURES]
        X_imp = imputer_1x2.transform(X)

        # ========================================
        # PREDIZIONI ML 1X2
        # ========================================
        proba_1x2 = model_1x2.predict_proba(X_imp)[0]

        classes = model_1x2.classes_
        class_to_prob = dict(zip(classes, proba_1x2))

        p_h_ml = class_to_prob.get(1, 0.33)
        p_d_ml = class_to_prob.get(0, 0.33)
        p_a_ml = class_to_prob.get(2, 0.33)

        # Normalizza
        total = p_h_ml + p_d_ml + p_a_ml
        p_h_ml /= total
        p_d_ml /= total
        p_a_ml /= total

        # ========================================
        # PREDIZIONI ML O/U
        # ========================================
        X_imp_ou = imputer_ou.transform(X)
        proba_ou = model_ou.predict_proba(X_imp_ou)[0]

        p_under25_ml = proba_ou[0]
        p_over25_ml = proba_ou[1]

        # ========================================
        # POISSON PER ALTRI MERCATI
        # ========================================
        lam_h = (X_dict['xg_for_home'] + X_dict['xg_against_away']) / 2
        lam_a = (X_dict['xg_for_away'] + X_dict['xg_against_home']) / 2

        # GG
        p_gg = 1 - (poisson.pmf(0, lam_h) * sum(poisson.pmf(j, lam_a) for j in range(10)) +
                    sum(poisson.pmf(i, lam_h) for i in range(10)) * poisson.pmf(0, lam_a) -
                    poisson.pmf(0, lam_h) * poisson.pmf(0, lam_a))
        p_ng = 1 - p_gg

        # DC
        p_1x = p_h_ml + p_d_ml
        p_x2 = p_d_ml + p_a_ml
        p_12 = p_h_ml + p_a_ml

        # ========================================
        # MOSTRA RISULTATI
        # ========================================
        print(f"\n📊 Expected Goals: Casa {lam_h:.2f} | Trasferta {lam_a:.2f}")

        print(f"\n🤖 PREDIZIONI MACHINE LEARNING:")
        print(f"   1X2:")
        print(f"      1 (Casa):      {p_h_ml*100:5.1f}% | Quota ~{1/p_h_ml:.2f}")
        print(f"      X (Pareggio):  {p_d_ml*100:5.1f}% | Quota ~{1/p_d_ml:.2f}")
        print(f"      2 (Trasferta): {p_a_ml*100:5.1f}% | Quota ~{1/p_a_ml:.2f}")

        print(f"\n   Over/Under 2.5:")
        print(f"      Over 2.5:  {p_over25_ml*100:5.1f}% | Quota ~{1/p_over25_ml:.2f}")
        print(f"      Under 2.5: {p_under25_ml*100:5.1f}% | Quota ~{1/p_under25_ml:.2f}")

        print(f"\n   Doppia Chance:")
        print(f"      1X:  {p_1x*100:5.1f}% | X2: {p_x2*100:5.1f}% | 12: {p_12*100:5.1f}%")

        print(f"\n   Gol:")
        print(f"      GG:  {p_gg*100:5.1f}% | NG: {p_ng*100:5.1f}%")

        # TOP PICK (SOLO DOPPIA CHANCE - PIÙ SICURO)
        mercati_dc = [
            ('DC 1X', p_1x, 'DC'),
            ('DC X2', p_x2, 'DC'),
            ('DC 12', p_12, 'DC'),
        ]

        best_dc = max(mercati_dc, key=lambda x: x[1])

        print(f"\n💡 PICK CONSIGLIATO:")
        icon = "🔥" if best_dc[1] >= 0.80 else "⭐" if best_dc[1] >= 0.70 else "✅"
        print(f"   {icon} {best_dc[0]:12} → {best_dc[1]*100:5.1f}% | Q ~{1/best_dc[1]:.2f}")

        predictions.append({
            'partita': f"{fix.home} vs {fix.away}",
            'ora': fix.time_local or fix.time,
            'mercato': best_dc[0],
            'categoria': best_dc[2],
            'prob': best_dc[1],
            'quota': 1/best_dc[1]
        })

    except Exception as e:
        print(f"❌ ERRORE: {e}")
        import traceback
        traceback.print_exc()
        continue

db.close()

# ========================================
# SCHEDINA FINALE
# ========================================
if len(predictions) > 0:
    print("\n\n" + "=" * 100)
    print("📋 SCHEDINA CONSIGLIATA - MACHINE LEARNING (SOLO DOPPIA CHANCE)")
    print("=" * 100)

    # Ordina per probabilità decrescente
    predictions_sorted = sorted(predictions, key=lambda x: x['prob'], reverse=True)

    # SCHEDINA 5 EVENTI (PIÙ ALTA PROBABILITÀ)
    top5 = predictions_sorted[:5]

    prob_tot_5 = 1.0
    quota_tot_5 = 1.0

    print(f"\n⭐⭐⭐ SCHEDINA 5 EVENTI (PIÙ SICURA) ⭐⭐⭐\n")

    for i, pred in enumerate(top5, 1):
        prob_tot_5 *= pred['prob']
        quota_tot_5 *= pred['quota']

        icon = "🔥" if pred['prob'] >= 0.80 else "⭐"

        print(f"{i}. {pred['partita']}")
        print(f"   ⏰ {pred['ora']}")
        print(f"   {icon} {pred['mercato']} → {pred['prob']*100:.1f}%\n")

    print(f"{'─'*100}")
    print(f"📊 PROBABILITÀ COMBINATA: {prob_tot_5*100:.2f}%")
    print(f"💰 QUOTA FAIR: ~{quota_tot_5:.2f}")
    print(f"💵 QUOTA BOOKMAKER STIMATA: ~{quota_tot_5*0.87:.2f} (dopo -13%)")
    print(f"\n💵 IMPORTO CONSIGLIATO: 10-20€")
    print(f"💵 VINCITA ATTESA (quota {quota_tot_5*0.87:.2f}): {quota_tot_5*0.87*10:.2f}€ con 10€, {quota_tot_5*0.87*20:.2f}€ con 20€")
    print(f"{'─'*100}")

    # SCHEDINA 9 EVENTI (TUTTI)
    if len(predictions_sorted) >= 8:
        print(f"\n\n📋 SCHEDINA COMPLETA ({len(predictions_sorted)} EVENTI)\n")

        prob_tot_9 = 1.0
        quota_tot_9 = 1.0

        for i, pred in enumerate(predictions_sorted, 1):
            prob_tot_9 *= pred['prob']
            quota_tot_9 *= pred['quota']

            icon = "🔥" if pred['prob'] >= 0.80 else "⭐" if pred['prob'] >= 0.70 else ""

            print(f"{i}. {pred['partita']:50} → {pred['mercato']:7} ({pred['prob']*100:4.1f}%) {icon}")

        print(f"\n{'─'*100}")
        print(f"📊 PROBABILITÀ COMBINATA: {prob_tot_9*100:.2f}%")
        print(f"💰 QUOTA FAIR: ~{quota_tot_9:.2f}")
        print(f"💵 QUOTA BOOKMAKER STIMATA: ~{quota_tot_9*0.87:.2f}")
        print(f"\n💵 IMPORTO CONSIGLIATO: 5-10€")
        print(f"💵 VINCITA ATTESA: {quota_tot_9*0.87*5:.2f}€ con 5€, {quota_tot_9*0.87*10:.2f}€ con 10€")
        print(f"{'─'*100}")

print("\n" + "=" * 100)
print("✅ PREDIZIONI ML COMPLETATE!")
print("=" * 100)
print(f"""
⚠️  NOTE IMPORTANTI:

1. 🎯 Modelli ML riaddestrati con 1761 partite storiche
   - Modello 1X2: 47.88% accuracy
   - Modello O/U: 56.66% accuracy

2. 💰 Quote mostrate sono FAIR (matematiche)
   - Le quote REALI del bookmaker saranno ~13% più basse
   - Es: Quota fair 3.0 → Quota reale ~2.6

3. ✅ STRATEGIA: Usa solo DOPPIA CHANCE (più sicura)
   - Probabilità 70-90% sui singoli pick
   - Schedina 5 eventi: probabilità combinata ~{prob_tot_5*100:.1f}%

4. ❌ GESTIONE BANKROLL:
   - Mai più del 2-5% del budget totale
   - Schedina 5 eventi raccomandata (più probabile)

5. 🔥 Pick più sicuri (>80%):
""")

for pred in predictions_sorted:
    if pred['prob'] >= 0.80:
        print(f"   - {pred['partita']:45} → {pred['mercato']} ({pred['prob']*100:.1f}%)")

print("\n" + "=" * 100)
print("🎯 BUONA FORTUNA!")
print("=" * 100)
