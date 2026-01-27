#!/usr/bin/env python3
"""
Create Champions League predictions report for 2026-01-28
Using available fixtures and features data
"""
import sqlite3
from datetime import datetime

conn = sqlite3.connect('/Users/gennaro.taurino/Develop/BET/BET/bet.db')
cursor = conn.cursor()

# Get CL fixtures for tomorrow
cursor.execute("""
SELECT f.match_id, f.home, f.away, f.time_local,
       fe.xg_for_home, fe.xg_against_home, fe.xg_for_away, fe.xg_against_away
FROM fixtures f
LEFT JOIN features fe ON f.match_id = fe.match_id
WHERE f.date = '2026-01-28' AND f.league_code = 'CL'
ORDER BY f.time_local, f.home
""")

matches = cursor.fetchall()

# Generate markdown
lines = []
lines.append("# ⚽ Champions League - Predictions for 28 January 2026")
lines.append("")
lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
lines.append(f"**Total Matches**: {len(matches)}")
lines.append("")
lines.append("## Match Predictions")
lines.append("")

for match_id, home, away, kickoff, xg_for_h, xg_ag_h, xg_for_a, xg_ag_a in matches:
    # Simple prediction based on xG
    if xg_for_h and xg_for_a:
        total_h = xg_for_h
        total_a = xg_for_a
        
        # Normalize to probabilities
        total = total_h + total_a + 1.0  # +1 for draw probability
        p1 = (total_h / total) * 100
        px = (1.0 / total) * 100
        p2 = (total_a / total) * 100
        
        # Double chance
        p1x = p1 + px
        px2 = px + p2
        p12 = p1 + p2
        
        # Best pick
        picks = {'1': p1, 'X': px, '2': p2, '1X': p1x, 'X2': px2, '12': p12}
        best = max(picks, key=picks.get)
        best_prob = picks[best]
        
        # Over/Under (based on total xG)
        total_goals = xg_for_h + xg_for_a
        if total_goals > 2.5:
            ou_pick = "OVER 2.5"
            ou_prob = min(95, 50 + (total_goals - 2.5) * 15)
        else:
            ou_pick = "UNDER 2.5"
            ou_prob = min(95, 50 + (2.5 - total_goals) * 15)
        
        conf = "🟢 ALTA" if best_prob >= 65 else "🟡 MEDIA" if best_prob >= 55 else "🔴 BASSA"
    else:
        p1 = px = p2 = 33.3
        p1x = px2 = p12 = 66.7
        best = "N/A"
        best_prob = 0
        ou_pick = "N/A"
        ou_prob = 0
        conf = "⚪ N/A"
    
    lines.append(f"### {home} vs {away} ({kickoff})")
    lines.append(f"**Best Pick**: {best} ({best_prob:.0f}%) | **Confidence**: {conf}")
    lines.append("")
    lines.append("| Market | Prediction | Probabilities |")
    lines.append("|--------|------------|---------------|")
    lines.append(f"| 1X2 | {best} | 1:{p1:.0f}% X:{px:.0f}% 2:{p2:.0f}% |")
    lines.append(f"| Double Chance | - | 1X:{p1x:.0f}% X2:{px2:.0f}% 12:{p12:.0f}% |")
    lines.append(f"| Over/Under 2.5 | {ou_pick} | {ou_prob:.0f}% |")
    lines.append("")
    if xg_for_h:
        lines.append(f"*xG*: {home} {xg_for_h:.2f} - {xg_for_a:.2f} {away}")
    lines.append("")
    lines.append("---")
    lines.append("")

lines.append("## ⚠️ Note")
lines.append("")
lines.append("- Predictions based on xG data and historical performance")
lines.append("- Odds API not available - probabilities calculated from xG models")
lines.append("- 🟢 ALTA: probability ≥ 65% | 🟡 MEDIA: ≥ 55% | 🔴 BASSA: < 55%")

output = "\\n".join(lines)
with open('/Users/gennaro.taurino/Develop/BET/BET/champions_league_predictions_20260128.md', 'w') as f:
    f.write(output)

print(f"\\n✅ Champions League report generated!")
print(f"   Total matches: {len(matches)}")
print(f"   File: champions_league_predictions_20260128.md")

conn.close()
