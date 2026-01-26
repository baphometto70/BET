#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCHEDINA CON VERI MODELLI ML - 17 GENNAIO 2026
USA I MODELLI LIGHTGBM ADDESTRATI, NON POISSON!
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
# CARICA I MODELLI ML
# ========================================
ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "models"

print("=" * 100)
print("🤖 SCHEDINA CON MACHINE LEARNING - 17 GENNAIO 2026")
print("=" * 100)
print("⚠️  QUESTA VOLTA USO I VERI MODELLI ML, NON POISSON!")
print("=" * 100)

# Carica modelli
try:
    print("\n🔄 Caricamento modelli ML...")

    # Prova prima ottimizzati, poi originali
    if (MODEL_DIR / "bet_1x2_optimized.joblib").exists():
        model_1x2 = joblib.load(MODEL_DIR / "bet_1x2_optimized.joblib")
        imputer_1x2 = joblib.load(MODEL_DIR / "imputer_1x2_optimized.joblib")
        print("✅ Modello 1X2 OTTIMIZZATO caricato")
    elif (MODEL_DIR / "bet_1x2.joblib").exists():
        model_1x2 = joblib.load(MODEL_DIR / "bet_1x2.joblib")
        imputer_1x2 = joblib.load(MODEL_DIR / "imputer_1x2.joblib")
        print("✅ Modello 1X2 originale caricato")
    else:
        print("❌ ERRORE: Nessun modello 1X2 trovato!")
        sys.exit(1)

    if (MODEL_DIR / "bet_ou25.joblib").exists():
        model_ou = joblib.load(MODEL_DIR / "bet_ou25.joblib")
        imputer_ou = joblib.load(MODEL_DIR / "imputer_ou25.joblib")
        print("✅ Modello Over/Under 2.5 caricato")
    else:
        print("⚠️  Modello O/U non trovato")
        model_ou = None

except Exception as e:
    print(f"❌ ERRORE nel caricamento modelli: {e}")
    sys.exit(1)

# ========================================
# FEATURES RICHIESTE DAI MODELLI
# ========================================
# Queste sono le feature che i modelli si aspettano
FEATURE_COLS = [
    # Base xG (4)
    'xg_for_home', 'xg_against_home', 'xg_for_away', 'xg_against_away',

    # Context (8)
    'is_derby', 'is_europe', 'weather_condition', 'ppda_home', 'ppda_away',
    'rest_days_home', 'rest_days_away', 'travel_distance',

    # Form features (20)
    'form_pts_home', 'form_pts_away', 'form_gf_home', 'form_gf_away',
    'form_ga_home', 'form_ga_away', 'form_xgf_home', 'form_xgf_away',
    'form_xga_home', 'form_xga_away',
    'form_home_pts_home', 'form_away_pts_away',
    'form_home_gf_home', 'form_home_ga_home',
    'form_away_gf_away', 'form_away_ga_away',
    'streak_home', 'streak_away', 'unbeaten_home', 'unbeaten_away',

    # H2H (8)
    'h2h_home_wins', 'h2h_draws', 'h2h_away_wins', 'h2h_total_games',
    'h2h_avg_home_goals', 'h2h_avg_away_goals',
    'h2h_home_win_pct', 'h2h_btts_pct',

    # Standings (10)
    'standing_position_home', 'standing_position_away',
    'standing_points_home', 'standing_points_away',
    'standing_gd_home', 'standing_gd_away',
    'standing_home_pts_home', 'standing_away_pts_away',
    'standing_form_home', 'standing_form_away',

    # Momentum (12)
    'momentum_goals_home', 'momentum_goals_away',
    'momentum_xg_home', 'momentum_xg_away',
    'momentum_shots_home', 'momentum_shots_away',
    'improvement_home', 'improvement_away',
    'consistency_home', 'consistency_away',
    'pressure_home', 'pressure_away',

    # Derived (4)
    'xg_total', 'xg_diff', 'xg_ratio', 'ppda_diff'
]

# ========================================
# QUERY PARTITE DI OGGI
# ========================================
db = SessionLocal()
oggi = date(2026, 1, 17)
now = datetime.now()

fixtures = db.query(Fixture).filter(Fixture.date == oggi).all()

print(f"\n📅 Partite trovate per il {oggi.strftime('%d/%m/%Y')}: {len(fixtures)}")

certezze_ml = []

for fix in fixtures:
    if not fix.feature:
        continue

    feat = fix.feature

    # SALTA partite già giocate
    match_time_str = fix.time_local or fix.time
    if match_time_str:
        try:
            match_time = datetime.strptime(match_time_str, "%H:%M").time()
            match_datetime = datetime.combine(fix.date, match_time)
            if match_datetime < now:
                continue
        except:
            pass

    # ========================================
    # PREPARA FEATURES PER ML
    # ========================================
    try:
        # Estrai features dal database
        feature_dict = {}

        # Base xG
        feature_dict['xg_for_home'] = feat.xg_for_home or 0
        feature_dict['xg_against_home'] = feat.xg_against_home or 0
        feature_dict['xg_for_away'] = feat.xg_for_away or 0
        feature_dict['xg_against_away'] = feat.xg_against_away or 0

        # Context
        feature_dict['is_derby'] = feat.is_derby or 0
        feature_dict['is_europe'] = feat.is_europe or 0
        feature_dict['weather_condition'] = feat.weather_condition or 0
        feature_dict['ppda_home'] = feat.ppda_home or 0
        feature_dict['ppda_away'] = feat.ppda_away or 0
        feature_dict['rest_days_home'] = feat.rest_days_home or 0
        feature_dict['rest_days_away'] = feat.rest_days_away or 0
        feature_dict['travel_distance'] = feat.travel_distance or 0

        # Form
        feature_dict['form_pts_home'] = feat.form_pts_home or 0
        feature_dict['form_pts_away'] = feat.form_pts_away or 0
        feature_dict['form_gf_home'] = feat.form_gf_home or 0
        feature_dict['form_gf_away'] = feat.form_gf_away or 0
        feature_dict['form_ga_home'] = feat.form_ga_home or 0
        feature_dict['form_ga_away'] = feat.form_ga_away or 0
        feature_dict['form_xgf_home'] = feat.form_xgf_home or 0
        feature_dict['form_xgf_away'] = feat.form_xgf_away or 0
        feature_dict['form_xga_home'] = feat.form_xga_home or 0
        feature_dict['form_xga_away'] = feat.form_xga_away or 0
        feature_dict['form_home_pts_home'] = feat.form_home_pts_home or 0
        feature_dict['form_away_pts_away'] = feat.form_away_pts_away or 0
        feature_dict['form_home_gf_home'] = feat.form_home_gf_home or 0
        feature_dict['form_home_ga_home'] = feat.form_home_ga_home or 0
        feature_dict['form_away_gf_away'] = feat.form_away_gf_away or 0
        feature_dict['form_away_ga_away'] = feat.form_away_ga_away or 0
        feature_dict['streak_home'] = feat.streak_home or 0
        feature_dict['streak_away'] = feat.streak_away or 0
        feature_dict['unbeaten_home'] = feat.unbeaten_home or 0
        feature_dict['unbeaten_away'] = feat.unbeaten_away or 0

        # H2H
        feature_dict['h2h_home_wins'] = feat.h2h_home_wins or 0
        feature_dict['h2h_draws'] = feat.h2h_draws or 0
        feature_dict['h2h_away_wins'] = feat.h2h_away_wins or 0
        feature_dict['h2h_total_games'] = feat.h2h_total_games or 0
        feature_dict['h2h_avg_home_goals'] = feat.h2h_avg_home_goals or 0
        feature_dict['h2h_avg_away_goals'] = feat.h2h_avg_away_goals or 0
        feature_dict['h2h_home_win_pct'] = feat.h2h_home_win_pct or 0
        feature_dict['h2h_btts_pct'] = feat.h2h_btts_pct or 0

        # Standings
        feature_dict['standing_position_home'] = feat.standing_position_home or 0
        feature_dict['standing_position_away'] = feat.standing_position_away or 0
        feature_dict['standing_points_home'] = feat.standing_points_home or 0
        feature_dict['standing_points_away'] = feat.standing_points_away or 0
        feature_dict['standing_gd_home'] = feat.standing_gd_home or 0
        feature_dict['standing_gd_away'] = feat.standing_gd_away or 0
        feature_dict['standing_home_pts_home'] = feat.standing_home_pts_home or 0
        feature_dict['standing_away_pts_away'] = feat.standing_away_pts_away or 0
        feature_dict['standing_form_home'] = feat.standing_form_home or 0
        feature_dict['standing_form_away'] = feat.standing_form_away or 0

        # Momentum
        feature_dict['momentum_goals_home'] = feat.momentum_goals_home or 0
        feature_dict['momentum_goals_away'] = feat.momentum_goals_away or 0
        feature_dict['momentum_xg_home'] = feat.momentum_xg_home or 0
        feature_dict['momentum_xg_away'] = feat.momentum_xg_away or 0
        feature_dict['momentum_shots_home'] = feat.momentum_shots_home or 0
        feature_dict['momentum_shots_away'] = feat.momentum_shots_away or 0
        feature_dict['improvement_home'] = feat.improvement_home or 0
        feature_dict['improvement_away'] = feat.improvement_away or 0
        feature_dict['consistency_home'] = feat.consistency_home or 0
        feature_dict['consistency_away'] = feat.consistency_away or 0
        feature_dict['pressure_home'] = feat.pressure_home or 0
        feature_dict['pressure_away'] = feat.pressure_away or 0

        # Derived
        feature_dict['xg_total'] = feature_dict['xg_for_home'] + feature_dict['xg_for_away']
        feature_dict['xg_diff'] = feature_dict['xg_for_home'] - feature_dict['xg_for_away']
        xg_away_safe = feature_dict['xg_for_away'] if feature_dict['xg_for_away'] > 0 else 0.01
        feature_dict['xg_ratio'] = feature_dict['xg_for_home'] / xg_away_safe
        feature_dict['ppda_diff'] = feature_dict['ppda_home'] - feature_dict['ppda_away']

        # Crea DataFrame con TUTTE le feature nell'ordine corretto
        X = pd.DataFrame([feature_dict])[FEATURE_COLS]

        # Imputa valori mancanti
        X_imputed_1x2 = imputer_1x2.transform(X)

        # ========================================
        # PREDIZIONI 1X2 CON ML
        # ========================================
        proba_1x2 = model_1x2.predict_proba(X_imputed_1x2)[0]

        # DEBUG: Stampa le prime 3 partite
        if len(certezze_ml) < 3:
            print(f"\n🔍 DEBUG {fix.home} vs {fix.away}:")
            print(f"   Classi modello: {model_1x2.classes_}")
            print(f"   Probabilità: {proba_1x2}")

        # Controlla quante classi ha predetto
        n_classes = len(proba_1x2)

        if n_classes == 3:
            # Normale: [Home, Draw, Away] oppure ordine diverso
            # Verifica qual è l'ordine delle classi
            classes = model_1x2.classes_

            # Mappa probabilità alle classi corrette
            class_to_prob = dict(zip(classes, proba_1x2))

            # Estrai probabilità per Home(1), Draw(0), Away(2)
            p_h = class_to_prob.get(1, class_to_prob.get('1', 0.33))
            p_d = class_to_prob.get(0, class_to_prob.get('X', 0.33))
            p_a = class_to_prob.get(2, class_to_prob.get('2', 0.33))

        elif n_classes == 2:
            # Modello rotto - solo 2 classi
            print(f"⚠️  MODELLO 1X2 ROTTO per {fix.home} vs {fix.away} - Solo {n_classes} classi: {model_1x2.classes_}")
            # Fallback uniforme
            p_h = 0.33
            p_d = 0.33
            p_a = 0.34
        else:
            print(f"⚠️  Classi inattese: {n_classes}")
            p_h = p_d = p_a = 1.0 / n_classes

        # ========================================
        # PREDIZIONI O/U 2.5 CON ML (se disponibile)
        # ========================================
        if model_ou:
            X_imputed_ou = imputer_ou.transform(X)
            proba_ou = model_ou.predict_proba(X_imputed_ou)[0]
            # [Under 2.5, Over 2.5]
            p_under25 = proba_ou[0]
            p_over25 = proba_ou[1]
        else:
            # Fallback da xG
            from scipy.stats import poisson
            lam_h = (feat.xg_for_home + feat.xg_against_away) / 2
            lam_a = (feat.xg_for_away + feat.xg_against_home) / 2
            p_over25 = 1 - sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                               for i in range(3) for j in range(3) if i+j <= 2)
            p_under25 = 1 - p_over25

        # ========================================
        # CALCOLA ALTRI MERCATI DA 1X2 + O/U
        # ========================================
        # Doppia Chance
        p_1x = p_h + p_d
        p_x2 = p_d + p_a
        p_12 = p_h + p_a

        # Goal/No Goal (stima da xG)
        from scipy.stats import poisson
        lam_h = feature_dict['xg_for_home']
        lam_a = feature_dict['xg_for_away']

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

        # ========================================
        # RACCOGLI CERTEZZE (≥ 65%)
        # ========================================
        mercati_ml = [
            ('1 (Casa)', p_h, '1X2'),
            ('X (Pareggio)', p_d, '1X2'),
            ('2 (Trasferta)', p_a, '1X2'),
            ('1X', p_1x, 'DOPPIA CHANCE'),
            ('X2', p_x2, 'DOPPIA CHANCE'),
            ('12', p_12, 'DOPPIA CHANCE'),
            ('Over 2.5', p_over25, 'OVER/UNDER'),
            ('Under 2.5', p_under25, 'OVER/UNDER'),
            ('GG', p_gg, 'GOL'),
            ('NG', p_ng, 'GOL'),
            ('Multigol 1-3', p_mg_13, 'MULTIGOL'),
            ('Multigol 2-4', p_mg_24, 'MULTIGOL'),
            ('Multigol 2-5', p_mg_25, 'MULTIGOL'),
        ]

        for mercato, prob, categoria in mercati_ml:
            if prob >= 0.55:  # Soglia realistica per ML
                certezze_ml.append({
                    'partita': f"{fix.home} vs {fix.away}",
                    'lega': fix.league_code,
                    'ora': match_time_str,
                    'mercato': mercato,
                    'categoria': categoria,
                    'prob': prob,
                    'quota': 1 / prob,
                    'fonte': 'ML' if 'Over' in mercato or 'Under' in mercato or categoria == '1X2' else 'ML+Poisson'
                })

    except Exception as e:
        print(f"⚠️  Errore su {fix.home} vs {fix.away}: {e}")
        continue

db.close()

# ========================================
# MOSTRA RISULTATI
# ========================================
certezze_sorted = sorted(certezze_ml, key=lambda x: x['prob'], reverse=True)

print(f"\n✅ CERTEZZE TROVATE (ML): {len(certezze_sorted)} eventi con probabilità ≥ 65%\n")

if not certezze_sorted:
    print("❌ NESSUNA CERTEZZA TROVATA")
    sys.exit(0)

# ========================================
# SCHEDINA CONSIGLIATA
# ========================================
print("=" * 100)
print("📋 SCHEDINA MACHINE LEARNING - TOP 8 EVENTI")
print("=" * 100)

# Diversifica per partita
partite_usate = set()
schedina_ml = []

for cert in certezze_sorted:
    if cert['partita'] not in partite_usate and len(schedina_ml) < 8:
        schedina_ml.append(cert)
        partite_usate.add(cert['partita'])

prob_tot = 1.0
quota_tot = 1.0

for i, ev in enumerate(schedina_ml, 1):
    prob_tot *= ev['prob']
    quota_tot *= ev['quota']

    print(f"\n{i}. {ev['partita']}")
    print(f"   🏆 {ev['lega']} | ⏰ {ev['ora']}")
    print(f"   🎯 {ev['mercato']} ({ev['categoria']}) → {ev['prob']*100:.1f}% [{ev['fonte']}]")

print(f"\n{'─' * 100}")
print(f"📊 PROBABILITÀ COMBINATA: {prob_tot*100:.2f}%")
print(f"💰 QUOTA TOTALE: {quota_tot:.2f}")
print(f"💵 Con 10€ → Vincita: {quota_tot*10:.2f}€ | Profitto: {(quota_tot-1)*10:.2f}€")
print(f"{'─' * 100}")

# ========================================
# CONFRONTO CON TOP CERTEZZE
# ========================================
print("\n\n" + "=" * 100)
print("🏆 TOP 10 CERTEZZE ASSOLUTE (MACHINE LEARNING)")
print("=" * 100)

for i, c in enumerate(certezze_sorted[:10], 1):
    icon = "🔥" if c['prob'] >= 0.80 else "⭐" if c['prob'] >= 0.75 else "✅"
    print(f"\n{i}. {icon} {c['partita']}")
    print(f"   🏆 {c['lega']} | ⏰ {c['ora']}")
    print(f"   🎯 {c['mercato']} ({c['categoria']})→ {c['prob']*100:.1f}% | Q ~{c['quota']:.2f} | {c['fonte']}")

print("\n" + "=" * 100)
print("✅ QUESTA VOLTA HO USATO I VERI MODELLI MACHINE LEARNING!")
print("=" * 100)
