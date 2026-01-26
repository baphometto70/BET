from database import SessionLocal
from models import Prediction, Fixture
from datetime import datetime

def generate_md():
    db = SessionLocal()
    date_str = "2026-01-24"
    preds = db.query(Prediction, Fixture).join(Fixture).filter(Prediction.prediction_date == date_str).order_by(Prediction.consensus_score.desc(), Prediction.prob_1.desc()).all()
    
    md = f"# 📅 Predictions for {date_str}\n\n"
    md += f"**Total Matches**: {len(preds)}\n"
    md += "Scorri per vedere tutte le 37 partite con pronostico 1X2, Doppia Chance consigliata e Goal/Over.\n\n"
    
    md += "| League | Match | 1X2 Pick | DC Safety (1X/X2) | O/U 2.5 | BTTS | Confidence |\n"
    md += "| :--- | :--- | :---: | :---: | :---: | :---: | :---: |\n"
    
    for p in preds:
        pred = p.Prediction
        fix = p.Fixture
        
        # Determine strict 1X2 Prob
        p1 = pred.prob_1
        px = pred.prob_x
        p2 = pred.prob_2
        
        # DC Probs
        p1x = (p1 + px) * 100
        px2 = (px + p2) * 100
        
        # Pick Display
        pick = pred.pick_1x2
        
        # Safety Display
        safety = ""
        if p1 > p2:
            safety = f"1X ({int(p1x)}%)"
        else:
            safety = f"X2 ({int(px2)}%)"
            
        # O/U Display
        ou = "**OVER**" if pred.prob_over > 0.5 else "UNDER"
        ou_conf = int(max(pred.prob_over, pred.prob_under) * 100)
        ou_str = f"{ou} ({ou_conf}%)"
        
        # BTTS Display
        btts = "**GOAL**" if pred.prob_btts_yes > 0.50 else "NOGOAL" # Slightly relaxed for display if needed, but keeping logic
        btts_conf = int(pred.prob_btts_yes * 100) if pred.prob_btts_yes > 0.5 else int((1-pred.prob_btts_yes) * 100)
        btts_str = f"{btts} ({btts_conf}%)"
        
        league = fix.league.replace("Premier League", "PL").replace("Serie A", "SA").replace("Bundesliga", "BL").replace("Primera Division", "PD")
        
        # Highlight strong confidence
        conf_icon = "🟢" if "ALTA" in pred.confidence_1x2 else ("🟡" if "MEDIA" in pred.confidence_1x2 else "🔴")
        
        md += f"| {league} | **{fix.home}** vs {fix.away} | **{pick}** | {safety} | {ou_str} | {btts_str} | {conf_icon} |\n"
        
    md += "\n> **Legenda**:\n> * 🟢 = Alta Confidenza\n> * 🟡 = Media\n> * 🔴 = Bassa (Value Bet)\n"
    
    with open(f"/Users/gennaro.taurino/.gemini/antigravity/brain/28e08f90-20f5-4afd-812e-45588ce81e0d/predictions_{date_str.replace('-', '')}.md", "w") as f:
        f.write(md)
    
    print("Markdown generated.")
    db.close()

if __name__ == "__main__":
    generate_md()
