#!/usr/bin/env python3
"""Generate final Champions League predictions table from database"""
import sqlite3
from datetime import datetime

conn = sqlite3.connect('/Users/gennaro.taurino/Develop/BET/BET/bet.db')
cursor = conn.cursor()

cursor.execute("""
SELECT f.home, f.away, f.time_local,
       p.pick_1x2, p.confidence_1x2, p.prob_1, p.prob_x, p.prob_2,
       p.pick_ou, p.prob_over, p.prob_under,
       p.pick_btts, p.prob_btts_yes,
       p.consensus_score, p.data_quality
FROM fixtures f
JOIN predictions p ON f.match_id = p.match_id
WHERE f.date = '2026-01-28' AND f.league_code = 'CL'
ORDER BY f.home
""")

matches = cursor.fetchall()

lines = []
lines.append("# ⚽ Champions League - 28 Gennaio 2026 (ML Predictions)")
lines.append("")
lines.append(f"**{len(matches)} partite - Tutte alle 20:00 CET**")
lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
lines.append("")
lines.append("| # | Partita | Pick | Conf | 1-X-2 | O/U | BTTS | Consensus |")
lines.append("|---|---------|------|------|-------|-----|------|-----------|")

for i, (home, away, time, pick, conf, p1, px, p2, ou, pov, pun, btts, pbtts, cons, qual) in enumerate(matches, 1):
    # Shorten names
    home_short = home.replace(" FC", "").replace("FC ", "").replace(" CF", "")[:15]
    away_short = away.replace(" FC", "").replace("FC ", "").replace(" CF", "")[:15]
    match = f"{home_short} - {away_short}"
    
    # Format probabilities
    probs = f"{int(p1*100)}-{int(px*100)}-{int(p2*100)}"
    
    # Over/Under
    ou_str = f"{ou} ({int(max(pov, pun)*100)}%)"
    
    # BTTS
    btts_str = f"{btts or 'N/A'} ({int(pbtts*100)}%)" if pbtts else "N/A"
    
    # Consensus
    cons_str = f"{int(cons) if cons else 0}/100"
    
    lines.append(f"| {i} | {match} | **{pick}** | {conf} | {probs} | {ou_str} | {btts_str} | {cons_str} |")

lines.append("")
lines.append("**Legenda**:")
lines.append("- **Pick**: Pronostico consigliato dal modello ML")
lines.append("- **Conf**: ALTA (≥65%), MEDIA (≥55%), BASSA (<55%)")
lines.append("- **1-X-2**: Probabilità percentuali per Casa-Pareggio-Trasferta")
lines.append("- **Consensus**: Accordo tra ML, Poisson e Quote (0-100)")

output = "\n".join(lines)
with open('/Users/gennaro.taurino/Develop/BET/BET/cl_predictions_ml.md', 'w') as f:
    f.write(output)

print(output)
print(f"\n\n✅ Salvato in: cl_predictions_ml.md")
print(f"   Partite con previsioni ML: {len(matches)}")

conn.close()
