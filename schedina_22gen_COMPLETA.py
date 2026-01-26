#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCHEDINA EUROPA LEAGUE - 22 GENNAIO 2026 - ANALISI COMPLETA TUTTI I MERCATI
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
print("🏆 SCHEDINA EUROPA LEAGUE - 22 GENNAIO 2026 - TUTTI I MERCATI")
print("=" * 100)

try:
    model_1x2 = joblib.load(MODEL_DIR / "bet_1x2_retrained.joblib")
    imputer_1x2 = joblib.load(MODEL_DIR / "imputer_1x2_retrained.joblib")
    print("✅ Modello 1X2 caricato (Accuracy: 47.74%)")

    model_ou = joblib.load(MODEL_DIR / "bet_ou25_retrained.joblib")
    imputer_ou = joblib.load(MODEL_DIR / "imputer_ou25_retrained.joblib")
    print("✅ Modello O/U caricato (Accuracy: 58.19%)")

except Exception as e:
    print(f"❌ ERRORE: {e}")
    sys.exit(1)

FEATURES = [
    'xg_for_home', 'xg_against_home', 'xg_for_away', 'xg_against_away',
    'rest_days_home', 'rest_days_away',
    'derby_flag', 'europe_flag_home', 'europe_flag_away',
    'meteo_flag', 'style_ppda_home', 'style_ppda_away',
    'odds_1', 'odds_x', 'odds_2',
    'xg_total', 'xg_diff', 'xg_ratio', 'ppda_diff'
]

# ========================================
# PARTITE 20:00
# ========================================
db = SessionLocal()
match_date = date(2026, 1, 22)

el_20 = db.query(Fixture).filter(
    Fixture.date == match_date,
    Fixture.league_code == 'EL',
    Fixture.time == '20:00'
).all()

print(f"\n🏆 Partite Europa League ore 20:00: {len(el_20)}")

all_predictions = []

for fix in el_20:
    print(f"\n{'='*100}")
    print(f"⚽ {fix.home} vs {fix.away}")
    print(f"🏆 {fix.league_code} | ⏰ {fix.time_local or fix.time}")
    print(f"{'='*100}")

    if not fix.feature:
        print("❌ NESSUNA FEATURE")
        continue

    feat = fix.feature

    try:
        X_dict = {
            'xg_for_home': feat.xg_for_home or 1.3,
            'xg_against_home': feat.xg_against_home or 1.3,
            'xg_for_away': feat.xg_for_away or 1.3,
            'xg_against_away': feat.xg_against_away or 1.3,
            'rest_days_home': feat.rest_days_home or 3,
            'rest_days_away': feat.rest_days_away or 3,
            'derby_flag': feat.derby_flag if hasattr(feat, 'derby_flag') else 0,
            'europe_flag_home': 1,
            'europe_flag_away': 1,
            'meteo_flag': feat.meteo_flag if hasattr(feat, 'meteo_flag') else 0,
            'style_ppda_home': feat.style_ppda_home if hasattr(feat, 'style_ppda_home') and feat.style_ppda_home else 10.0,
            'style_ppda_away': feat.style_ppda_away if hasattr(feat, 'style_ppda_away') and feat.style_ppda_away else 10.0,
        }

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

        total = p_h_ml + p_d_ml + p_a_ml
        p_h_ml /= total
        p_d_ml /= total
        p_a_ml /= total

        # ========================================
        # PREDIZIONI ML O/U 2.5
        # ========================================
        X_imp_ou = imputer_ou.transform(X)
        proba_ou = model_ou.predict_proba(X_imp_ou)[0]
        p_under25_ml = proba_ou[0]
        p_over25_ml = proba_ou[1]

        # ========================================
        # POISSON per GG/NG
        # ========================================
        lam_h = (X_dict['xg_for_home'] + X_dict['xg_against_away']) / 2
        lam_a = (X_dict['xg_for_away'] + X_dict['xg_against_home']) / 2

        p_gg = 1 - (poisson.pmf(0, lam_h) * sum(poisson.pmf(j, lam_a) for j in range(10)) +
                    sum(poisson.pmf(i, lam_h) for i in range(10)) * poisson.pmf(0, lam_a) -
                    poisson.pmf(0, lam_h) * poisson.pmf(0, lam_a))
        p_ng = 1 - p_gg

        # DC
        p_1x = p_h_ml + p_d_ml
        p_x2 = p_d_ml + p_a_ml
        p_12 = p_h_ml + p_a_ml

        # ========================================
        # MOSTRA TUTTI I MERCATI
        # ========================================
        print(f"\n📊 ANALISI COMPLETA:")
        print(f"\n🎯 1X2 (Esito finale):")
        print(f"   1 (Casa):      {p_h_ml*100:5.1f}% | Quota: ~{1/p_h_ml:.2f}")
        print(f"   X (Pareggio):  {p_d_ml*100:5.1f}% | Quota: ~{1/p_d_ml:.2f}")
        print(f"   2 (Trasferta): {p_a_ml*100:5.1f}% | Quota: ~{1/p_a_ml:.2f}")

        print(f"\n🔀 Doppia Chance:")
        print(f"   DC 1X:  {p_1x*100:5.1f}% | Quota: ~{1/p_1x:.2f}")
        print(f"   DC X2:  {p_x2*100:5.1f}% | Quota: ~{1/p_x2:.2f}")
        print(f"   DC 12:  {p_12*100:5.1f}% | Quota: ~{1/p_12:.2f}")

        print(f"\n⚽ Over/Under 2.5:")
        print(f"   Over 2.5:  {p_over25_ml*100:5.1f}% | Quota: ~{1/p_over25_ml:.2f}")
        print(f"   Under 2.5: {p_under25_ml*100:5.1f}% | Quota: ~{1/p_under25_ml:.2f}")

        print(f"\n🥅 Gol (entrambe segnano):")
        print(f"   GG:  {p_gg*100:5.1f}% | Quota: ~{1/p_gg:.2f}")
        print(f"   NG:  {p_ng*100:5.1f}% | Quota: ~{1/p_ng:.2f}")

        print(f"\n📈 Expected Goals: Casa {lam_h:.2f} | Trasferta {lam_a:.2f}")

        # ========================================
        # TOP 3 PICKS (migliori probabilità)
        # ========================================
        tutti_mercati = [
            ('1 (Casa)', p_h_ml, '1X2'),
            ('X (Pareggio)', p_d_ml, '1X2'),
            ('2 (Trasferta)', p_a_ml, '1X2'),
            ('DC 1X', p_1x, 'DC'),
            ('DC X2', p_x2, 'DC'),
            ('DC 12', p_12, 'DC'),
            ('Over 2.5', p_over25_ml, 'O/U'),
            ('Under 2.5', p_under25_ml, 'O/U'),
            ('GG', p_gg, 'GG/NG'),
            ('NG', p_ng, 'GG/NG'),
        ]

        # Ordina per probabilità
        tutti_mercati_sorted = sorted(tutti_mercati, key=lambda x: x[1], reverse=True)

        print(f"\n💡 TOP 3 PICKS (più probabili):")
        for i, (nome, prob, cat) in enumerate(tutti_mercati_sorted[:3], 1):
            icon = "🔥" if prob >= 0.80 else "⭐" if prob >= 0.70 else "✅"
            print(f"   {i}. {icon} {nome:15} → {prob*100:5.1f}% ({cat})")

        # Salva per schedina finale
        for nome, prob, cat in tutti_mercati_sorted[:5]:  # Top 5 per partita
            if prob >= 0.70:  # Solo se prob >70%
                all_predictions.append({
                    'partita': f"{fix.home} vs {fix.away}",
                    'ora': fix.time_local or fix.time,
                    'mercato': nome,
                    'categoria': cat,
                    'prob': prob,
                    'quota': 1/prob
                })

    except Exception as e:
        print(f"❌ ERRORE: {e}")
        import traceback
        traceback.print_exc()
        continue

db.close()

# ========================================
# SCHEDINE FINALI - VARI MERCATI
# ========================================
if len(all_predictions) > 0:
    print("\n\n" + "=" * 100)
    print("📋 SCHEDINE CONSIGLIATE - TUTTI I MERCATI")
    print("=" * 100)

    # Ordina per probabilità
    all_predictions_sorted = sorted(all_predictions, key=lambda x: x['prob'], reverse=True)

    # SCHEDINA 1: TOP 5 PIÙ SICURI (mix mercati)
    print(f"\n🛡️ SCHEDINA 1: TOP 5 PIÙ SICURI (MIX MERCATI)\n")

    top5 = all_predictions_sorted[:5]
    prob_tot = 1.0
    quota_tot = 1.0

    for i, pred in enumerate(top5, 1):
        prob_tot *= pred['prob']
        quota_tot *= pred['quota']

        icon = "🔥" if pred['prob'] >= 0.85 else "⭐" if pred['prob'] >= 0.80 else "✅"

        print(f"{i}. {pred['partita']}")
        print(f"   {icon} {pred['mercato']:15} → {pred['prob']*100:.1f}% ({pred['categoria']})\n")

    print(f"{'─'*100}")
    print(f"📊 PROBABILITÀ COMBINATA: {prob_tot*100:.2f}%")
    print(f"💰 QUOTA FAIR: ~{quota_tot:.2f}")
    print(f"💵 QUOTA BOOKMAKER: ~{quota_tot*0.87:.2f}")
    print(f"💵 Puntata 20€ → Vincita: {quota_tot*0.87*20:.2f}€")
    print(f"{'─'*100}")

    # SCHEDINA 2: SOLO OVER/UNDER
    ou_picks = [p for p in all_predictions_sorted if p['categoria'] == 'O/U']
    if len(ou_picks) >= 4:
        print(f"\n\n⚽ SCHEDINA 2: SOLO OVER/UNDER 2.5\n")

        top_ou = ou_picks[:4]
        prob_tot_ou = 1.0
        quota_tot_ou = 1.0

        for i, pred in enumerate(top_ou, 1):
            prob_tot_ou *= pred['prob']
            quota_tot_ou *= pred['quota']

            print(f"{i}. {pred['partita']}")
            print(f"   ⚽ {pred['mercato']} → {pred['prob']*100:.1f}%\n")

        print(f"{'─'*100}")
        print(f"📊 PROBABILITÀ COMBINATA: {prob_tot_ou*100:.2f}%")
        print(f"💰 QUOTA: ~{quota_tot_ou*0.87:.2f}")
        print(f"{'─'*100}")

    # SCHEDINA 3: SOLO GG/NG
    gg_picks = [p for p in all_predictions_sorted if p['categoria'] == 'GG/NG']
    if len(gg_picks) >= 4:
        print(f"\n\n🥅 SCHEDINA 3: SOLO GOL (GG/NG)\n")

        top_gg = gg_picks[:4]
        prob_tot_gg = 1.0
        quota_tot_gg = 1.0

        for i, pred in enumerate(top_gg, 1):
            prob_tot_gg *= pred['prob']
            quota_tot_gg *= pred['quota']

            print(f"{i}. {pred['partita']}")
            print(f"   🥅 {pred['mercato']} → {pred['prob']*100:.1f}%\n")

        print(f"{'─'*100}")
        print(f"📊 PROBABILITÀ COMBINATA: {prob_tot_gg*100:.2f}%")
        print(f"💰 QUOTA: ~{quota_tot_gg*0.87:.2f}")
        print(f"{'─'*100}")

print("\n" + "=" * 100)
print("✅ ANALISI COMPLETA TUTTI I MERCATI COMPLETATA!")
print("=" * 100)
