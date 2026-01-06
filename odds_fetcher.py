#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import math
import os
import re
import subprocess
import time, json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import requests
from unidecode import unidecode

from database import SessionLocal
from models import Fixture, Odds

ROOT = Path(__file__).resolve().parent
CFG = ROOT / "config.toml"
API_USAGE_FILE = ROOT / "data" / "api_usage.json"
THE_ODDS_API_LIMIT = 500

SPORT_KEYS = {
    "CL": "soccer_uefa_champs_league",
    "EL": "soccer_uefa_europa_league",
    "SA": "soccer_italy_serie_a",
    "PL": "soccer_epl",
    "PD": "soccer_spain_la_liga",
    "BL1":"soccer_germany_bundesliga",
    "FL1":"soccer_france_ligue_one",
    "DED":"soccer_netherlands_eredivisie",
    "PPL":"soccer_portugal_primeira_liga",
    "ELC":"soccer_efl_champ",
    "BSA":"soccer_brazil_campeonato",
}

ALIAS = {
    # normalizzazioni comuni
    "qarabag agdam fk": "qarabag",
    "olympique de marseille": "marseille",
    "manchester city fc": "manchester city",
    "fc barcelona": "barcelona",
    "athletic club": "athletic bilbao",
    "sport lisboa e benfica": "benfica",
    "bayer 04 leverkusen": "bayer leverkusen",
    "paphos fc": "paphos",
    "fk kairat": "kairat",
    "kobenhavn": "copenhagen",  # FC København
    "fc copenhagen": "copenhagen",
}

# --- API USAGE COUNTER ---

def get_api_usage() -> dict:
    """Legge il file di utilizzo dell'API."""
    if not API_USAGE_FILE.exists():
        return {"the_odds_api": {"count": 0, "last_reset": datetime.now().strftime("%Y-%m-01")}}
    try:
        return json.loads(API_USAGE_FILE.read_text())
    except (json.JSONDecodeError, FileNotFoundError):
        return {"the_odds_api": {"count": 0, "last_reset": datetime.now().strftime("%Y-%m-01")}}

def save_api_usage(usage_data: dict):
    """Salva il file di utilizzo dell'API."""
    API_USAGE_FILE.parent.mkdir(exist_ok=True)
    API_USAGE_FILE.write_text(json.dumps(usage_data, indent=2))

def check_and_increment_usage() -> bool:
    """
    Controlla l'utilizzo dell'API. Se il limite non è stato raggiunto,
    incrementa il contatore e ritorna True. Altrimenti, ritorna False.
    Resetta il contatore se è iniziato un nuovo mese.
    """
    usage = get_api_usage()
    today = datetime.now()
    
    odds_api_usage = usage.get("the_odds_api", {})
    count = odds_api_usage.get("count", 0)
    last_reset_str = odds_api_usage.get("last_reset", "1970-01-01")
    
    try:
        last_reset_date = datetime.strptime(last_reset_str, "%Y-%m-%d")
    except ValueError:
        last_reset_date = datetime(1970, 1, 1)

    if today.year > last_reset_date.year or today.month > last_reset_date.month:
        print("[API-USAGE] Nuovo mese, resetto il contatore di utilizzo di The-Odds-API.")
        count = 0
        odds_api_usage["last_reset"] = today.strftime("%Y-%m-01")

    if count >= THE_ODDS_API_LIMIT:
        print(f"[ERRORE] Limite API per The-Odds-API raggiunto ({count}/{THE_ODDS_API_LIMIT}). Impossibile continuare.")
        return False
    
    odds_api_usage["count"] = count + 1
    usage["the_odds_api"] = odds_api_usage
    save_api_usage(usage)
    
    print(f"[API-USAGE] The-Odds-API: {odds_api_usage['count']}/{THE_ODDS_API_LIMIT} utilizzi questo mese.")
    return True

# --- END API USAGE COUNTER ---

def read_cfg():
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    cfg = tomllib.loads(CFG.read_text(encoding="utf-8"))
    api_cfg = cfg.get("api", {})
    settings_cfg = cfg.get("settings", {})
    key = (
        api_cfg.get("THEODDSAPI_KEY")
        or api_cfg.get("theoddsapi_key")
        or os.getenv("THEODDSAPI_KEY")
        or ""
    )
    bookmakers = settings_cfg.get("bookmakers", [])
    max_or = float(settings_cfg.get("max_overround", 0.6))
    return key.strip(), bookmakers, max_or

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

def norm(s: str) -> str:
    """Normalizzazione avanzata nomi squadre per matching robusto."""
    s = unidecode((s or "").lower().strip())
    # Rimuovi prefissi comuni calcio
    s = re.sub(r"\b(fc|cf|afc|kv|sc|bc|as|ac|us|ssc|cd|ud)\b", "", s)
    # Rimuovi numeri come "1907", "1909" spesso presenti nei nomi
    s = re.sub(r"\b\d{4}\b", "", s)
    # Rimuovi caratteri speciali
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    # Normalizza spazi multipli
    s = re.sub(r"\s+", " ", s).strip()
    # Check alias
    return ALIAS.get(s, s)

def overround(o1, ox, o2) -> float:
    """Calcola l'overround per le quote 1X2. Ritorna -1.0 se non valide."""
    try:
        vals = [float(v) for v in [o1, ox, o2] if v is not None]
        if len(vals) != 3:
            return -1.0
    except (ValueError, TypeError):
        return -1.0

    if any(v <= 1.0 for v in vals):
        return -1.0

    try:
        inv = sum(1.0 / v for v in vals)
        return inv - 1.0
    except (ZeroDivisionError, TypeError):
        return -1.0

def best_price(market):
    # restituisce (o1, ox, o2) oppure (oo, ou)
    prices = {}
    for mk in market:
        for outc in mk.get("outcomes", []):
            name = outc["name"]
            prices[name] = max(prices.get(name, 0.0), float(outc["price"]))
    return prices

def fetch_events_from_api(url: str, params: dict, code: str, delay: float) -> list:
    """Esegue la chiamata API a TheOddsAPI e gestisce i tentativi."""
    for attempt in range(3):
        try:
            if delay > 0 and attempt > 0:
                time.sleep(delay)
            
            r = http_get(url, params=params, timeout=30, desc=f"TOA {code}")
            
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    print(f"[TOA] {code}: JSON non valido")
                    continue
            
            if r.status_code == 429:
                wait = 60
                print(f"[TOA] {code}: Rate limit, attendo {wait}s...")
                time.sleep(wait)
                continue
            
            if r.status_code in (401, 403):
                print(f"[TOA] {code}: Autenticazione fallita (HTTP {r.status_code})")
                return []
            
            print(f"[TOA] {code}: HTTP {r.status_code}")
            if attempt < 2:
                time.sleep(2)
                continue
            return []
            
        except requests.exceptions.Timeout:
            if attempt < 2:
                print(f"[TOA] {code}: Timeout, retry {attempt+1}/3...")
                time.sleep(5)
                continue
            print(f"[TOA] {code}: Timeout dopo 3 tentativi")
            return []
        except requests.exceptions.RequestException as e:
            if attempt < 2:
                print(f"[TOA] {code}: Errore rete, retry {attempt+1}/3...")
                time.sleep(2)
                continue
            print(f"[TOA] {code}: Errore: {e}")
            return []
    return []

def process_and_store_odds(events: list, fixtures_to_process: list, whitelist: list, max_or: float, verbose: bool):
    """Esegue il matching tra eventi API e partite DB, e salva le quote."""
    updated_odds_count = 0
    unmatched_fixtures = []

    for fixture in fixtures_to_process:
        h, a = norm(fixture.home), norm(fixture.away)
        found = None

        # Tentativo 1: Match esatto normalizzato
        for ev in events:
            eh, ea = norm(ev.get("home_team", "")), norm(ev.get("away_team", ""))
            if (h == eh and a == ea) or (h == ea and a == eh):
                found = ev
                break

        # Tentativo 2: Match fuzzy se Tentativo 1 fallisce
        if not found:
            from rapidfuzz import fuzz
            best_match = None
            best_score = 0
            for ev in events:
                eh, ea = norm(ev.get("home_team", "")), norm(ev.get("away_team", ""))
                # Calcola similarità complessiva match
                score_h = fuzz.ratio(h, eh)
                score_a = fuzz.ratio(a, ea)
                total_score = (score_h + score_a) / 2

                # Match inverso (home/away scambiati)
                score_h_inv = fuzz.ratio(h, ea)
                score_a_inv = fuzz.ratio(a, eh)
                total_score_inv = (score_h_inv + score_a_inv) / 2

                max_score = max(total_score, total_score_inv)

                if max_score > best_score and max_score >= 85:  # Soglia 85% similarità
                    best_score = max_score
                    best_match = ev

            if best_match:
                found = best_match
                if verbose:
                    print(f"[FUZZY-MATCH {best_score:.0f}%] {fixture.home} vs {fixture.away} → {best_match.get('home_team')} vs {best_match.get('away_team')}")

        if not found:
            unmatched_fixtures.append(fixture)
            if verbose:
                print(f"[MISS] {fixture.league_code} : {fixture.home} vs {fixture.away}")
            continue

        h2h_mk = [b for b in found.get("bookmakers", []) if not whitelist or b["key"] in whitelist]
        totals_mk = h2h_mk

        o1 = ox = o2 = None
        for b in h2h_mk:
            for mk in b.get("markets", []):
                if mk.get("key") == "h2h":
                    for outc in mk.get("outcomes", []):
                        if norm(outc["name"]) == h:
                            o1 = max(o1 or 0.0, float(outc["price"]))
                        elif norm(outc["name"]) == a:
                            o2 = max(o2 or 0.0, float(outc["price"]))
                        elif outc["name"].lower() == "draw":
                            ox = max(ox or 0.0, float(outc["price"]))

        if o1 == 0: o1 = None
        if ox == 0: ox = None
        if o2 == 0: o2 = None

        orv = overround(o1, ox, o2)
        if orv != -1.0 and orv > max_or:
            if verbose:
                print(f"[REJECT] Overround alto ({orv:.2f}) per {fixture.home}–{fixture.away}. Scarto quote 1X2.")
            o1 = ox = o2 = None

        oo = ou = None
        for b in totals_mk:
            for mk in b.get("markets", []):
                if mk.get("key") == "totals":
                    for outc in mk.get("outcomes", []):
                        if str(outc.get("point")) == "2.5":
                            if outc["name"].lower() == "over":
                                oo = max(oo or 0.0, float(outc["price"]))
                            else:
                                ou = max(ou or 0.0, float(outc["price"]))
        if oo == 0: oo = None
        if ou == 0: ou = None

        if any(v is not None for v in [o1, ox, o2, oo, ou]):
            db = SessionLocal()
            try:
                odds_obj = Odds(
                    match_id=fixture.match_id,
                    odds_1=o1, odds_x=ox, odds_2=o2,
                    odds_ou25_over=oo, odds_ou25_under=ou,
                    line_ou="2.5",
                )
                db.merge(odds_obj)
                db.commit()
                updated_odds_count += 1
            except Exception as e:
                print(f"[DB-ERR] Errore salvataggio quote per {fixture.match_id}: {e}")
                db.rollback()
            finally:
                db.close()

            if verbose:
                print(f"[OK] {fixture.home}–{fixture.away} 1X2=({o1},{ox},{o2}) OU=({oo},{ou})")
        elif verbose:
            print(f"[MISS] quote non trovate per {fixture.home}–{fixture.away}")

    print(f"\n[OK] Quote aggiornate nel database → {updated_odds_count} partite.")

    # Report finale partite non matchate
    if unmatched_fixtures:
        print(f"\n[WARN] {len(unmatched_fixtures)} partite NON matchate con eventi API:")
        for uf in unmatched_fixtures[:10]:  # Mostra max 10
            print(f"  • {uf.league_code}: {uf.home} vs {uf.away}")
        if len(unmatched_fixtures) > 10:
            print(f"  ... e altre {len(unmatched_fixtures) - 10} partite")
        print("\n[HINT] Possibili cause:")
        print("  1. TheOddsAPI non copre questa lega/partita")
        print("  2. Nomi squadre molto diversi tra football-data.org e TheOddsAPI")
        print("  3. Partita cancellata/rimandata ma ancora nel DB")
        print(f"\n[ACTION] Prova a verificare manualmente su https://the-odds-api.com/sports-odds-data/")

def run_daily_fetch(args):
    """Esegue lo scaricamento delle quote solo per le partite del giorno a cui mancano."""
    key, whitelist, max_or = read_cfg()
    if not key:
        print("[ERRORE] TheOddsAPI key non trovata.")
        return

    db = SessionLocal()
    try:
        comps_to_run = [c.strip().upper() for c in args.comps.split(",") if c.strip()]

        fixtures_for_day = db.query(Fixture).filter(Fixture.date == args.date, Fixture.league_code.in_(comps_to_run)).all()
        if not fixtures_for_day:
            print(f"[WARN] Nessuna partita trovata nel DB per il {args.date} e campionati {args.comps}")
            return

        match_ids_for_day = {f.match_id for f in fixtures_for_day}

        # FIX CRITICO: Verificare che le quote siano VALIDE, non solo che esistano
        existing_valid_odds = db.query(Odds).filter(
            Odds.match_id.in_(match_ids_for_day),
            Odds.odds_1.isnot(None),  # Almeno odds_1 deve essere presente
            Odds.odds_x.isnot(None),
            Odds.odds_2.isnot(None)
        ).all()
        existing_valid_ids = {o.match_id for o in existing_valid_odds}

        # Anche quote parziali (solo OU) sono considerate da aggiornare
        partial_odds = db.query(Odds).filter(
            Odds.match_id.in_(match_ids_for_day),
            Odds.match_id.notin_(existing_valid_ids),
            (Odds.odds_ou25_over.isnot(None) | Odds.odds_ou25_under.isnot(None))
        ).all()
        partial_ids = {o.match_id for o in partial_odds}

        missing_odds_fixtures = [f for f in fixtures_for_day if f.match_id not in existing_valid_ids]

        if not missing_odds_fixtures:
            print(f"[INFO] Tutte le {len(fixtures_for_day)} partite per il {args.date} hanno già quote VALIDE (1X2 completo). Nessuna azione richiesta.")
            if partial_ids:
                print(f"[INFO] {len(partial_ids)} partite hanno quote parziali (solo OU) ma 1X2 completo OK.")
            return

        print(f"[INFO] Trovate {len(missing_odds_fixtures)} partite senza quote VALIDE per il {args.date} ({len(partial_ids)} con quote parziali). Procedo allo scaricamento.")

        leagues_to_fetch = sorted(list({f.league_code for f in missing_odds_fixtures}))
        
        all_events = []
        for code in leagues_to_fetch:
            sport = SPORT_KEYS.get(code)
            if not sport:
                print(f"[SKIP] {code}: sport key non mappata.")
                continue
            
            if not check_and_increment_usage():
                print(f"[ERRORE] Limite API raggiunto per {code}. Salto.")
                continue

            url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
            params = {"apiKey": key, "regions": "eu,uk", "markets": "h2h,totals"}
            
            events_for_sport = fetch_events_from_api(url, params, code, args.delay)
            if events_for_sport:
                all_events.extend(events_for_sport)
            
            if args.delay > 0:
                time.sleep(args.delay)
        
        if not all_events:
            print("[WARN] Nessun evento di quote scaricato durante il daily fetch.")
            return
        
        process_and_store_odds(all_events, missing_odds_fixtures, whitelist, max_or, args.verbose)

    finally:
        db.close()

def run_bulk_fetch(args):
    """Esegue uno scaricamento massivo di tutte le quote future per pre-popolare il DB."""
    print("\n[BULK FETCH] Avvio scaricamento massivo delle quote future...")
    key, whitelist, max_or = read_cfg()
    if not key:
        print("[ERRORE] TheOddsAPI key non trovata.")
        return

    db = SessionLocal()
    try:
        today = datetime.now().date()
        future_limit = today + timedelta(days=args.bulk_days)
        fixtures_to_process = db.query(Fixture).filter(Fixture.date >= today, Fixture.date <= future_limit).all()
        print(f"[DB] Trovate {len(fixtures_to_process)} partite future (fino a {future_limit.isoformat()}) nel DB da mappare.")

        all_events = []
        for code, sport in SPORT_KEYS.items():
            print(f"--- Scaricamento quote per {code} ({sport}) ---")
            if not check_and_increment_usage():
                print("[ERRORE] Limite API raggiunto. Interrompo il bulk fetch.")
                break
            
            url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
            params = {"apiKey": key, "regions": "eu,uk", "markets": "h2h,totals"}
            
            events_for_sport = fetch_events_from_api(url, params, code, args.delay)
            if events_for_sport:
                all_events.extend(events_for_sport)
            
            if args.delay > 0:
                time.sleep(args.delay)
        
        if not all_events:
            print("[WARN] Nessun evento di quote scaricato. Termino.")
            return

        print(f"\n[PROCESS] Totale eventi di quote scaricati: {len(all_events)}. Inizio il matching...")
        process_and_store_odds(all_events, fixtures_to_process, whitelist, max_or, args.verbose)

    finally:
        db.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="Data YYYY-MM-DD per cui scaricare le quote (modalità giornaliera)")
    ap.add_argument("--comps", help="Competizioni separate da virgola (es. SA,PL)")
    ap.add_argument("--delay", type=float, default=0.3, help="Ritardo tra richieste (s)")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--bulk-fetch", action="store_true", help="Esegue uno scaricamento massivo di tutte le quote future per pre-popolare il DB.")
    ap.add_argument("--bulk-days", type=int, default=30, help="Numero di giorni futuri da considerare nel bulk-fetch.")
    args = ap.parse_args()

    if args.bulk_fetch:
        run_bulk_fetch(args)
    else:
        if not args.date or not args.comps:
            print("[ERRORE] Le opzioni --date e --comps sono richieste per la modalità giornaliera.")
            return
        run_daily_fetch(args)

if __name__ == "__main__":
    main()
