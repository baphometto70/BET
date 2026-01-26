import sys
import argparse
from datetime import datetime, date
from pathlib import Path
import requests
from database import SessionLocal
from models import Fixture
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parent

# Leggi token da config
try:
    import tomllib
except ImportError:
    import tomli as tomllib

CFG_PATH = ROOT / "config.toml"
cfg = tomllib.loads(CFG_PATH.read_text(encoding="utf-8"))
TOKEN = cfg.get("api", {}).get("FOOTBALL_DATA_ORG_TOKEN")

if not TOKEN:
    print("[ERROR] Token football-data.org non trovato in config.toml")
    sys.exit(1)


# football-data.org competition IDs (v4)
COMP_MAP = {
    "SA": "2019",
    "PL": "2021",
    "PD": "2014",
    "BL1": "2002",
    "FL1": "2015",
    "DED": "2003",
    "PPL": "2017",
    "ELC": "2016",
    "BSA": "2013",
    "CL": "2001",
    "EL": "2146",
}

def fetch_and_store_results(target_date: str):
    """
    Scarica risultati per una data specifica iterando per competizione.
    """
    db = SessionLocal()
    headers = {"X-Auth-Token": TOKEN}
    
    try:
        print(f"[INFO] Fetching results for {target_date}...")
        
        # Carica i fixture del nostro DB per quella data
        db_fixtures = db.query(Fixture).filter(Fixture.date == datetime.fromisoformat(target_date).date()).all()
        print(f"[INFO] Trovati {len(db_fixtures)} match nel DB locale per {target_date}.")
        
        updated_count = 0
        
        for code, comp_id in COMP_MAP.items():
            url = f"https://api.football-data.org/v4/competitions/{comp_id}/matches?dateFrom={target_date}&dateTo={target_date}"
            
            try:
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code == 403: # Free tier limit or restricted comp
                    continue
                r.raise_for_status()
            except Exception as e:
                # print(f"  [WARN] Failed to fetch {code}: {e}")
                continue

            matches_data = r.json().get("matches", [])
            
            if not matches_data:
                continue

            for api_match in matches_data:
                home_api = api_match['homeTeam']['name']
                away_api = api_match['awayTeam']['name']
                
                score = api_match.get("score", {}).get("fullTime", {})
                h_goals = score.get("home")
                a_goals = score.get("away")
                status = api_match.get("status")
                
                # Accetta anche match non ufficialmente "FINISHED" se hanno score
                if h_goals is None or a_goals is None:
                    continue

                # Matching con il DB
                found_fix = None
                best_score = 0
                
                for f in db_fixtures:
                    if f.result_home_goals is not None: 
                        continue # Già aggiornato

                    s1 = fuzz.ratio(home_api.lower(), f.home.lower())
                    s2 = fuzz.ratio(away_api.lower(), f.away.lower())
                    avg_score = (s1 + s2) / 2
                    
                    if avg_score > 80 and avg_score > best_score:
                        best_score = avg_score
                        found_fix = f
                
                if found_fix:
                    found_fix.result_home_goals = h_goals
                    found_fix.result_away_goals = a_goals
                    # Salviamo anche lo status se volessimo, ma per ora basta il risultato
                    db.merge(found_fix)
                    updated_count += 1
                    print(f"  ✓ [{code}] {found_fix.home} {h_goals}-{a_goals} {found_fix.away}")
        
        db.commit()
        print(f"\n[DONE] {updated_count} risultati aggiornati nel DB.")
    
    except Exception as e:
        print(f"[ERROR] {e}")
        db.rollback()
    
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=str, required=True, help='YYYY-MM-DD')
    args = parser.parse_args()
    
    fetch_and_store_results(args.date)
