#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trova tutte le partite del 21 gennaio 2026
"""

from datetime import date
from database import SessionLocal
from models import Fixture

db = SessionLocal()
match_date = date(2026, 1, 21)

# Tutte le partite
partite = db.query(Fixture).filter(Fixture.date == match_date).all()

print(f"📅 PARTITE DEL {match_date}: {len(partite)}\n")

# Separa per lega
by_league = {}
for fix in partite:
    league = fix.league_code or "UNKNOWN"
    if league not in by_league:
        by_league[league] = []
    by_league[league].append(fix)

for league, matches in sorted(by_league.items()):
    print(f"\n🏆 {league} ({len(matches)} partite):")
    for fix in matches:
        orario = fix.time_local or fix.time or "?"
        print(f"  {orario} | {fix.home:35} vs {fix.away}")

db.close()
