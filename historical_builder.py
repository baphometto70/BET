#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
historical_builder.py
---------------------
Costruisce un dataset STORICO completo per training ML usando SOLO fonti gratuite:

- Risultati + Closing Odds 1X2 (football-data.co.uk, per leghe nazionali)
- Feature xG ultime N (Understat scraping + cache locale)
- Rest days (calcolati dall’ultima gara Understat)
- Meteo flag (Open-Meteo, opzionale via dizionario stadi)
- Target: OU2.5, BTTS, 1X2 (derivati dai gol finali)

Output: data/historical_dataset.csv

USO:
  python historical_builder.py --from 2023-07-01 --to 2025-06-30 --comps "SA,PL,PD,BL1" --n_recent 5 --delay 0.5

Dipendenze:
  pip install pandas requests beautifulsoup4 lxml rapidfuzz

Note:
- Evita di usare football-data.org (token) per lo storico: per risultati/quote le CSV di football-data.co.uk bastano e sono gratis.
- Understat scraping usa cache/understat/ e un mapping auto-apprendente in data/team_map.json
"""

from __future__ import annotations

import io
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from rapidfuzz import fuzz, process

UA = {"User-Agent": "Mozilla/5.0 (compatible; HistBuilder/1.0)"}

# ---------- CONFIG ----------
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True, parents=True)
CACHE_DIR = Path("cache/understat")
CACHE_DIR.mkdir(exist_ok=True, parents=True)
LEAGUE_TEAMS_DIR = CACHE_DIR / "leagues"
LEAGUE_TEAMS_DIR.mkdir(exist_ok=True, parents=True)
TEAM_MAP_FILE = DATA_DIR / "team_map.json"

OUT_CSV = DATA_DIR / "historical_dataset.csv"
OUT_CSV_1X2 = DATA_DIR / "historical_1x2.csv"

COMP_MAP = {
    "PL": "Premier League",
    "SA": "Serie A",
    "PD": "Primera Division",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
    "DED": "Eredivisie",
    "PPL": "Primeira Liga",
    "ELC": "Championship (ENG)",
}

# football-data.co.uk codici
FD_LEAGUE_CODE = {
    "PL": "E0",
    "SA": "I1",
    "PD": "SP1",
    "BL1": "D1",
    "FL1": "F1",
    "DED": "N1",
    "PPL": "P1",
    "ELC": "E1",
}

# Understat slug per leghe (serve per elenco squadre/fuzzy)
UNDERSTAT_LEAGUE = {
    "SA": "Serie_A",
    "PL": "EPL",
    "PD": "La_Liga",
    "BL1": "Bundesliga",
    "FL1": "Ligue_1",
    "DED": "Eredivisie",
    "PPL": "Primeira_Liga",
}

# Dizionario rudimentale stadi (per meteo_flag; opzionale)
STADIUMS = {
    "Napoli": (40.827, 14.193),
    "Arsenal": (51.555, -0.108),
    "Atletico Madrid": (40.436, -3.599),
    "Liverpool": (53.430, -2.961),
    "Real Madrid": (40.453, -3.688),
    "Juventus": (45.109, 7.641),
    "PSG": (48.841, 2.253),
    "Bayern Munich": (48.218, 11.624),
    "Inter": (45.478, 9.123),
    "Milan": (45.478, 9.123),
    "Roma": (41.934, 12.454),
    "Lazio": (41.934, 12.454),
    "Fiorentina": (43.780, 11.283),
    "Atalanta": (45.712, 9.676),
    "Torino": (45.041, 7.652),
    "Bologna": (44.493, 11.309),
    "Genoa": (44.416, 8.952),
    "Sampdoria": (44.416, 8.952),
    "Udinese": (46.081, 13.201),
    "Verona": (45.439, 10.968),
}

SEED_UNDERSTAT_NAME_MAP = {
    "SSC Napoli": "Napoli",
    "Eintracht Frankfurt": "Eintracht Frankfurt",
    "Arsenal FC": "Arsenal",
    "Club Atlético de Madrid": "Atletico Madrid",
    "Liverpool FC": "Liverpool",
    "Real Madrid CF": "Real Madrid",
    "Juventus FC": "Juventus",
    "Paris Saint-Germain FC": "PSG",
    "FC Bayern München": "Bayern Munich",
}

FEA_COLS = [
    "xg_for_home",
    "xg_against_home",
    "xg_for_away",
    "xg_against_away",
    "rest_days_home",
    "rest_days_away",
    "derby_flag",
    "europe_flag_home",
    "europe_flag_away",
    "meteo_flag",
    "style_ppda_home",
    "style_ppda_away",
    "travel_km_away",
]


# ---------- UTILS ----------
def _ascii_clean(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def _norm_team(s: str) -> str:
    s = _ascii_clean(str(s))
    s = re.sub(r"\s+", " ", s).strip().lower()
    s = re.sub(r"\b(fc|cf|afc|sc|bk|ac|bc|calcio|sfp)\b\.?", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def season_from_date(date_iso: str) -> int:
    dt = datetime.fromisoformat(date_iso)
    return dt.year if dt.month >= 7 else dt.year - 1


def fd_season_token(date_iso: str) -> str:
    dt = datetime.fromisoformat(date_iso)
    start = dt.year if dt.month >= 7 else dt.year - 1
    end = start + 1
    return f"{str(start)[-2:]}{str(end)[-2:]}"


def fd_url_for(code: str, date_iso: str) -> Optional[str]:
    sig = FD_LEAGUE_CODE.get(code)
    if not sig:
        return None
    season = fd_season_token(date_iso)
    return f"https://www.football-data.co.uk/mmz4281/{season}/{sig}.csv"


def understat_team_url(team: str, date_iso: str) -> str:
    season = season_from_date(date_iso)
    from urllib.parse import quote

    return f"https://understat.com/team/{quote(team)}/{season}"


def _cache_path(team: str, date_iso: str) -> Path:
    season = season_from_date(date_iso)
    safe = re.sub(r"[^A-Za-z0-9_\-\.]", "_", team)
    return CACHE_DIR / f"{safe}_{season}.html"


def _extract_json_from_understat(html: str, varname: str) -> Optional[list]:
    """
    Estrae un oggetto JSON da una variabile JavaScript all'interno di un tag <script> nel codice HTML.
    È progettato per essere robusto a cambiamenti minori nel formato della pagina.
    """
    # Cerca il tag <script> che contiene la variabile per restringere la ricerca
    script_tag_pattern = re.compile(rf"<script>.*?\b{re.escape(varname)}\b.*?</script>", re.DOTALL)
    match = script_tag_pattern.search(html)
    
    if not match:
        return None
        
    script_content = match.group(0)

    # Cerca il pattern di assegnazione della variabile.
    data_pattern = re.search(
        rf"\b{re.escape(varname)}\s*=\s*(?:JSON\.parse\(\s*'((?:\\.|[^'])*)'\s*\)|(\[.*?\]|\{{.*?\}}))\s*;?",
        script_content,
        re.DOTALL
    )

    if not data_pattern:
        return None

    escaped_json_str = data_pattern.group(1)
    literal_json_str = data_pattern.group(2)

    json_to_parse = None
    if escaped_json_str:
        try:
            json_to_parse = bytes(escaped_json_str, "utf-8").decode("unicode_escape")
        except Exception:
            return None
    elif literal_json_str:
        json_to_parse = literal_json_str

    if json_to_parse:
        try:
            return json.loads(json_to_parse)
        except json.JSONDecodeError:
            return None
            
    return None


def load_team_map() -> Dict[str, str]:
    mp = SEED_UNDERSTAT_NAME_MAP.copy()
    if TEAM_MAP_FILE.exists():
        try:
            mp.update(json.loads(TEAM_MAP_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return mp


def save_team_map(mp: Dict[str, str]):
    try:
        TEAM_MAP_FILE.write_text(
            json.dumps(mp, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def fetch_league_teams(code: str, date_iso: str, delay: float = 0.0) -> List[str]:
    slug = UNDERSTAT_LEAGUE.get(code)
    if not slug:
        return []
    season = season_from_date(date_iso)
    url = f"https://understat.com/league/{slug}/{season}"
    pth = LEAGUE_TEAMS_DIR / f"{code}_{season}.json"
    if pth.exists():
        try:
            return json.loads(pth.read_text(encoding="utf-8"))
        except Exception:
            pass
    try:
        r = requests.get(url, headers=UA, timeout=30)
        r.raise_for_status()
        html = r.text
        teams = _extract_json_from_understat(html, "teamsData")
        names = []
        if teams and isinstance(teams, list):
            for t in teams:
                nm = t.get("title") or t.get("team_name") or t.get("label")
                if nm and nm not in names:
                    names.append(nm)
        if not names:
            for m in re.finditer(r'"title"\s*:\s*"([^"]+)"', html):
                nm = m.group(1).strip()
                if nm and nm not in names:
                    names.append(nm)
        pth.write_text(
            json.dumps(names, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if delay > 0:
            time.sleep(delay)
        return names
    except Exception:
        return []


def resolve_understat_name(
    api_name: str,
    date_iso: str,
    comp_code: Optional[str],
    team_map: Dict[str, str],
    league_cache: Dict[str, List[str]],
    delay: float,
) -> Optional[str]:
    if api_name in team_map:
        return team_map[api_name]
    # Trial varianti “ragionevoli”
    variants = [api_name]
    base = re.sub(r"\s+", " ", api_name).strip()
    if base not in variants:
        variants.append(base)
    ascii_base = _ascii_clean(base)
    if ascii_base not in variants:
        variants.append(ascii_base)
    short = re.sub(r"\s+(FC|CF|SFP|AC|BC)$", "", base, flags=re.I).strip()
    if short not in variants:
        variants.append(short)

    for cand in variants:
        url = understat_team_url(cand, date_iso)
        cp = _cache_path(cand, date_iso)
        html = cp.read_text(encoding="utf-8") if cp.exists() else None
        if html is None:
            try:
                rr = requests.get(url, headers=UA, timeout=30)
                if rr.status_code == 404:
                    continue
                rr.raise_for_status()
                html = rr.text
                cp.write_text(html, encoding="utf-8")
                if delay > 0:
                    time.sleep(delay)
            except Exception:
                continue
        if _extract_json_from_understat(html, "matchesData"):
            team_map[api_name] = cand
            save_team_map(team_map)
            return cand

    # Fuzzy su elenco lega
    if comp_code:
        if comp_code not in league_cache:
            league_cache[comp_code] = fetch_league_teams(comp_code, date_iso, delay)
        names = league_cache.get(comp_code, [])
        if names:
            best = process.extractOne(api_name, names, scorer=fuzz.WRatio)
            if best and best[1] >= 85:
                cand = best[0]
                # verifica
                url = understat_team_url(cand, date_iso)
                cp = _cache_path(cand, date_iso)
                html = cp.read_text(encoding="utf-8") if cp.exists() else None
                if html is None:
                    try:
                        rr = requests.get(url, headers=UA, timeout=30)
                        rr.raise_for_status()
                        html = rr.text
                        cp.write_text(html, encoding="utf-8")
                        if delay > 0:
                            time.sleep(delay)
                    except Exception:
                        html = None
                if html and _extract_json_from_understat(html, "matchesData"):
                    team_map[api_name] = cand
                    save_team_map(team_map)
                    return cand
    return None


def compute_xg_and_rest(
    team_understat: str, date_iso: str, n: int, delay: float
) -> Tuple[float, float, Optional[datetime]]:
    if not team_understat:
        return (1.2, 1.2, None)
    url = understat_team_url(team_understat, date_iso)
    cp = _cache_path(team_understat, date_iso)
    html = cp.read_text(encoding="utf-8") if cp.exists() else None
    if html is None:
        try:
            r = requests.get(url, headers=UA, timeout=30)
            r.raise_for_status()
            html = r.text
            cp.write_text(html, encoding="utf-8")
            if delay > 0:
                time.sleep(delay)
        except Exception:
            return (1.2, 1.2, None)
    data = _extract_json_from_understat(html, "matchesData")
    if not data:
        return (1.2, 1.2, None)
    cut = datetime.fromisoformat(date_iso)
    rows = []
    for m in data:
        d = m.get("date")
        try:
            dt = datetime.strptime(d, "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        if dt.date() > cut.date():
            continue
        xg = float(m.get("xG", 0.0) or 0.0)
        xga = float(m.get("xGA", 0.0) or 0.0)
        rows.append((dt, xg, xga))
    rows.sort(key=lambda r: r[0], reverse=True)
    last_dt = rows[0][0] if rows else None
    rows = rows[: max(1, n)]
    if not rows:
        return (1.2, 1.2, last_dt)

    # Calcola una media pesata: le partite più recenti hanno più peso.
    # Questo crea una feature di "forma" più reattiva per il training.
    weights = list(range(len(rows), 0, -1))
    total_weight = sum(weights)

    if total_weight > 0:
        xg_avg = sum(r[1] * w for r, w in zip(rows, weights)) / total_weight
        xga_avg = sum(r[2] * w for r, w in zip(rows, weights)) / total_weight
    else:
        # Fallback a media semplice
        xg_avg = sum(r[1] for r in rows) / len(rows)
        xga_avg = sum(r[2] for r in rows) / len(rows)

    return (round(xg_avg, 3), round(xga_avg, 3), last_dt)


def openmeteo_flag(lat: float, lon: float, kickoff_iso: str) -> str:
    try:
        dt = datetime.fromisoformat(kickoff_iso)
    except Exception:
        return "0"
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "precipitation,wind_speed_10m",
        "start": (dt - timedelta(hours=2)).strftime("%Y-%m-%dT%H:00"),
        "end": (dt + timedelta(hours=2)).strftime("%Y-%m-%dT%H:00"),
        "timezone": "UTC",
    }
    try:
        r = requests.get(url, params=params, headers=UA, timeout=30)
        if r.status_code != 200:
            return "0"
        h = r.json().get("hourly", {})
        prec = h.get("precipitation", []) or []
        wind = h.get("wind_speed_10m", []) or []
        if any((p or 0) >= 2.0 for p in prec) or any((w or 0) >= 9.0 for w in wind):
            return "1"
        return "0"
    except Exception:
        return "0"


def europe_flag_from_league(league_name: str) -> str:
    if not league_name:
        return "0"
    up = league_name.upper()
    return (
        "1"
        if any(k in up for k in ("CHAMPIONS", "EUROPA", "EUROPEAN CHAMPIONSHIP"))
        else "0"
    )


# ---------- FOOTBALL-DATA.CO.UK ----------
def fetch_fd_csv(
    code: str, example_date_iso: str, delay: float = 0.0
) -> Optional[pd.DataFrame]:
    url = fd_url_for(code, example_date_iso)
    if not url:
        return None
    try:
        r = requests.get(url, headers=UA, timeout=30)
        if r.status_code != 200:
            print(f"[FD] {code} -> HTTP {r.status_code}")
            return None
        if delay > 0:
            time.sleep(delay)
        df = pd.read_csv(io.StringIO(r.text))
        return df
    except Exception as e:
        print(f"[FD] errore {code}: {e}")
        return None


def parse_fd_date(s: str) -> Optional[str]:
    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(s), fmt).date().isoformat()
        except Exception:
            pass
    return None


# ---------- COSTRUZIONE STORICO ----------
def build_historical(
    date_from: str, date_to: str, comps: List[str], n_recent: int, delay: float
):
    # step 1: scarica csv stagione per ogni lega (basta usare date_to per determinare cartella)
    all_rows = []

    league_team_cache: Dict[str, List[str]] = {}
    team_map = load_team_map()

    for code in comps:
        if code not in FD_LEAGUE_CODE:
            print(f"[SKIP] {code}: non supportato da football-data.co.uk")
            continue
        # prendi tutte le stagioni comprese tra date_from e date_to
        start_season = season_from_date(date_from)
        end_season = season_from_date(date_to)
        seasons = list(range(start_season, end_season + 1))
        if not seasons:
            seasons = [season_from_date(date_to)]

        for season in seasons:
            print(f"[FD] Scarico {code} stagione {season}/{season+1}...")
            season_ref = f"{season}-08-01"
            fd = fetch_fd_csv(code, season_ref, delay=delay)
            if fd is None or fd.empty:
                print(f"[FD] {code} stagione {season}/{season+1} non disponibile.")
                continue

            # normalizza subset utile
            cols = fd.columns
            # colonne tipiche: Date, HomeTeam, AwayTeam, FTHG, FTAG, AvgH, AvgD, AvgA, B365H/B365D/B365A, Time opzionale
            keep = [
                c
                for c in [
                    "Date",
                    "Time",
                    "HomeTeam",
                    "AwayTeam",
                    "FTHG",
                    "FTAG",
                    "AvgH",
                    "AvgD",
                    "AvgA",
                    "B365H",
                    "B365D",
                    "B365A",
                ]
                if c in cols
            ]
            g = fd[keep].copy()
            g["date_iso"] = g["Date"].apply(parse_fd_date)
            g = g[(g["date_iso"] >= date_from) & (g["date_iso"] <= date_to)]
            if g.empty:
                continue

            league_name = COMP_MAP.get(code, code)

            # crea record base
            for _, r in g.iterrows():
                d = r.get("date_iso")
                if not d:
                    continue
                ht = str(r.get("HomeTeam", "")).strip()
                at = str(r.get("AwayTeam", "")).strip()
                if not ht or not at:
                    continue
                time_local = (
                    str(r.get("Time", "15:00")).strip()
                    if "Time" in g.columns
                    else "15:00"
                )

                # match_id stile progetto
                mid = f"{d.replace('-', '')}_{re.sub(r'[^A-Z0-9]+', '_', ht.upper())}_{re.sub(r'[^A-Z0-9]+', '_', at.upper())}_{re.sub(r'[^A-Z0-9]+', '_', league_name.upper())}"

                # risultati
                fthg = r.get("FTHG", None)
                ftag = r.get("FTAG", None)

                # odds 1X2 (preferisci Avg*, poi B365*)
                odds1 = r.get("AvgH", None) if "AvgH" in g.columns else None
                oddsx = r.get("AvgD", None) if "AvgD" in g.columns else None
                odds2 = r.get("AvgA", None) if "AvgA" in g.columns else None
                if (odds1 is None or pd.isna(odds1)) and "B365H" in g.columns:
                    odds1 = r.get("B365H", None)
                    oddsx = r.get("B365D", None)
                    odds2 = r.get("B365A", None)

                rec = {
                    "match_id": mid,
                    "date": d,
                    "time_local": time_local,
                    "league": league_name,
                    "home": ht,
                    "away": at,
                    "ft_home_goals": pd.to_numeric(fthg, errors="coerce"),
                    "ft_away_goals": pd.to_numeric(ftag, errors="coerce"),
                    "odds_1": pd.to_numeric(odds1, errors="coerce"),
                    "odds_x": pd.to_numeric(odsx := oddsx, errors="coerce"),
                    "odds_2": pd.to_numeric(odds2, errors="coerce"),
                }
                all_rows.append(rec)

    if not all_rows:
        print("[ERR] Nessun dato trovato nelle leghe/dati indicati.")
        sys.exit(1)

    base = pd.DataFrame(all_rows).drop_duplicates(subset=["match_id"])

    # target derivati
    base["target_ou25"] = (
        (base["ft_home_goals"].fillna(0) + base["ft_away_goals"].fillna(0)) > 2
    ).astype(int)
    base["target_btts"] = (
        (base["ft_home_goals"].fillna(0) > 0) & (base["ft_away_goals"].fillna(0) > 0)
    ).astype(int)
    base["target_1x2"] = pd.Series(0, index=base.index)
    base.loc[base["ft_home_goals"] == base["ft_away_goals"], "target_1x2"] = 1
    base.loc[base["ft_home_goals"] < base["ft_away_goals"], "target_1x2"] = 2

    # feature xG/rest_days/meteo
    features_rows = []
    league_cache: Dict[str, List[str]] = {}

    comps_set = set([c.strip().upper() for c in comps])

    for i, r in base.iterrows():
        d = r["date"]
        ht = r["home"]
        at = r["away"]
        league = r["league"]
        # deduci comp_code per fuzzy Understat (se presente)
        comp_code = None
        for k, v in COMP_MAP.items():
            if v == league:
                comp_code = k
                break

        # risolvi nomi understat
        home_us = resolve_understat_name(
            ht, d, comp_code, team_map, league_cache, delay
        )
        away_us = resolve_understat_name(
            at, d, comp_code, team_map, league_cache, delay
        )

        hxg_f, hxg_a, h_last_dt = compute_xg_and_rest(home_us, d, n_recent, delay)
        axg_f, axg_a, a_last_dt = compute_xg_and_rest(away_us, d, n_recent, delay)

        def _rest_days(last_dt: Optional[datetime], game_date: str) -> str:
            if not last_dt:
                return ""
            try:
                g = datetime.fromisoformat(game_date + " 00:00:00")
            except Exception:
                return ""
            return str(max(0, (g - last_dt).days))

        rest_h = _rest_days(h_last_dt, d)
        rest_a = _rest_days(a_last_dt, d)

        eflag = "0"  # competizione domestica -> 0
        meteo = "0"
        latlon = STADIUMS.get(home_us or ht)
        if latlon:
            try:
                meteo = openmeteo_flag(
                    latlon[0], latlon[1], f"{d}T{(r.get('time_local') or '15:00')}"
                )
            except Exception:
                meteo = "0"

        features_rows.append(
            {
                "match_id": r["match_id"],
                "xg_for_home": hxg_f,
                "xg_against_home": hxg_a,
                "xg_for_away": axg_f,
                "xg_against_away": axg_a,
                "rest_days_home": rest_h,
                "rest_days_away": rest_a,
                "derby_flag": "0",
                "europe_flag_home": eflag,
                "europe_flag_away": eflag,
                "meteo_flag": meteo,
                "style_ppda_home": "",
                "style_ppda_away": "",
                "travel_km_away": "",
            }
        )

    fea = pd.DataFrame(features_rows)
    out = base.merge(fea, on="match_id", how="left")

    # ordine colonne finale
    cols = [
        "match_id",
        "date",
        "time_local",
        "league",
        "home",
        "away",
        "ft_home_goals",
        "ft_away_goals",
        "odds_1",
        "odds_x",
        "odds_2",
        "xg_for_home",
        "xg_against_home",
        "xg_for_away",
        "xg_against_away",
        "rest_days_home",
        "rest_days_away",
        "derby_flag",
        "europe_flag_home",
        "europe_flag_away",
        "meteo_flag",
        "style_ppda_home",
        "style_ppda_away",
        "travel_km_away",
        "target_ou25",
        "target_btts",
        "target_1x2",
    ]
    for c in cols:
        if c not in out.columns:
            out[c] = ""
    out = out[cols]

    out.to_csv(OUT_CSV, index=False)
    out.to_csv(OUT_CSV_1X2, index=False)
    print(f"[OK] Storico scritto: {OUT_CSV} ({len(out)} righe)")
    print(f"[OK] Storico 1X2 scritto: {OUT_CSV_1X2} ({len(out)} righe)")


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD")
    ap.add_argument("--comps", required=True, help="es. 'SA,PL,PD,BL1'")
    ap.add_argument("--n_recent", type=int, default=5, help="xG medie ultime N")
    ap.add_argument("--delay", type=float, default=0.0, help="ritardo scraping (s)")
    args = ap.parse_args()

    comps = [c.strip().upper() for c in args.comps.split(",") if c.strip()]
    build_historical(args.date_from, args.date_to, comps, args.n_recent, args.delay)


if __name__ == "__main__":
    main()
