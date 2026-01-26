#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PREDIZIONI CHAMPIONS LEAGUE - MACHINE LEARNING PURO
Usa i modelli appena addestrati
"""

import sys
from pathlib import Path
from datetime import date
import joblib
import pandas as pd
import numpy as np
from database import SessionLocal
from models import Fixture
from scipy.stats import poisson

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "models"

print("=" * 100)
print("🤖 PREDIZIONI CHAMPIONS LEAGUE - MACHINE LEARNING PURO")
print("=" * 100)

# ========================================
# CARICA MODELLI RIADESTRATI
# ========================================
print("\n🔄 Caricamento modelli ML appena addestrati...")

try:
    model_1x2 = joblib.load(MODEL_DIR / "bet_1x2_retrained.joblib")
    imputer_1x2 = joblib.load(MODEL_DIR / "imputer_1x2_retrained.joblib")
    print("✅ Modello 1X2 caricato")

    model_ou = joblib.load(MODEL_DIR / "bet_ou25_retrained.joblib")
    imputer_ou = joblib.load(MODEL_DIR / "imputer_ou25_retrained.joblib")
    print("✅ Modello O/U caricato")

except Exception as e:
    print(f"❌ ERRORE: {e}")
    sys.exit(1)

# Features usate dal modello (devono matchare il training!)
FEATURES = [
    'xg_for_home', 'xg_against_home', 'xg_for_away', 'xg_against_away',
    'rest_days_home', 'rest_days_away',
    'derby_flag', 'europe_flag_home', 'europe_flag_away',
    'meteo_flag', 'style_ppda_home', 'style_ppda_away',
    'odds_1', 'odds_x', 'odds_2',  # AGGIUNTE
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

print(f"\n🏆 Partite Champions League oggi: {len(cl_oggi)}")

if len(cl_oggi) == 0:
    print("⚠️  Nessuna partita Champions - uso tutte le partite di oggi")
    cl_oggi = db.query(Fixture).filter(Fixture.date == oggi).all()

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
            'europe_flag_home': feat.europe_flag_home if hasattr(feat, 'europe_flag_home') else (1 if fix.league_code == 'CL' else 0),
            'europe_flag_away': feat.europe_flag_away if hasattr(feat, 'europe_flag_away') else (1 if fix.league_code == 'CL' else 0),
            'meteo_flag': feat.meteo_flag if hasattr(feat, 'meteo_flag') else 0,
            'style_ppda_home': feat.style_ppda_home if hasattr(feat, 'style_ppda_home') and feat.style_ppda_home else 10.0,
            'style_ppda_away': feat.style_ppda_away if hasattr(feat, 'style_ppda_away') and feat.style_ppda_away else 10.0,
        }

        # Aggiungi odds se presenti (dal database Odds)
        if fix.odds:
            X_dict['odds_1'] = fix.odds.odds_1 if fix.odds.odds_1 else 2.5
            X_dict['odds_x'] = fix.odds.odds_x if fix.odds.odds_x else 3.5
            X_dict['odds_2'] = fix.odds.odds_2 if fix.odds.odds_2 else 3.0
        else:
            # Stima odds da xG
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

        # Mappa probabilità
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

        print(f"\n   Altri mercati (Poisson):")
        print(f"      GG:  {p_gg*100:5.1f}% | NG: {p_ng*100:5.1f}%")
        print(f"      1X:  {p_1x*100:5.1f}% | X2: {p_x2*100:5.1f}% | 12: {p_12*100:5.1f}%")

        # TOP PICK
        mercati = [
            ('1', p_h_ml, '1X2', 'ML'),
            ('X', p_d_ml, '1X2', 'ML'),
            ('2', p_a_ml, '1X2', 'ML'),
            ('Over 2.5', p_over25_ml, 'O/U', 'ML'),
            ('Under 2.5', p_under25_ml, 'O/U', 'ML'),
            ('GG', p_gg, 'GOL', 'Poisson'),
            ('NG', p_ng, 'GOL', 'Poisson'),
            ('1X', p_1x, 'DC', 'ML'),
            ('X2', p_x2, 'DC', 'ML'),
            ('12', p_12, 'DC', 'ML')
        ]

        mercati_sorted = sorted(mercati, key=lambda x: x[1], reverse=True)

        print(f"\n💡 TOP 3 PICKS:")
        for i, (mercato, prob, cat, fonte) in enumerate(mercati_sorted[:3], 1):
            icon = "🔥" if prob >= 0.70 else "⭐" if prob >= 0.60 else "✅"
            print(f"   {i}. {icon} {mercato:12} ({cat:3}) → {prob*100:5.1f}% | Q ~{1/prob:.2f} [{fonte}]")

            if i == 1:
                predictions.append({
                    'partita': f"{fix.home} vs {fix.away}",
                    'ora': fix.time_local or fix.time,
                    'mercato': mercato,
                    'categoria': cat,
                    'prob': prob,
                    'quota': 1/prob,
                    'fonte': fonte
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
    print("📋 SCHEDINA CONSIGLIATA - MACHINE LEARNING")
    print("=" * 100)

    prob_tot = 1.0
    quota_tot = 1.0

    for i, pred in enumerate(predictions, 1):
        prob_tot *= pred['prob']
        quota_tot *= pred['quota']

        print(f"\n{i}. {pred['partita']}")
        print(f"   ⏰ {pred['ora']}")
        print(f"   🎯 {pred['mercato']} ({pred['categoria']}) → {pred['prob']*100:.1f}% [{pred['fonte']}]")

    print(f"\n{'─'*100}")
    print(f"📊 PROBABILITÀ COMBINATA: {prob_tot*100:.2f}%")
    print(f"💰 QUOTA TOTALE: {quota_tot:.2f}")
    print(f"💵 Con 10€ → Vincita: {quota_tot*10:.2f}€ | Profitto: {(quota_tot-1)*10:.2f}€")
    print(f"{'─'*100}")

    # Alternative migliorate
    print(f"\n\n💡 ALTERNATIVE CONSIGLIATE:")

    # Solo ML Over/Under (migliore accuracy)
    ml_ou = [p for p in predictions if 'Over' in p['mercato'] or 'Under' in p['mercato']]
    if len(ml_ou) >= 5:
        print(f"\n🔥 SCHEDINA OVER/UNDER (ML - Accuracy 53.6%):")
        prob_ou = 1.0
        for p in ml_ou[:5]:
            prob_ou *= p['prob']
            print(f"   • {p['partita']:40} → {p['mercato']:12} ({p['prob']*100:.1f}%)")
        print(f"   📊 Prob: {prob_ou*100:.2f}% | Quota: ~{1/prob_ou:.2f}")

    # Solo Doppia Chance (più sicuro)
    dc_picks = [p for p in predictions if p['categoria'] == 'DC']
    if len(dc_picks) >= 5:
        print(f"\n⭐ SCHEDINA DOPPIA CHANCE (Conservativa):")
        prob_dc = 1.0
        for p in dc_picks[:5]:
            prob_dc *= p['prob']
            print(f"   • {p['partita']:40} → {p['mercato']:12} ({p['prob']*100:.1f}%)")
        print(f"   📊 Prob: {prob_dc*100:.2f}% | Quota: ~{1/prob_dc:.2f}")

print("\n" + "=" * 100)
print("✅ PREDIZIONI ML COMPLETATE!")
print("=" * 100)
print("""
⚠️  NOTA IMPORTANTE:
   - Modello 1X2: 37% accuracy (basso, normale per 1X2)
   - Modello O/U: 53.6% accuracy (buono!)
   - Consiglio: Usa preferibilmente Over/Under che ha migliore performance
   - Quote bookmaker saranno 10-15% più basse delle quote fair
""")
