#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
features_populator.py (FREE SOURCES, AUTO-LEARNING)
---------------------------------------------------
Popola/aggiorna features.csv partendo da fixtures.csv usando SOLO fonti gratuite:

- xG medie ultime N gare per squadra da Understat (scraping leggero + cache locale)
- rest_days basati sulla data dell’ultima gara (sempre da Understat)
- meteo_flag (0/1) con Open-Meteo SE conosciamo lat/lon dello stadio (dizionario interno)
- AUTO-LEARNING nomi: salva in data/team_map.json i mapping scoperti
- REFRESH leghe: scarica l’elenco squadre di una lega/stagione e usa fuzzy match

USO tipico:
  python features_populator.py --date 2025-11-05 --comps "SA,PL,CL" --n_recent 5 --delay 0.6 --cache 1 --learn-map 1

Prima della stagione:
  python features_populator.py --date 2026-08-24 --comps "SA,PL,PD" --refresh-leagues 1 --cache 1

Dipendenze:
  pip install requests pandas beautifulsoup4 lxml rapidfuzz
"""

import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import pandas as pd
import requests
from rapidfuzz import fuzz, process

# bs4/lxml tenuti per eventuali parsing futuri

# ----------------- CONFIG -----------------
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

# Understat slugs per leghe (per refresh elenco squadre)
UNDERSTAT_LEAGUE = {
    "SA": "Serie_A",
    "PL": "EPL",
    "PD": "La_Liga",
    "BL1": "Bundesliga",
    "FL1": "Ligue_1",
    "DED": "Eredivisie",
    "PPL": "Primeira_Liga",
    "CL": "Champions_League",
    "EL": "Europa_League",
}

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

UA = {"User-Agent": "Mozilla/5.0 (compatible; ScommesseFree/2.0)"}
CACHE_DIR = Path("cache/understat")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
TEAM_MAP_FILE = (
    DATA_DIR / "team_map.json"
)  # mapping appreso: "nome_api" -> "nome_understat"
LEAGUE_TEAMS_DIR = CACHE_DIR / "leagues"  # cache elenco squadre per lega/stagione
LEAGUE_TEAMS_DIR.mkdir(parents=True, exist_ok=True)

# Dizionario "best-effort" lat/lon stadi (aggiungi nel tempo i club che ti interessano)
STADIUMS = {
    "SSC Napoli": (40.827, 14.193),
    "Arsenal": (51.555, -0.108),
    "Atletico Madrid": (40.436, -3.599),
    "Union St. Gilloise": (50.806, 4.347),
    "Liverpool": (53.430, -2.961),
    "Real Madrid": (40.453, -3.688),
    "Bodo/Glimt": (67.281, 14.404),
    "Monaco": (43.727, 7.415),
    "Tottenham": (51.604, -0.067),
    "Kobenhavn": (55.672, 12.572),
    "Olympiakos": (37.946, 23.664),
    "PSV Eindhoven": (51.441, 5.467),
    "Juventus": (45.109, 7.641),
    "Sporting CP": (38.763, -9.160),
    "PSG": (48.841, 2.253),
    "Bayern Munich": (48.218, 11.624),
}

# Seed iniziale di mapping manuale (puoi ampliarlo in futuro)
SEED_UNDERSTAT_NAME_MAP = {
    "SSC Napoli": "Napoli",
    "Eintracht Frankfurt": "Eintracht Frankfurt",
    "Arsenal FC": "Arsenal",
    "Club Atlético de Madrid": "Atletico Madrid",
    "Royale Union Saint-Gilloise": "Union St. Gilloise",
    "Liverpool FC": "Liverpool",
    "Real Madrid CF": "Real Madrid",
    "FK Bodø/Glimt": "Bodo/Glimt",
    "AS Monaco FC": "Monaco",
    "Tottenham Hotspur FC": "Tottenham",
    "FC København": "Kobenhavn",
    "PAE Olympiakos SFP": "Olympiakos",
    "PSV": "PSV Eindhoven",
    "Juventus FC": "Juventus",
    "Sporting Clube de Portugal": "Sporting CP",
    "Paris Saint-Germain FC": "PSG",
    "FC Bayern München": "Bayern Munich",
    # Varianti “difficili”
    "Qarabağ Ağdam FK": "Qarabag Agdam",
    "Qarabağ FK": "Qarabag Agdam",
    "Qarabag FK": "Qarabag Agdam",
    "Qarabag Ağdam": "Qarabag Agdam",
    "Qarabag Agdam": "Qarabag Agdam",
}


# -------------- UTIL STRINGA & STAGIONE --------------
def _ascii_clean(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def _drop_suffixes(s: str) -> str:
    for suf in (" FC", " Cf", " CF", " FK", " SK", " SFP", " SAD", " AC", " BC"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    return s


def season_from_date(date_iso: str) -> int:
    dt = datetime.fromisoformat(date_iso[:10])
    return dt.year if dt.month >= 7 else dt.year - 1


# -------------- CACHE HTML --------------
def _cache_path(team: str, date_iso: str) -> Path:
    season = season_from_date(date_iso)
    safe = re.sub(r"[^A-Za-z0-9_\-\.]", "_", team)
    return CACHE_DIR / f"{safe}_{season}.html"


def _read_cache(path: Path) -> Optional[str]:
    try:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        pass
    return None


def _write_cache(path: Path, text: str):
    try:
        path.write_text(text, encoding="utf-8")
    except Exception:
        pass


# -------------- TEAM MAP (AUTO-LEARNING) --------------
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


# -------------- UNDERSTAT: URL & PARSER --------------
def understat_team_url(team: str, date_iso: str) -> str:
    season = season_from_date(date_iso)
    return f"https://understat.com/team/{quote(team)}/{season}"


def _extract_json_from_understat(html: str, varname: str) -> Optional[list]:
    m = re.search(
        rf"var\s+{re.escape(varname)}\s*=\s*JSON\.parse\('(.+?)'\)", html, flags=re.S
    )
    if m:
        js_escaped = m.group(1)
        try:
            js_unescaped = js_escaped.encode("utf-8").decode("unicode_escape")
            return json.loads(js_unescaped)
        except Exception:
            return None
    m2 = re.search(rf"var\s+{re.escape(varname)}\s*=\s*(\[[^\]]+\])", html, flags=re.S)
    if m2:
        try:
            return json.loads(m2.group(1))
        except Exception:
            return None
    return None


# -------------- UNDERSTAT: LEAGUE TEAMS (REFRESH) --------------
def league_teams_path(code: str, date_iso: str) -> Path:
    season = season_from_date(date_iso)
    return LEAGUE_TEAMS_DIR / f"{code}_{season}.json"


def fetch_league_teams(code: str, date_iso: str, delay: float = 0.0) -> List[str]:
    """Scarica elenco squadre per la lega/stagione da Understat (se supportata)."""
    slug = UNDERSTAT_LEAGUE.get(code)
    if not slug:
        return []
    season = season_from_date(date_iso)
    url = f"https://understat.com/league/{slug}/{season}"
    pth = league_teams_path(code, date_iso)
    if pth.exists():
        try:
            return json.loads(pth.read_text(encoding="utf-8"))
        except Exception:
            pass
    try:
        r = requests.get(url, headers=UA, timeout=30)
        r.raise_for_status()
        html = r.text
        # Understat espone "teamsData"
        teams = _extract_json_from_understat(html, "teamsData")
        names = []
        if teams and isinstance(teams, list):
            for team_obj in teams:
                nm = (
                    team_obj.get("title")
                    or team_obj.get("team_name")
                    or team_obj.get("label")
                )
                if nm and nm not in names:
                    names.append(nm)
        # fallback: prova a parseare in altro modo
        if not names:
            # pattern molto lasco
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


# -------------- MATCHING NOMI --------------
def candidate_names(api_name: str) -> List[str]:
    base = re.sub(r"\s+", " ", api_name).strip()
    cand = [base]
    no_suf = _drop_suffixes(base)
    if no_suf not in cand:
        cand.append(no_suf)
    ascii_base = _ascii_clean(base)
    if ascii_base not in cand:
        cand.append(ascii_base)
    ascii_no_suf = _ascii_clean(no_suf)
    if ascii_no_suf not in cand:
        cand.append(ascii_no_suf)

    repl = {
        "København": "Kobenhavn",
        "München": "Munich",
        "Atlético": "Atletico",
        "Athlético": "Atletico",
        "São": "Sao",
        "İstanbul": "Istanbul",
        "Ş": "S",
        "Ğ": "G",
        "ğ": "g",
        "Á": "A",
        "á": "a",
        "À": "A",
        "à": "a",
        "Ä": "A",
        "ä": "a",
        "Ó": "O",
        "ó": "o",
        "Ö": "O",
        "ö": "o",
        "Ú": "U",
        "ú": "u",
        "Ü": "U",
        "ü": "u",
        "Ć": "C",
        "ć": "c",
        "Č": "C",
        "č": "c",
        "ß": "ss",
    }
    tmp = base
    for k, v in repl.items():
        tmp = tmp.replace(k, v)
    tmp = re.sub(r"\s+", " ", tmp).strip()
    if tmp not in cand:
        cand.append(tmp)
    return cand


def resolve_understat_name(
    api_name: str,
    date_iso: str,
    comp_code: Optional[str],
    team_map: Dict[str, str],
    learn: bool,
    delay: float,
    league_teams_cache: Dict[str, List[str]],
) -> Optional[str]:
    """Trova un nome valido per Understat:
    1) se già mappato -> ritorna;
    2) prova varianti dirette (request + parse);
    3) se abbiamo elenco lega -> fuzzy match con threshold alto;
    4) se trova, salva in team_map (se learn=True).
    """
    # 1) mapping già noto
    if api_name in team_map:
        return team_map[api_name]

    # 2) prova varianti dirette
    for cand in candidate_names(api_name):
        url = understat_team_url(cand, date_iso)
        cache_p = _cache_path(cand, date_iso)
        html = _read_cache(cache_p)
        if html is None:
            try:
                resp = requests.get(url, headers=UA, timeout=30)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                html = resp.text
                _write_cache(cache_p, html)
                if delay > 0:
                    time.sleep(delay)
            except Exception:
                continue
        matches = _extract_json_from_understat(html, "matchesData")
        if matches:
            if learn:
                team_map[api_name] = cand
                save_team_map(team_map)
            return cand

    # 3) fuzzy match su elenco lega se disponibile
    if comp_code:
        if comp_code not in league_teams_cache:
            league_teams_cache[comp_code] = fetch_league_teams(
                comp_code, date_iso, delay=delay
            )
        league_names = league_teams_cache.get(comp_code, [])
        if league_names:
            # prova fuzzy
            # alza soglia per ridurre errori (es. 85)
            best = process.extractOne(api_name, league_names, scorer=fuzz.WRatio)
            if best and best[1] >= 85:
                cand = best[0]
                # verifica che la pagina di squadra esista
                url = understat_team_url(cand, date_iso)
                cache_p = _cache_path(cand, date_iso)
                html = _read_cache(cache_p)
                if html is None:
                    try:
                        resp = requests.get(url, headers=UA, timeout=30)
                        resp.raise_for_status()
                        html = resp.text
                        _write_cache(cache_p, html)
                        if delay > 0:
                            time.sleep(delay)
                    except Exception:
                        html = None
                if html:
                    ok = _extract_json_from_understat(html, "matchesData")
                    if ok:
                        if learn:
                            team_map[api_name] = cand
                            save_team_map(team_map)
                        return cand

    # nulla trovato
    return None


# -------------- xG & REST DAYS --------------
def compute_xg_and_rest(
    team_understat: str, date_iso: str, n: int, delay: float
) -> Tuple[float, float, Optional[datetime]]:
    """Scarica pagina team e calcola medie xG/xGA ultime N partite <= date_iso."""
    if not team_understat:
        return (1.2, 1.2, None)
    url = understat_team_url(team_understat, date_iso)
    cache_p = _cache_path(team_understat, date_iso)
    html = _read_cache(cache_p)
    if html is None:
        try:
            resp = requests.get(url, headers=UA, timeout=30)
            resp.raise_for_status()
            html = resp.text
            _write_cache(cache_p, html)
            if delay > 0:
                time.sleep(delay)
        except Exception:
            return (1.2, 1.2, None)

    data = _extract_json_from_understat(html, "matchesData")
    if not data:
        return (1.2, 1.2, None)

    cut = datetime.fromisoformat(date_iso[:10])
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
    xg_avg = sum(r[1] for r in rows) / len(rows)
    xga_avg = sum(r[2] for r in rows) / len(rows)
    return (round(xg_avg, 3), round(xga_avg, 3), last_dt)


# -------------- METEO & FLAG --------------
def openmeteo_flag(lat: float, lon: float, kickoff_iso: str) -> str:
    try:
        dt = datetime.fromisoformat(kickoff_iso.replace("Z", "").replace("T", " ")[:19])
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


# -------------- MAIN --------------
def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--date", required=True, help="YYYY-MM-DD (stessa data in fixtures.csv)"
    )
    ap.add_argument(
        "--comps", required=False, help="Filtra competizioni, es. 'SA,PL,CL'"
    )
    ap.add_argument("--n_recent", type=int, default=5, help="N partite per medie xG")
    ap.add_argument(
        "--delay", type=float, default=0.0, help="ritardo tra richieste (s)"
    )
    ap.add_argument(
        "--cache",
        type=int,
        default=1,
        help="1=usa cache sotto cache/understat, 0=disabilita",
    )
    ap.add_argument(
        "--learn-map",
        type=int,
        default=1,
        help="1=salva auto-mapping in data/team_map.json",
    )
    ap.add_argument(
        "--refresh-leagues",
        type=int,
        default=0,
        help="1=scarica elenco squadre delle leghe specificate",
    )
    ap.add_argument("--fixtures", default="fixtures.csv")
    ap.add_argument("--features", default="features.csv")
    args = ap.parse_args()

    use_cache = bool(args.cache)
    learn_map = bool(args.learn_map)

    # Carica fixtures
    try:
        df_fix = pd.read_csv(args.fixtures)
    except Exception as e:
        print(f"[ERR] Impossibile leggere {args.fixtures}: {e}")
        sys.exit(1)

    df_fix = df_fix[df_fix["date"] == args.date].copy()
    if args.comps:
        comps = [c.strip().upper() for c in args.comps.split(",") if c.strip()]
        names_ok = {COMP_MAP.get(c, c) for c in comps}
        df_fix = df_fix[df_fix["league"].isin(names_ok)]
    else:
        comps = []
    if df_fix.empty:
        print(f"[INFO] Nessun fixture trovato il {args.date} con i filtri richiesti.")
        sys.exit(0)

    # Carica features esistenti
    try:
        df_fea = pd.read_csv(args.features)
    except Exception:
        df_fea = pd.DataFrame(columns=FEA_COLS)
    existing = {
        r["match_id"]: r for _, r in df_fea.fillna("").to_dict(orient="index").items()
    }

    # Carica/salva team_map
    team_map = load_team_map()

    # (Opzionale) refresh elenco squadre leghe richieste
    league_teams_cache: Dict[str, List[str]] = {}
    if args.refresh_leagues and comps:
        for code in comps:
            league_teams_cache[code] = fetch_league_teams(
                code, args.date, delay=args.delay
            )
        print(
            f"[INFO] Aggiornati elenchi leghe: { {c: len(league_teams_cache.get(c, [])) for c in comps} }"
        )

    updated_rows = []

    for _, row in df_fix.iterrows():
        mid = row.get("match_id", "")
        date_str = row.get("date", "")
        time_local = (row.get("time_local", "") or "12:00").strip()
        league = row.get("league", "")
        home_api = row.get("home", "")
        away_api = row.get("away", "")

        # Prova a dedurre il comp_code inverso dal nome league (se presente in COMP_MAP)
        comp_code = None
        for k, v in COMP_MAP.items():
            if v == league:
                comp_code = k
                break

        # Risolvi nomi Understat (auto-learning + fuzzy)
        home_us = resolve_understat_name(
            home_api,
            date_str,
            comp_code,
            team_map,
            learn_map,
            args.delay,
            league_teams_cache,
        )
        away_us = resolve_understat_name(
            away_api,
            date_str,
            comp_code,
            team_map,
            learn_map,
            args.delay,
            league_teams_cache,
        )

        # xG medie ultime N (Understat) + last match date (per rest-days)
        hxg_f, hxg_a, h_last_dt = compute_xg_and_rest(
            home_us, date_str, args.n_recent, args.delay
        )
        axg_f, axg_a, a_last_dt = compute_xg_and_rest(
            away_us, date_str, args.n_recent, args.delay
        )

        def _rest_days(last_dt: Optional[datetime], game_date: str) -> str:
            if not last_dt:
                return ""
            try:
                g = datetime.fromisoformat(game_date + " 00:00:00")
            except Exception:
                return ""
            return str(max(0, (g - last_dt).days))

        rest_h = _rest_days(h_last_dt, date_str)
        rest_a = _rest_days(a_last_dt, date_str)

        injuries_h = existing.get(mid, {}).get("injuries_key_home", "")
        injuries_a = existing.get(mid, {}).get("injuries_key_away", "")
        style_h = existing.get(mid, {}).get("style_ppda_home", "")
        style_a = existing.get(mid, {}).get("style_ppda_away", "")

        e_home = europe_flag_from_league(league)
        e_away = e_home

        latlon = STADIUMS.get(home_us or home_api)
        if latlon:
            kickoff_iso = (
                f"{date_str}T{(time_local if len(time_local) == 5 else '12:00')}:00"
            )
            meteo = openmeteo_flag(latlon[0], latlon[1], kickoff_iso)
        else:
            meteo = "0"

        travel_km = existing.get(mid, {}).get("travel_km_away", "")

        rec = {
            "match_id": mid,
            "xG_for_5_home": hxg_f,
            "xG_against_5_home": hxg_a,
            "xG_for_5_away": axg_f,
            "xG_against_5_away": axg_a,
            "rest_days_home": rest_h,
            "rest_days_away": rest_a,
            "injuries_key_home": injuries_h,
            "injuries_key_away": injuries_a,
            "derby_flag": existing.get(mid, {}).get("derby_flag", "0"),
            "europe_flag_home": e_home,
            "europe_flag_away": e_away,
            "meteo_flag": meteo,
            "style_ppda_home": style_h,
            "style_ppda_away": style_a,
            "travel_km_away": travel_km,
        }
        updated_rows.append(rec)

    df_new = pd.DataFrame(updated_rows, columns=FEA_COLS).drop_duplicates(
        subset=["match_id"], keep="last"
    )
    df_old = df_fea[~df_fea["match_id"].isin(df_new["match_id"])]
    df_out = pd.concat([df_old, df_new], ignore_index=True)
    df_out.to_csv(args.features, index=False)
    print(f"[OK] Aggiornate {len(df_new)} righe in {args.features}")


if __name__ == "__main__":
    main()
