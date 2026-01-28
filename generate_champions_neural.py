#!/usr/bin/env python3
"""
Genera schedine Champions con Neural Reasoning V2 PESANTE
"""
import sys
from pathlib import Path
from datetime import date
import sqlite3

ROOT = Path(__file__).resolve().parent
sys.path.append(str(ROOT))

from neural_reasoning_engine_v2 import NeuralReasoningEngineV2
from database import SessionLocal
from models import Fixture

print("=" * 100)
print("🏆 SCHEDINE CHAMPIONS LEAGUE CON NEURAL REASONING V2")
print("=" * 100)

# Init Neural Engine
engine = NeuralReasoningEngineV2(str(ROOT / "bet.db"))
engine.context_analyzer.debug = False
engine.debug = False

# Get Champions matches
db = SessionLocal()
match_date = date(2026, 1, 28)

cl_matches = db.query(Fixture).filter(
    Fixture.date == match_date,
    Fixture.league_code == 'CL'
).all()

print(f"\n✅ Trovate {len(cl_matches)} partite Champions del {match_date}\n")

predictions = []

for fix in cl_matches:
    # Probabilità ML simulate (in produzione vengono da ML models)
    # Per ora uso stime base
    ml_prob_1 = 0.40
    ml_prob_x = 0.30
    ml_prob_2 = 0.30

    try:
        # Apply Neural Reasoning
        neural_p1, neural_px, neural_p2, reasoning = engine.apply_reasoning(
            match_id=fix.match_id,
            home=fix.home,
            away=fix.away,
            league=fix.league_code,
            date=fix.date,
            ml_prob_1=ml_prob_1,
            ml_prob_x=ml_prob_x,
            ml_prob_2=ml_prob_2
        )

        # Calcola DC
        dc_1x = neural_p1 + neural_px
        dc_x2 = neural_px + neural_p2
        dc_12 = neural_p1 + neural_p2

        # Trova best pick
        mercati = [
            ('1', neural_p1),
            ('X', neural_px),
            ('2', neural_p2),
            ('DC 1X', dc_1x),
            ('DC X2', dc_x2),
            ('DC 12', dc_12),
        ]

        best_mercato = max(mercati, key=lambda x: x[1])

        predictions.append({
            'home': fix.home,
            'away': fix.away,
            'ora': fix.time or '?',
            'ml_prob_1': ml_prob_1,
            'neural_prob_1': neural_p1,
            'neural_prob_x': neural_px,
            'neural_prob_2': neural_p2,
            'change_home': reasoning['home_change_pct'],
            'change_away': reasoning['away_change_pct'],
            'impact': reasoning['impact'],
            'best_mercato': best_mercato[0],
            'best_prob': best_mercato[1],
        })

        print(f"⚽ {fix.home} vs {fix.away}")
        print(f"   ML:     1={ml_prob_1:.1%} X={ml_prob_x:.1%} 2={ml_prob_2:.1%}")
        print(f"   NEURAL: 1={neural_p1:.1%} X={neural_px:.1%} 2={neural_p2:.1%}")
        print(f"   Change: 1={reasoning['home_change_pct']:+.1f}% 2={reasoning['away_change_pct']:+.1f}%")
        print(f"   IMPATTO: {reasoning['impact']}")
        print(f"   🎯 BEST: {best_mercato[0]} ({best_mercato[1]:.1%})\n")

    except Exception as e:
        print(f"❌ Errore su {fix.home} vs {fix.away}: {e}\n")
        continue

db.close()

# Genera schedine
print("\n" + "=" * 100)
print("📋 SCHEDINA CONSERVATIVA (TOP 5 PIÙ SICURI)")
print("=" * 100)

# Ordina per probabilità
predictions_sorted = sorted(predictions, key=lambda x: x['best_prob'], reverse=True)
top5 = predictions_sorted[:5]

prob_tot = 1.0
for i, pred in enumerate(top5, 1):
    prob_tot *= pred['best_prob']
    icon = "🔥" if pred['best_prob'] >= 0.80 else "⭐" if pred['best_prob'] >= 0.70 else "✅"

    print(f"\n{i}. {pred['home']} vs {pred['away']} ({pred['ora']})")
    print(f"   {icon} {pred['best_mercato']} → {pred['best_prob']:.1%}")
    if abs(pred['change_home']) > 3 or abs(pred['change_away']) > 3:
        print(f"   🧠 Neural: 1={pred['change_home']:+.1f}% 2={pred['change_away']:+.1f}% | IMPATTO: {pred['impact']}")

print(f"\n{'─'*100}")
print(f"📊 PROBABILITÀ COMBINATA: {prob_tot*100:.2f}%")
print(f"💰 QUOTA FAIR: ~{1/prob_tot:.2f}")
print(f"{'─'*100}")

# Schedina con forti aggiustamenti Neural
print("\n\n" + "=" * 100)
print("🧠 SCHEDINA NEURAL (Aggiustamenti forti >5%)")
print("=" * 100)

neural_picks = [p for p in predictions if abs(p['change_home']) > 5 or abs(p['change_away']) > 5]

if neural_picks:
    neural_sorted = sorted(neural_picks, key=lambda x: max(abs(x['change_home']), abs(x['change_away'])), reverse=True)

    for i, pred in enumerate(neural_sorted[:5], 1):
        print(f"\n{i}. {pred['home']} vs {pred['away']}")
        print(f"   ML:     1={pred['ml_prob_1']:.1%}")
        print(f"   NEURAL: 1={pred['neural_prob_1']:.1%} X={pred['neural_prob_x']:.1%} 2={pred['neural_prob_2']:.1%}")
        print(f"   🧠 Change: 1={pred['change_home']:+.1f}% 2={pred['change_away']:+.1f}%")
        print(f"   IMPATTO: {pred['impact']}")
else:
    print("\n⚖️ Nessun aggiustamento forte trovato (tutti match bilanciati)")

print("\n" + "=" * 100)
print("✅ SCHEDINE GENERATE CON NEURAL REASONING V2!")
print("=" * 100)
