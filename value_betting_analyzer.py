#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VALUE BETTING ANALYZER - Layer aggiuntivo per ottimizzare le predizioni ML
Mantiene il sistema esistente (77.8% accuracy) e aggiunge:
- Expected Value (EV) analysis
- Kelly Criterion per sizing ottimale
- Filtro per value bets (EV > 5%)
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
# CARICA MODELLI ML (STESSI DI PRIMA)
# ========================================
ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "models"

print("=" * 100)
print("💎 VALUE BETTING ANALYZER - OTTIMIZZAZIONE SCHEDINA ML")
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
# FUNZIONI VALUE BETTING
# ========================================

def calculate_expected_value(prob_ml, quota_bookmaker):
    """
    Calcola Expected Value (EV)
    EV = (prob × quota) - 1

    EV > 0 = value bet (bookmaker sottostima)
    EV > 5% = strong value
    EV > 10% = excellent value
    """
    return (prob_ml * quota_bookmaker) - 1

def kelly_criterion(prob_ml, quota_bookmaker, fraction=0.25):
    """
    Kelly Criterion per sizing ottimale
    Kelly% = (p × q - 1) / (q - 1)

    Usa fraction=0.25 (Kelly frazionario) per ridurre volatilità
    """
    if quota_bookmaker <= 1:
        return 0

    kelly = (prob_ml * quota_bookmaker - 1) / (quota_bookmaker - 1)

    # Applica fraction per ridurre rischio
    kelly_fractional = kelly * fraction

    # Limiti di sicurezza
    if kelly_fractional < 0:
        return 0  # No bet se EV negativo
    if kelly_fractional > 0.05:  # Max 5% del bankroll
        return 0.05

    return kelly_fractional

def classify_value(ev):
    """Classifica il value della scommessa"""
    if ev >= 0.15:
        return "🔥 EXCELLENT VALUE"
    elif ev >= 0.10:
        return "⭐⭐ STRONG VALUE"
    elif ev >= 0.05:
        return "⭐ GOOD VALUE"
    elif ev >= 0:
        return "✅ FAIR"
    else:
        return "❌ NO VALUE"

# ========================================
# TROVA PARTITE CHAMPIONS 21 GENNAIO
# ========================================
# ========================================
# TROVA PARTITE PER LA DATA
# ========================================
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--date', type=str, default=None, help='Data YYYY-MM-DD')
args = parser.parse_args()

if args.date:
    match_date = date.fromisoformat(args.date)
else:
    match_date = date.today()

db = SessionLocal()
fixtures = db.query(Fixture).filter(
    Fixture.date == match_date
).all()

print(f"\n🏆 Partite trovate per il {match_date}: {len(fixtures)}")

all_bets = []

for fix in fixtures:
    print(f"\n{'='*100}")
    print(f"⚽ {fix.home} vs {fix.away}")
    print(f"🏆 {fix.league_code} | ⏰ {fix.time_local or fix.time}")
    print(f"{'='*100}")

    if not fix.feature:
        print("❌ NESSUNA FEATURE")
        continue

    feat = fix.feature

    # ========================================
    # PREPARA FEATURES PER ML (COME PRIMA)
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
            'europe_flag_home': 1,
            'europe_flag_away': 1,
            'meteo_flag': feat.meteo_flag if hasattr(feat, 'meteo_flag') else 0,
            'style_ppda_home': feat.style_ppda_home if hasattr(feat, 'style_ppda_home') and feat.style_ppda_home else 10.0,
            'style_ppda_away': feat.style_ppda_away if hasattr(feat, 'style_ppda_away') and feat.style_ppda_away else 10.0,
        }

        # Odds REALI dal bookmaker (se disponibili)
        has_real_odds = False
        if fix.odds and fix.odds.odds_1 and fix.odds.odds_x and fix.odds.odds_2:
            odds_1_real = fix.odds.odds_1
            odds_x_real = fix.odds.odds_x
            odds_2_real = fix.odds.odds_2
            has_real_odds = True

            # Usa per il modello
            X_dict['odds_1'] = odds_1_real
            X_dict['odds_x'] = odds_x_real
            X_dict['odds_2'] = odds_2_real
        else:
            # Stima odds da xG (come prima)
            lam_h_tmp = (X_dict['xg_for_home'] + X_dict['xg_against_away']) / 2
            lam_a_tmp = (X_dict['xg_for_away'] + X_dict['xg_against_home']) / 2
            p_h_tmp = min(0.7, max(0.15, lam_h_tmp / (lam_h_tmp + lam_a_tmp + 0.5)))
            X_dict['odds_1'] = 1 / p_h_tmp if p_h_tmp > 0 else 3.0
            X_dict['odds_x'] = 3.5
            X_dict['odds_2'] = 1 / (1 - p_h_tmp - 0.27) if (1 - p_h_tmp - 0.27) > 0 else 3.5

            # Simula quote bookmaker (-13% margin)
            odds_1_real = X_dict['odds_1'] * 0.87
            odds_x_real = X_dict['odds_x'] * 0.87
            odds_2_real = X_dict['odds_2'] * 0.87

        # Derived
        X_dict['xg_total'] = X_dict['xg_for_home'] + X_dict['xg_for_away']
        X_dict['xg_diff'] = X_dict['xg_for_home'] - X_dict['xg_for_away']
        X_dict['xg_ratio'] = X_dict['xg_for_home'] / (X_dict['xg_for_away'] + 0.01)
        X_dict['ppda_diff'] = (X_dict['style_ppda_home'] or 10.0) - (X_dict['style_ppda_away'] or 10.0)

        X = pd.DataFrame([X_dict])[FEATURES]
        X_imp = imputer_1x2.transform(X)

        # ========================================
        # PREDIZIONI ML (COME PRIMA)
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

        # O/U
        X_imp_ou = imputer_ou.transform(X)
        proba_ou = model_ou.predict_proba(X_imp_ou)[0]
        p_under25_ml = proba_ou[0]
        p_over25_ml = proba_ou[1]

        # Poisson per GG
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
        # NUOVO: VALUE BETTING ANALYSIS
        # ========================================
        print(f"\n💎 VALUE BETTING ANALYSIS:")
        print(f"{'─'*100}")

        # Analizza TUTTI i mercati disponibili
        mercati = [
            ('1 (Casa)', p_h_ml, odds_1_real, 'DC'),
            ('X (Pareggio)', p_d_ml, odds_x_real, 'DC'),
            ('2 (Trasferta)', p_a_ml, odds_2_real, 'DC'),
            ('DC 1X', p_1x, (1/((1/odds_1_real + 1/odds_x_real))), 'DC'),
            ('DC X2', p_x2, (1/((1/odds_x_real + 1/odds_2_real))), 'DC'),
            ('DC 12', p_12, (1/((1/odds_1_real + 1/odds_2_real))), 'DC'),
        ]

        value_bets = []

        for nome, prob_ml, quota_book, categoria in mercati:
            ev = calculate_expected_value(prob_ml, quota_book)
            kelly = kelly_criterion(prob_ml, quota_book)
            value_class = classify_value(ev)

            # Aggiungi a lista
            value_bets.append({
                'partita': f"{fix.home} vs {fix.away}",
                'ora': fix.time_local or fix.time,
                'mercato': nome,
                'categoria': categoria,
                'prob_ml': prob_ml,
                'quota': quota_book,
                'ev': ev,
                'kelly': kelly,
                'value_class': value_class,
                'has_real_odds': has_real_odds
            })

            # Mostra solo se EV > 0 o prob > 60%
            if ev > 0 or prob_ml > 0.60:
                print(f"{nome:20} | Prob: {prob_ml*100:5.1f}% | Q: {quota_book:5.2f} | EV: {ev*100:+6.2f}% | Kelly: {kelly*100:4.2f}% | {value_class}")

        # Trova BEST VALUE BET (migliore EV con prob > 50%)
        best_value = max([b for b in value_bets if b['prob_ml'] > 0.50], key=lambda x: x['ev'])

        print(f"\n🎯 BEST VALUE BET:")
        print(f"   {best_value['mercato']:20} → Prob: {best_value['prob_ml']*100:.1f}% | Q: {best_value['quota']:.2f}")
        print(f"   EV: {best_value['ev']*100:+.2f}% | Kelly Size: {best_value['kelly']*100:.2f}% | {best_value['value_class']}")

        all_bets.extend(value_bets)

    except Exception as e:
        print(f"❌ ERRORE: {e}")
        import traceback
        traceback.print_exc()
        continue

db.close()

# ========================================
# SCHEDINA OTTIMIZZATA CON VALUE BETTING
# ========================================
if len(all_bets) > 0:
    print("\n\n" + "=" * 100)
    print("💎 SCHEDINA OTTIMIZZATA - VALUE BETTING + ML")
    print("=" * 100)

    # Filtra solo value bets (EV > 0) con prob > 50%
    value_picks = [b for b in all_bets if b['ev'] > 0 and b['prob_ml'] > 0.50]

    # Ordina per EV decrescente
    value_picks_sorted = sorted(value_picks, key=lambda x: x['ev'], reverse=True)

    print(f"\n🔍 Trovati {len(value_picks_sorted)} value bets (EV > 0%, Prob > 50%)")

    # STRATEGIA 1: TOP 5 VALUE BETS
    top5_value = value_picks_sorted[:5]

    if len(top5_value) >= 3:
        print(f"\n\n💎 SCHEDINA TOP 5 VALUE BETS (MIGLIORE EV)")
        print(f"{'─'*100}\n")
    
        prob_tot = 1.0
        quota_tot = 1.0
        kelly_tot = 0.0

        for i, bet in enumerate(top5_value, 1):
            prob_tot *= bet['prob_ml']
            quota_tot *= bet['quota']
            kelly_tot += bet['kelly']

            print(f"{i}. {bet['partita']}")
            print(f"   ⏰ {bet['ora']}")
            print(f"   💎 {bet['mercato']:20} → {bet['prob_ml']*100:.1f}% | Q {bet['quota']:.2f}")
            print(f"   📊 EV: {bet['ev']*100:+.2f}% | Kelly: {bet['kelly']*100:.2f}% | {bet['value_class']}")
            # New fields display (if available in bet dict, populated later)
            # For now just showing the standard output
            print("")

        print(f"{'─'*100}")
        print(f"📊 PROBABILITÀ COMBINATA: {prob_tot*100:.2f}%")
        print(f"💰 QUOTA TOTALE: ~{quota_tot:.2f}")
        print(f"💎 EXPECTED VALUE: {((quota_tot * prob_tot) - 1)*100:+.2f}%")
        print(f"💵 KELLY SIZE TOTALE: {kelly_tot*100:.2f}% del bankroll")
        print(f"\n💡 CONSIGLIO: Punta {kelly_tot*100:.1f}% del tuo bankroll")
        print(f"   Es: Con 1000€ → {kelly_tot*1000:.2f}€")
        print(f"       Con 500€ → {kelly_tot*500:.2f}€")
        print(f"{'─'*100}")

    # STRATEGIA 2: SOLO DC 1X/X2/12 CON ALTA PROBABILITÀ (come prima)
    dc_picks = [b for b in all_bets if b['categoria'] == 'DC' and 'DC' in b['mercato'] and b['prob_ml'] > 0.70]
    dc_sorted = sorted(dc_picks, key=lambda x: x['prob_ml'], reverse=True)

    if len(dc_sorted) >= 3:
        print(f"\n\n⭐ SCHEDINA SICURA (DOPPIA CHANCE >70%)")
        print(f"{'─'*100}\n")

        top5_dc = dc_sorted[:5]
        prob_tot_dc = 1.0
        quota_tot_dc = 1.0

        for i, bet in enumerate(top5_dc, 1):
            prob_tot_dc *= bet['prob_ml']
            quota_tot_dc *= bet['quota']

            icon = "🔥" if bet['prob_ml'] >= 0.80 else "⭐"

            print(f"{i}. {bet['partita']}")
            print(f"   ⏰ {bet['ora']}")
            print(f"   {icon} {bet['mercato']} → {bet['prob_ml']*100:.1f}% | Q {bet['quota']:.2f}")
            print(f"   💎 EV: {bet['ev']*100:+.2f}% | {bet['value_class']}\n")

        print(f"{'─'*100}")
        print(f"📊 PROBABILITÀ COMBINATA: {prob_tot_dc*100:.2f}%")
        print(f"💰 QUOTA TOTALE: ~{quota_tot_dc:.2f}")
        print(f"💎 EXPECTED VALUE: {((quota_tot_dc * prob_tot_dc) - 1)*100:+.2f}%")
        print(f"{'─'*100}")

    # STRATEGIA 3: NUOVI MERCATI (COMBO & MULTIGOL) - Se disponibili
    # Nota: questo analyzer lavora "live" calcolando EV su 1X2. 
    # Per integrare i nuovi mercati (Combo/Multigol) dovremmo estendere la logica di calcolo EV anche per loro
    # Se le quote non sono disponibili, mostriamo solo le probabilità alte.
    
    print(f"\n\n🚀 NUOVE STRATEGIE SPERIMENTALI (COMBO & MULTIGOL)")
    print(f"{'─'*100}")
    print("Nota: Queste scommesse si basano su Consensus Score & Poisson puro.")
    
    # Placeholder per future integrazioni complete. Al momento l'analyzer si concentra su 1X2 Value.
    print("Per vedere le previsioni su Multigol, Combo e BTTS, esegui:")
    print("  python predictions_generator.py --date 2026-01-21")
    print(f"{'─'*100}")

print("\n" + "=" * 100)
print("✅ ANALISI VALUE BETTING COMPLETATA!")
print("=" * 100)
print(f"""
⚠️  NOTE IMPORTANTI:

1. 🎯 Questo sistema MANTIENE la qualità del precedente (77.8% accuracy)
   - Stessi modelli ML (47.88% 1X2, 56.66% O/U)
   - AGGIUNGE layer di ottimizzazione con Value Betting

2. 💎 Expected Value (EV):
   - EV > 0% = bookmaker sottostima (value bet)
   - EV > 5% = good value
   - EV > 10% = strong value
   - EV > 15% = excellent value

3. 💰 Kelly Criterion:
   - Indica % ottimale del bankroll da puntare
   - Usa Kelly Frazionario (25%) per ridurre rischio
   - Max 5% del bankroll per singolo bet

4. 📊 DUE STRATEGIE:
   - TOP 5 VALUE: Massimizza EV (più rischio, più rendimento)
   - DC SICURA: Alta probabilità (strategia originale 77.8%)

5. ⚠️ RACCOMANDAZIONI:
   - Se hai quote REALI dal bookmaker → usa TOP 5 VALUE
   - Se usi quote stimate → preferisci DC SICURA
   - SEMPRE rispetta il Kelly Size suggerito
""")

print("\n" + "=" * 100)
print("🎯 BUONA FORTUNA!")
print("=" * 100)
