#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inserisce i risultati reali nel database
"""

from database import SessionLocal
from models import Fixture
from datetime import date

# Risultati forniti dall'utente - AGGIORNATI 6 gennaio 2026
risultati = {
    # Serie A - 6 gennaio 2026
    'Lecce': {'away': 'Roma', 'home_goals': 0, 'away_goals': 2},
    'Sassuolo': {'away': 'Juventus', 'home_goals': 0, 'away_goals': 3},

    # Premier League - 6 gennaio 2026
    'West Ham': {'away': 'Nottingham Forest', 'home_goals': 1, 'away_goals': 2},
}

db = SessionLocal()

print("INSERIMENTO RISULTATI NEL DATABASE")
print("="*100)

updated = 0
not_found = 0

for home_team, data in risultati.items():
    # Cerca la partita nel database
    matches = db.query(Fixture).filter(
        Fixture.date == date(2026, 1, 6),
        Fixture.home.contains(home_team)
    ).all()

    if len(matches) == 0:
        print(f"❌ NON TROVATA: {home_team} vs {data['away']}")
        not_found += 1
        continue

    # Trova la partita corretta
    match = None
    for m in matches:
        if data['away'] in m.away or m.away in data['away']:
            match = m
            break

    if not match:
        print(f"❌ NON TROVATA: {home_team} vs {data['away']}")
        not_found += 1
        continue

    # Aggiorna risultato
    match.result_home_goals = data['home_goals']
    match.result_away_goals = data['away_goals']

    print(f"✅ {match.home} {data['home_goals']}-{data['away_goals']} {match.away}")
    updated += 1

db.commit()
db.close()

print("\n" + "="*100)
print(f"Risultati aggiornati: {updated}")
print(f"Partite non trovate: {not_found}")
print("="*100)
