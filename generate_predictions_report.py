#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_predictions_report.py

Generates a comprehensive markdown report of upcoming match predictions.
Reads from the predictions table (populated by predictions_generator.py)
and displays all market probabilities in a clean, readable format.

Usage:
    python generate_predictions_report.py --date 2026-01-26
"""
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))

from models import Fixture, Prediction
from database import engine, SessionLocal

def generate_report(date_str: str = None):
    """
    Generate markdown report for predictions on a specific date.
    
    Args:
        date_str: Date in YYYY-MM-DD format. If None, uses today.
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    try:
        target_date = datetime.fromisoformat(date_str).date()
    except:
        print(f"Invalid date format: {date_str}")
        return
    
    session = SessionLocal()
    now = datetime.now()
    
    # Query predictions with their fixtures for the target date
    # Only include matches that haven't started yet
    query = (
        session.query(Prediction, Fixture)
        .join(Fixture, Prediction.match_id == Fixture.match_id)
        .filter(Fixture.date == target_date)
    )
    
    results = []
    for pred, fixture in query.all():
        # Skip past matches
        time_str = fixture.time_local or fixture.time
        if time_str:
            try:
                kickoff_time = datetime.strptime(time_str, "%H:%M").time()
                kickoff_datetime = datetime.combine(fixture.date, kickoff_time)
                if kickoff_datetime <= now:
                    continue
            except:
                pass
        
        # Get probabilities (stored as 0-1 floats)
        p1 = (pred.prob_1 or 0.0) * 100
        px = (pred.prob_x or 0.0) * 100
        p2 = (pred.prob_2 or 0.0) * 100
        pover = (pred.prob_over or 0.0) * 100
        punder = (pred.prob_under or 0.0) * 100
        pbtts = (pred.prob_btts_yes or 0.0) * 100
        
        # Double chance
        p1x = p1 + px
        px2 = px + p2
        p12 = p1 + p2
        
        # Advanced markets
        pmg13 = (pred.prob_mg_1_3 or 0.0) *

 100
        pmg24 = (pred.prob_mg_2_4 or 0.0) * 100
        pc1o = (pred.prob_combo_1_over or 0.0) * 100
        pc1xo = (pred.prob_combo_1x_over or 0.0) * 100
        
        # Determine best pick
        picks = {
            '1': p1, 'X': px, '2': p2,
            '1X': p1x, 'X2': px2, '12': p12
        }
        best_pick = max(picks, key=picks.get)
        best_prob = picks[best_pick]
        
        # Confidence indicator
        if pred.confidence_1x2 == "ALTA":
            conf_emoji = "🟢"
        elif pred.confidence_1x2 == "MEDIA":
            conf_emoji = "🟡"
        else:
            conf_emoji = "🔴"
        
        results.append({
            'kickoff': time_str or '??:??',
            'league': fixture.league,
            'match': f"{fixture.home} vs {fixture.away}",
            'best_pick': f"{best_pick} ({best_prob:.0f}%)",
            'confidence': f"{conf_emoji} {pred.confidence_1x2}",
            '1x2': f"1:{p1:.0f}% X:{px:.0f}% 2:{p2:.0f}%",
            'dc': f"1X:{p1x:.0f}% X2:{px2:.0f}% 12:{p12:.0f}%",
            'ou': f"{pred.pick_ou} ({max(pover, punder):.0f}%) | O:{pover:.0f}% U:{punder:.0f}%",
            'btts': f"{pred.pick_btts or 'N/A'} ({pbtts:.0f}%)",
            'multigol': f"1-3:{pmg13:.0f}% 2-4:{pmg24:.0f}%",
            'combo': f"1+O:{pc1o:.0f}% 1X+O:{pc1xo:.0f}%",
            'quality': pred.data_quality or 'N/A',
            'consensus': pred.consensus_score or 0
        })
    
    # Sort by kickoff time
    results.sort(key=lambda x: x['kickoff'])
    
    # Generate markdown
    lines = []
    lines.append(f"# 📊 Predictions Report - {target_date.strftime('%d %B %Y')}")
    lines.append("")
    lines.append(f"**Generated**: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Total Upcoming Matches**: {len(results)}")
    lines.append("")
    
    if not results:
        lines.append("*No upcoming matches found for this date.*")
    else:
        lines.append("## Match Predictions")
        lines.append("")
        
        for r in results:
            lines.append(f"### {r['match']} ({r['kickoff']})")
            lines.append(f"**League**: {r['league']} | **Best Pick**: {r['best_pick']} | **Confidence**: {r['confidence']}")
            lines.append("")
            lines.append("| Market | Prediction | Probabilities |")
            lines.append("|--------|------------|---------------|")
            lines.append(f"| 1X2 | {r['best_pick'].split()[0]} | {r['1x2']} |")
            lines.append(f"| Double Chance | - | {r['dc']} |")
            lines.append(f"| Over/Under 2.5 | {r['ou'].split('|')[0].strip()} | {r['ou'].split('|')[1].strip()} |")
            lines.append(f"| BTTS | {r['btts'].split('(')[0].strip()} | {r['btts']} |")
            lines.append(f"| Multigol | - | {r['multigol']} |")
            lines.append(f"| Combo | - | {r['combo']} |")
            lines.append("")
            lines.append(f"*Data Quality*: {r['quality']} | *Consensus Score*: {r['consensus']}/100")
            lines.append("")
            lines.append("---")
            lines.append("")
        
        lines.append("## Legend")
        lines.append("")
        lines.append("- 🟢 **ALTA** - High confidence (probability >= 65%)")
        lines.append("- 🟡 **MEDIA** - Medium confidence (probability >= 55%)")
        lines.append("- 🔴 **BASSA** - Low confidence (probability < 55%)")
        lines.append("")
        lines.append("**Data Quality**: Indicates source reliability (High = Understat xG, Medium = FBRef, Low = Fallback)")
        lines.append("**Consensus Score**: Agreement between ML models, Poisson, and betting odds (0-100)")
    
    # Write to file
    output_file = PROJECT_ROOT / f"predictions_report_{date_str.replace('-', '')}.md"
    output_file.write_text("\n".join(lines), encoding='utf-8')
    print(f"\n✅ Report generated: {output_file}")
    print(f"   Upcoming matches: {len(results)}")
    
    session.close()
    return output_file

def main():
    parser = argparse.ArgumentParser(description="Generate predictions report")
    parser.add_argument('--date', type=str, default=None,
                      help='Date in YYYY-MM-DD format (default: today)')
    args = parser.parse_args()
    
    generate_report(args.date)

if __name__ == "__main__":
    main()
