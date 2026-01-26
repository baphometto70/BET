#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_team_mapping.py
---------------------
Scarica nomi di squadre da Understat e FBRef, li mappa ai nomi nel DB (Fixture),
e popola la tabella team_mappings in PostgreSQL.

USO:
  python build_team_mapping.py

Questo script:
1. Estrae tutti i nomi home/away univoci dalla tabella fixtures
2. Scarica i nomi di squadre da Understat (per ogni lega/stagione)
3. Scarica i nomi di squadre da FBRef (per ogni lega/stagione)
4. Fa fuzzy matching tra i nomi DB e quelli dei siti
5. Salva i mapping in team_mappings
6. Logga discrepanze o nomi non trovati
"""

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import quote

import requests
from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session
from unidecode import unidecode

from database import SessionLocal
from models import Fixture, TeamMapping

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "cache" / "team_mappings"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Mapping competizioni → Understat slug
UNDERSTAT_LEAGUE = {
    "SA": "Serie_A",
    "PL": "EPL",
    "PD": "La_Liga",
    "BL1": "Bundesliga",
    "FL1": "Ligue_1",
    "DED": "Eredivisie",
    "PPL": "Primeira_Liga",
    "CL": "Champions_League",
    "EL": "Europa_League",
}

# Mapping competizioni → FBRef comp_id
FBREF_COMP = {
    "SA": {"id": 11, "name": "Serie-A"},
    "PL": {"id": 9, "name": "Premier-League"},
    "PD": {"id": 12, "name": "La-Liga"},
    "BL1": {"id": 20, "name": "Bundesliga"},
    "FL1": {"id": 13, "name": "Ligue-1"},
    "DED": {"id": 23, "name": "Eredivisie"},
    "PPL": {"id": 32, "name": "Primeira-Liga"},
    "CL": {"id": 8, "name": "Champions-League"},
    "EL": {"id": 19, "name": "Europa-League"},
}


def _norm(s: str) -> str:
    """Normalizza un nome di squadra per confronto."""
    s = unidecode((s or "").lower().strip())
    s = re.sub(r"\b(fc|cf|afc|kv|sc|bc|as|cd|ud|rcd|ca)\b", "", s)
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def fetch_understat_teams(league: str, season: str) -> Optional[Dict[str, Tuple[str, str]]]:
    """
    Scarica i nomi di squadre da Understat per una lega/stagione.
    Restituisce dict: {normalized_name: (original_understat_name, understat_id)}
    """
    slug = UNDERSTAT_LEAGUE.get(league)
    if not slug:
        print(f"[WARN] Lega {league} non supportata su Understat")
        return None

    cache_file = CACHE_DIR / f"understat_{league}_{season}.json"
    if cache_file.exists():
        print(f"[CACHE] Carico nomi Understat {league} {season} da cache locale")
        import json
        return json.loads(cache_file.read_text())

    url = f"https://understat.com/league/{slug}/{season}"
    print(f"[UNDERSTAT] Scarico squadre da {url}...")
    
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERR] Fallimento Understat {league}: {e}")
        return None

    # Parsing (regex per estrarre nome e ID da href="/team/TeamName/ID")
    pattern = r'href="/team/([^/]+)/(\d+)"'
    matches = re.findall(pattern, r.text)
    
    if not matches:
        print(f"[WARN] Nessuna squadra trovata per {league} su Understat")
        return None

    result = {_norm(name): (name, team_id) for name, team_id in matches}
    
    # Cache locale
    import json
    cache_file.write_text(json.dumps(result, ensure_ascii=False))
    print(f"[OK] Scaricate {len(result)} squadre Understat {league}")
    return result


def fetch_fbref_teams(league: str, season: str) -> Optional[Dict[str, Tuple[str, str]]]:
    """
    Scarica i nomi di squadre da FBRef.
    Restituisce dict: {normalized_name: (original_fbref_name, fbref_id)}
    """
    comp_info = FBREF_COMP.get(league)
    if not comp_info:
        print(f"[WARN] Lega {league} non supportata su FBRef")
        return None

    comp_id = comp_info["id"]
    comp_name = comp_info["name"]
    cache_file = CACHE_DIR / f"fbref_{league}_{season}.json"
    
    if cache_file.exists():
        print(f"[CACHE] Carico nomi FBRef {league} {season} da cache locale")
        import json
        return json.loads(cache_file.read_text())

    url = f"https://fbref.com/en/comps/{comp_id}/{season}/{comp_name}-Stats"
    print(f"[FBRef] Scarico squadre da {url}...")
    
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERR] Fallimento FBRef {league}: {e}")
        return None

    # Parsing: cerca link squadre con ID esadecimale di 8 caratteri
    pattern = r'href="/en/squads/([a-f0-9]{8})/[^"]*">([^<]+)</a>'
    matches = re.findall(pattern, r.text)
    
    if not matches:
        print(f"[WARN] Nessuna squadra trovata per {league} su FBRef")
        return None

    result = {_norm(name): (name, fbref_id) for fbref_id, name in matches}
    
    # Cache locale
    import json
    cache_file.write_text(json.dumps(result, ensure_ascii=False))
    print(f"[OK] Scaricate {len(result)} squadre FBRef {league}")
    return result


def get_all_teams_from_db(db: Session) -> Dict[str, Set[str]]:
    """
    Estrae tutti i nomi home/away dal DB, raggruppati per lega.
    Restituisce: {league_code: {team_names}}
    """
    fixtures = db.query(Fixture).all()
    teams_by_league = {}
    
    for f in fixtures:
        code = f.league_code
        if code not in teams_by_league:
            teams_by_league[code] = set()
        teams_by_league[code].add(f.home)
        teams_by_league[code].add(f.away)
    
    for code, teams in teams_by_league.items():
        print(f"[DB] Lega {code}: {len(teams)} squadre univoche")
    
    return teams_by_league


def fuzzy_match(
    db_name: str, 
    understat_dict: Optional[Dict[str, Tuple[str, str]]], 
    fbref_dict: Optional[Dict[str, Tuple[str, str]]]
) -> Dict[str, Optional[str]]:
    """
    Fa fuzzy matching tra un nome DB e i dizionari Understat/FBRef.
    Restituisce: {understat_name, fbref_name, fbref_id}
    """
    norm_db = _norm(db_name)
    result = {"understat_name": None, "fbref_name": None, "fbref_id": None}
    
    # Understat
    if understat_dict:
        # Prova exact match
        if norm_db in understat_dict:
            result["understat_name"] = understat_dict[norm_db][0]
        else:
            # Fuzzy match
            best, score, _ = process.extractOne(norm_db, understat_dict.keys(), score_cutoff=85)
            if best:
                result["understat_name"] = understat_dict[best][0]
    
    # FBRef
    if fbref_dict:
        # Prova exact match
        if norm_db in fbref_dict:
            original_name, fbref_id = fbref_dict[norm_db]
            result["fbref_name"] = original_name
            result["fbref_id"] = fbref_id
        else:
            # Fuzzy match
            best, score, _ = process.extractOne(norm_db, fbref_dict.keys(), score_cutoff=85)
            if best:
                original_name, fbref_id = fbref_dict[best]
                result["fbref_name"] = original_name
                result["fbref_id"] = fbref_id
    
    return result


def main():
    db = SessionLocal()
    season = "2024"  # Adatta secondo l'anno attuale
    
    print(f"\n[START] Build team mappings (stagione {season})")
    
    # Step 1: Ottieni tutte le squadre dal DB
    teams_by_league = get_all_teams_from_db(db)
    
    # Step 2: Scarica squadre da Understat e FBRef
    understat_by_league = {}
    fbref_by_league = {}
    
    for league in teams_by_league.keys():
        understat_by_league[league] = fetch_understat_teams(league, season)
        time.sleep(0.5)  # Rispetto i server
        fbref_by_league[league] = fetch_fbref_teams(league, season)
        time.sleep(0.5)
    
    # Step 3: Crea mapping e salva nel DB
    print("\n[MAPPING] Creazione mapping e salvataggio nel DB...")
    mapped_count = 0
    unmapped_count = 0
    
    for league, db_teams in teams_by_league.items():
        understat_dict = understat_by_league.get(league)
        fbref_dict = fbref_by_league.get(league)
        
        for db_team in db_teams:
            # Controlla se esiste già
            existing = db.query(TeamMapping).filter(
                TeamMapping.source_name == db_team,
                TeamMapping.league_code == league
            ).first()
            
            if existing:
                print(f"[SKIP] {league} {db_team} (già in DB)")
                continue
            
            matches = fuzzy_match(db_team, understat_dict, fbref_dict)
            
            if matches["understat_name"] or matches["fbref_id"]:
                # Usa db.merge per fare INSERT o UPDATE
                tm = TeamMapping(
                    source_name=db_team,
                    understat_name=matches["understat_name"],
                    fbref_id=matches["fbref_id"],
                    fbref_name=matches["fbref_name"],
                    league_code=league,
                    source="football-data.org" # Fonte dei nomi in `fixtures`
                )
                db.merge(tm)
                u_name = matches['understat_name'] or 'N/A'
                f_name = matches['fbref_name'] or 'N/A'
                print(f"[MAP] {league}: '{db_team}' → U: '{u_name}', F: '{f_name}'")
                mapped_count += 1
            else:
                print(f"[NOMATCH] {league} {db_team} (non trovato su Understat/FBRef)")
                unmapped_count += 1
    
    db.commit()
    print(f"\n[SUMMARY] Mappati: {mapped_count}, Non mappati: {unmapped_count}")
    db.close()
    print("[END] Build team mappings completato")


if __name__ == "__main__":
    print("[ERROR] build_team_mapping.py è disabilitato!")
    print("[REASON] Le fonti dati (Understat, FBRef) non sono accessibili:")
    print("  - Understat: HTML pattern fallito (regex non trova team)")
    print("  - FBRef: HTTP 403 Cloudflare (non bypassabile senza headless browser)")
    print("")
    print("[ALTERNATIVE] Opzioni per popolare team_mappings:")
    print("  1. Importare manualmente via CSV/JSON")
    print("  2. Usare Selenium + headless browser per FBRef")
    print("  3. Contattare Understat per accesso API")
    print("[SKIPPED] Saltando main()")
    # main()
