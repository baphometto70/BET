#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aggiorna database con risultati Champions 21 gennaio 2026
"""

from datetime import date
from database import SessionLocal
from models import Fixture

print("=" * 100)
print("📊 AGGIORNAMENTO RISULTATI CHAMPIONS - 21 GENNAIO 2026")
print("=" * 100)

# Risultati delle 9 partite
results = [
    ("Qarabağ Ağdam FK", "Eintracht Frankfurt", 3, 2),
    ("Galatasaray SK", "Club Atlético de Madrid", 1, 1),
    ("Olympique de Marseille", "Liverpool FC", 0, 3),
    ("SK Slavia Praha", "FC Barcelona", 2, 4),
    ("Atalanta BC", "Athletic Club", 2, 3),
    ("Juventus FC", "Sport Lisboa e Benfica", 2, 0),
    ("Newcastle United FC", "PSV", 3, 0),
    ("FC Bayern München", "Royale Union Saint-Gilloise", 2, 0),
    ("Chelsea FC", "Paphos FC", 1, 0),
]

db = SessionLocal()
match_date = date(2026, 1, 21)

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
