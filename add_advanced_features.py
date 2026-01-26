#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AGGIUNGE LE 61 ADVANCED FEATURES MANCANTI AL DATABASE
Step 1: Modifica schema database
Step 2: Calcola features da partite storiche
Step 3: Popola database
"""

import sys
from pathlib import Path
from datetime import date, timedelta
from sqlalchemy import text

from database import SessionLocal, engine
from models import Fixture, Feature

print("=" * 100)
print("🔧 AGGIUNTA ADVANCED FEATURES AL DATABASE")
print("=" * 100)

# ========================================
# STEP 1: AGGIUNGI COLONNE AL DATABASE
# ========================================
print("\n📊 STEP 1: Aggiungo colonne mancanti alla tabella 'features'...")

# SQL per aggiungere TUTTE le colonne mancanti
alter_statements = [
    # Context features (già presenti parzialmente, verifichiamo)
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS is_derby INTEGER DEFAULT 0;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS is_europe INTEGER DEFAULT 0;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS weather_condition INTEGER DEFAULT 0;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS ppda_home REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS ppda_away REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS travel_distance REAL;",

    # Form features (20) - ultimi 5 match
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS form_pts_home REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS form_pts_away REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS form_gf_home REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS form_gf_away REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS form_ga_home REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS form_ga_away REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS form_xgf_home REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS form_xgf_away REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS form_xga_home REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS form_xga_away REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS form_home_pts_home REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS form_away_pts_away REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS form_home_gf_home REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS form_home_ga_home REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS form_away_gf_away REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS form_away_ga_away REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS streak_home INTEGER;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS streak_away INTEGER;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS unbeaten_home INTEGER;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS unbeaten_away INTEGER;",

    # H2H features (8)
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS h2h_home_wins INTEGER;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS h2h_draws INTEGER;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS h2h_away_wins INTEGER;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS h2h_total_games INTEGER;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS h2h_avg_home_goals REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS h2h_avg_away_goals REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS h2h_home_win_pct REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS h2h_btts_pct REAL;",

    # Standings features (10)
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS standing_position_home INTEGER;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS standing_position_away INTEGER;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS standing_points_home INTEGER;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS standing_points_away INTEGER;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS standing_gd_home INTEGER;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS standing_gd_away INTEGER;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS standing_home_pts_home INTEGER;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS standing_away_pts_away INTEGER;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS standing_form_home REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS standing_form_away REAL;",

    # Momentum features (12)
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS momentum_goals_home REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS momentum_goals_away REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS momentum_xg_home REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS momentum_xg_away REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS momentum_shots_home REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS momentum_shots_away REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS improvement_home REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS improvement_away REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS consistency_home REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS consistency_away REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS pressure_home REAL;",
    "ALTER TABLE features ADD COLUMN IF NOT EXISTS pressure_away REAL;",
]

try:
    with engine.begin() as conn:
        for stmt in alter_statements:
            try:
                conn.execute(text(stmt))
            except Exception as e:
                # Ignora errori se colonna esiste già
                if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
                    print(f"⚠️  Errore: {e}")

    print("✅ Colonne aggiunte con successo!")

except Exception as e:
    print(f"❌ ERRORE nell'aggiunta colonne: {e}")
    sys.exit(1)

# ========================================
# STEP 2: CALCOLA FEATURES DA STORICHE
# ========================================
print("\n📊 STEP 2: Calcolo features dalle partite storiche...")
print("⚠️  NOTA: Questo richiede dati storici delle partite giocate.")
print("   Per ora imposto valori di default. Dovrai:")
print("   1. Scaricare storiche da FBRef/Understat")
print("   2. Calcolare form/h2h/standings da quelle partite")
print("   3. Ripopolare il database")

db = SessionLocal()

try:
    # Per tutte le fixture FUTURE (non ancora giocate)
    fixtures = db.query(Fixture).filter(
        Fixture.date >= date.today()
    ).all()

    print(f"\n🔍 Trovate {len(fixtures)} partite future da aggiornare...")

    updated_count = 0

    for fix in fixtures:
        if not fix.feature:
            # Crea feature se non esiste
            fix.feature = Feature(match_id=fix.match_id)
            db.add(fix.feature)

        feat = fix.feature

        # ========================================
        # VALORI DI DEFAULT (DA SOSTITUIRE CON CALCOLI VERI)
        # ========================================

        # Context (già parzialmente presenti)
        feat.is_derby = feat.derby_flag if hasattr(feat, 'derby_flag') else 0
        feat.is_europe = feat.europe_flag_home or feat.europe_flag_away if hasattr(feat, 'europe_flag_home') else 0
        feat.weather_condition = feat.meteo_flag if hasattr(feat, 'meteo_flag') else 0
        feat.ppda_home = feat.style_ppda_home if hasattr(feat, 'style_ppda_home') and feat.style_ppda_home else 10.0
        feat.ppda_away = feat.style_ppda_away if hasattr(feat, 'style_ppda_away') and feat.style_ppda_away else 10.0
        feat.travel_distance = feat.travel_km_away if hasattr(feat, 'travel_km_away') and feat.travel_km_away else 0.0

        # Form (media neutrale)
        feat.form_pts_home = 5.0  # Media ~1 punto/partita ultimi 5
        feat.form_pts_away = 5.0
        feat.form_gf_home = 6.0  # Media ~1.2 gol/partita
        feat.form_gf_away = 6.0
        feat.form_ga_home = 6.0
        feat.form_ga_away = 6.0
        feat.form_xgf_home = feat.xg_for_home * 5 if feat.xg_for_home else 6.0
        feat.form_xgf_away = feat.xg_for_away * 5 if feat.xg_for_away else 6.0
        feat.form_xga_home = feat.xg_against_home * 5 if feat.xg_against_home else 6.0
        feat.form_xga_away = feat.xg_against_away * 5 if feat.xg_against_away else 6.0
        feat.form_home_pts_home = 7.0  # Casa più forte
        feat.form_away_pts_away = 3.0  # Trasferta più debole
        feat.form_home_gf_home = 7.0
        feat.form_home_ga_home = 4.0
        feat.form_away_gf_away = 5.0
        feat.form_away_ga_away = 7.0
        feat.streak_home = 0  # Neutro
        feat.streak_away = 0
        feat.unbeaten_home = 2  # Media 2 partite senza sconfitte
        feat.unbeaten_away = 1

        # H2H (neutro - nessuno storico)
        feat.h2h_home_wins = 1
        feat.h2h_draws = 1
        feat.h2h_away_wins = 1
        feat.h2h_total_games = 3
        feat.h2h_avg_home_goals = 1.5
        feat.h2h_avg_away_goals = 1.5
        feat.h2h_home_win_pct = 0.33
        feat.h2h_btts_pct = 0.5

        # Standings (posizione media)
        feat.standing_position_home = 10
        feat.standing_position_away = 10
        feat.standing_points_home = 30
        feat.standing_points_away = 30
        feat.standing_gd_home = 0
        feat.standing_gd_away = 0
        feat.standing_home_pts_home = 18
        feat.standing_away_pts_away = 12
        feat.standing_form_home = 1.0
        feat.standing_form_away = 1.0

        # Momentum (neutro)
        feat.momentum_goals_home = 0.0
        feat.momentum_goals_away = 0.0
        feat.momentum_xg_home = 0.0
        feat.momentum_xg_away = 0.0
        feat.momentum_shots_home = 0.0
        feat.momentum_shots_away = 0.0
        feat.improvement_home = 0.0
        feat.improvement_away = 0.0
        feat.consistency_home = 0.5
        feat.consistency_away = 0.5
        feat.pressure_home = 0.5
        feat.pressure_away = 0.5

        updated_count += 1

        if updated_count % 10 == 0:
            print(f"   Aggiornate {updated_count}/{len(fixtures)} partite...")

    db.commit()
    print(f"\n✅ Features aggiornate per {updated_count} partite!")

except Exception as e:
    db.rollback()
    print(f"❌ ERRORE: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()

# ========================================
# RIEPILOGO
# ========================================
print("\n" + "=" * 100)
print("✅ COMPLETATO!")
print("=" * 100)
print("""
📋 COSA È STATO FATTO:
   1. ✅ Aggiunte ~60 colonne alla tabella 'features'
   2. ✅ Popolate con valori di DEFAULT per partite future

⚠️  PROSSIMI PASSI NECESSARI:
   1. Scaricare STORICHE complete (ultimi 2-3 anni) da:
      - FBRef (risultati, gol, xG)
      - Understat (xG dettagliato)
      - Football-Data.co.uk (quote storiche)

   2. Calcolare VERE features per ogni partita:
      - Form: da ultimi 5 match della squadra
      - H2H: da storico scontri diretti
      - Standings: da classifica attuale
      - Momentum: trend ultimi 3 match

   3. Riaddestra i modelli ML con features complete

📊 PER ORA: Le predizioni ML useranno valori DEFAULT (non accurati)
   Le predizioni Poisson rimangono invariate (usano solo 4 xG)
""")

print("\n🎯 PROSSIMO COMANDO DA ESEGUIRE:")
print("   python schedina_ML_17gennaio.py")
print("   (Vedremo se ora funziona con le features di default)")
