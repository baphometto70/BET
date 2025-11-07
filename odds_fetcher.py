#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, time, requests, re, os, json, subprocess
from pathlib import Path
import pandas as pd
from unidecode import unidecode
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent
CFG  = ROOT/"config.toml"
FX   = ROOT/"fixtures.csv"

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
    "qarabag agdam fk":"qarabag",
    "olympique de marseille":"marseille",
    "manchester city fc":"manchester city",
    "fc barcelona":"barcelona",
    "athletic club":"athletic bilbao",
    "sport lisboa e benfica":"benfica",
    "bayer 04 leverkusen":"bayer leverkusen",
    "paphos fc":"paphos",
    "fk kairat":"kairat",
}

def read_cfg():
    import tomllib
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
    return key.strip(), bookmakers


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
    s = unidecode((s or "").lower())
    s = re.sub(r"\b(fc|cf|afc|kv|sc|bc)\b","",s)
    s = re.sub(r"[^a-z0-9 ]+","",s)
    s = re.sub(r"\s+"," ",s).strip()
    return ALIAS.get(s, s)

def best_price(market):
    # restituisce (o1, ox, o2) oppure (oo, ou)
    prices = {}
    for mk in market:
        for outc in mk.get("outcomes", []):
            name = outc["name"].lower()
            prices[name] = max(prices.get(name,0), float(outc["price"]))
    return prices

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--comps", required=True)
    ap.add_argument("--delay", type=float, default=0.3, help="ritardo tra richieste (s)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    key, whitelist = read_cfg()
    if not key or not key.strip():
        print("[ERR] TheOddsAPI key non trovata (config.toml o variabile THEODDSAPI_KEY).")
        return
    
    try:
        df = pd.read_csv(FX, dtype=str)
    except FileNotFoundError:
        print(f"[ERR] {FX} non trovato. Esegui prima fixtures_fetcher.py")
        return
    except Exception as e:
        print(f"[ERR] Errore lettura {FX}: {e}")
        return
    
    if df.empty:
        print("[WARN] fixtures.csv vuoto.")
        return

    touched = 0
    for code in [c.strip() for c in args.comps.split(",") if c.strip()]:
        sport = SPORT_KEYS.get(code)
        if not sport:
            print(f"[SKIP] {code}: sport key non mappata.")
            continue

        url = "https://api.the-odds-api.com/v4/sports/{}/odds".format(sport)
        params = {
            "apiKey": key,
            "regions": "eu,uk",
            "markets": "h2h,totals",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }
        
        # Retry con backoff
        events = None
        for attempt in range(3):
            try:
                if args.delay > 0 and attempt > 0:
                    time.sleep(args.delay)
                
                r = http_get(url, params=params, timeout=30, desc=f"TOA {code}")
                
                if r.status_code == 200:
                    try:
                        events = r.json()
                        break
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
                    break
                
                print(f"[TOA] {code}: HTTP {r.status_code}")
                if attempt < 2:
                    time.sleep(2)
                    continue
                break
                
            except requests.exceptions.Timeout:
                if attempt < 2:
                    print(f"[TOA] {code}: Timeout, retry {attempt+1}/3...")
                    time.sleep(5)
                    continue
                print(f"[TOA] {code}: Timeout dopo 3 tentativi")
                break
            except requests.exceptions.RequestException as e:
                if attempt < 2:
                    print(f"[TOA] {code}: Errore rete, retry {attempt+1}/3...")
                    time.sleep(2)
                    continue
                print(f"[TOA] {code}: Errore: {e}")
                break
        
        if events is None:
            print(f"[SKIP] {code}: Nessun dato disponibile")
            continue

        # per ogni riga fixtures del codice campionato
        for i, row in df[df["league_code"]==code].iterrows():
            h, a = norm(row["home"]), norm(row["away"])
            found = None
            for ev in events:
                eh, ea = norm(ev.get("home_team","")), norm(ev.get("away_team",""))
                # match simmetrico
                if (h==eh and a==ea) or (h==ea and a==eh):
                    found = ev
                    break
            if not found:
                if args.verbose:
                    print(f"[MISS] {row['league']} : {row['home']} vs {row['away']}")
                continue

            # MERCATI
            h2h_mk    = [b for b in found.get("bookmakers",[]) if not whitelist or b["key"] in whitelist]
            totals_mk = h2h_mk

            # 1X2
            o1=ox=o2=None
            for b in h2h_mk:
                for mk in b.get("markets",[]):
                    if mk.get("key")=="h2h":
                        prices = best_price([mk])
                        o1 = max(o1 or 0.0, prices.get("home",0.0))
                        ox = max(ox or 0.0, prices.get("draw",0.0))
                        o2 = max(o2 or 0.0, prices.get("away",0.0))
            if o1==0:o1=None
            if ox==0:ox=None
            if o2==0:o2=None

            # O/U 2.5
            oo=ou=None
            for b in totals_mk:
                for mk in b.get("markets",[]):
                    if mk.get("key")=="totals":
                        for outc in mk.get("outcomes",[]):
                            if str(outc.get("point"))=="2.5":
                                if outc["name"].lower()=="over":
                                    oo = max(oo or 0.0, float(outc["price"]))
                                else:
                                    ou = max(ou or 0.0, float(outc["price"]))
            if oo==0:oo=None
            if ou==0:ou=None

            if any(v is not None for v in [o1,ox,o2,oo,ou]):
                df.loc[i,"odds_1"] = o1 if o1 is not None else ""
                df.loc[i,"odds_x"] = ox if ox is not None else ""
                df.loc[i,"odds_2"] = o2 if o2 is not None else ""
                df.loc[i,"odds_ou25_over"]  = oo if oo is not None else ""
                df.loc[i,"odds_ou25_under"] = ou if ou is not None else ""
                touched += 1
                if args.verbose:
                    print(f"[OK] {row['home']}–{row['away']} 1X2=({o1},{ox},{o2}) OU=({oo},{ou})")
            else:
                if args.verbose:
                    print(f"[MISS] quote non trovate per {row['home']}–{row['away']}")

    try:
        df.to_csv(FX, index=False)
        print(f"[OK] Quote aggiornate → righe toccate: {touched}")
    except Exception as e:
        print(f"[ERR] Errore scrittura {FX}: {e}")

if __name__=="__main__":
    main()
