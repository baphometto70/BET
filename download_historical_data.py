#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DOWNLOAD DATI STORICI COMPLETI 2025-2026
Scarica da Football-Data.org API:
- Risultati (tutti i match 2025-2026)
- Lineups (formazioni)
- Goalscorers (marcatori)
- Match statistics (shots, corners, possesso, etc.)
"""

import os
import sys
import time
import toml
from pathlib import Path
from datetime import date, datetime, timedelta
import requests
from database import SessionLocal
from models import Fixture
from models_extended import MatchResult, MatchStats, Lineup, Goalscorer

# ========================================
# CONFIG
# ========================================
ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.toml"

# Carica token API
cfg = toml.load(CONFIG_PATH)
TOKEN = cfg.get("api", {}).get("FOOTBALL_DATA_ORG_TOKEN")

if not TOKEN:
    print("❌ Token Football-Data.org non trovato in config.toml!")
    sys.exit(1)

API_BASE = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": TOKEN}

# Leghe supportate
LEAGUES = {
    'SA': 'SA',      # Serie A
    'PL': 'PL',      # Premier League
    'PD': 'PD',      # La Liga
    'BL1': 'BL',     # Bundesliga
    'FL1': 'FL1',    # Ligue 1
}

# ========================================
# FUNZIONI HELPER
# ========================================
def get_league_id(league_code):
    """Mappa codici lega a ID Football-Data.org"""
    mapping = {
        'SA': 2019,   # Serie A
        'PL': 2021,   # Premier League
        'PD': 2014,   # La Liga
        'BL': 2002,   # Bundesliga
        'FL1': 2015,  # Ligue 1
    }
    return mapping.get(league_code)


def fetch_matches(league_code, season='2025', status='FINISHED'):
    """Scarica tutti i match finiti di una lega/stagione"""
    league_id = get_league_id(league_code)
    if not league_id:
        print(f"⚠️  Lega {league_code} non supportata")
        return []

    url = f"{API_BASE}/competitions/{league_id}/matches"
    params = {
        'season': season,
        'status': status
    }

    try:
        print(f"\n📡 Scarico match {league_code} stagione {season}...")
        resp = requests.get(url, headers=HEADERS, params=params, timeout=30)

        if resp.status_code == 429:
            print("⏸️  Rate limit - aspetto 60s...")
            time.sleep(60)
            return fetch_matches(league_code, season, status)

        resp.raise_for_status()
        data = resp.json()

        matches = data.get('matches', [])
        print(f"✅ {len(matches)} match trovati")
        return matches

    except Exception as e:
        print(f"❌ Errore download {league_code}: {e}")
        return []


def fetch_match_details(match_id):
    """Scarica dettagli completi di un match (lineups, stats, scorers)"""
    url = f"{API_BASE}/matches/{match_id}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)

        if resp.status_code == 429:
            print("⏸️  Rate limit - aspetto 60s...")
            time.sleep(60)
            return fetch_match_details(match_id)

        if resp.status_code == 404:
            print(f"⚠️  Match {match_id} non trovato")
            return None

        resp.raise_for_status()
        return resp.json()

    except Exception as e:
        print(f"❌ Errore dettagli match {match_id}: {e}")
        return None


# ========================================
# SALVA NEL DATABASE
# ========================================
def save_match_result(db, match_data, our_match_id):
    """Salva risultato nel database"""
    score = match_data.get('score', {})
    fulltime = score.get('fullTime', {})
    halftime = score.get('halfTime', {})

    result = MatchResult(
        match_id=our_match_id,
        ft_home_goals=fulltime.get('home'),
        ft_away_goals=fulltime.get('away'),
        ht_home_goals=halftime.get('home'),
        ht_away_goals=halftime.get('away'),
        winner=score.get('winner'),  # 'HOME_TEAM', 'AWAY_TEAM', 'DRAW'
        referee=match_data.get('referees', [{}])[0].get('name') if match_data.get('referees') else None,
        venue=match_data.get('venue'),
        attendance=match_data.get('attendance')
    )

    # Check se esiste già
    existing = db.query(MatchResult).filter(MatchResult.match_id == our_match_id).first()
    if existing:
        db.delete(existing)

    db.add(result)
    return result


def save_match_stats(db, match_data, our_match_id):
    """Salva statistiche match"""
    # Football-Data.org non fornisce stats dettagliate nell'API gratuita
    # Usiamo placeholder per ora
    stats = MatchStats(
        match_id=our_match_id,
        shots_home=None,
        shots_away=None,
        shots_on_target_home=None,
        shots_on_target_away=None,
        possession_home=None,
        possession_away=None,
        corners_home=None,
        corners_away=None,
        fouls_home=None,
        fouls_away=None,
        yellow_cards_home=None,
        yellow_cards_away=None,
        red_cards_home=None,
        red_cards_away=None
    )

    existing = db.query(MatchStats).filter(MatchStats.match_id == our_match_id).first()
    if existing:
        db.delete(existing)

    db.add(stats)
    return stats


def save_goalscorers(db, match_data, our_match_id):
    """Salva marcatori"""
    # Rimuovi vecchi
    db.query(Goalscorer).filter(Goalscorer.match_id == our_match_id).delete()

    goals = match_data.get('goals', [])
    if not goals:
        return

    for goal in goals:
        scorer = Goalscorer(
            match_id=our_match_id,
            team=goal.get('team', {}).get('name', 'HOME' if goal.get('type') == 'REGULAR' else 'AWAY'),
            player_name=goal.get('scorer', {}).get('name', 'Unknown'),
            minute=goal.get('minute', 0),
            is_penalty=goal.get('type') == 'PENALTY',
            is_own_goal=goal.get('type') == 'OWN',
            assist_by=goal.get('assist', {}).get('name') if goal.get('assist') else None
        )
        db.add(scorer)


# ========================================
# MAIN
# ========================================
def main():
    print("=" * 100)
    print("📥 DOWNLOAD DATI STORICI COMPLETI 2025-2026")
    print("=" * 100)

    db = SessionLocal()

    total_saved = 0
    total_errors = 0

    try:
        # Per ogni lega
        for league_code in ['SA', 'PL', 'PD', 'BL', 'FL1']:
            print(f"\n{'='*100}")
            print(f"🏆 LEGA: {league_code}")
            print(f"{'='*100}")

            # Scarica match 2025
            matches_2025 = fetch_matches(league_code, '2025', 'FINISHED')
            # Scarica match 2026 (in corso)
            matches_2026 = fetch_matches(league_code, '2026', 'FINISHED')

            all_matches = matches_2025 + matches_2026

            print(f"\n📊 Totale match da processare: {len(all_matches)}")

            for i, match in enumerate(all_matches, 1):
                api_match_id = match.get('id')
                home_team = match.get('homeTeam', {}).get('name', 'Unknown')
                away_team = match.get('awayTeam', {}).get('name', 'Unknown')
                match_date = match.get('utcDate', '')[:10]  # YYYY-MM-DD

                print(f"\n[{i}/{len(all_matches)}] {match_date} | {home_team} vs {away_team}")

                # Trova nel nostro database
                our_match = db.query(Fixture).filter(
                    Fixture.home.ilike(f"%{home_team}%"),
                    Fixture.away.ilike(f"%{away_team}%"),
                    Fixture.date == datetime.strptime(match_date, '%Y-%m-%d').date()
                ).first()

                if not our_match:
                    print(f"   ⚠️  Non trovato nel nostro DB - skip")
                    continue

                our_match_id = our_match.match_id

                # Salva risultato base
                try:
                    save_match_result(db, match, our_match_id)
                    save_match_stats(db, match, our_match_id)

                    # Scarica dettagli completi (rate limit!)
                    print(f"   📡 Scarico dettagli...")
                    details = fetch_match_details(api_match_id)

                    if details:
                        save_goalscorers(db, details, our_match_id)

                    db.commit()
                    total_saved += 1
                    print(f"   ✅ Salvato!")

                    # Rate limit: max 10 chiamate/minuto
                    if i % 10 == 0:
                        print(f"\n⏸️  Pausa 60s per rate limit...")
                        time.sleep(60)
                    else:
                        time.sleep(2)  # Piccola pausa tra richieste

                except Exception as e:
                    db.rollback()
                    print(f"   ❌ Errore: {e}")
                    total_errors += 1
                    continue

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrotto dall'utente")
    finally:
        db.close()

    # Riepilogo
    print("\n\n" + "=" * 100)
    print("📊 RIEPILOGO")
    print("=" * 100)
    print(f"✅ Match salvati: {total_saved}")
    print(f"❌ Errori: {total_errors}")
    print("=" * 100)


if __name__ == "__main__":
    main()
