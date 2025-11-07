#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestore CSV per progetto Scommesse.
Funzioni:
- Backup, svuota e ripopola `fixtures.csv` e `features.csv` con menu interattivo.
- Modalità non-interattiva: --clear, --demo per popolare esempi.

Esecuzione:
  python manage_scommesse_csv.py            # menu
  python manage_scommesse_csv.py --clear    # svuota entrambi mantenendo intestazioni
  python manage_scommesse_csv.py --demo     # riempie con righe di esempio
"""

import argparse, sys, os, shutil
from datetime import datetime
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(ROOT, "fixtures.csv")
FEA = os.path.join(ROOT, "features.csv")

FIX_COLS = [
    "match_id","league","date","time_local","home","away",
    "odds_1","odds_x","odds_2",
    "line_ou","odds_over","odds_under"
]
FEA_COLS = [
    "match_id",
    "xG_for_5_home","xG_against_5_home","xG_for_5_away","xG_against_5_away",
    "rest_days_home","rest_days_away",
    "injuries_key_home","injuries_key_away",
    "derby_flag","europe_flag_home","europe_flag_away",
    "meteo_flag","style_ppda_home","style_ppda_away","travel_km_away"
]

def ensure_csv(path, cols):
    import pandas as pd
    if not os.path.exists(path):
        pd.DataFrame(columns=cols).to_csv(path, index=False)
        return
    # validate columns
    df = pd.read_csv(path)
    missing = [c for c in cols if c not in df.columns]
    if missing or len(df.columns)!=len(cols):
        pd.DataFrame(columns=cols).to_csv(path, index=False)

def backup(path):
    if not os.path.exists(path):
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = f"{path}.bak_{ts}"
    shutil.copy2(path, dest)
    return dest

def clear_csv(path, cols):
    import pandas as pd
    pd.DataFrame(columns=cols).to_csv(path, index=False)

def append_fixture_row():
    print("\nAggiungi riga fixtures.csv (invio per default/skip campo opzionale)")
    date = input("Data (YYYY-MM-DD): ").strip()
    time_local = input("Ora locale (HH:MM): ").strip()
    league = input("Lega (es. Serie A): ").strip()
    home = input("Home team: ").strip()
    away = input("Away team: ").strip()
    odds_1 = input("Quota 1: ").strip()
    odds_x = input("Quota X: ").strip()
    odds_2 = input("Quota 2: ").strip()
    line_ou = input("Linea O/U (es. 2.5 o 3.0): ").strip()
    odds_over = input("Quota Over: ").strip()
    odds_under = input("Quota Under: ").strip()

    match_id = f"{date.replace('-','')}_{home.upper().replace(' ','_')}_{away.upper().replace(' ','_')}_{league.replace(' ','_')}"
    row = {
        "match_id": match_id,
        "league": league,
        "date": date,
        "time_local": time_local,
        "home": home,
        "away": away,
        "odds_1": odds_1 or "",
        "odds_x": odds_x or "",
        "odds_2": odds_2 or "",
        "line_ou": line_ou or "",
        "odds_over": odds_over or "",
        "odds_under": odds_under or ""
    }
    return row

def append_feature_row(match_id=None):
    print("\nAggiungi riga features.csv (invio per default vuoto)")
    if not match_id:
        match_id = input("match_id (identico a fixtures): ").strip()
    def g(name):
        return input(f"{name}: ").strip()
    row = {
        "match_id": match_id,
        "xG_for_5_home": g("xG_for_5_home"),
        "xG_against_5_home": g("xG_against_5_home"),
        "xG_for_5_away": g("xG_for_5_away"),
        "xG_against_5_away": g("xG_against_5_away"),
        "rest_days_home": g("rest_days_home"),
        "rest_days_away": g("rest_days_away"),
        "injuries_key_home": g("injuries_key_home"),
        "injuries_key_away": g("injuries_key_away"),
        "derby_flag": g("derby_flag (0/1)"),
        "europe_flag_home": g("europe_flag_home (0/1)"),
        "europe_flag_away": g("europe_flag_away (0/1)"),
        "meteo_flag": g("meteo_flag (0/1)"),
        "style_ppda_home": g("style_ppda_home"),
        "style_ppda_away": g("style_ppda_away"),
        "travel_km_away": g("travel_km_away")
    }
    return row

def menu():
    ensure_csv(FIX, FIX_COLS)
    ensure_csv(FEA, FEA_COLS)
    import pandas as pd
    while True:
        print("\n=== Gestore CSV Scommesse ===")
        print("1) Backup dei CSV")
        print("2) Svuota fixtures.csv")
        print("3) Svuota features.csv")
        print("4) Aggiungi righe a fixtures.csv")
        print("5) Aggiungi righe a features.csv")
        print("6) Popola esempi demo (2 match)")
        print("7) Mostra prime righe")
        print("0) Esci")
        choice = input("Selezione: ").strip()
        if choice == "1":
            b1 = backup(FIX); b2 = backup(FEA)
            print(f"Backup fixtures: {b1}\nBackup features: {b2}")
        elif choice == "2":
            clear_csv(FIX, FIX_COLS); print("fixtures.csv svuotato.")
        elif choice == "3":
            clear_csv(FEA, FEA_COLS); print("features.csv svuotato.")
        elif choice == "4":
            df = pd.read_csv(FIX)
            while True:
                row = append_fixture_row()
                df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
                if input("Aggiungere un'altra riga? (y/N): ").strip().lower() != "y":
                    break
            df.to_csv(FIX, index=False); print("fixtures.csv aggiornato.")
        elif choice == "5":
            df = pd.read_csv(FEA)
            while True:
                rid = input("Hai un match_id da usare? (invio per inserirlo nel prossimo campo) ").strip()
                rid = rid or None
                row = append_feature_row(rid)
                df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
                if input("Aggiungere un'altra riga? (y/N): ").strip().lower() != "y":
                    break
            df.to_csv(FEA, index=False); print("features.csv aggiornato.")
        elif choice == "6":
            demo()
        elif choice == "7":
            print("\n--- fixtures.csv ---")
            print(pd.read_csv(FIX).head(10).to_string(index=False))
            print("\n--- features.csv ---")
            print(pd.read_csv(FEA).head(10).to_string(index=False))
        elif choice == "0":
            print("Bye."); break
        else:
            print("Scelta non valida.")

def demo():
    import pandas as pd
    clear_csv(FIX, FIX_COLS)
    clear_csv(FEA, FEA_COLS)
    today = datetime.now().strftime("%Y-%m-%d")
    rows_fix = [
        {
            "match_id": f"{today.replace('-','')}_NAPOLI_COMO_SERIE_A",
            "league": "Serie A",
            "date": today,
            "time_local": "18:00",
            "home": "Napoli",
            "away": "Como",
            "odds_1": "1.55",
            "odds_x": "4.10",
            "odds_2": "6.50",
            "line_ou": "3.0",
            "odds_over": "1.95",
            "odds_under": "1.85"
        },
        {
            "match_id": f"{today.replace('-','')}_CREMONESE_JUVENTUS_SERIE_A",
            "league": "Serie A",
            "date": today,
            "time_local": "20:45",
            "home": "Cremonese",
            "away": "Juventus",
            "odds_1": "5.40",
            "odds_x": "3.60",
            "odds_2": "1.70",
            "line_ou": "3.0",
            "odds_over": "2.02",
            "odds_under": "1.78"
        }
    ]
    rows_fea = [
        {
            "match_id": f"{today.replace('-','')}_NAPOLI_COMO_SERIE_A",
            "xG_for_5_home": "1.85","xG_against_5_home": "0.90",
            "xG_for_5_away": "1.05","xG_against_5_away": "1.55",
            "rest_days_home": "6","rest_days_away": "6",
            "injuries_key_home": "0","injuries_key_away": "1",
            "derby_flag": "0","europe_flag_home": "1","europe_flag_away": "0",
            "meteo_flag": "0","style_ppda_home": "8.5","style_ppda_away": "12.0",
            "travel_km_away": "780"
        },
        {
            "match_id": f"{today.replace('-','')}_CREMONESE_JUVENTUS_SERIE_A",
            "xG_for_5_home": "0.92","xG_against_5_home": "1.30",
            "xG_for_5_away": "1.60","xG_against_5_away": "0.85",
            "rest_days_home": "6","rest_days_away": "6",
            "injuries_key_home": "1","injuries_key_away": "2",
            "derby_flag": "0","europe_flag_home": "0","europe_flag_away": "1",
            "meteo_flag": "0","style_ppda_home": "12.8","style_ppda_away": "9.9",
            "travel_km_away": "160"
        }
    ]
    pd.DataFrame(rows_fix, columns=FIX_COLS).to_csv(FIX, index=False)
    pd.DataFrame(rows_fea, columns=FEA_COLS).to_csv(FEA, index=False)
    print("[DEMO] fixtures.csv e features.csv popolati con 2 esempi.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clear", action="store_true", help="Svuota entrambi i CSV mantenendo le intestazioni")
    parser.add_argument("--demo", action="store_true", help="Popola i CSV con esempi dimostrativi (2 match)")
    args = parser.parse_args()

    ensure_csv(FIX, FIX_COLS)
    ensure_csv(FEA, FEA_COLS)

    if args.clear and args.demo:
        print("Usa --clear oppure --demo, non entrambi."); sys.exit(1)

    if args.clear:
        backup(FIX); backup(FEA)
        clear_csv(FIX, FIX_COLS)
        clear_csv(FEA, FEA_COLS)
        print("Entrambi i CSV sono stati svuotati (backup creati).")
        sys.exit(0)

    if args.demo:
        backup(FIX); backup(FEA)
        demo()
        sys.exit(0)

    # Menu interattivo
    menu()

if __name__ == "__main__":
    main()
