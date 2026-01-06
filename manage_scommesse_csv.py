#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestore CSV per progetto Scommesse.
Funzioni:
- Menu interattivo (backup/svuota/aggiungi/demo/anteprima + fetch guidato)
- Modalità non-interattiva:
    --clear                       (svuota CSV)
    --demo                        (riempie esempi)
    --fetch DATE --comps "SA,PL"  (scarica partite del giorno per competizioni)

Fonte dati partite: football-data.org (gratuito).

API KEY:
- Usa l'env FOOTBALL_DATA_API_KEY se presente,
- altrimenti usa il token predefinito (inserito su richiesta dell'utente).

ATTENZIONE: il tier gratuito NON fornisce quote. Le colonne quote restano vuote.
"""

import argparse, sys, os, shutil
from datetime import datetime
import pandas as pd

try:
    import requests
except ImportError:
    requests = None

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
    "xg_for_home","xg_against_home","xg_for_away","xg_against_away",
    "rest_days_home","rest_days_away",
    "injuries_key_home","injuries_key_away",
    "derby_flag","europe_flag_home","europe_flag_away",
    "meteo_flag","style_ppda_home","style_ppda_away","travel_km_away"
]

# Mappa competizioni + legenda stampabile
COMP_MAP = {
    "WC":  "FIFA World Cup",
    "CL":  "UEFA Champions League",
    "BL1": "Bundesliga",
    "DED": "Eredivisie",
    "BSA": "Campeonato Brasileiro Série A",
    "PD":  "Primera Division",
    "FL1": "Ligue 1",
    "ELC": "Championship (ENG)",
    "PPL": "Primeira Liga",
    "EC":  "European Championship",
    "SA":  "Serie A",
    "PL":  "Premier League",
}

LEGEND = "\n".join([f"  {k:<4} = {v}" for k,v in COMP_MAP.items()])

# Token API: env override, else fallback predefinito (richiesta dell'utente)
DEFAULT_API_TOKEN = "9f48528ff8d5482f8851ae808eaa9f13"

def ensure_csv(path, cols):
    if not os.path.exists(path):
        pd.DataFrame(columns=cols).to_csv(path, index=False)
        return
    try:
        df = pd.read_csv(path)
        missing = [c for c in cols if c not in df.columns]
        if missing or len(df.columns)!=len(cols):
            pd.DataFrame(columns=cols).to_csv(path, index=False)
    except Exception:
        pd.DataFrame(columns=cols).to_csv(path, index=False)

def backup(path):
    if not os.path.exists(path):
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = f"{path}.bak_{ts}"
    shutil.copy2(path, dest)
    return dest

def clear_csv(path, cols):
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

    match_id = f"{date.replace('-','')}_{home.upper().replace(' ','_')}_{away.upper().replace(' ','_')}_{league.replace(' ','_').upper()}"
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
        "xg_for_home": g("xg_for_home"),
        "xg_against_home": g("xg_against_home"),
        "xg_for_away": g("xg_for_away"),
        "xg_against_away": g("xg_against_away"),
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

def resolve_api_token():
    tok = os.getenv("FOOTBALL_DATA_API_KEY")
    if tok and tok.strip():
        return tok.strip()
    return DEFAULT_API_TOKEN

def fetch_from_api(date_str, comp_codes):
    if requests is None:
        raise RuntimeError("Richiede 'requests'. Installa: pip install requests python-dotenv")
    token = resolve_api_token()
    url = "https://api.football-data.org/v4/matches"
    params = {"date": date_str}
    if comp_codes:
        params["competitions"] = ",".join(comp_codes)
    headers = {"X-Auth-Token": token}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"API error {r.status_code}: {r.text}")
    data = r.json()
    matches = data.get("matches", [])
    rows_fix, rows_fea = [], []
    for m in matches:
        comp_code = (m.get("competition", {}) or {}).get("code") or ""
        comp_name = COMP_MAP.get(comp_code, (m.get("competition", {}) or {}).get("name", comp_code))
        utc_dt = m.get("utcDate") or ""
        time_local = utc_dt[11:16] if isinstance(utc_dt, str) and len(utc_dt)>=16 else ""
        home = ((m.get("homeTeam", {}) or {}).get("name","") or "").strip()
        away = ((m.get("awayTeam", {}) or {}).get("name","") or "").strip()
        lid = comp_name.upper().replace(" ", "_")
        mid = f"{date_str.replace('-','')}_{home.upper().replace(' ','_')}_{away.upper().replace(' ','_')}_{lid}"
        rows_fix.append({
            "match_id": mid,"league": comp_name,"date": date_str,"time_local": time_local,
            "home": home,"away": away,"odds_1": "","odds_x": "","odds_2": "","line_ou": "","odds_over": "","odds_under": ""
        })
        rows_fea.append({"match_id": mid,"xg_for_home": "","xg_against_home": "","xg_for_away": "","xg_against_away": "",
                         "rest_days_home": "","rest_days_away": "","injuries_key_home": "","injuries_key_away": "",
                         "derby_flag": "0","europe_flag_home": "0","europe_flag_away": "0","meteo_flag": "0",
                         "style_ppda_home": "","style_ppda_away": "","travel_km_away": ""})
    return rows_fix, rows_fea

def interactive_fetch():
    print("\n== FETCH PARTITE DA API ==")
    print("Legenda competizioni supportate:")
    print(LEGEND)
    date_str = input("Data (YYYY-MM-DD): ").strip()
    comps_in = input("Codici competizioni separati da virgola (es. SA,PL,CL): ").strip()
    comps = [c.strip().upper() for c in comps_in.split(",") if c.strip()]
    try:
        rows_fix, rows_fea = fetch_from_api(date_str, comps)
    except Exception as e:
        print(f"[ERRORE] {e}")
        return
    backup(FIX); backup(FEA)
    pd.DataFrame(rows_fix, columns=FIX_COLS).to_csv(FIX, index=False)
    pd.DataFrame(rows_fea, columns=FEA_COLS).to_csv(FEA, index=False)
    print(f"[OK] Scritti {len(rows_fix)} match in fixtures.csv e features.csv per {date_str} ({', '.join(comps)})")

def menu():
    ensure_csv(FIX, FIX_COLS)
    ensure_csv(FEA, FEA_COLS)
    import pandas as pd
    while True:
        print("\n=== Gestore CSV Scommesse ===")
        print("Legenda competizioni:")
        print(LEGEND)
        print("\n1) Backup dei CSV")
        print("2) Svuota fixtures.csv")
        print("3) Svuota features.csv")
        print("4) Aggiungi righe a fixtures.csv")
        print("5) Aggiungi righe a features.csv")
        print("6) Popola esempi demo (2 match)")
        print("7) Mostra prime righe")
        print("8) FETCH da API per data + competizioni")
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
            print(pd.read_csv(FIX).head(50).to_string(index=False))
            print("\n--- features.csv ---")
            print(pd.read_csv(FEA).head(50).to_string(index=False))
        elif choice == "8":
            interactive_fetch()
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
            "xg_for_home": "1.85","xg_against_home": "0.90",
            "xg_for_away": "1.05","xg_against_away": "1.55",
            "rest_days_home": "6","rest_days_away": "6",
            "injuries_key_home": "0","injuries_key_away": "1",
            "derby_flag": "0","europe_flag_home": "1","europe_flag_away": "0",
            "meteo_flag": "0","style_ppda_home": "8.5","style_ppda_away": "12.0",
            "travel_km_away": "780"
        },
        {
            "match_id": f"{today.replace('-','')}_CREMONESE_JUVENTUS_SERIE_A",
            "xg_for_home": "0.92","xg_against_home": "1.30",
            "xg_for_away": "1.60","xg_against_away": "0.85",
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

def do_fetch(date_str, comps):
    ensure_csv(FIX, FIX_COLS)
    ensure_csv(FEA, FEA_COLS)
    rows_fix, rows_fea = fetch_from_api(date_str, comps)
    backup(FIX); backup(FEA)
    pd.DataFrame(rows_fix, columns=FIX_COLS).to_csv(FIX, index=False)
    pd.DataFrame(rows_fea, columns=FEA_COLS).to_csv(FEA, index=False)
    print(f"[OK] Fetched {len(rows_fix)} partite per {date_str} ({', '.join(comps) if comps else 'tutte'})")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clear", action="store_true", help="Svuota entrambi i CSV mantenendo le intestazioni")
    parser.add_argument("--demo", action="store_true", help="Popola i CSV con esempi dimostrativi (2 match)")
    parser.add_argument("--fetch", type=str, help="Data (YYYY-MM-DD) da scaricare")
    parser.add_argument("--comps", type=str, help="Codici competizioni separati da virgola (es. 'SA,PL,CL,EL')")
    args = parser.parse_args()

    ensure_csv(FIX, FIX_COLS)
    ensure_csv(FEA, FEA_COLS)

    if args.clear and (args.demo or args.fetch):
        print("Usa un'operazione alla volta: --clear oppure --demo oppure --fetch."); sys.exit(1)

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

    if args.fetch:
        if requests is None:
            print("Questo comando richiede 'requests'. Installa: pip install requests python-dotenv")
            sys.exit(1)
        comps = []
        if args.comps:
            comps = [c.strip().upper() for c in args.comps.split(",") if c.strip()]
        do_fetch(args.fetch, comps)
        sys.exit(0)

    # Menu interattivo
    menu()

if __name__ == "__main__":
    main()
