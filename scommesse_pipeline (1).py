#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scommesse pipeline: selezione, metriche (ROI, Brier, Logloss), report HTML (tabella + grafici ROI/CLV).
Dipendenze: pandas, numpy, matplotlib.
"""
import argparse, json, math, base64, io
from datetime import datetime
import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent

def load_cfg():
    with open(ROOT / "config.json","r") as f:
        return json.load(f)

def implied_from_odds(o):
    try:
        o = float(o)
    except:
        return 0.0
    return 0.0 if o <= 0 else 1.0/o

def normalize_triple(a, b, c):
    s = a+b+c
    if s <= 0: 
        return (1/3,1/3,1/3)
    return (a/s, b/s, c/s)

def confidence_band(p, cfg):
    if p >= cfg["confidence_bands"]["A_min"]:
        return "A"
    if p >= cfg["confidence_bands"]["B_min"]:
        return "B"
    if p >= cfg["confidence_bands"]["C_min"]:
        return "C"
    return "NO"

def kelly_fraction(p, odds):
    b = max(0.0, float(odds) - 1.0) if odds and odds>0 else 0.0
    q = 1.0 - p
    return (b*p - q)/b if b>0 else 0.0

def pick_market(row, cfg):
    # Probabilità modello 1X2
    p1_m, px_m, p2_m = float(row.p1), float(row.px), float(row.p2)
    p1_m, px_m, p2_m = normalize_triple(p1_m, px_m, p2_m)

    # Probabilità mercato 1X2 (da quote)
    p1_mkt = implied_from_odds(row.odds_1)
    px_mkt = implied_from_odds(row.odds_x)
    p2_mkt = implied_from_odds(row.odds_2)
    p1_mkt, px_mkt, p2_mkt = normalize_triple(p1_mkt, px_mkt, p2_mkt)

    lam = cfg["blend_lambda_serie_a"] if str(row.league).strip().lower()=="serie a" else cfg["blend_lambda_major"]
    p1 = lam*p1_m + (1-lam)*p1_mkt
    px = lam*px_m + (1-lam)*px_mkt
    p2 = lam*p2_m + (1-lam)*p2_mkt

    # Edge 1X2
    e1 = p1 - p1_mkt
    ex = px - px_mkt
    e2 = p2 - p2_mkt

    # Totali
    mu = float(row.mu_gol) if "mu_gol" in row and not pd.isna(row.mu_gol) else 2.6
    line = float(row.line_ou) if not pd.isna(row.line_ou) else 2.5
    p_over = float(row.p_over) if "p_over" in row and not pd.isna(row.p_over) else np.nan
    p_under = float(row.p_under) if "p_under" in row and not pd.isna(row.p_under) else np.nan
    odds_over = float(row.odds_over) if not pd.isna(row.odds_over) else np.nan
    odds_under = float(row.odds_under) if not pd.isna(row.odds_under) else np.nan
    p_over_mkt = implied_from_odds(odds_over) if odds_over>0 else np.nan
    p_under_mkt = implied_from_odds(odds_under) if odds_under>0 else np.nan

    picks = []  # (market, pick, edge, odds_for_kelly_prob)

    # 1X2
    if e1 >= cfg["thresholds"]["edge_1x2"]:
        picks.append(("1X2","1", e1, (p1, row.odds_1)))
    if ex >= cfg["thresholds"]["edge_1x2"]:
        picks.append(("1X2","X", ex, (px, row.odds_x)))
    if e2 >= cfg["thresholds"]["edge_1x2"]:
        picks.append(("1X2","2", e2, (p2, row.odds_2)))

    # DNB (approssimo edge con lato migliore tra 1 e 2)
    if max(e1,e2) >= cfg["thresholds"]["edge_handicap_dnb"]:
        side = "Home DNB" if e1>=e2 else "Away DNB"
        picks.append(("DNB", side, max(e1,e2), None))

    # Double Chance
    if (p1+px) - (p1_mkt+px_mkt) >= cfg["thresholds"]["edge_handicap_dnb"]:
        picks.append(("DC","1X", (p1+px)-(p1_mkt+px_mkt), None))
    if (p1+p2) - (p1_mkt+p2_mkt) >= cfg["thresholds"]["edge_handicap_dnb"]:
        picks.append(("DC","12", (p1+p2)-(p1_mkt+p2_mkt), None))
    if (px+p2) - (px_mkt+p2_mkt) >= cfg["thresholds"]["edge_handicap_dnb"]:
        picks.append(("DC","X2", (px+p2)-(px_mkt+p2_mkt), None))

    # Totali
    if not np.isnan(p_under) and not np.isnan(p_under_mkt):
        if abs(mu - line) < 0.25 and line == 3.0:
            line = cfg["lines"]["under_borderline_push_prefer"]
        edge_under = p_under - p_under_mkt
        if edge_under >= cfg["thresholds"]["edge_totals"]:
            picks.append(("O/U", f"Under {line}", edge_under, None))
    if not np.isnan(p_over) and not np.isnan(p_over_mkt):
        edge_over = p_over - p_over_mkt
        if edge_over >= cfg["thresholds"]["edge_totals"]:
            picks.append(("O/U", f"Over {line}", edge_over, None))

    if not picks:
        return None

    best = max(picks, key=lambda t: t[2])
    # Confidenza
    if best[1] == "1":
        conf_p = p1
        quota = float(row.odds_1) if not pd.isna(row.odds_1) else np.nan
    elif best[1] == "X":
        conf_p = px
        quota = float(row.odds_x) if not pd.isna(row.odds_x) else np.nan
    elif best[1] == "2":
        conf_p = p2
        quota = float(row.odds_2) if not pd.isna(row.odds_2) else np.nan
    else:
        conf_p = max(p1,px,p2)
        quota = np.nan

    conf = confidence_band(conf_p, cfg)

    # Stake
    stake = cfg["staking"]["flat_pct"]
    if conf=="A" and best[0]=="1X2" and best[2] >= cfg["staking"]["kelly_min_edge"] and quota==quota:
        k = kelly_fraction(conf_p, quota)
        stake = max(stake, cfg["staking"]["kelly_fraction"] * max(0.0, k))

    return {
        "market_used": best[0],
        "pick": best[1],
        "edge_pct": round(float(best[2]), 4),
        "confidenza": conf,
        "quota": quota,
        "stake": round(float(stake), 6)
    }

def run_selection(update_metrics=False):
    cfg = load_cfg()
    fixtures = pd.read_csv(ROOT/"fixtures.csv")
    features = pd.read_csv(ROOT/"features.csv")
    preds    = pd.read_csv(ROOT/"predictions.csv")
    df = fixtures.merge(preds, on="match_id", how="left").merge(features, on="match_id", how="left")

    selections = []
    for _, row in df.iterrows():
        res = pick_market(row, cfg)
        if res is None:
            continue
        selections.append({
            "datetime_bet": datetime.now().isoformat(timespec="seconds"),
            "match_id": row.match_id,
            "league": row.league,
            "home": row.home,
            "away": row.away,
            "market_used": res["market_used"],
            "pick": res["pick"],
            "confidenza": res["confidenza"],
            "edge_pct": res["edge_pct"],
            "stake": res["stake"],
            "quota": res["quota"],
            "quota_closing": np.nan,
            "risultato": "",
            "esito": "",
            "profitto": "",
            "CLV": ""
        })

    if selections:
        sel_df = pd.DataFrame(selections)
        log_path = ROOT/"bets_log.csv"
        if log_path.exists():
            prev = pd.read_csv(log_path)
            out = pd.concat([prev, sel_df], ignore_index=True)
        else:
            out = sel_df.copy()
        out.to_csv(log_path, index=False)
        print(f"[OK] Selezioni aggiunte: {len(sel_df)} (bets_log.csv)")
    else:
        print("[INFO] Nessuna selezione sopra le soglie.")

    if update_metrics:
        update_metrics_file()

def parse_goals(result):
    """Parsa '2-1' -> (2,1). Ritorna (None,None) se non valido."""
    if not isinstance(result, str) or "-" not in result:
        return (None, None)
    try:
        h, a = result.split("-")
        return int(h.strip()), int(a.strip())
    except:
        return (None, None)

def compute_brier_1x2(row, preds):
    # Restituisce brier per questo match se 1X2 disponibile, altrimenti np.nan
    outcome = row.get("outcome_1x2", None)
    if outcome not in ["1","X","2"]:
        return np.nan
    probs = {
        "1": preds.get("p1", np.nan),
        "X": preds.get("px", np.nan),
        "2": preds.get("p2", np.nan)
    }
    if np.any([pd.isna(probs["1"]), pd.isna(probs["X"]), pd.isna(probs["2"])]):
        return np.nan
    # Brier multiclass: somma (p_i - o_i)^2
    o = {"1":0.0,"X":0.0,"2":0.0}
    o[outcome] = 1.0
    return (probs["1"]-o["1"])**2 + (probs["X"]-o["X"])**2 + (probs["2"]-o["2"])**2

def compute_logloss_ou(row, preds, line):
    # Usa p_over/p_under e outcome O/U dalla linea fixtures
    if pd.isna(preds.get("p_over", np.nan)) or pd.isna(preds.get("p_under", np.nan)):
        return np.nan
    goals_h, goals_a = parse_goals(row.get("risultato",""))
    if goals_h is None: 
        return np.nan
    total = goals_h + goals_a
    if pd.isna(line): 
        return np.nan
    try:
        line = float(line)
    except:
        return np.nan
    y_over = 1.0 if total > line else 0.0
    p_over = float(preds.get("p_over", np.nan))
    p_over = min(max(p_over, 1e-12), 1-1e-12)
    # logloss binaria
    return -(y_over*np.log(p_over) + (1-y_over)*np.log(1-p_over))

def update_metrics_file():
    cfg = load_cfg()
    log_path = ROOT/"bets_log.csv"
    if not log_path.exists():
        print("[WARN] bets_log.csv assente; niente metriche.")
        return
    fixtures = pd.read_csv(ROOT/"fixtures.csv")
    preds    = pd.read_csv(ROOT/"predictions.csv")
    log = pd.read_csv(log_path)

    # Calcolo ROI per giocate con esito valorizzato
    played = log[log["esito"].isin(["W","L","Push"])].copy()
    ROI = np.nan
    if not played.empty:
        def _ret(r):
            try:
                stake = float(r["stake"])
            except:
                stake = 0.0
            try:
                quota = float(r["quota"]) if r["quota"]==r["quota"] else 0.0
            except:
                quota = 0.0
            if r["esito"]=="W":
                return (quota-1.0)*stake
            if r["esito"]=="Push":
                return 0.0
            return -stake
        played["ret"] = played.apply(_ret, axis=1)
        denom = played["stake"].sum()
        ROI = played["ret"].sum()/denom if denom>0 else np.nan

    # Merge per metriche probabilistiche
    m = log.merge(preds, on="match_id", how="left", suffixes=("","_pred")).merge(
        fixtures[["match_id","line_ou"]], on="match_id", how="left"
    )

    # Outcome 1X2 dalla stringa risultato
    outcomes = []
    for _, r in m.iterrows():
        h, a = parse_goals(str(r.get("risultato","")))
        if h is None:
            outcomes.append(None)
            continue
        if h>a: outcomes.append("1")
        elif h<a: outcomes.append("2")
        else: outcomes.append("X")
    m["outcome_1x2"] = outcomes

    # Brier solo per match con 1X2 definita e probabilità presenti
    briers = []
    for _, r in m.iterrows():
        pr = {"p1": r.get("p1", np.nan), "px": r.get("px", np.nan), "p2": r.get("p2", np.nan)}
        b = compute_brier_1x2(r, pr)
        briers.append(b)
    m["brier_1x2"] = briers

    # Logloss O/U (binario) usando p_over, linea fixtures e risultato
    loglosses = []
    for _, r in m.iterrows():
        pr = {"p_over": r.get("p_over", np.nan), "p_under": r.get("p_under", np.nan)}
        ll = compute_logloss_ou(r, pr, r.get("line_ou", np.nan))
        loglosses.append(ll)
    m["logloss_ou"] = loglosses

    # Aggregati
    brier_mean = m["brier_1x2"].dropna().mean() if "brier_1x2" in m else np.nan
    logloss_mean = m["logloss_ou"].dropna().mean() if "logloss_ou" in m else np.nan

    row = {
        "data": datetime.now().date().isoformat(),
        "brier_1x2": brier_mean,
        "logloss_ou": logloss_mean,
        "ROI": ROI,
        "CLV_pos_pct": np.nan,
        "n_bet": len(played),
        "ROI_DNB": np.nan,
        "ROI_DC": np.nan,
        "ROI_UO": np.nan,
        "ROI_1X2": np.nan
    }
    met_path = ROOT/"metrics_daily.csv"
    if met_path.exists():
        prev = pd.read_csv(met_path)
        out = pd.concat([prev, pd.DataFrame([row])], ignore_index=True)
    else:
        out = pd.DataFrame([row])
    out.to_csv(met_path, index=False)
    print("[OK] metrics_daily.csv aggiornato (ROI, Brier, Logloss)")

def _fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("ascii")
    plt.close(fig)
    return b64

def generate_report_html(outfile="report_scommesse.html", last_n=50):
    # Carica log e metriche
    log_path = ROOT/"bets_log.csv"
    met_path = ROOT/"metrics_daily.csv"
    if not log_path.exists():
        raise FileNotFoundError("bets_log.csv non trovato")
    log = pd.read_csv(log_path)
    metrics = pd.read_csv(met_path) if met_path.exists() else pd.DataFrame()

    # Tabella ultime pick
    recent = log.tail(last_n).copy()

    # Grafici ROI cumulata e (placeholder) CLV medio nel tempo
    # ROI cumulata: somma profitti su stake
    plot_df = log[log["esito"].isin(["W","L","Push"])].copy()
    if not plot_df.empty:
        def _ret_row(r):
            stake = float(r.get("stake",0.0) or 0.0)
            quota = float(r.get("quota",0.0) or 0.0)
            if r.get("esito")=="W": return (quota-1.0)*stake
            if r.get("esito")=="Push": return 0.0
            return -stake
        plot_df["ret"] = plot_df.apply(_ret_row, axis=1)
        plot_df["cum_ret"] = plot_df["ret"].cumsum()
        fig1 = plt.figure()
        plt.plot(range(len(plot_df["cum_ret"])), plot_df["cum_ret"])
        plt.title("Profitto cumulato")
        plt.xlabel("Bet #")
        plt.ylabel("Profitto (unità stake)")
        img1 = _fig_to_base64(fig1)
    else:
        img1 = ""

    # CLV: se disponibile (quota vs quota_closing)
    clv_series = log.copy()
    clv_series = clv_series[(clv_series["quota"].notna()) & (clv_series["quota_closing"].notna())]
    if not clv_series.empty:
        clv_series["clv"] = (clv_series["quota_closing"]/clv_series["quota"]) - 1.0
        fig2 = plt.figure()
        plt.plot(range(len(clv_series["clv"])), clv_series["clv"].rolling(5).mean())
        plt.title("CLV rolling (5)")
        plt.xlabel("Bet # con CLV")
        plt.ylabel("CLV medio (rolling)")
        img2 = _fig_to_base64(fig2)
    else:
        img2 = ""

    # HTML
    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8" />
  <title>Report Scommesse</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; }}
    h1, h2 {{ margin-bottom: 0.2rem; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
    th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; font-size: 14px; }}
    th {{ background: #f5f5f5; }}
    .chart {{ margin: 1rem 0; }}
    .muted {{ color: #666; font-size: 12px; }}
  </style>
</head>
<body>
  <h1>Report Scommesse</h1>
  <p class="muted">Generato: {datetime.now().isoformat(timespec="seconds")}</p>
  <h2>Ultime pick</h2>
  {recent.to_html(index=False)}
  <h2>Profitto cumulato</h2>
  {'<img class="chart" src="data:image/png;base64,'+img1+'" />' if img1 else '<p class="muted">Ancora nessun dato con esito.</p>'}
  <h2>CLV Rolling (5)</h2>
  {'<img class="chart" src="data:image/png;base64,'+img2+'" />' if img2 else '<p class="muted">CLV non disponibile (manca quota_closing).</p>'}
  <h2>Metriche giornaliere</h2>
  {metrics.to_html(index=False) if not metrics.empty else '<p class="muted">metrics_daily.csv vuoto.</p>'}
</body>
</html>"""
    out = ROOT / outfile
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[OK] Report HTML generato: {out}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="Genera selezioni e aggiorna bets_log.csv")
    ap.add_argument("--update-metrics", action="store_true", help="Aggiorna metrics_daily.csv (ROI, Brier, Logloss)")
    ap.add_argument("--report", action="store_true", help="Genera report HTML (report_scommesse.html)")
    args = ap.parse_args()
    if args.run:
        run_selection(update_metrics=args.update_metrics)
    if args.update_metrics and not args.run:
        update_metrics_file()
    if args.report:
        generate_report_html()

    if not (args.run or args.update_metrics or args.report):
        print("Usa --run, --update-metrics e/o --report.")

if __name__=="__main__":
    main()
