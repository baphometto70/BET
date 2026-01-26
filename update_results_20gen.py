#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aggiorna database con risultati Champions 20 gennaio 2026
"""

from datetime import date
from database import SessionLocal
from models import Fixture

print("=" * 100)
print("📊 AGGIORNAMENTO RISULTATI CHAMPIONS - 20 GENNAIO 2026")
print("=" * 100)

# Risultati delle 9 partite
results = [
    ("FK Kairat", "Club Brugge KV", 1, 4),
    ("FK Bodø/Glimt", "Manchester City FC", 3, 1),
    ("Tottenham Hotspur FC", "Borussia Dortmund", 2, 0),
    ("Sporting Clube de Portugal", "Paris Saint-Germain FC", 2, 1),
    ("PAE Olympiakos SFP", "Bayer 04 Leverkusen", 2, 0),
    ("Villarreal CF", "AFC Ajax", 1, 2),
    ("FC København", "SSC Napoli", 1, 1),
    ("Real Madrid CF", "AS Monaco FC", 6, 1),
    ("FC Internazionale Milano", "Arsenal FC", 1, 3),
]

db = SessionLocal()
match_date = date(2026, 1, 20)

updated = 0
not_found = []

for home, away, hg, ag in results:
    # Cerca partita
    fix = db.query(Fixture).filter(
        Fixture.date == match_date,
        Fixture.home == home,
        Fixture.away == away
    ).first()

    if fix:
        fix.result_home_goals = hg
        fix.result_away_goals = ag
        print(f"✅ {home} {hg}-{ag} {away}")
        updated += 1
    else:
        # Prova con nomi abbreviati
        fix = db.query(Fixture).filter(
            Fixture.date == match_date,
            Fixture.home.contains(home.split()[0]),
            Fixture.away.contains(away.split()[0])
        ).first()

        if fix:
            fix.result_home_goals = hg
            fix.result_away_goals = ag
            print(f"✅ {fix.home} {hg}-{ag} {fix.away}")
            updated += 1
        else:
            print(f"❌ NON TROVATA: {home} vs {away}")
            not_found.append((home, away))

db.commit()
db.close()

print(f"\n{'='*100}")
print(f"✅ AGGIORNATE {updated}/9 PARTITE")
if not_found:
    print(f"❌ Non trovate: {len(not_found)}")
    for h, a in not_found:
        print(f"   • {h} vs {a}")
print(f"{'='*100}")
