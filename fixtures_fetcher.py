#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import os
import time
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import requests
from unidecode import unidecode

ROOT = Path(__file__).resolve().parent
CFG = ROOT / "config.toml"
OUT = ROOT / "fixtures.csv"

# football-data.org competition IDs (v4)
COMP_MAP = {
    "SA": "2019",
    "PL": "2021",
    "PD": "2014",
    "BL1": "2002",
    "FL1": "2015",
    "DED": "2003",
    "PPL": "2017",
    "ELC": "2016",
    "BSA": "2013",
    "CL": "2001",
    "EL": "2146",  # EL spesso NON è nel free plan → gestita con fallback
}

# TheOddsAPI sports keys
SPORT_KEYS = {
    "CL": "soccer_uefa_champs_league",
    "EL": "soccer_uefa_europa_league",
    "SA": "soccer_italy_serie_a",
    "PL": "soccer_epl",
    "PD": "soccer_spain_la_liga",
    "BL1": "soccer_germany_bundesliga",
    "FL1": "soccer_france_ligue_one",
    "DED": "soccer_netherlands_eredivisie",
    "PPL": "soccer_portugal_primeira_liga",
    "ELC": "soccer_efl_champ",
    "BSA": "soccer_brazil_campeonato",
}


def read_cfg():
    import tomllib

    cfg = tomllib.loads(CFG.read_text(encoding="utf-8"))
    api_cfg = cfg.get("api", {})

    fd = (
        api_cfg.get("FOOTBALL_DATA_ORG_TOKEN")
        or api_cfg.get("football_data_token")
        or os.getenv("FOOTBALL_DATA_ORG_TOKEN")
        or os.getenv("FOOTBALL_DATA_API_KEY")
        or ""
    )
    toa = (
        api_cfg.get("THEODDSAPI_KEY")
        or api_cfg.get("theoddsapi_key")
        or os.getenv("THEODDSAPI_KEY")
        or ""
    )
    return fd.strip(), toa.strip()


class CurlResponse:
    def __init__(self, text: str):
        self.text = text
        self.status_code = 200

    def json(self):
        return json.loads(self.text)


def http_get(url: str, headers=None, params=None, timeout=30, desc=""):
    headers = headers or {}
    params = params or {}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=timeout)
        return r
    except requests.exceptions.RequestException as exc:
        full_url = f"{url}?{urlencode(params)}" if params else url
        label = desc or url
        print(f"[HTTP-FALLBACK] {label}: {exc}. Provo con curl…")
        cmd = ["curl", "-sS", "-m", str(timeout)]
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
        cmd.append(full_url)
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(
                f"curl fallito per {label} (exit {res.returncode}): {res.stderr.strip()}"
            )
        return CurlResponse(res.stdout)


def fd_get(path, params=None, token="", max_retries=3):
    url = f"https://api.football-data.org/v4{path}"
    headers = {"X-Auth-Token": token}
    params = params or {}
    
    for attempt in range(max_retries):
        try:
            r = http_get(url, headers=headers, params=params, timeout=30, desc=f"FD {path}")
            
            if r.status_code == 200:
                return r
            
            if r.status_code == 429:
                retry_after = int(r.headers.get("X-RequestCounter-Reset", "60"))
                wait_time = min(retry_after + 1, 65)
                print(f"[FD] Rate limit, attendo {wait_time}s...")
                time.sleep(wait_time)
                continue
            
            if r.status_code in (401, 403):
                raise PermissionError(f"FD API {r.status_code}: {r.text[:200]}")
            
            r.raise_for_status()
            return r
            
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 5
                print(f"[FD] Timeout, retry {attempt+1}/{max_retries} dopo {wait}s...")
                time.sleep(wait)
                continue
            raise
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 2
                print(f"[FD] Errore rete, retry {attempt+1}/{max_retries} dopo {wait}s...")
                time.sleep(wait)
                continue
            raise
    
    raise RuntimeError(f"FD API fallita dopo {max_retries} tentativi")


def fd_fixtures_for(code: str, date_str: str, token: str):
    comp_id = COMP_MAP.get(code)
    if not comp_id:
        return []
    try:
        day = datetime.fromisoformat(date_str)
    except ValueError:
        print(f"[ERR] Data non valida: {date_str}")
        return []
    
    dfrom = day.strftime("%Y-%m-%d")
    dto = (day + timedelta(days=1)).strftime("%Y-%m-%d")
    
    try:
        r = fd_get(
            f"/competitions/{comp_id}/matches", {"dateFrom": dfrom, "dateTo": dto}, token
        )
        js = r.json()
    except PermissionError:
        raise
    except Exception as e:
        print(f"[ERR] FD {code}: {e}")
        return []
    
    rows = []
    for m in js.get("matches", []):
        status = m.get("status", "")
        if status in {"FINISHED", "POSTPONED", "CANCELLED"}:
            continue
        
        try:
            utc_str = m.get("utcDate", "")
            if not utc_str:
                continue
            utc = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
            
            home_name = m.get("homeTeam", {}).get("name", "")
            away_name = m.get("awayTeam", {}).get("name", "")
            if not home_name or not away_name:
                continue
            
            # Match ID più robusto: usa ID match se disponibile
            match_id_api = m.get("id")
            if match_id_api:
                match_id = f"{date_str.replace('-', '')}_{match_id_api}_{code}"
            else:
                match_id = f"{date_str.replace('-', '')}_{unidecode(home_name).upper().replace(' ', '_')}_{unidecode(away_name).upper().replace(' ', '_')}_{code}"
            
            comp_name = js.get("competition", {}).get("name", code)
            
            rows.append(
                {
                    "match_id": match_id,
                    "date": date_str,
                    "time": utc.strftime("%H:%M"),
                    "time_local": utc.strftime("%H:%M"),  # aggiunto per compatibilità
                    "league": comp_name,
                    "league_code": code,
                    "home": home_name,
                    "away": away_name,
                }
            )
        except (KeyError, ValueError, AttributeError) as e:
            print(f"[WARN] Errore parsing match {m.get('id', 'unknown')}: {e}")
            continue
    
    return rows


def toa_fixtures_for(code: str, date_str: str, api_key: str, max_retries=2):
    """Fallback: costruisce i fixtures da TheOddsAPI (home/away/commence_time)."""
    sport = SPORT_KEYS.get(code)
    if not sport:
        return []
    
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
    params = {
        "apiKey": api_key,
        "regions": "eu,uk",
        "markets": "h2h",
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    
    try:
        wanted = datetime.fromisoformat(date_str).date()
    except ValueError:
        return []
    
    for attempt in range(max_retries):
        try:
            r = http_get(url, params=params, timeout=30, desc=f"TOA {code}")
            if r.status_code == 200:
                break
            if r.status_code == 429 and attempt < max_retries - 1:
                wait = 60
                print(f"[TOA] Rate limit, attendo {wait}s...")
                time.sleep(wait)
                continue
            return []
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            print(f"[TOA] Errore: {e}")
            return []
    else:
        return []
    
    try:
        events = r.json()
    except ValueError:
        return []
    
    rows = []
    for ev in events:
        try:
            ct = ev.get("commence_time")
            if not ct:
                continue
            dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
            if dt.date() != wanted:
                continue
            home = ev.get("home_team", "").strip()
            away = ev.get("away_team", "").strip()
            if not home or not away:
                continue
            
            match_id = f"{date_str.replace('-', '')}_{unidecode(home).upper().replace(' ', '_')}_{unidecode(away).upper().replace(' ', '_')}_{code}"
            
            rows.append(
                {
                    "match_id": match_id,
                    "date": date_str,
                    "time": dt.strftime("%H:%M"),
                    "time_local": dt.strftime("%H:%M"),
                    "league": code,
                    "league_code": code,
                    "home": home,
                    "away": away,
                }
            )
        except (KeyError, ValueError, AttributeError):
            continue
    
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--comps", required=True, help="es. SA,PL,EL")
    args = ap.parse_args()

    fd_token, toa_key = read_cfg()

    all_rows = []
    for code in [c.strip() for c in args.comps.split(",") if c.strip()]:
        try:
            rows = fd_fixtures_for(code, args.date, fd_token)
            if rows:
                print(f"[FD] {code}: trovate {len(rows)} partite.")
                all_rows.extend(rows)
            else:
                # nessun match → fallback
                fr = toa_fixtures_for(code, args.date, toa_key)
                if fr:
                    print(
                        f"[FD→TOA] {code}: FD vuoto, recuperate {len(fr)} partite da TheOddsAPI."
                    )
                    all_rows.extend(fr)
                else:
                    print(f"[WARN] {code}: nessuna partita da FD o TOA.")
        except PermissionError:
            # 401/403 → usa TOA
            fr = toa_fixtures_for(code, args.date, toa_key)
            if fr:
                print(f"[FD 403] {code}: fallback TOA, {len(fr)} partite.")
                all_rows.extend(fr)
            else:
                print(f"[ERR] {code}: 403/401 FD e TOA senza eventi utili.")
        except requests.HTTPError as e:
            print(f"[ERR] {code}: HTTP error FD: {e}")
        except Exception as e:
            print(f"[ERR] {code}: {e}")

    df = pd.DataFrame(all_rows)
    if df.empty:
        print("[WARN] Nessuna partita trovata.")
        df = pd.DataFrame(
            columns=[
                "match_id",
                "date",
                "time",
                "league",
                "league_code",
                "home",
                "away",
            ]
        )

    # colonne quote vuote (verranno riempite dopo)
    for c in ["odds_1", "odds_x", "odds_2", "odds_ou25_over", "odds_ou25_under", "line_ou"]:
        if c not in df.columns:
            df[c] = pd.NA
    
    # Assicura colonna line_ou con default 2.5
    if "line_ou" in df.columns:
        df["line_ou"] = df["line_ou"].fillna("2.5")

    df.to_csv(OUT, index=False)
    print(f"[OK] Fixtures scritte: {len(df)} righe → {OUT}")


if __name__ == "__main__":
    main()
