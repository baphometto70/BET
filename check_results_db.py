#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verifica risultati salvati nel DB
"""

from datetime import date
from database import SessionLocal
from models import Fixture

db = SessionLocal()
match_date = date(2026, 1, 20)

# Tutte le partite del 20 gennaio
partite = db.query(Fixture).filter(Fixture.date == match_date).all()

print(f"📊 Partite del {match_date}: {len(partite)}\n")

for fix in partite:
    risultato = f"{fix.result_home_goals or '?'}-{fix.result_away_goals or '?'}" if fix.result_home_goals is not None else "N/D"
    print(f"{fix.home:40} vs {fix.away:40} | {risultato} | {fix.league_code}")

db.close()
