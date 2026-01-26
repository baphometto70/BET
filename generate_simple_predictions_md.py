#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple predictions generator for upcoming matches (date = today).
Uses odds to compute implied probabilities, selects best pick (double chance if high confidence).
Outputs a markdown table with best option and all options percentages.
"""
import os
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Database path (same as used in project)
DB_PATH = os.path.expanduser('~/Develop/BET/BET/bet.db')
engine = create_engine(f'sqlite:///{DB_PATH}')
Session = sessionmaker(bind=engine)
session = Session()

# Import models
import sys
sys.path.append('/Users/gennaro.taurino/Develop/BET/BET')
from models import Fixture, Odds

now = datetime.now()

# Fetch fixtures with odds for today (date = now.date())
fixtures = (
    session.query(Fixture, Odds)
    .join(Odds, Fixture.match_id == Odds.match_id)
    .filter(Fixture.date == now.date())
    .all()
)

results = []
for fix, odd in fixtures:
    # Determine kickoff datetime (prefer local time)
    time_str = fix.time_local or fix.time
    if not time_str:
        continue
    try:
        kickoff_time = datetime.strptime(time_str, "%H:%M").time()
    except Exception:
        continue
    kickoff = datetime.combine(fix.date, kickoff_time)
    if kickoff <= now:
        continue  # skip already started

    # Compute implied probabilities from odds (if available)
    def imp(o):
        return 1.0 / o if o and o > 1.0 else 0.0
    p1 = imp(odd.odds_1)
    px = imp(odd.odds_x)
    p2 = imp(odd.odds_2)
    total = p1 + px + p2
    if total > 0:
        p1, px, p2 = p1 / total, px / total, p2 / total
    else:
        p1 = px = p2 = 0.0

    # Double chance probabilities
    p1x = p1 + px
    px2 = px + p2
    p12 = p1 + p2

    # Choose best pick
    best_key = None
    best_prob = 0.0
    # Prefer double chance if >= 0.70
    if p1x >= 0.70:
        best_key, best_prob = "1X", p1x
    elif px2 >= 0.70:
        best_key, best_prob = "X2", px2
    elif p12 >= 0.70:
        best_key, best_prob = "12", p12
    else:
        # fallback to highest single
        singles = {"1": p1, "X": px, "2": p2}
        best_key = max(singles, key=singles.get)
        best_prob = singles[best_key]

    # Over/Under 2.5 using odds if present
    over_prob = imp(odd.odds_ou25_over)
    under_prob = imp(odd.odds_ou25_under)
    ou_total = over_prob + under_prob
    if ou_total > 0:
        over_prob, under_prob = over_prob / ou_total, under_prob / ou_total
    else:
        over_prob = under_prob = 0.0
    ou_pick = "OVER 2.5" if over_prob >= under_prob else "UNDER 2.5"

    # Build compact string of all options
    options = {
        "1": p1,
        "X": px,
        "2": p2,
        "1X": p1x,
        "X2": px2,
        "12": p12,
        "OVER": over_prob,
        "UNDER": under_prob,
    }
    probs_str = ", ".join([f"{k}:{int(v*100)}%" for k, v in options.items() if v > 0])

    results.append({
        "league": fix.league,
        "match": f"{fix.home} vs {fix.away}",
        "kickoff": kickoff.strftime("%H:%M"),
        "best": f"{best_key} ({int(best_prob*100)}%)",
        "ou": f"{ou_pick} ({int(max(over_prob, under_prob)*100)}%)",
        "all": probs_str,
    })

# Sort by kickoff time
results.sort(key=lambda x: x["kickoff"])

# Generate markdown
md_lines = []
md_lines.append(f"# 📅 Upcoming Matches – Predictions ({now.strftime('%d %b %Y')})")
md_lines.append("")
md_lines.append("| League | Match | Kick‑off | Best Pick (prob) | Over/Under (prob) | All Options (prob) |")
md_lines.append("| :--- | :--- | :---: | :---: | :---: | :--- |")
for r in results:
    md_lines.append(f"| {r['league']} | {r['match']} | {r['kickoff']} | {r['best']} | {r['ou']} | {r['all']} |")

output_path = Path(__file__).with_name('upcoming_predictions_20260125.md')
output_path.write_text("\n".join(md_lines), encoding='utf-8')
print('Markdown generated at', output_path)
