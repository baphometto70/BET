#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate a markdown table for today's upcoming matches (kickoff > now).
For each match we list the best betting option (including 1X2, double chance, over/under, BTTS, multigol, combo)
and its probability, plus a compact column with the probabilities of the other options.
"""
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Adjust the DB URL if needed; the project uses SQLite by default
DB_PATH = os.path.expanduser('~/Develop/BET/BET/bet.db')
engine = create_engine(f'sqlite:///{DB_PATH}')
Session = sessionmaker(bind=engine)
session = Session()

from models import Fixture, Prediction

now = datetime.now()

# Query predictions for today's fixtures with kickoff later than now
results = []
query = session.query(Prediction, Fixture).join(Fixture, Prediction.match_id == Fixture.match_id)
for pred, fix in query.all():
    # Determine kickoff time (prefer time_local, fallback to time)
    time_str = getattr(fix, 'time_local', None) or getattr(fix, 'time', None)
    if not time_str:
        continue
    try:
        kickoff_time = datetime.strptime(time_str, "%H:%M").time()
    except Exception:
        continue
    kickoff = datetime.combine(fix.date, kickoff_time)
    if kickoff <= now:
        continue  # skip already started

    # Probabilities (already stored as floats 0-1)
    prob_1 = pred.prob_1 or 0.0
    prob_x = pred.prob_x or 0.0
    prob_2 = pred.prob_2 or 0.0
    prob_over = pred.prob_over or 0.0
    prob_under = pred.prob_under or 0.0
    prob_btts = pred.prob_btts_yes or 0.0
    prob_mg_1_3 = getattr(pred, 'prob_mg_1_3', 0.0) or 0.0
    prob_mg_2_4 = getattr(pred, 'prob_mg_2_4', 0.0) or 0.0
    prob_combo_1_over = getattr(pred, 'prob_combo_1_over', 0.0) or 0.0
    prob_combo_1x_over = getattr(pred, 'prob_combo_1x_over', 0.0) or 0.0

    # Double‑chance probabilities
    prob_1x = prob_1 + prob_x
    prob_x2 = prob_x + prob_2
    prob_12 = prob_1 + prob_2

    # Build a dict of all options with their probabilities
    options = {
        '1': prob_1,
        'X': prob_x,
        '2': prob_2,
        '1X': prob_1x,
        'X2': prob_x2,
        '12': prob_12,
        'OVER': prob_over,
        'UNDER': prob_under,
        'BTTS': prob_btts,
        'MG1-3': prob_mg_1_3,
        'MG2-4': prob_mg_2_4,
        'C1+O1.5': prob_combo_1_over,
        'C1X+O1.5': prob_combo_1x_over,
    }
    # Find the best option
    best_key = max(options, key=options.get)
    best_prob = options[best_key]
    # Build a compact string of all percentages (rounded)
    probs_str = ', '.join([f"{k}:{int(v*100)}%" for k, v in options.items() if v > 0])

    results.append({
        'league': fix.league,
        'match': f"{fix.home} vs {fix.away}",
        'kickoff': kickoff.strftime('%H:%M'),
        'best': f"{best_key} ({int(best_prob*100)}%)",
        'all': probs_str,
    })

# Sort by kickoff
results.sort(key=lambda x: x['kickoff'])

# Generate markdown
md_lines = []
md_lines.append('# 📅 Upcoming Matches – Best Predictions (24 Jan 2026)')
md_lines.append('')
md_lines.append('| League | Match | Kick‑off | Best Option (prob) | All Options (prob) |')
md_lines.append('| :--- | :--- | :---: | :---: | :--- |')
for r in results:
    md_lines.append(f"| {r['league']} | {r['match']} | {r['kickoff']} | {r['best']} | {r['all']} |")

output_path = Path(__file__).with_name('upcoming_predictions_20260124.md')
output_path.write_text('\n'.join(md_lines), encoding='utf-8')
print('Markdown generated at', output_path)
