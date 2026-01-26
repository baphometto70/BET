#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCHEDINA EUROPA LEAGUE - 22 GENNAIO 2026 con ML CONSERVATIVO
Strategia migliorata dopo analisi errori 21 gennaio
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
print("🏆 SCHEDINA EUROPA LEAGUE - 22 GENNAIO 2026 (ML CONSERVATIVO)")
print("=" * 100)
print("📊 Strategia: Conservativa dopo analisi errori 21/01")
print("🎯 Focus: Solo DC 1X/X2 con prob >75%, NO DC 12 rischiosi")
print("=" * 100)

try:
    print("\n🔄 Caricamento modelli ML riaddestrati (1770 partite)...")
    model_1x2 = joblib.load(MODEL_DIR / "bet_1x2_retrained.joblib")
    imputer_1x2 = joblib.load(MODEL_DIR / "imputer_1x2_retrained.joblib")
    print("✅ Modello 1X2 caricato (Accuracy: 47.74%)")

    model_ou = joblib.load(MODEL_DIR / "bet_ou25_retrained.joblib")
    imputer_ou = joblib.load(MODEL_DIR / "imputer_ou25_retrained.joblib")
    print("✅ Modello O/U caricato (Accuracy: 58.19%)")

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
# TROVA PARTITE EUROPA LEAGUE 22 GENNAIO
# ========================================
db = SessionLocal()
match_date = date(2026, 1, 22)

el_oggi = db.query(Fixture).filter(
    Fixture.date == match_date,
    Fixture.league_code == 'EL'
).all()

print(f"\n🏆 Partite Europa League del 22/01/2026: {len(el_oggi)}")

predictions = []

for fix in el_oggi:
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
            'xg_for_home': feat.xg_for_home or 1.3,
            'xg_against_home': feat.xg_against_home or 1.3,
            'xg_for_away': feat.xg_for_away or 1.3,
            'xg_against_away': feat.xg_against_away or 1.3,
            'rest_days_home': feat.rest_days_home or 3,
            'rest_days_away': feat.rest_days_away or 3,
            'derby_flag': feat.derby_flag if hasattr(feat, 'derby_flag') else 0,
            'europe_flag_home': 1,  # Europa League
            'europe_flag_away': 1,
            'meteo_flag': feat.meteo_flag if hasattr(feat, 'meteo_flag') else 0,
            'style_ppda_home': feat.style_ppda_home if hasattr(feat, 'style_ppda_home') and feat.style_ppda_home else 10.0,
            'style_ppda_away': feat.style_ppda_away if hasattr(feat, 'style_ppda_away') and feat.style_ppda_away else 10.0,
        }

        # Odds
        if fix.odds:
            X_dict['odds_1'] = fix.odds.odds_1 if fix.odds.odds_1 else 2.5
            X_dict['odds_x'] = fix.odds.odds_x if fix.odds.odds_x else 3.2
            X_dict['odds_2'] = fix.odds.odds_2 if fix.odds.odds_2 else 3.0
        else:
            lam_h_tmp = (X_dict['xg_for_home'] + X_dict['xg_against_away']) / 2
            lam_a_tmp = (X_dict['xg_for_away'] + X_dict['xg_against_home']) / 2
            p_h_tmp = min(0.7, max(0.15, lam_h_tmp / (lam_h_tmp + lam_a_tmp + 0.5)))
            X_dict['odds_1'] = 1 / p_h_tmp if p_h_tmp > 0 else 3.0
            X_dict['odds_x'] = 3.2
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

        # DC - NUOVA STRATEGIA CONSERVATIVA
        p_1x = p_h_ml + p_d_ml
        p_x2 = p_d_ml + p_a_ml

        # ⚠️ EVITA DC 12 se pareggio >15% (lezione da Galatasaray-Atletico)
        if p_d_ml < 0.15:
            p_12 = p_h_ml + p_a_ml
        else:
            p_12 = 0  # Non giocare DC 12 se pareggio probabile!

        # ========================================
        # MOSTRA RISULTATI
        # ========================================
        print(f"\n🤖 PREDIZIONI ML:")
        print(f"   1 (Casa):      {p_h_ml*100:5.1f}%")
        print(f"   X (Pareggio):  {p_d_ml*100:5.1f}%")
        print(f"   2 (Trasferta): {p_a_ml*100:5.1f}%")

        print(f"\n   Doppia Chance CONSERVATIVA:")
        print(f"      DC 1X:  {p_1x*100:5.1f}%")
        print(f"      DC X2:  {p_x2*100:5.1f}%")
        if p_12 > 0:
            print(f"      DC 12:  {p_12*100:5.1f}% (pareggio <15%)")
        else:
            print(f"      DC 12:  ⚠️  NON CONSIGLIATO (pareggio {p_d_ml*100:.1f}% >15%)")

        # TOP PICK - SOLO DC 1X o X2 con prob >75%
        mercati_sicuri = []

        if p_1x >= 0.75:
            mercati_sicuri.append(('DC 1X', p_1x, 'DC'))

        if p_x2 >= 0.75:
            mercati_sicuri.append(('DC X2', p_x2, 'DC'))

        # DC 12 solo se pareggio <15% E prob >80%
        if p_d_ml < 0.15 and p_12 >= 0.80:
            mercati_sicuri.append(('DC 12', p_12, 'DC'))

        if mercati_sicuri:
            best_pick = max(mercati_sicuri, key=lambda x: x[1])

            print(f"\n💡 PICK CONSIGLIATO (CONSERVATIVO):")
            icon = "🔥" if best_pick[1] >= 0.85 else "⭐" if best_pick[1] >= 0.80 else "✅"
            print(f"   {icon} {best_pick[0]:12} → {best_pick[1]*100:5.1f}% | Q ~{1/best_pick[1]:.2f}")

            predictions.append({
                'partita': f"{fix.home} vs {fix.away}",
                'ora': fix.time_local or fix.time,
                'mercato': best_pick[0],
                'categoria': best_pick[2],
                'prob': best_pick[1],
                'quota': 1/best_pick[1],
                'prob_pareggio': p_d_ml
            })
        else:
            print(f"\n⚠️  NESSUN PICK SICURO (tutte prob <75%)")

    except Exception as e:
        print(f"❌ ERRORE: {e}")
        import traceback
        traceback.print_exc()
        continue

db.close()

# ========================================
# SCHEDINA FINALE CONSERVATIVA
# ========================================
if len(predictions) > 0:
    print("\n\n" + "=" * 100)
    print("📋 SCHEDINA CONSIGLIATA - STRATEGIA CONSERVATIVA")
    print("=" * 100)

    # Ordina per probabilità decrescente
    predictions_sorted = sorted(predictions, key=lambda x: x['prob'], reverse=True)

    # SCHEDINA TOP 4 (più conservativa)
    top4 = predictions_sorted[:4]

    prob_tot_4 = 1.0
    quota_tot_4 = 1.0

    print(f"\n🛡️ SCHEDINA CONSERVATIVA (TOP 4 PIÙ SICURI)\n")

    for i, pred in enumerate(top4, 1):
        prob_tot_4 *= pred['prob']
        quota_tot_4 *= pred['quota']

        icon = "🔥" if pred['prob'] >= 0.85 else "⭐"

        print(f"{i}. {pred['partita']}")
        print(f"   ⏰ {pred['ora']}")
        print(f"   {icon} {pred['mercato']} → {pred['prob']*100:.1f}% | Pareggio: {pred['prob_pareggio']*100:.1f}%\n")

    print(f"{'─'*100}")
    print(f"📊 PROBABILITÀ COMBINATA: {prob_tot_4*100:.2f}%")
    print(f"💰 QUOTA FAIR: ~{quota_tot_4:.2f}")
    print(f"💵 QUOTA BOOKMAKER STIMATA: ~{quota_tot_4*0.87:.2f} (dopo -13%)")
    print(f"\n💵 IMPORTO CONSIGLIATO: 20-30€ (3-4% bankroll)")
    print(f"💵 VINCITA ATTESA (quota {quota_tot_4*0.87:.2f}):")
    print(f"   • Con 20€ → {quota_tot_4*0.87*20:.2f}€")
    print(f"   • Con 30€ → {quota_tot_4*0.87*30:.2f}€")
    print(f"{'─'*100}")

    # SCHEDINA COMPLETA (se ci sono abbastanza pick)
    if len(predictions_sorted) >= 6:
        print(f"\n\n📋 SCHEDINA COMPLETA ({len(predictions_sorted)} EVENTI - RISCHIOSA)\n")

        prob_tot_all = 1.0
        quota_tot_all = 1.0

        for i, pred in enumerate(predictions_sorted, 1):
            prob_tot_all *= pred['prob']
            quota_tot_all *= pred['quota']

            icon = "🔥" if pred['prob'] >= 0.85 else "⭐" if pred['prob'] >= 0.80 else ""

            print(f"{i}. {pred['partita']:45} → {pred['mercato']:7} ({pred['prob']*100:4.1f}%) {icon}")

        print(f"\n{'─'*100}")
        print(f"📊 PROBABILITÀ COMBINATA: {prob_tot_all*100:.2f}%")
        print(f"💰 QUOTA FAIR: ~{quota_tot_all:.2f}")
        print(f"💵 QUOTA BOOKMAKER STIMATA: ~{quota_tot_all*0.87:.2f}")
        print(f"\n⚠️  IMPORTO CONSIGLIATO: 10€ MAX (schedina rischiosa)")
        print(f"{'─'*100}")

print("\n" + "=" * 100)
print("✅ PREDIZIONI ML COMPLETATE (STRATEGIA CONSERVATIVA)")
print("=" * 100)
print(f"""
⚠️  STRATEGIA MIGLIORATA DOPO ANALISI 21/01:

1. 🛡️ SOLO DC 1X o DC X2 con probabilità >75%
   - NO più DC 12 (rischio pareggio come Galatasaray-Atletico!)
   - DC 12 solo se pareggio <15% E prob >80%

2. 📊 PROBABILITÀ PAREGGIO MONITORATA
   - Se pareggio >15% → EVITA DC 12
   - Lezione da Galatasaray-Atletico (15.7% → uscito!)

3. 💰 GESTIONE BANKROLL CONSERVATIVA
   - Schedina TOP 4: 20-30€ (3-4% bankroll)
   - Mai più del 5% del budget totale

4. 🎯 MODELLI RIADDESTRATI
   - Dataset: 1770 partite (+9 dal 21/01)
   - 1X2: 47.74% accuracy
   - O/U: 58.19% accuracy

5. ⚠️ ASPETTATIVE REALISTICHE
   - 20/01: 77.8% → 21/01: 33.3%
   - Media: ~55% (normale per ML su calcio)
   - Gestione bankroll fondamentale!
""")

print("\n" + "=" * 100)
print("🎯 BUONA FORTUNA!")
print("=" * 100)
