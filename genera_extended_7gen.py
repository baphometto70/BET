#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genera predizioni estese per 7 gennaio 2026
"""

from database import SessionLocal
from models import Fixture
from datetime import date
import pandas as pd
from scipy.stats import poisson

db = SessionLocal()

# Carica partite 7 gennaio
fixtures = db.query(Fixture).filter(
    Fixture.date == date(2026, 1, 7)
).all()

print(f"Partite trovate: {len(fixtures)}")

# Lista per salvare tutte le predizioni
all_predictions = []

for fix in fixtures:
    if not fix.feature:
        continue

    feat = fix.feature
    if not all([feat.xg_for_home, feat.xg_against_home, feat.xg_for_away, feat.xg_against_away]):
        continue

    # Calcola lambda (gol attesi)
    lambda_home = (feat.xg_for_home + feat.xg_against_away) / 2
    lambda_away = (feat.xg_for_away + feat.xg_against_home) / 2

    match_id = fix.match_id
    home = fix.home
    away = fix.away
    league = fix.league
    kickoff_time = fix.time

    # Calcola tutte le probabilità

    # 1X2
    p_home = sum(
        poisson.pmf(i, lambda_home) * poisson.pmf(j, lambda_away)
        for i in range(10) for j in range(i)
    )
    p_draw = sum(
        poisson.pmf(i, lambda_home) * poisson.pmf(i, lambda_away)
        for i in range(10)
    )
    p_away = 1 - p_home - p_draw

    # Doppia Chance
    p_1x = p_home + p_draw
    p_x2 = p_draw + p_away
    p_12 = p_home + p_away

    # Over/Under
    p_00 = poisson.pmf(0, lambda_home) * poisson.pmf(0, lambda_away)
    p_10 = poisson.pmf(1, lambda_home) * poisson.pmf(0, lambda_away)
    p_01 = poisson.pmf(0, lambda_home) * poisson.pmf(1, lambda_away)
    p_11 = poisson.pmf(1, lambda_home) * poisson.pmf(1, lambda_away)

    p_over_05 = 1 - p_00
    p_over_15 = 1 - (p_00 + p_10 + p_01 + p_11)

    p_under_25 = sum(
        poisson.pmf(i, lambda_home) * poisson.pmf(j, lambda_away)
        for i in range(3) for j in range(3) if i + j <= 2
    )
    p_over_25 = 1 - p_under_25

    p_under_35 = sum(
        poisson.pmf(i, lambda_home) * poisson.pmf(j, lambda_away)
        for i in range(4) for j in range(4) if i + j <= 3
    )
    p_over_35 = 1 - p_under_35

    # Goal/No Goal
    p_gg = 1 - (
        poisson.pmf(0, lambda_home) * sum(poisson.pmf(j, lambda_away) for j in range(10)) +
        sum(poisson.pmf(i, lambda_home) for i in range(10)) * poisson.pmf(0, lambda_away) -
        poisson.pmf(0, lambda_home) * poisson.pmf(0, lambda_away)
    )
    p_ng = 1 - p_gg

    # Multigol
    p_mg_01 = p_00 + p_10 + p_01 + p_11
    p_mg_23 = p_under_35 - p_mg_01
    p_mg_45 = sum(
        poisson.pmf(i, lambda_home) * poisson.pmf(j, lambda_away)
        for i in range(6) for j in range(6) if 4 <= i + j <= 5
    )

    # Multigol range
    p_mg_13 = sum(
        poisson.pmf(i, lambda_home) * poisson.pmf(j, lambda_away)
        for i in range(4) for j in range(4) if 1 <= i + j <= 3
    )
    p_mg_24 = sum(
        poisson.pmf(i, lambda_home) * poisson.pmf(j, lambda_away)
        for i in range(5) for j in range(5) if 2 <= i + j <= 4
    )
    p_mg_25 = sum(
        poisson.pmf(i, lambda_home) * poisson.pmf(j, lambda_away)
        for i in range(6) for j in range(6) if 2 <= i + j <= 5
    )

    # Crea le righe per extended_predictions.csv
    predictions = [
        # Doppia Chance
        (match_id, home, away, league, kickoff_time, 'dc_1x', '1X (Home or Draw)', p_1x, max(0, p_1x - 0.55), '', 0.0,
         'high' if p_1x > 0.70 else 'medium' if p_1x > 0.60 else 'low', 'Doppia Chance'),
        (match_id, home, away, league, kickoff_time, 'dc_x2', 'X2 (Draw or Away)', p_x2, max(0, p_x2 - 0.55), '', 0.0,
         'high' if p_x2 > 0.70 else 'medium' if p_x2 > 0.60 else 'low', 'Doppia Chance'),
        (match_id, home, away, league, kickoff_time, 'dc_12', '12 (Home or Away)', p_12, max(0, p_12 - 0.55), '', 0.0,
         'high' if p_12 > 0.70 else 'medium' if p_12 > 0.60 else 'low', 'Doppia Chance'),

        # Over/Under
        (match_id, home, away, league, kickoff_time, 'over_0.5', 'Over 0.5 goals', p_over_05, max(0, p_over_05 - 0.55), '', 0.0,
         'high' if p_over_05 > 0.70 else 'medium' if p_over_05 > 0.60 else 'low', 'Over/Under'),
        (match_id, home, away, league, kickoff_time, 'over_1.5', 'Over 1.5 goals', p_over_15, max(0, p_over_15 - 0.55), '', 0.0,
         'high' if p_over_15 > 0.70 else 'medium' if p_over_15 > 0.60 else 'low', 'Over/Under'),
        (match_id, home, away, league, kickoff_time, 'over_2.5', 'Over 2.5 goals', p_over_25, max(0, p_over_25 - 0.55), '', 0.0,
         'high' if p_over_25 > 0.70 else 'medium' if p_over_25 > 0.60 else 'low', 'Over/Under'),
        (match_id, home, away, league, kickoff_time, 'under_2.5', 'Under 2.5 goals', 1-p_over_25, max(0, (1-p_over_25) - 0.55), '', 0.0,
         'high' if (1-p_over_25) > 0.70 else 'medium' if (1-p_over_25) > 0.60 else 'low', 'Over/Under'),
        (match_id, home, away, league, kickoff_time, 'under_3.5', 'Under 3.5 goals', 1-p_over_35, max(0, (1-p_over_35) - 0.55), '', 0.0,
         'high' if (1-p_over_35) > 0.70 else 'medium' if (1-p_over_35) > 0.60 else 'low', 'Over/Under'),

        # Goal/No Goal
        (match_id, home, away, league, kickoff_time, 'gg', 'Goal/Goal (Both Score)', p_gg, max(0, p_gg - 0.55), '', 0.0,
         'high' if p_gg > 0.70 else 'medium' if p_gg > 0.60 else 'low', 'Goal/No Goal'),
        (match_id, home, away, league, kickoff_time, 'ng', 'No Goal (At least one blank)', p_ng, max(0, p_ng - 0.55), '', 0.0,
         'high' if p_ng > 0.70 else 'medium' if p_ng > 0.60 else 'low', 'Goal/No Goal'),

        # Multigol
        (match_id, home, away, league, kickoff_time, 'mg_1-3', 'Multigol 1-3 goals', p_mg_13, max(0, p_mg_13 - 0.55), '', 0.0,
         'high' if p_mg_13 > 0.70 else 'medium' if p_mg_13 > 0.60 else 'low', 'Multigol'),
        (match_id, home, away, league, kickoff_time, 'mg_2-4', 'Multigol 2-4 goals', p_mg_24, max(0, p_mg_24 - 0.55), '', 0.0,
         'high' if p_mg_24 > 0.70 else 'medium' if p_mg_24 > 0.60 else 'low', 'Multigol'),
        (match_id, home, away, league, kickoff_time, 'mg_2-5', 'Multigol 2-5 goals', p_mg_25, max(0, p_mg_25 - 0.55), '', 0.0,
         'high' if p_mg_25 > 0.70 else 'medium' if p_mg_25 > 0.60 else 'low', 'Multigol'),
    ]

    all_predictions.extend(predictions)

db.close()

# Salva in extended_predictions.csv
df = pd.DataFrame(all_predictions, columns=[
    'match_id', 'home', 'away', 'league', 'kickoff_time', 'market', 'market_name',
    'probability', 'value', 'odds', 'kelly', 'confidence', 'category'
])

# Ordina per partita e probabilità
df = df.sort_values(['match_id', 'probability'], ascending=[True, False])

df.to_csv('extended_predictions.csv', index=False)

print(f"\n✅ Salvate {len(df)} predizioni in extended_predictions.csv")
print(f"   {len(fixtures)} partite analizzate")
print(f"   ~13 mercati per partita")

# Stampa riepilogo picks ad alta probabilità
high_conf = df[df['confidence'] == 'high']
print(f"\n🎯 Predizioni HIGH CONFIDENCE (>70%): {len(high_conf)}")
print("\nTop 10:")
for i, row in high_conf.head(10).iterrows():
    print(f"   {row['home']} vs {row['away']}")
    print(f"   → {row['market_name']}: {row['probability']*100:.1f}%")
