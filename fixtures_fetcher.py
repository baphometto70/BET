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

# Importazioni per il database
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Fixture, Odds

ROOT = Path(__file__).resolve().parent
CFG = ROOT / "config.toml"

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
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

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


def fd_fixtures_for(code: str, date_from: str, date_to: str, token: str):
    comp_id = COMP_MAP.get(code)
    if not comp_id:
        return []
    
    try:
        r = fd_get(
            f"/competitions/{comp_id}/matches",
            {"dateFrom": date_from, "dateTo": date_to},
            token,
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
            date_str = utc.strftime("%Y-%m-%d")
            
            home_name = m.get("homeTeam", {}).get("name", "")
            away_name = m.get("awayTeam", {}).get("name", "")
            if not home_name or not away_name:
                continue
            
            # Match ID più robusto: usa ID match se disponibile
            match_id_api = m.get("id")
            if match_id_api:
                match_id = f"{utc.strftime('%Y%m%d')}_{match_id_api}_{code}"
            else:
                match_id = f"{utc.strftime('%Y%m%d')}_{unidecode(home_name).upper().replace(' ', '_')}_{unidecode(away_name).upper().replace(' ', '_')}_{code}"
            
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


def toa_fixtures_for(
    code: str, date_from: datetime.date, date_to: datetime.date, api_key: str, max_retries=2
):
    """Fallback: costruisce i fixtures da TheOddsAPI (home/away/commence_time)."""
    sport = SPORT_KEYS.get(code)
    if not sport:
        return []
    
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
    params = {"apiKey": api_key, "regions": "eu,uk", "markets": "h2h"}
    
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
            if not (date_from <= dt.date() <= date_to):
                continue
            home = ev.get("home_team", "").strip()
            away = ev.get("away_team", "").strip()
            if not home or not away:
                continue
            
            date_str = dt.strftime("%Y-%m-%d")
            match_id = f"{dt.strftime('%Y%m%d')}_{unidecode(home).upper().replace(' ', '_')}_{unidecode(away).upper().replace(' ', '_')}_{code}"
            
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
    ap.add_argument(
        "--days",
        type=int,
        default=10,
        help="Numero di giorni nel futuro da scaricare (default: 10, max per API free)",
    )
    ap.add_argument(
        "--comps", help="es. SA,PL,EL. Default: tutti i campionati gestiti."
    )
    ap.add_argument(
        "--date",
        type=str,
        default=None,
        help="Data di inizio da cui scaricare (YYYY-MM-DD). Default: oggi.",
    )
    args = ap.parse_args()

    fd_token, toa_key = read_cfg()

    # Calcola il range di date
    if args.date:
        try:
            start_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"[ERR] Formato data non valido: {args.date}. Usare YYYY-MM-DD.")
            return
    else:
        start_date = datetime.utcnow().date()
    date_from_dt = start_date
    date_to_dt = date_from_dt + timedelta(days=args.days - 1)
    date_from_str = date_from_dt.strftime("%Y-%m-%d")
    date_to_str = date_to_dt.strftime("%Y-%m-%d")
    print(f"[INFO] Scarico partite da {date_from_str} a {date_to_str} ({args.days} giorni).")

    if args.comps:
        comps_to_run = [c.strip().upper() for c in args.comps.split(",") if c.strip()]
    else:
        comps_to_run = list(COMP_MAP.keys())
        print(f"[INFO] Nessun campionato specificato, scarico tutti: {', '.join(comps_to_run)}")

    all_rows = []
    for code in comps_to_run:
        try:
            rows = fd_fixtures_for(code, date_from_str, date_to_str, fd_token)
            if rows:
                print(f"[FD] {code}: trovate {len(rows)} partite.")
                all_rows.extend(rows)
            else:
                # nessun match → fallback
                fr = toa_fixtures_for(code, date_from_dt, date_to_dt, toa_key)
                if fr:
                    print(
                        f"[FD→TOA] {code}: FD vuoto, recuperate {len(fr)} partite da TheOddsAPI."
                    )
                    all_rows.extend(fr)
                else:
                    print(f"[WARN] {code}: nessuna partita da FD o TOA.")
        except PermissionError:
            # 401/403 → usa TOA
            fr = toa_fixtures_for(code, date_from_dt, date_to_dt, toa_key)
            if fr:
                print(f"[FD 403] {code}: fallback TOA, {len(fr)} partite.")
                all_rows.extend(fr)
            else:
                print(f"[ERR] {code}: 403/401 FD e TOA senza eventi utili.")
        except requests.HTTPError as e:
            print(f"[ERR] {code}: HTTP error FD: {e}")
        except Exception as e:
            print(f"[ERR] {code}: {e}")

    if not all_rows:
        print("[WARN] Nessuna partita trovata.")
        return

    # --- Logica di inserimento nel Database ---
    db: Session = SessionLocal()
    try:
        print(f"\n[DB] Connessione al database per inserire/aggiornare {len(all_rows)} partite...")
        
        match_ids_processed = set()
        upserted_count = 0

        for row_data in all_rows:
            match_id = row_data.get("match_id")
            if not match_id or match_id in match_ids_processed:
                continue

            # Crea l'oggetto Fixture
            fixture_obj = Fixture(
                match_id=match_id,
                date=datetime.fromisoformat(row_data["date"]).date(),
                time=row_data.get("time"),
                time_local=row_data.get("time_local"),
                league=row_data.get("league"),
                league_code=row_data.get("league_code"),
                home=row_data.get("home"),
                away=row_data.get("away"),
            )

            # db.merge gestisce INSERT o UPDATE in base alla chiave primaria
            db.merge(fixture_obj)
            match_ids_processed.add(match_id)
            upserted_count += 1

        db.commit()
        print(f"[DB] Commit eseguito. {upserted_count} partite inserite/aggiornate nel database.")
    except Exception as e:
        print(f"[DB-ERR] Errore durante l'operazione sul database: {e}")
        db.rollback()
    finally:
        db.close()
        print("[DB] Connessione al database chiusa.")


if __name__ == "__main__":
    main()
