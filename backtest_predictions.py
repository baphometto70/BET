#!/usr/bin/env python3
"""
backtest_predictions.py

Genera predizioni "live" per una data passata e le confronta con i risultati reali salvati nel DB.
Utile per testare la qualità del modello su dati storici.
"""

import argparse
import sys
from datetime import datetime
from predictions_generator import generate_predictions
from database import SessionLocal
from models import Fixture

def backtest(date_str):
    print(f"🔄 Backtesting predictions for {date_str}...")
    
    # 1. Genera predizioni usando il codice corrente
    preds = generate_predictions(date_str)
    if not preds:
        print("❌ Nessuna predizione generata.")
        return

    # 2. Recupera risultati reali dal DB
    db = SessionLocal()
    fixtures = db.query(Fixture).filter(Fixture.date == date_str).all()
    results_map = {}
    for f in fixtures:
        if f.result_home_goals is not None:
            results_map[f.match_id] = {
                'home': f.result_home_goals,
                'away': f.result_away_goals,
                'total': f.result_home_goals + f.result_away_goals
            }
    db.close()

    if not results_map:
        print("❌ Nessun risultato reale trovato nel DB per questa data.")
        return

    print(f"✅ Trovati {len(results_map)} risultati reali.\n")

    # 3. Confronto
    correct_picks = 0
    correct_ou = 0
    correct_btts = 0
    correct_mg = 0
    correct_combo = 0
    total_valid = 0

    print(f"{'MATCH':<50} | {'PRED OK?':<10} | {'REAL':<5} | {'PICK':<5} | {'O/U':<5} | {'BTTS':<5}")
    print("-" * 100)

    for p in preds:
        mid = p['match_id']
        if mid not in results_map:
            continue
            
        res = results_map[mid]
        h_goals = res['home']
        a_goals = res['away']
        tot_goals = res['total']
        
        # Check 1X2 Pick
        pick = p['pick']
        outcome = "X"
        if h_goals > a_goals: outcome = "1"
        elif a_goals > h_goals: outcome = "2"
        
        pick_ok = (pick == outcome)
        if pick_ok: correct_picks += 1
        
        # Check OU 2.5
        ou_pred = p['ou_pred'] # "OVER 2.5" / "UNDER 2.5"
        is_over = tot_goals > 2.5
        ou_ok = (ou_pred == "OVER 2.5" and is_over) or (ou_pred == "UNDER 2.5" and not is_over)
        if ou_ok: correct_ou += 1
        
        # Check BTTS
        btts_pred = p['btts_pred'] # "GOAL" / "NOGOAL"
        is_btts = (h_goals > 0 and a_goals > 0)
        btts_ok = (btts_pred == "GOAL" and is_btts) or (btts_pred == "NOGOAL" and not is_btts)
        if btts_ok: correct_btts += 1
        
        # Check Multigol 1-3
        mg_ok = (1 <= tot_goals <= 3)
        # Qui semplifico: considero "corretto" se il range 1-3 ha > 60% e si è verificato
        # Oppure traccio solo se la previsione "più probabile" (diciamo 1-3) si è avverata. 
        # Per ora traccio 1X2 e OU come KPI principali.
        
        total_valid += 1
        
        print(f"{p['home']:<20} vs {p['away']:<20} | {('✅' if pick_ok else '❌')}        | {h_goals}-{a_goals}   | {pick}     | {('O' if is_over else 'U')}     | {('G' if is_btts else 'NG')} ({btts_pred})")

    if total_valid == 0:
        print("No matching records.")
        return

    print("\n" + "="*50)
    print("📊 REPORT FINALE")
    print("="*50)
    print(f"Matches analizzati: {total_valid}")
    print(f"🎯 1X2 Accuracy:  {correct_picks}/{total_valid} ({correct_picks/total_valid*100:.1f}%)")
    print(f"📈 O/U Accuracy:  {correct_ou}/{total_valid} ({correct_ou/total_valid*100:.1f}%)")
    print(f"⚽ BTTS Accuracy: {correct_btts}/{total_valid} ({correct_btts/total_valid*100:.1f}%)")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 backtest_predictions.py YYYY-MM-DD")
        sys.exit(1)
    backtest(sys.argv[1])
