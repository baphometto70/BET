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

import io
import json
import math
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

# Importazioni per il database
from sqlalchemy.orm import Session, joinedload
from database import SessionLocal, Base, engine
from models import Fixture, Feature, Odds, TeamMapping

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
    "xg_for_home",
    "xg_against_home",
    "xg_for_away",
    "xg_against_away",
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
    "ELC": "Championship",
}

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

DEFAULT_XG_VALUE = 1.2

# Tabella empirica di squadre "forti" (che tendono a segnare di più) per varie leghe
# Usata per variare gli xG nel fallback quando non abbiamo dati Understat
STRONG_TEAMS = {
    "SA": ["Inter", "Milan", "Juventus", "Napoli", "Roma", "Lazio", "Atalanta"],
    "PL": ["Manchester City", "Manchester United", "Liverpool", "Chelsea", "Arsenal", "Tottenham"],
    "PD": ["Real Madrid", "Barcelona", "Atletico Madrid", "Sevilla"],
    "BL1": ["Bayern München", "Borussia Dortmund", "RB Leipzig"],
    "FL1": ["Paris Saint-Germain", "Olympique Lyonnais", "Olympique Marseille"],
    "DED": ["Ajax", "Feyenoord", "PSV"],
    "PPL": ["Benfica", "Porto", "Sporting"],
    "ELC": ["Leicester City", "Leeds United"],
}

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

# -------------- UTIL STRINGA & STAGIONE --------------
def _ascii_clean(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def season_from_date(date_iso: str) -> int:
    dt = datetime.fromisoformat(date_iso[:10])
    return dt.year if dt.month >= 7 else dt.year - 1


def _to_float(val) -> float:
    try:
        out = float(val)
        if math.isfinite(out):
            return out
    except Exception:
        pass
    return math.nan


def _implied_prob(odds) -> float:
    o = _to_float(odds)
    if math.isnan(o) or o <= 0:
        return math.nan
    return 1.0 / o


def market_based_expected_goals(
    fixture_row: pd.Series, default_total: float = 2.6
) -> Optional[Tuple[float, float]]:
    """Stima xG da quote 1X2 + linea goal (fallback)."""
    line_candidates = [
        fixture_row.get("line_ou"),
        fixture_row.get("line_ou_main"),
        fixture_row.get("line_ou25"),
    ]
    line = next(
        (_to_float(v) for v in line_candidates if not math.isnan(_to_float(v))),
        math.nan,
    )

    odds_over = _implied_prob(
        fixture_row.get("odds_over")
        or fixture_row.get("odds_ou25_over")
        or fixture_row.get("odds_over_2_5")
    )
    odds_under = _implied_prob(
        fixture_row.get("odds_under")
        or fixture_row.get("odds_ou25_under")
        or fixture_row.get("odds_under_2_5")
    )

    if not math.isnan(line):
        total_goals = line
        if not math.isnan(odds_over) and not math.isnan(odds_under):
            over_share = odds_over / (odds_over + odds_under)
            # adjust +/- 0.8 goals depending on over bias
            total_goals = line + (over_share - 0.5) * 0.8
    else:
        total_goals = default_total

    if math.isnan(total_goals) or total_goals <= 0:
        total_goals = default_total

    p1 = _implied_prob(fixture_row.get("odds_1"))
    px = _implied_prob(fixture_row.get("odds_x"))
    p2 = _implied_prob(fixture_row.get("odds_2"))
    probs = [p for p in (p1, px, p2) if not math.isnan(p)]
    if len(probs) < 2:
        return None
    s = sum([p for p in (p1, px, p2) if not math.isnan(p)])
    if s <= 0:
        return None
    p_home = p1 / s if not math.isnan(p1) else 0.45
    p_away = p2 / s if not math.isnan(p2) else 0.25

    # goal diff via log ratio (bounded)
    goal_diff = 0.6 * math.log(max(p_home, 1e-6) / max(p_away, 1e-6))
    lambda_home = total_goals / 2.0 + goal_diff / 2.0
    lambda_away = total_goals - lambda_home

    # enforce bounds and renormalize to keep sum == total_goals
    lambda_home = max(0.2, lambda_home)
    lambda_away = max(0.2, lambda_away)
    denom = lambda_home + lambda_away
    if denom <= 0:
        return None
    scale = total_goals / denom
    lambda_home *= scale
    lambda_away *= scale
    return (round(lambda_home, 3), round(lambda_away, 3))


def is_strong_team(team_name: str, league_code: str) -> bool:
    """Controlla se una squadra è in lista "forti" per la lega."""
    if league_code not in STRONG_TEAMS:
        return False
    strong_list = STRONG_TEAMS[league_code]
    # Fuzzy match per gestire variazioni di nome
    best_ratio = max(
        [fuzz.ratio(team_name.upper(), strong.upper()) for strong in strong_list],
        default=0
    )
    return best_ratio >= 70  # Soglia di similarità


# -------------- TEAM MAPPING (DA DATABASE) --------------
def get_team_mapping(team_api: str, league_code: str, db: Session) -> Optional[str]:
    """
    Tenta di trovare il nome Understat per una squadra dal mapping salvato nel DB.
    Se non trovato, ritorna None (fallback a SEED_UNDERSTAT_NAME_MAP).
    """
    mapping = db.query(TeamMapping).filter(
        TeamMapping.source_name == team_api,
        TeamMapping.league_code == league_code
    ).first()
    return mapping.understat_name if mapping else None


def get_fbref_mapping_from_db(
    source_name: str, league_code: str, db: Session
) -> Optional[Tuple[str, str]]:
    """Recupera l'ID e il nome FBRef mappati dal database."""
    mapping = (
        db.query(TeamMapping)
        .filter_by(source_name=source_name, league_code=league_code)
        .first()
    )
    if mapping and mapping.fbref_id and mapping.fbref_name:
        return mapping.fbref_id, mapping.fbref_name
    return None


# -------------- UNDERSTAT: URL & PARSER --------------
def understat_team_url(team: str, date_iso: str) -> str:
    season = season_from_date(date_iso)
    return f"https://understat.com/team/{quote(team)}/{season}"


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

    # Cerca il pattern di assegnazione della variabile. Questo gestisce:
    # 1. var/let/const nome_variabile = JSON.parse('stringa_json_escapata')
    # 2. var/let/const nome_variabile = [{...}] o {{...}} (JSON letterale)
    # Il pattern per la stringa escapata (?:\\.|[^'])* è robusto e gestisce i caratteri escapati.
    data_pattern = re.search(
        rf"\b{re.escape(varname)}\s*=\s*(?:JSON\.parse\(\s*'((?:\\.|[^'])*)'\s*\)|(\[.*?\]|\{{.*?\}}))\s*;?",
        script_content,
        re.DOTALL
    )

    if not data_pattern:
        return None

    # Il pattern ha due gruppi di cattura. Solo uno sarà popolato.
    escaped_json_str = data_pattern.group(1)
    literal_json_str = data_pattern.group(2)

    json_to_parse = None
    if escaped_json_str:
        try:
            # La stringa è escapata per JavaScript. `unicode_escape` è un buon metodo per decodificarla.
            json_to_parse = bytes(escaped_json_str, "utf-8").decode("unicode_escape")
        except Exception:
            return None # Errore nella decodifica della stringa
    elif literal_json_str:
        json_to_parse = literal_json_str

    if json_to_parse:
        try:
            return json.loads(json_to_parse)
        except json.JSONDecodeError:
            return None # Parsing fallito
            
    return None


# -------------- FBRef: FALLBACK SOURCE --------------
FBRef_COMP_MAP = {
    "SA": (11, "Serie-A"),
    "PL": (9, "Premier-League"),
    "PD": (12, "La-Liga"),
    "BL1": (20, "Bundesliga"),
    "FL1": (13, "Ligue-1"),
}

def fetch_xg_from_fbref_team_page(fbref_id: str, fbref_name: str, date_iso: str) -> Optional[Tuple[float, float]]:
    """
    Scarica xG/xGA per 90' da una pagina squadra di FBRef usando il suo ID univoco.
    """
    season = season_from_date(date_iso)
    season_str = f"{season}-{season+1}"
    
    # FBRef usa nomi "sanitized" negli URL, ma l'ID è la chiave robusta.
    # Il nome è utile per rendere l'URL più leggibile.
    safe_name = fbref_name.replace(" ", "-")
    
    # L'URL per "All Competitions" è più completo.
    url = f"https://fbref.com/en/squads/{fbref_id}/{season_str}/all_comps/{safe_name}-Stats-All-Competitions"

    try:
        r = requests.get(url, headers=UA, timeout=20)
        # Se la pagina "all_comps" non esiste (comune per squadre di leghe minori), prova quella della lega.
        if r.status_code == 404:
            url = f"https://fbref.com/en/squads/{fbref_id}/{season_str}/{safe_name}-Stats"
            r = requests.get(url, headers=UA, timeout=20)

        r.raise_for_status()
        
        # FBRef usa commenti HTML per nascondere le tabelle a scraper semplici.
        html_content = r.text.replace("<!--", "").replace("-->", "")
        
        # Cerca la tabella "Squad Standard Stats" tramite il suo ID HTML.
        tables = pd.read_html(io.StringIO(html_content), attrs={"id": "stats_standard_squads"})
        
        if not tables:
            return None
            
        stats_df = tables[0]
        # Pulisci i multi-header di pandas
        stats_df.columns = ['_'.join(col).strip() for col in stats_df.columns.values]
        
        # Cerca la riga di riepilogo "Squad Total"
        total_row = stats_df[stats_df.iloc[:, 0] == 'Squad Total']
        if total_row.empty:
            return None
            
        # Trova le colonne xG e xGA "Per 90 Minutes"
        xg_col = next((c for c in total_row.columns if 'Per_90_Minutes_xG' in c), None)
        xga_col = next((c for c in total_row.columns if 'Per_90_Minutes_xGA' in c), None)
        
        if not xg_col or not xga_col:
            return None
            
        xg_for = pd.to_numeric(total_row.iloc[0][xg_col], errors='coerce')
        xg_against = pd.to_numeric(total_row.iloc[0][xga_col], errors='coerce')
        
        if pd.isna(xg_for) or pd.isna(xg_against):
            return None
            
        return (xg_for, xg_against)

    except Exception as e:
        print(f"[FBRef-Team-ERR] Fallito recupero per {fbref_name} ({fbref_id}): {e}")
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
def get_understat_name_from_db(
    source_name: str, league_code: str, db: Session
) -> Optional[str]:
    """Recupera il nome Understat mappato dal database."""
    mapping = (
        db.query(TeamMapping)
        .filter_by(source_name=source_name, league_code=league_code)
        .first()
    )
    return mapping.understat_name if mapping else None


# -------------- xG & REST DAYS --------------
def compute_xg_and_rest(
    team_understat: str, date_iso: str, n: int, delay: float
) -> Tuple[float, float, Optional[datetime]]:
    """Scarica pagina team e calcola medie xG/xGA ultime N partite <= date_iso."""
    if not team_understat:
        return (DEFAULT_XG_VALUE, DEFAULT_XG_VALUE, None)
    
    url = understat_team_url(team_understat, date_iso)
    cache_p = _cache_path(team_understat, date_iso)
    html = _read_cache(cache_p)
    
    # Verifica TTL cache (7 giorni)
    if html and cache_p.exists():
        try:
            age_days = (time.time() - cache_p.stat().st_mtime) / 86400
            if age_days > 7:
                html = None  # Cache scaduta
        except Exception:
            pass
    
    if html is None:
        for attempt in range(2):
            try:
                resp = requests.get(url, headers=UA, timeout=30)
                if resp.status_code == 404:
                    # Squadra non trovata
                    return (DEFAULT_XG_VALUE, DEFAULT_XG_VALUE, None)
                resp.raise_for_status()
                html = resp.text
                _write_cache(cache_p, html)
                if delay > 0:
                    time.sleep(delay)
                break
            except requests.exceptions.Timeout:
                if attempt < 1:
                    time.sleep(5)
                    continue
                return (DEFAULT_XG_VALUE, DEFAULT_XG_VALUE, None)
            except requests.exceptions.RequestException:
                if attempt < 1:
                    time.sleep(2)
                    continue
                return (DEFAULT_XG_VALUE, DEFAULT_XG_VALUE, None)
            except Exception:
                return (DEFAULT_XG_VALUE, DEFAULT_XG_VALUE, None)

    data = _extract_json_from_understat(html, "matchesData")
    if not data:
        return (DEFAULT_XG_VALUE, DEFAULT_XG_VALUE, None)

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
        return (DEFAULT_XG_VALUE, DEFAULT_XG_VALUE, last_dt)

    # Calcola una media pesata: le partite più recenti hanno più peso.
    # Questo crea una feature di "forma" più reattiva.
    weights = list(range(len(rows), 0, -1))
    total_weight = sum(weights)

    if total_weight > 0:
        xg_avg = sum(r[1] * w for r, w in zip(rows, weights)) / total_weight
        xga_avg = sum(r[2] * w for r, w in zip(rows, weights)) / total_weight
    else:
        # Fallback a media semplice in caso di problemi
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
    args = ap.parse_args()

    use_cache = bool(args.cache)
    learn_map = bool(args.learn_map)

    print(f"[FEATURE-POP] Avvio population features per {args.date}")
    sys.stdout.flush()

    # --- CARICA DATI DAL DATABASE ---
    db: Session = SessionLocal()
    try:
        query = (
            db.query(Fixture)
            .options(joinedload(Fixture.odds))
            .filter(Fixture.date == args.date)
        )
        if args.comps:
            comps = [c.strip().upper() for c in args.comps.split(",") if c.strip()]
            query = query.filter(Fixture.league_code.in_(comps))
        else:
            comps = []
        
        fixtures_to_process = query.all()
        if not fixtures_to_process:
            print(f"[INFO] Nessun fixture trovato nel DB il {args.date} con i filtri richiesti.")
            sys.exit(0)
        print(f"[DB] Trovate {len(fixtures_to_process)} partite nel DB da processare.")
        sys.stdout.flush()

    except Exception as e:
        print(f"[DB-ERR] Impossibile caricare le partite dal database: {e}")
        sys.exit(1)

    # --- CICLO PRINCIPALE ---
    for i, fixture in enumerate(fixtures_to_process, 1):
        mid = fixture.match_id
        date_str = fixture.date.isoformat()
        time_local = (fixture.time_local or "12:00").strip()
        league = fixture.league
        home_api = fixture.home
        away_api = fixture.away
        comp_code = fixture.league_code

        print(f"[{i}/{len(fixtures_to_process)}] Processamento {mid}: {home_api} vs {away_api}")
        sys.stdout.flush()

        # Carica (o crea) l'oggetto Feature per questo match
        feature_obj = db.query(Feature).filter(Feature.match_id == mid).first()
        if feature_obj is None:
            feature_obj = Feature(match_id=mid)

        # Crea un oggetto simile a una riga di pandas per la funzione di fallback
        row_for_fallback = {
            "odds_1": fixture.odds.odds_1 if fixture.odds else None,
            "odds_x": fixture.odds.odds_x if fixture.odds else None,
            "odds_2": fixture.odds.odds_2 if fixture.odds else None,
            "odds_ou25_over": fixture.odds.odds_ou25_over if fixture.odds else None,
            "odds_ou25_under": fixture.odds.odds_ou25_under if fixture.odds else None,
            "line_ou": fixture.odds.line_ou if fixture.odds else "2.5",
        }

        # Risolvi nomi Understat (auto-learning + fuzzy)
        home_us = get_understat_name_from_db(home_api, comp_code, db)
        away_us = get_understat_name_from_db(away_api, comp_code, db)

        # xG medie ultime N (Understat) + last match date (per rest-days)
        hxg_f, hxg_a, h_last_dt = compute_xg_and_rest(
            home_us, date_str, args.n_recent, args.delay
        )
        axg_f, axg_a, a_last_dt = compute_xg_and_rest(
            away_us, date_str, args.n_recent, args.delay
        )

        # --- GESTIONE FALLBACK A PIÙ LIVELLI ---
        fallback_msgs: List[str] = []
        need_home_fallback = (home_us is None) or (h_last_dt is None)
        need_away_fallback = (away_us is None) or (a_last_dt is None)
        # Traccia origine dati xG
        source_home = "understat" if (home_us and h_last_dt) else None
        source_away = "understat" if (away_us and a_last_dt) else None

        # 1. TENTATIVO DI FALLBACK SU FBREF (se Understat fallisce)
        if need_home_fallback:
            fbref_map_home = get_fbref_mapping_from_db(home_api, comp_code, db)
            if fbref_map_home:
                fbref_id, fbref_name = fbref_map_home
                fbref_xg = fetch_xg_from_fbref_team_page(fbref_id, fbref_name, date_str)
                if fbref_xg:
                    hxg_f, hxg_a = fbref_xg
                    h_last_dt = datetime.fromisoformat(date_str)  # Usa la data della partita
                    need_home_fallback = False
                    source_home = "fbref"
                    fallback_msgs.append(f"[FALLBACK] {mid}: xG home stimati da FBRef.")

        if need_away_fallback:
            fbref_map_away = get_fbref_mapping_from_db(away_api, comp_code, db)
            if fbref_map_away:
                fbref_id, fbref_name = fbref_map_away
                fbref_xg = fetch_xg_from_fbref_team_page(fbref_id, fbref_name, date_str)
                if fbref_xg:
                    axg_f, axg_a = fbref_xg
                    a_last_dt = datetime.fromisoformat(date_str)
                    need_away_fallback = False
                    source_away = "fbref"
                    fallback_msgs.append(f"[FALLBACK] {mid}: xG away stimati da FBRef.")
        
        # 2. TENTATIVO DI FALLBACK SU QUOTE (se ancora necessario)
        fallback_pair: Optional[Tuple[float, float]] = None
        if need_home_fallback or need_away_fallback:
            fallback_pair = market_based_expected_goals(pd.Series(row_for_fallback))
            if fallback_pair:
                if need_home_fallback:
                    hxg_f, hxg_a = fallback_pair
                    h_last_dt = None # Nessuna data, quindi rest_days sarà vuoto
                    fallback_msgs.append(
                        f"[FALLBACK] {mid}: xG home stimati da quote (Understat/FBRef assenti)."
                    )
                    source_home = "odds"
                if need_away_fallback:
                    axg_f, axg_a = fallback_pair[1], fallback_pair[0]
                    a_last_dt = None
                    fallback_msgs.append(
                        f"[FALLBACK] {mid}: xG away stimati da quote (Understat/FBRef assenti)."
                    )
                    source_away = "odds"
            else:
                # 3. FALLBACK FINALE: Stima basata su profili di squadra (Forte/Medio) con variabilità.
                # Questo riduce la ripetitività delle previsioni quando mancano dati primari.
                home_is_strong = is_strong_team(home_api, comp_code)
                away_is_strong = is_strong_team(away_api, comp_code)

                import random

                def get_profile(is_strong: bool) -> Tuple[float, float]:
                    """
                    Restituisce un profilo (xG_fatti, xG_subiti) con variabilità.
                    - FORTE: attacco alto (1.7-2.1), difesa solida (0.9-1.2)
                    - MEDIA: attacco medio (1.2-1.5), difesa media (1.3-1.6)
                    """
                    if is_strong:
                        xg_for = random.uniform(1.7, 2.1)
                        xg_against = random.uniform(0.9, 1.2)
                    else:
                        xg_for = random.uniform(1.2, 1.5)
                        xg_against = random.uniform(1.3, 1.6)
                    return (round(xg_for, 2), round(xg_against, 2))

                if need_home_fallback:
                    hxg_f, hxg_a = get_profile(home_is_strong)
                    h_last_dt = None
                    fallback_msgs.append(
                        f"[FALLBACK-L2] {mid}: xG home stimati ({hxg_f:.2f}|{hxg_a:.2f}) - profilo {'FORTE' if home_is_strong else 'MEDIO'}."
                    )
                    source_home = "fallback"

                if need_away_fallback:
                    # Per la squadra in trasferta, l'attacco è leggermente penalizzato
                    axg_f_base, axg_a_base = get_profile(away_is_strong)
                    axg_f = round(axg_f_base * 0.95, 2) # Penalità trasferta
                    axg_a = axg_a_base
                    a_last_dt = None
                    fallback_msgs.append(
                        f"[FALLBACK-L2] {mid}: xG away stimati ({axg_f:.2f}|{axg_a:.2f}) - profilo {'FORTE' if away_is_strong else 'MEDIO'}."
                    )
                    source_away = "fallback"

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

        # Popola l'oggetto Feature (i campi non calcolati come 'injuries' vengono preservati)
        feature_obj.xg_for_home = hxg_f
        feature_obj.xg_against_home = hxg_a
        feature_obj.xg_for_away = axg_f
        feature_obj.xg_against_away = axg_a
        # Salva origine e confidenza: assegna un valore numerico di confidenza
        # regole semplici: understat=90, fbref=75, odds=60, fallback=20
        feature_obj.xg_source_home = source_home
        feature_obj.xg_source_away = source_away
        try:
            def _src_conf(s):
                if s == 'understat':
                    return 90.0
                if s == 'fbref': # Mantenuto per compatibilità futura
                    return 75.0
                if s == 'odds':
                    return 60.0
                if s == 'fallback':
                    return 20.0
                return 0.0

            ch = _src_conf(source_home)
            ca = _src_conf(source_away)
            # Media aritmetica: sempre numerica, mai None (se entrambi 0, assegna 0)
            feature_obj.xg_confidence = round(((ch + ca) / 2.0), 1)
        except Exception:
            feature_obj.xg_confidence = None
        feature_obj.rest_days_home = int(rest_h) if rest_h else None
        feature_obj.rest_days_away = int(rest_a) if rest_a else None
        feature_obj.europe_flag_home = int(e_home)
        feature_obj.europe_flag_away = int(e_away)
        feature_obj.meteo_flag = int(meteo)
        
        db.merge(feature_obj)

        if fallback_msgs:
            for msg in fallback_msgs:
                print(msg)

    # --- SALVATAGGIO SU DATABASE ---
    try:
        db.commit()
        print(f"\n[DB] Commit eseguito. {len(fixtures_to_process)} features inserite/aggiornate nel database.")
    except Exception as e:
        print(f"[DB-ERR] Errore durante il salvataggio delle features: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
