#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
run_day.py — giornata automatica (fixtures -> features -> predictions)

- Estrae partite del giorno per le competizioni scelte (football-data.org)
- Raccoglie statistiche reali (ultime N gare in 180 giorni) per le squadre
- Stima con Poisson: 1X2, OU 2.0/2.5/3.0, BTTS, DC, DNB, Top-3 Correct Score
- Stampa tabella riepilogo a console
- Scrive: fixtures.csv, features.csv, predictions.csv, picks_only.csv
- Opzioni:
  --delay   : throttling anti-429
  --append  : accoda ai CSV esistenti invece di sovrascriverli
  --html    : genera report HTML (report_YYYYMMDD.html o percorso custom)
"""

import argparse
import json
import math
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

try:
    import requests
except ImportError:
    requests = None

# ---------------- CONFIG ----------------
DEFAULT_API_TOKEN = "9f48528ff8d5482f8851ae808eaa9f13"
COMP_MAP = {
    "SA": "Serie A",
    "PL": "Premier League",
    "CL": "UEFA Champions League",
    "EL": "UEFA Europa League",
    "BL1": "Bundesliga",
    "PD": "Primera Division",
    "FL1": "Ligue 1",
    "DED": "Eredivisie",
    "PPL": "Primeira Liga",
    "ELC": "Championship (ENG)",
    "BSA": "Campeonato Brasileiro Série A",
    "EC": "European Championship",
    "WC": "FIFA World Cup",
}
LEGEND = "\n".join([f"  {k:<4} = {v}" for k, v in COMP_MAP.items()])

FIX_COLS = [
    "match_id",
    "league",
    "date",
    "time_local",
    "home",
    "away",
    "odds_1",
    "odds_x",
    "odds_2",
    "line_ou",
    "odds_over",
    "odds_under",
]
FEA_COLS = [
    "match_id",
    "xG_for_5_home",
    "xG_against_5_home",
    "xG_for_5_away",
    "xG_against_5_away",
    "rest_days_home",
    "rest_days_away",
    "injuries_key_home",
    "injuries_key_away",
    "derby_flag",
    "europe_flag_home",
    "europe_flag_away",
    "meteo_flag",
    "style_ppda_home",
    "style_ppda_away",
    "travel_km_away",
]
PRED_COLS = [
    "match_id",
    "p1",
    "px",
    "p2",
    "line_ou",
    "p_over",
    "p_under",
    "p_over_2.0",
    "p_under_2.0",
    "p_over_2.5",
    "p_under_2.5",
    "p_over_3.0",
    "p_under_3.0",
    "p_btts",
    "p_nobtts",
    "p_1x",
    "p_x2",
    "p_12",
    "p_dnb1",
    "p_dnb2",
    "cs_top3",
    "pick_main",
    "confidence",
]


# ---------------- HTTP & RATE LIMIT ----------------
def api_token() -> str:
    tok = os.getenv("FOOTBALL_DATA_API_KEY")
    return tok.strip() if tok and tok.strip() else DEFAULT_API_TOKEN


def _sleep_with_msg(seconds: float):
    secs = max(0.0, float(seconds))
    print(f"[THROTTLE] Attendo {secs:.1f}s per rispetto rate-limit…", flush=True)
    time.sleep(secs)


def api_get(
    path: str, params: Dict, base_delay: float = 0.0, max_retries: int = 5
) -> Dict:
    if requests is None:
        raise RuntimeError("Richiede 'requests'. Installa: pip install requests")
    base = "https://api.football-data.org/v4"
    headers = {"X-Auth-Token": api_token()}
    attempt = 0
    while True:
        if base_delay > 0:
            time.sleep(base_delay)
        r = requests.get(base + path, headers=headers, params=params, timeout=30)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429 and attempt < max_retries:
            retry_after = r.headers.get("Retry-After")
            if retry_after:
                wait_s = float(retry_after)
            else:
                try:
                    msg = r.json().get("message", "")
                except Exception:
                    msg = r.text
                m = re.search(r"Wait\s+(\d+)\s+seconds", msg, re.IGNORECASE)
                wait_s = float(m.group(1)) if m else 60.0
            wait_s += random.uniform(0.1, 0.6)
            _sleep_with_msg(wait_s)
            attempt += 1
            continue
        raise RuntimeError(f"API error {r.status_code}: {r.text}")


# ---------------- DATA ACCESS ----------------
def list_matches_by_date(date_str: str, comps: List[str], delay: float) -> List[Dict]:
    params = {"date": date_str}
    if comps:
        params["competitions"] = ",".join(comps)
    data = api_get("/matches", params, base_delay=delay)
    return data.get("matches", [])


def comp_recent_matches_stats(
    comp_code: str, delay: float, limit: int = 150
) -> Tuple[float, float]:
    try:
        data = api_get(
            "/matches",
            {"competitions": comp_code, "status": "FINISHED", "limit": limit},
            base_delay=delay,
        )
        ms = data.get("matches", [])
        if not ms:
            return 2.5, 1.05
        goals, home_win = [], 0
        for m in ms:
            ft = (m.get("score", {}) or {}).get("fullTime", {}) or {}
            hg, ag = ft.get("home", 0) or 0, ft.get("away", 0) or 0
            goals.append(hg + ag)
            if hg > ag:
                home_win += 1
        avg_goals = sum(goals) / len(goals)
        home_rate = home_win / max(1, len(ms))
        hadv = 1.10 if home_rate >= 0.42 else (1.05 if home_rate >= 0.37 else 1.02)
        return round(avg_goals, 3), hadv
    except Exception:
        return 2.5, 1.05


def _iso_date(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


_team_cache: Dict[Tuple[int, str, str, int], List[Dict]] = {}


def team_recent_matches(
    team_id: Optional[int], comp_code: str, up_to_date: str, n: int, delay: float
) -> List[Dict]:
    if not team_id:
        return []
    key = (team_id, comp_code, up_to_date, n)
    if key in _team_cache:
        return _team_cache[key]
    try:
        date_to = datetime.fromisoformat(up_to_date[:10])
    except Exception:
        date_to = datetime.fromisoformat(up_to_date[:10])
    date_from = date_to - timedelta(days=180)
    base_params = {
        "status": "FINISHED",
        "dateFrom": _iso_date(date_from),
        "dateTo": _iso_date(date_to),
        "limit": 200,
    }
    params = dict(base_params)
    params["competitions"] = comp_code
    data = api_get(f"/teams/{team_id}/matches", params, base_delay=delay)
    matches = data.get("matches", [])
    if len(matches) < n:
        data2 = api_get(f"/teams/{team_id}/matches", base_params, base_delay=delay)
        matches2 = data2.get("matches", [])
        by_id = {}
        for m in matches + matches2:
            by_id[m.get("id")] = m
        matches = list(by_id.values())
    matches.sort(key=lambda m: m.get("utcDate", ""), reverse=True)
    matches = matches[:n]
    _team_cache[key] = matches
    return matches


def gf_ga_from_matches(
    team_id: Optional[int], matches: List[Dict]
) -> Tuple[float, float, str]:
    if not matches:
        return 1.2, 1.2, ""
    gf, ga, last_date = [], [], ""
    for m in matches:
        s = m.get("score", {}) or {}
        ft = s.get("fullTime", {}) or {}
        hg, ag = ft.get("home", 0) or 0, ft.get("away", 0) or 0
        home_team = (m.get("homeTeam", {}) or {}).get("id")
        if team_id and home_team == team_id:
            gf.append(hg)
            ga.append(ag)
        else:
            gf.append(ag)
            ga.append(hg)
        last_date = m.get("utcDate", last_date)
    return round(sum(gf) / len(gf), 3), round(sum(ga) / len(ga), 3), last_date


# ---------------- POISSON ----------------
def poisson_prob(lmbd: float, k: int) -> float:
    return (math.exp(-lmbd) * (lmbd**k)) / math.factorial(k)


def poisson_match_probs(
    lambda_home: float, lambda_away: float, max_goals: int = 6
) -> Tuple[float, float, float, float, float]:
    p1 = px = p2 = 0.0
    pover = punder = 0.0
    for hg in range(max_goals + 1):
        ph = poisson_prob(lambda_home, hg)
        for ag in range(max_goals + 1):
            pa = poisson_prob(lambda_away, ag)
            p = ph * pa
            if hg > ag:
                p1 += p
            elif hg == ag:
                px += p
            else:
                p2 += p
            if hg + ag > 2:
                pover += p
            else:
                punder += p
    tot = p1 + px + p2
    if tot > 0:
        p1, px, p2 = p1 / tot, px / tot, p2 / tot
    tot2 = pover + punder
    if tot2 > 0:
        pover, punder = pover / tot2, punder / tot2
    return round(p1, 4), round(px, 4), round(p2, 4), round(pover, 4), round(punder, 4)


# ---------------- UTIL ----------------
def fmt_pct(x: float) -> str:
    s = f"{x * 100:,.1f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def best_label_prob(p1: float, px: float, p2: float) -> Tuple[str, float]:
    m = max(p1, px, p2)
    if m == p1:
        return "1", p1
    if m == px:
        return "X", px
    return "2", p2


def write_csv(path: str, rows: List[Dict], cols: List[str], append: bool):
    if append and os.path.exists(path):
        try:
            df_old = pd.read_csv(path)
            df_new = pd.DataFrame(rows, columns=cols)
            missing = [c for c in df_new.columns if c not in df_old.columns]
            for c in missing:
                df_old[c] = ""
            extra = [c for c in df_old.columns if c not in df_new.columns]
            for c in extra:
                df_new[c] = ""
            df_all = pd.concat(
                [df_old[df_new.columns], df_new[df_new.columns]], ignore_index=True
            )
            df_all.to_csv(path, index=False)
            return
        except Exception:
            pass
    pd.DataFrame(rows, columns=cols).to_csv(path, index=False)


def render_html_report(
    date_str: str,
    picks_rows: List[Dict],
    pred_rows: List[Dict],
    out_path: Optional[str] = None,
) -> str:
    if out_path is None or not out_path.strip():
        out_path = f"report_{date_str.replace('-', '')}.html"
    headers = [
        "Data",
        "Ora",
        "Campionato",
        "Partita",
        "Pick",
        "Conf",
        "Segno Max",
        "Prob Max",
        "OU2.5 O/U",
        "BTTS",
    ]
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = []
    for r in picks_rows:
        tr = f"<tr><td>{r['date']}</td><td>{r['time']}</td><td>{r['league']}</td><td>{r['match']}</td><td>{r['pick']}</td><td>{r['conf']}</td><td>{r['best']}</td><td>{r['best_prob']}</td><td>{r.get('OU2.5', '')}</td><td>{r.get('BTTS', '')}</td></tr>"
        trs.append(tr)
    html = f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8"><title>Report {date_str}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,'Helvetica Neue',Arial,sans-serif;margin:24px;color:#111}}
h1{{margin:0 0 12px 0}}
table{{border-collapse:collapse;width:100%;}}
th,td{{border:1px solid #ddd;padding:8px;font-size:14px;vertical-align:top}}
th{{background:#f4f6f8;text-align:left}}
tr:nth-child(even){{background:#fafafa}}
.small{{color:#555;font-size:12px;margin-top:8px}}
code{{background:#f6f8fa;padding:2px 4px;border-radius:4px}}
</style></head><body>
<h1>Report previsioni — {date_str}</h1>
<table><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table>
<p class="small">Generato da <code>run_day.py</code>. Modello Poisson. Probabilità non incorporate con le quote.</p>
</body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


# ---------------- MAIN ----------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, help="YYYY-MM-DD")
    parser.add_argument("--comps", type=str, help="es. 'SA,PL,CL,PD'")
    parser.add_argument("--n_recent", type=int, default=5)
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="ritardo (s) tra chiamate per evitare 429",
    )
    parser.add_argument(
        "--append", action="store_true", help="accoda nei CSV invece di sovrascrivere"
    )
    parser.add_argument(
        "--html",
        nargs="?",
        const="AUTO",
        help="genera report HTML (facoltativo: path destinazione)",
    )
    args = parser.parse_args()

    if not args.date or not args.comps:
        print("== GIORNATA (estrazione + previsioni) ==")
        print("Legenda competizioni:\n" + LEGEND + "\n")
        date_str = input("Data (YYYY-MM-DD): ").strip()
        comps_in = input("Codici competizioni (es. SA,PL,CL): ").strip()
    else:
        date_str = args.date
        comps_in = args.comps

    comps = [c.strip().upper() for c in comps_in.split(",") if c.strip()]
    if not comps:
        print("Nessuna competizione valida.")
        sys.exit(1)

    # 1) fixtures
    matches = list_matches_by_date(date_str, comps, delay=args.delay)
    if not matches:
        print(f"Nessuna partita trovata il {date_str} per {comps}.")
        sys.exit(0)

    # 2) stats competizione
    comp_stats = {}
    for code in {(m.get("competition", {}) or {}).get("code", "") for m in matches}:
        if code:
            comp_stats[code] = comp_recent_matches_stats(
                code, delay=args.delay, limit=150
            )

    fixtures_rows, features_rows, pred_rows = [], [], []

    for m in matches:
        comp_code = (m.get("competition", {}) or {}).get("code", "")
        comp_name = COMP_MAP.get(
            comp_code, (m.get("competition", {}) or {}).get("name", comp_code)
        )
        utc_dt = (m.get("utcDate") or "")[:16]
        time_local = utc_dt[11:16] if len(utc_dt) >= 16 else ""
        home = ((m.get("homeTeam", {}) or {}).get("name", "") or "").strip()
        away = ((m.get("awayTeam", {}) or {}).get("name", "") or "").strip()
        home_id = (m.get("homeTeam", {}) or {}).get("id", None)
        away_id = (m.get("awayTeam", {}) or {}).get("id", None)
        match_id = f"{date_str.replace('-', '')}_{home.upper().replace(' ', '_')}_{away.upper().replace(' ', '_')}_{comp_name.upper().replace(' ', '_')}"

        recent_home = team_recent_matches(
            home_id, comp_code, date_str, n=args.n_recent, delay=args.delay
        )
        recent_away = team_recent_matches(
            away_id, comp_code, date_str, n=args.n_recent, delay=args.delay
        )
        gf_h, ga_h, last_h = gf_ga_from_matches(home_id, recent_home)
        gf_a, ga_a, last_a = gf_ga_from_matches(away_id, recent_away)

        def rest_days(last_iso: str):
            if not last_iso:
                return ""
            try:
                s = last_iso.replace("Z", "").replace("T", " ")
                last = datetime.fromisoformat(s[:19])
                game = datetime.fromisoformat(date_str + " 00:00:00")
                return max(0, (game - last).days)
            except Exception:
                return ""

        rest_h, rest_a = rest_days(last_h), rest_days(last_a)

        avg_goals, hadv = comp_stats.get(comp_code, (2.5, 1.05))
        base = max(1e-6, avg_goals / 2.0)
        lam_home_raw = (gf_h * ga_a) ** 0.5 if gf_h > 0 and ga_a > 0 else 1.0
        lam_away_raw = (gf_a * ga_h) ** 0.5 if gf_a > 0 and ga_h > 0 else 1.0
        lam_home = (lam_home_raw / 1.2) * base * hadv
        lam_away = (lam_away_raw / 1.2) * base

        p1, px, p2, pover, punder = poisson_match_probs(lam_home, lam_away, max_goals=6)

        def _ou_prob(line: float, max_goals: int = 10):
            over = 0.0
            for hg in range(max_goals + 1):
                ph = poisson_prob(lam_home, hg)
                for ag in range(max_goals + 1):
                    pa = poisson_prob(lam_away, ag)
                    if (hg + ag) > line:
                        over += ph * pa
            under = 1.0 - over
            return round(over, 4), round(under, 4)

        ou2_over, ou2_under = _ou_prob(2.0)
        ou25_over, ou25_under = _ou_prob(2.5)
        ou3_over, ou3_under = _ou_prob(3.0)

        from math import exp

        p_btts = 1 - exp(-lam_home) - exp(-lam_away) + exp(-(lam_home + lam_away))
        p_btts = round(p_btts, 4)
        p_nobtts = round(1 - p_btts, 4)

        p_1x = round(p1 + px, 4)
        p_x2 = round(p2 + px, 4)
        p_12 = round(p1 + p2, 4)
        p_dnb1 = round(p1, 4)
        p_dnb2 = round(p2, 4)

        grid = []
        for hg in range(0, 7):
            ph = poisson_prob(lam_home, hg)
            for ag in range(0, 7):
                pa = poisson_prob(lam_away, ag)
                grid.append((hg, ag, ph * pa))
        grid.sort(key=lambda x: x[2], reverse=True)
        cs_top3 = ", ".join([f"{hg}-{ag} ({prob:.3f})" for (hg, ag, prob) in grid[:3]])

        if p1 >= 0.60:
            pick, conf = "1", "high"
        elif p2 >= 0.60:
            pick, conf = "2", "high"
        elif p1 >= 0.45 or (p1 + px) >= 0.70:
            pick, conf = "1X", "medium"
        elif p2 >= 0.45 or (p2 + px) >= 0.70:
            pick, conf = "X2", "medium"
        else:
            pick, conf = ("X" if px == max(p1, px, p2) else "NoBet"), "low"

        fixtures_rows.append(
            {
                "match_id": match_id,
                "league": comp_name,
                "date": date_str,
                "time_local": time_local,
                "home": home,
                "away": away,
                "odds_1": "",
                "odds_x": "",
                "odds_2": "",
                "line_ou": "2.5",
                "odds_over": "",
                "odds_under": "",
            }
        )
        features_rows.append(
            {
                "match_id": match_id,
                "xG_for_5_home": gf_h,
                "xG_against_5_home": ga_h,
                "xG_for_5_away": gf_a,
                "xG_against_5_away": ga_a,
                "rest_days_home": rest_h,
                "rest_days_away": rest_a,
                "injuries_key_home": "",
                "injuries_key_away": "",
                "derby_flag": "0",
                "europe_flag_home": "1" if comp_code in ("CL", "EL", "EC") else "0",
                "europe_flag_away": "1" if comp_code in ("CL", "EL", "EC") else "0",
                "meteo_flag": "0",
                "style_ppda_home": "",
                "style_ppda_away": "",
                "travel_km_away": "",
            }
        )
        pred_rows.append(
            {
                "match_id": match_id,
                "p1": round(p1, 4),
                "px": round(px, 4),
                "p2": round(p2, 4),
                "line_ou": "2.5",
                "p_over": round(pover, 4),
                "p_under": round(punder, 4),
                "p_over_2.0": ou2_over,
                "p_under_2.0": ou2_under,
                "p_over_2.5": ou25_over,
                "p_under_2.5": ou25_under,
                "p_over_3.0": ou3_over,
                "p_under_3.0": ou3_under,
                "p_btts": p_btts,
                "p_nobtts": p_nobtts,
                "p_1x": p_1x,
                "p_x2": p_x2,
                "p_12": p_12,
                "p_dnb1": p_dnb1,
                "p_dnb2": p_dnb2,
                "cs_top3": cs_top3,
                "pick_main": pick,
                "confidence": conf,
            }
        )

    # --------- RIEPILOGO A VIDEO (tabellare) ---------
    def _fmt_pct(x: float) -> str:
        s = f"{x * 100:,.1f}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")

    rows_print = []
    pred_map = {p["match_id"]: p for p in pred_rows}
    for f in fixtures_rows:
        pr = pred_map.get(f["match_id"])
        if not pr:
            continue
        best_lbl, best_prob = best_label_prob(pr["p1"], pr["px"], pr["p2"])
        rows_print.append(
            {
                "date": f["date"],
                "time": f["time_local"] or "--:--",
                "league": f["league"],
                "match": f"{f['home']} – {f['away']}",
                "pick": pr["pick_main"],
                "conf": pr["confidence"],
                "best": best_lbl,
                "best_prob": _fmt_pct(best_prob),
                "OU2.5": _fmt_pct(pr["p_over_2.5"])
                + " OVR / "
                + _fmt_pct(pr["p_under_2.5"])
                + " UDR",
                "BTTS": _fmt_pct(pr["p_btts"]) + " YES",
            }
        )

    cols = [
        "date",
        "time",
        "league",
        "match",
        "pick",
        "conf",
        "best",
        "best_prob",
        "OU2.5",
        "BTTS",
    ]
    headers = {
        "date": "Data",
        "time": "Ora",
        "league": "Campionato",
        "match": "Partita",
        "pick": "Pick",
        "conf": "Conf",
        "best": "Segno Max",
        "best_prob": "Prob Max",
        "OU2.5": "OU2.5",
        "BTTS": "BTTS",
    }
    widths = {c: len(headers[c]) for c in cols}
    for r in rows_print:
        for c in cols:
            widths[c] = max(widths[c], len(str(r[c])))

    def _row_str(row_dict: dict) -> str:
        return " | ".join(str(row_dict[c]).ljust(widths[c]) for c in cols)

    print("\n=== RIEPILOGO PREVISIONI (tabella) ===")
    print(_row_str(headers))
    print("-" * (sum(widths.values()) + 3 * (len(cols) - 1)))
    for r in rows_print:
        print(_row_str(r))
    print(
        "\nLegenda: Pick = scelta prudente; Segno Max = 1/X/2 con prob. massima; OU2.5 = Over/Under 2.5; BTTS = entrambe segnano.\n"
    )

    # --------- PICKS ONLY CSV ---------
    picks_rows = []
    for r in rows_print:
        picks_rows.append(
            {
                "date": r["date"],
                "time_local": r["time"],
                "league": r["league"],
                "home": r["match"].split(" – ")[0],
                "away": r["match"].split(" – ")[1] if " – " in r["match"] else "",
                "pick_main": r["pick"],
                "confidence": r["conf"],
                "segno_max": r["best"],
                "prob_max": r["best_prob"],
                "ou25": r["OU2.5"],
                "btts": r["BTTS"],
            }
        )

    # --------- SALVATAGGI ---------
    write_csv("fixtures.csv", fixtures_rows, FIX_COLS, append=args.append)
    write_csv("features.csv", features_rows, FEA_COLS, append=args.append)
    write_csv("predictions.csv", pred_rows, PRED_COLS, append=args.append)
    write_csv(
        "picks_only.csv",
        picks_rows,
        [
            "date",
            "time_local",
            "league",
            "home",
            "away",
            "pick_main",
            "confidence",
            "segno_max",
            "prob_max",
            "ou25",
            "btts",
        ],
        append=args.append,
    )

    # --------- HTML REPORT (opzionale) ---------
    if args.html is not None:
        out_path = None if args.html == "AUTO" else args.html
        html_path = render_html_report(
            date_str, rows_print, pred_rows, out_path=out_path
        )
        print(f"[OK] Report HTML: {html_path}")

    print(
        f"[OK] Scritti {len(fixtures_rows)} match per {date_str}. File: fixtures.csv, features.csv, predictions.csv, picks_only.csv"
    )
    if pred_rows:
        print(json.dumps(pred_rows[0], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
