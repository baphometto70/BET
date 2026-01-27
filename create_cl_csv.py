#!/usr/bin/env python3
"""Generate CSV with ML + Poisson predictions for Champions League"""
import csv
import sqlite3

conn = sqlite3.connect('/Users/gennaro.taurino/Develop/BET/BET/bet.db')
cursor = conn.cursor()

cursor.execute("""
SELECT f.home, f.away,
       p.prob_1, p.prob_x, p.prob_2,
       p.pick_1x2, p.confidence_1x2,
       p.prob_over, p.prob_under,
       p.prob_btts_yes,
       p.prob_mg_1_3, p.prob_mg_2_4,
       p.prob_combo_1_over, p.prob_combo_1x_over,
       p.consensus_score, p.data_quality
FROM fixtures f
JOIN predictions p ON f.match_id = p.match_id
WHERE f.date = '2026-01-28' AND f.league_code = 'CL'
ORDER BY f.home
""")

rows = cursor.fetchall()

# Generate CSV
csv_file = '/Users/gennaro.taurino/Develop/BET/BET/champions_league_previsioni.csv'
with open(csv_file, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    
    # Header
    writer.writerow([
        'Partita',
        'CONSIGLIO', 'PROB%',
        '1 %', 'X %', '2 %',
        '1X %', 'X2 %', '12 %',
        'Over 2.5%', 'Under 2.5%',
        'BTTS %',
        'Multigol 1-3%', 'Multigol 2-4%',
        'Combo 1+Over%', 'Combo 1X+Over%',
        'Consensus', 'Qualita'
    ])
    
    for (home, away, p1, px, p2, ml_pick, ml_conf, 
         pov, pun, pbtts, mg13, mg24, c1o, c1xo, cons, qual) in rows:
        
        # Probabilities as percentages
        p1_pct = int(p1 * 100)
        px_pct = int(px * 100)
        p2_pct = int(p2 * 100)
        p1x_pct = p1_pct + px_pct
        px2_pct = px_pct + p2_pct
        p12_pct = p1_pct + p2_pct
        
        # Determine best pick with double chance logic
        if p1x_pct >= 70:
            best_pick = "1X (Doppia Chance)"
            best_pct = p1x_pct
        elif px2_pct >= 70:
            best_pick = "X2 (Doppia Chance)"
            best_pct = px2_pct
        elif p12_pct >= 70:
            best_pick = "12 (Doppia Chance)"
            best_pct = p12_pct
        else:
            # Use ML pick
            best_pick = f"{ml_pick} ({ml_conf})"
            if ml_pick == "1":
                best_pct = p1_pct
            elif ml_pick == "X":
                best_pct = px_pct
            elif ml_pick == "2":
                best_pct = p2_pct
            elif ml_pick == "1X":
                best_pct = p1x_pct
            elif ml_pick == "X2":
                best_pct = px2_pct
            else:
                best_pct = p12_pct
        
        # Other markets
        over_pct = int(pov * 100)
        under_pct = int(pun * 100)
        btts_pct = int(pbtts * 100)
        mg13_pct = int(mg13 * 100) if mg13 else 0
        mg24_pct = int(mg24 * 100) if mg24 else 0
        c1o_pct = int(c1o * 100) if c1o else 0
        c1xo_pct = int(c1xo * 100) if c1xo else 0
        cons_score = int(cons) if cons else 0
        
        writer.writerow([
            f"{home} vs {away}",
            best_pick, best_pct,
            p1_pct, px_pct, p2_pct,
            p1x_pct, px2_pct, p12_pct,
            over_pct, under_pct,
            btts_pct,
            mg13_pct, mg24_pct,
            c1o_pct, c1xo_pct,
            cons_score, qual or 'N/A'
        ])

print(f"✅ CSV generato: {csv_file}")
print(f"   {len(rows)} partite Champions League")
print(f"\nApri con Excel o LibreOffice Calc")

conn.close()
