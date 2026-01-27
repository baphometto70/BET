#!/usr/bin/env python3
"""Generate compact table for CL predictions"""
import sqlite3

conn = sqlite3.connect('/Users/gennaro.taurino/Develop/BET/BET/bet.db')
cursor = conn.cursor()

cursor.execute("""
SELECT f.home, f.away, f.time_local,
       fe.xg_for_home, fe.xg_for_away
FROM fixtures f
LEFT JOIN features fe ON f.match_id = fe.match_id
WHERE f.date = '2026-01-28' AND f.league_code = 'CL'
ORDER BY f.home
""")

matches = cursor.fetchall()

lines = []
lines.append("# ⚽ Champions League - 28 Gennaio 2026")
lines.append("")
lines.append(f"**{len(matches)} partite - Tutte alle 20:00 CET**")
lines.append("")
lines.append("| # | Partita | Pronostico | Prob | xG | Over 2.5 |")
lines.append("|---|---------|------------|------|----|---------:|")

for i, (home, away, time, xg_h, xg_a) in enumerate(matches, 1):
    # Simple prediction
    if xg_h and xg_a:
        total = xg_h + xg_a + 1.0
        p1 = (xg_h / total) * 100
        p2 = (xg_a / total) * 100
        
        # Best pick logic
        if max(p1, p2) >= 45:
            pick = "1" if p1 > p2 else "2"
            prob = int(max(p1, p2))
        else:
            pick = "12"
            prob = int(p1 + p2)
        
        total_goals = xg_h + xg_a
        ou = "✅" if total_goals > 2.5 else "❌"
        xg_str = f"{xg_h:.1f} - {xg_a:.1f}"
    else:
        pick = "12"
        prob = 67
        ou = "?"
        xg_str = "N/A"
    
    # Shorten team names
    home_short = home.replace(" FC", "").replace("FC ", "").replace(" CF", "")[:15]
    away_short = away.replace(" FC", "").replace("FC ", "").replace(" CF", "")[:15]
    match = f"{home_short} - {away_short}"
    
    lines.append(f"| {i} | {match} | **{pick}** | {prob}% | {xg_str} | {ou} |")

lines.append("")
lines.append("**Legenda**: 1=Casa | X=Pareggio | 2=Trasferta | 12=Doppia Chance | ✅=Over 2.5 consigliato")

output = "\n".join(lines)
with open('/Users/gennaro.taurino/Develop/BET/BET/cl_predictions_compact.md', 'w') as f:
    f.write(output)

print(output)
print(f"\n✅ Salvato in: cl_predictions_compact.md")

conn.close()
