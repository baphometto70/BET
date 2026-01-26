#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
map_builder.py
--------------
Costruisce la tabella di mapping dei nomi delle squadre (`team_mappings`) nel database.

1. Itera sulle leghe principali definite in `FD_LEAGUE_CODE`.
2. Per ogni lega, scarica l'elenco ufficiale delle squadre da Understat.
3. Scarica l'elenco delle squadre dalla fonte primaria (football-data.co.uk).
4. Usa il fuzzy matching per trovare la migliore corrispondenza tra i nomi.
5. Salva i mapping con score elevato nel database.

USO:
  python map_builder.py
"""

import io
import re
import time
from datetime import datetime

import pandas as pd
import requests
from rapidfuzz import fuzz, process

from database import SessionLocal
from models import TeamMapping
from historical_builder import (
    FD_LEAGUE_CODE,
    UNDERSTAT_LEAGUE,
    UA,
    fetch_league_teams,
    fd_url_for,
)


def fetch_fd_teams(code: str, season_date: str) -> list[str]:
    """Scarica i nomi delle squadre da un file CSV di football-data.co.uk."""
    url = fd_url_for(code, season_date)
    if not url:
        return []
    try:
        r = requests.get(url, headers=UA, timeout=30)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        
        # Unisce i nomi delle squadre di casa e trasferta e rimuove i duplicati
        teams = pd.concat([df["HomeTeam"], df["AwayTeam"]]).dropna().unique()
        return sorted([str(t).strip() for t in teams])
    except Exception as e:
        print(f"[ERR] Impossibile scaricare squadre da football-data per {code}: {e}")
        return []


def main():
    db = SessionLocal()
    print("Avvio del processo di mapping dei nomi delle squadre...")

    # Usiamo la stagione corrente come riferimento
    current_date = datetime.now().isoformat()
    
    # Itera su tutte le leghe definite in historical_builder
    for comp_code in FD_LEAGUE_CODE.keys():
        if comp_code not in UNDERSTAT_LEAGUE:
            print(f"[SKIP] {comp_code}: non ha una controparte definita per Understat.")
            continue

        print(f"\n--- Processo per la lega: {comp_code} ---")

        # 1. Ottieni elenco squadre da Understat (la nostra "verità")
        understat_teams = fetch_league_teams(comp_code, current_date, delay=0.5)
        if not understat_teams:
            print(f"[WARN] Nessuna squadra trovata su Understat per {comp_code}. Salto.")
            continue
        print(f"Trovate {len(understat_teams)} squadre su Understat.")

        # 2. Ottieni elenco squadre dalla fonte primaria (football-data.co.uk)
        fd_teams = fetch_fd_teams(comp_code, current_date)
        if not fd_teams:
            print(f"[WARN] Nessuna squadra trovata su football-data.co.uk per {comp_code}. Salto.")
            continue
        print(f"Trovate {len(fd_teams)} squadre su football-data.co.uk.")

        # 3. Esegui il matching e salva nel DB
        mappings_found = 0
        for fd_name in fd_teams:
            # Trova la migliore corrispondenza nella lista di Understat
            best_match = process.extractOne(fd_name, understat_teams, scorer=fuzz.WRatio, score_cutoff=88)
            
            if best_match:
                understat_name = best_match[0]
                score = best_match[1]
                
                # Crea o aggiorna il record nel database
                mapping_obj = TeamMapping(
                    source_name=fd_name,
                    understat_name=understat_name,
                    league_code=comp_code,
                    source="football-data.co.uk",
                    last_updated=datetime.utcnow().date()
                )
                db.merge(mapping_obj)
                mappings_found += 1
                print(f"  '{fd_name}' -> '{understat_name}' (Score: {score:.1f})")

        print(f"Trovati {mappings_found} mapping per {comp_code}.")
        db.commit()

    db.close()
    print("\n[OK] Processo di mapping completato.")


if __name__ == "__main__":
    main()