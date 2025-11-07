#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
odds_fetcher.py — TheOddsAPI v4 (h2h + totals) -> aggiorna fixtures.csv con 1X2 e OU2.5.

Uso:
  python odds_fetcher.py --date 2025-11-05 --comps "CL,SA,PL" --delay 0.3 [--verbose]

Token:
  in config.toml ([api].theoddsapi_key) oppure env THEODDSAPI_KEY
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import requests
from unidecode import unidecode

ROOT = Path(__file__).resolve().parent
FIX_PATH = ROOT / "fixtures.csv"
CONF_PATH = ROOT / "config.toml"

SPORT_KEY = {
    "SA": "soccer_italy_serie_a",
    "PL": "soccer_epl",
    "PD": "soccer_spain_la_liga",
    "BL1": "soccer_germany_bundesliga",
    "FL1": "soccer_france_ligue_one",
    "DED": "soccer_netherlands_eredivisie",
    "PPL": "soccer_portugal_primeira_liga",
    "ELC": "soccer_efl_champ",
    "CL": "soccer_uefa_champs_league",
    "EL": "soccer_uefa_europa_league",
}

BASE_URL = "https://api.the-odds-api.com/v4/sports/{sport}/odds"

# alias per i nomi “capricciosi”
ALIASES = {
    "athletic club": "athletic bilbao",
    "athletic bilbao": "athletic bilbao",
    "club brugge kv": "club brugge",
    "bayer 04 leverkusen": "bayer leverkusen",
    "fc barcelona": "barcelona",
    "manchester city fc": "manchester city",
    "newcastle united fc": "newcastle united",
    "olympique de marseille": "marseille",
    "fc internazionale milano": "inter milan",
    "inter": "inter milan",
    "inter milano": "inter milan",
    "qarabag agdam fk": "qarabag",
    "paphos": "pafos",
    "paphos fc": "pafos",
    "pafos fc": "pafos",
    "galatasaray sk": "galatasaray",
    "psg": "paris saint-germain",
    "real sociedad de futbol": "real sociedad",
    "athletic club de bilbao": "athletic bilbao",
    "villarreal cf": "villarreal",
}


def read_api_key() -> str:
    if CONF_PATH.exists():
        try:
            import tomllib

            data = tomllib.loads(CONF_PATH.read_text(encoding="utf-8"))
            key = data.get("api", {}).get("theoddsapi_key", "")
            if key:
                return key
        except Exception:
            pass
    key = os.getenv("THEODDSAPI_KEY", "")
    if key:
        return key
    raise RuntimeError(
        "TheOddsAPI key non trovata. Mettila in config.toml ([api].theoddsapi_key) o in THEODDSAPI_KEY."
    )


def norm_team(name: str) -> str:
    if not isinstance(name, str):
        return ""
    n = unidecode(name).lower()
    junk = [
        " fc",
        " cf",
        " ssc",
        " bc",
        " kv",
        " as ",
        " ac ",
        " club",
        " sc",
        " afc",
        " sfp",
        ".",
        ",",
        "-",
        "_",
    ]
    for j in junk:
        n = n.replace(j, " ")
    n = " ".join(n.split())
    if n in ALIASES:
        n = ALIASES[n]
    return n


def tokens(s: str) -> set[str]:
    return set([t for t in s.split() if t])


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    uni = len(a | b)
    return inter / uni if uni else 0.0


def pick_best_decimal(prices: List[float]) -> float | None:
    prices = [float(p) for p in prices if p and isinstance(p, (int, float)) and p > 1]
    return max(prices) if prices else None


def fetch_odds_for_sport(sport_key: str, api_key: str) -> List[Dict[str, Any]]:
    params = {
        "apiKey": api_key,
        "regions": "eu,uk,us,au",
        "markets": "h2h,totals",
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    url = BASE_URL.format(sport=sport_key)
    r = requests.get(url, params=params, timeout=30)
    if r.status_code == 429:
        raise RuntimeError(f"HTTP 429 TheOddsAPI: {r.text}")
    r.raise_for_status()
    return r.json()


def extract_h2h(
    bookmakers: List[Dict[str, Any]], home_name: str, away_name: str
) -> Dict[str, float | None]:
    """Gli esiti h2h hanno i NOMI DELLE SQUADRE, non 'home/away'. Mappiamo per confronto stringa."""
    odds_home, odds_draw, odds_away = [], [], []
    # normalizzati per confronto robusto
    nh = norm_team(home_name)
    na = norm_team(away_name)
    for bk in bookmakers:
        for m in bk.get("markets", []):
            if m.get("key") != "h2h":
                continue
            for o in m.get("outcomes", []):
                nm = norm_team(o.get("name", ""))
                pr = o.get("price", None)
                if not pr:
                    continue
                if nm == nh:
                    odds_home.append(pr)
                elif nm == na:
                    odds_away.append(pr)
                elif nm in ("draw", "tie"):
                    odds_draw.append(pr)
    return {
        "odds_1": pick_best_decimal(odds_home),
        "odds_x": pick_best_decimal(odds_draw),
        "odds_2": pick_best_decimal(odds_away),
    }


def extract_totals_25(bookmakers: List[Dict[str, Any]]) -> Dict[str, float | None]:
    lines: dict[float, dict[str, list[float]]] = {}
    for bk in bookmakers:
        for m in bk.get("markets", []):
            if m.get("key") != "totals":
                continue
            for o in m.get("outcomes", []):
                try:
                    lbl = o.get("name")
                    pt = float(o.get("point"))
                    pr = float(o.get("price"))
                    lines.setdefault(pt, {}).setdefault(lbl, []).append(pr)
                except Exception:
                    continue
    if not lines:
        return {"odds_ou25_over": None, "odds_ou25_under": None}
    if 2.5 in lines:
        over = pick_best_decimal(lines[2.5].get("Over", []))
        under = pick_best_decimal(lines[2.5].get("Under", []))
    else:
        best = sorted(lines.keys(), key=lambda x: abs(x - 2.5))[0]
        over = pick_best_decimal(lines[best].get("Over", []))
        under = pick_best_decimal(lines[best].get("Under", []))
    return {"odds_ou25_over": over, "odds_ou25_under": under}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--comps", required=True)
    ap.add_argument("--delay", default="0.3")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not FIX_PATH.exists():
        raise SystemExit("fixtures.csv mancante. Esegui prima run_day.py.")

    api_key = read_api_key()
    df = pd.read_csv(FIX_PATH)

    for need in ["odds_1", "odds_x", "odds_2", "odds_ou25_over", "odds_ou25_under"]:
        if need not in df.columns:
            df[need] = pd.NA
    df["__hn"] = df["home"].map(norm_team)
    df["__an"] = df["away"].map(norm_team)
    df["__htok"] = df["__hn"].map(tokens)
    df["__atok"] = df["__an"].map(tokens)

    comps = [c.strip().upper() for c in args.comps.split(",") if c.strip()]
    delay = float(args.delay)

    touched = 0
    not_matched: list[tuple[str, str, str]] = []

    for comp in comps:
        sport = SPORT_KEY.get(comp)
        if not sport:
            print(f"[WARN] Competizione non supportata: {comp}")
            continue
        print(f"[TOA] fetching {sport} …")
        try:
            games = fetch_odds_for_sport(sport, api_key)
        except RuntimeError as e:
            print(str(e))
            time.sleep(2.0)
            continue

        day_mask = (df["date"] == args.date) & (
            df["league"].str.contains(
                "Champions"
                if comp == "CL"
                else "Serie A"
                if comp == "SA"
                else "Premier"
                if comp == "PL"
                else "Primera"
                if comp == "PD"
                else "Bundesliga"
                if comp == "BL1"
                else "",
                case=False,
            )
        )
        day_ix = df.index[day_mask]

        for g in games:
            home_name = g.get("home_team", "")
            away_name = g.get("away_team", "")
            gh = norm_team(home_name)
            ga = norm_team(away_name)
            ht = tokens(gh)
            at = tokens(ga)
            if not gh or not ga:
                continue

            # 1) match esatto
            mask = (df.loc[day_ix, "__hn"] == gh) & (df.loc[day_ix, "__an"] == ga)
            idx = df.loc[day_ix].index[mask]

            # 2) similarità token (Jaccard >= 0.6)
            if len(idx) == 0:
                sims = []
                for i in day_ix:
                    sc = 0.5 * jaccard(ht, df.at[i, "__htok"]) + 0.5 * jaccard(
                        at, df.at[i, "__atok"]
                    )
                    sims.append((sc, i))
                sims.sort(reverse=True)
                if sims and sims[0][0] >= 0.6:
                    idx = [sims[0][1]]

            # 3) swap
            if len(idx) == 0:
                sims = []
                for i in day_ix:
                    sc = 0.5 * jaccard(at, df.at[i, "__htok"]) + 0.5 * jaccard(
                        ht, df.at[i, "__atok"]
                    )
                    sims.append((sc, i))
                sims.sort(reverse=True)
                if sims and sims[0][0] >= 0.6:
                    idx = [sims[0][1]]

            if len(idx) == 0:
                not_matched.append((comp, gh, ga))
                if args.verbose:
                    print(f"[MISS] {comp}: '{gh}' vs '{ga}'")
                continue

            # --- h2h con mapping per nome squadra ---
            prices_h2h = extract_h2h(g.get("bookmakers", []), home_name, away_name)
            prices_ou25 = extract_totals_25(g.get("bookmakers", []))
            for col, val in {**prices_h2h, **prices_ou25}.items():
                if val is not None:
                    df.loc[idx, col] = float(val)
            touched += 1

        time.sleep(delay)

    df.drop(columns=["__hn", "__an", "__htok", "__atok"], inplace=True)
    df.to_csv(FIX_PATH, index=False)

    print(f"[OK] Quote aggiornate in fixtures.csv — righe toccate: {touched}")
    if not_matched:
        print("[INFO] Fixture non matchate:")
        for comp, h, a in not_matched:
            print(f"  - {comp}: {h}  vs  {a}")


if __name__ == "__main__":
    main()
