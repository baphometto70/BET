#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
expand_historical_dataset.py

Script per ampliare massivamente il dataset storico scaricando dati da più stagioni.
Target: almeno 2500+ partite per training ML robusto.

Strategia:
1. Scarica fixture storiche da football-data.org (2022-2025)
2. Popola features per ogni partita (xG, rest, context)
3. Scarica risultati finali
4. Costruisce dataset completo per training

Usage:
    python3 expand_historical_dataset.py --start-year 2022 --end-year 2025 --comps "SA,PL,PD,BL1,FL1"
"""

import argparse
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Mappa competizioni per stagioni disponibili su football-data.org
# Nota: alcune leghe hanno ID diversi per stagioni diverse
COMP_SEASONS = {
    "SA": {"2022": "SA", "2023": "SA", "2024": "SA", "2025": "SA"},  # Serie A
    "PL": {"2022": "PL", "2023": "PL", "2024": "PL", "2025": "PL"},  # Premier League
    "PD": {"2022": "PD", "2023": "PD", "2024": "PD", "2025": "PD"},  # La Liga
    "BL1": {"2022": "BL1", "2023": "BL1", "2024": "BL1", "2025": "BL1"},  # Bundesliga
    "FL1": {"2022": "FL1", "2023": "FL1", "2024": "FL1", "2025": "FL1"},  # Ligue 1
}

def run_cmd(cmd: str, desc: str = ""):
    """Esegue un comando shell e stampa output."""
    print(f"\n{'=' * 80}")
    print(f"[{desc or 'CMD'}] {cmd}")
    print(f"{'=' * 80}\n")

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=str(ROOT))

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        print(f"\n[ERROR] Comando fallito con exit code {result.returncode}")
        return False
    return True

def get_season_dates(year: int) -> tuple:
    """
    Restituisce le date (inizio, fine) per una stagione calcistica.
    Stagione europea tipicamente: agosto anno N → maggio anno N+1
    """
    start_date = date(year, 8, 1)  # Inizio agosto
    end_date = date(year + 1, 5, 31)  # Fine maggio anno successivo
    return start_date, end_date

def expand_dataset(start_year: int, end_year: int, comps: list[str], n_recent: int = 5, delay: float = 0.6):
    """
    Espande il dataset storico scaricando dati per più stagioni.

    Args:
        start_year: Anno inizio (es. 2022)
        end_year: Anno fine (es. 2025)
        comps: Lista di competizioni (es. ["SA", "PL", "BL1"])
        n_recent: Numero partite recenti per calcolare xG
        delay: Delay tra richieste scraping
    """
    print(f"\n{'#' * 80}")
    print(f"# ESPANSIONE DATASET STORICO")
    print(f"# Stagioni: {start_year}-{start_year+1} → {end_year}-{end_year+1}")
    print(f"# Competizioni: {', '.join(comps)}")
    print(f"# Target: ~300 partite/stagione × {len(comps)} × {end_year - start_year + 1} stagioni")
    print(f"# = ~{300 * len(comps) * (end_year - start_year + 1)} partite totali")
    print(f"{'#' * 80}\n")

    total_success = 0
    total_attempted = 0

    for year in range(start_year, end_year + 1):
        print(f"\n{'*' * 80}")
        print(f"* STAGIONE {year}-{year + 1}")
        print(f"{'*' * 80}\n")

        start_date, end_date = get_season_dates(year)

        # Step 1: Costruisci dataset storico per questa stagione
        cmd = (
            f"{sys.executable} historical_builder.py "
            f"--from {start_date.isoformat()} "
            f"--to {end_date.isoformat()} "
            f"--comps \"{','.join(comps)}\" "
            f"--n_recent {n_recent} "
            f"--delay {delay}"
        )

        total_attempted += 1
        if run_cmd(cmd, f"Historical Builder {year}-{year+1}"):
            total_success += 1
            print(f"\n[✓] Stagione {year}-{year+1} completata con successo")
        else:
            print(f"\n[✗] Stagione {year}-{year+1} fallita")
            # Continua comunque con le altre stagioni

    print(f"\n{'#' * 80}")
    print(f"# RIEPILOGO ESPANSIONE")
    print(f"# Stagioni processate con successo: {total_success}/{total_attempted}")
    print(f"# Dataset finale salvato in: {ROOT / 'data' / 'historical_dataset.csv'}")
    print(f"{'#' * 80}\n")

    # Mostra statistiche dataset finale
    import pandas as pd
    hist_path = ROOT / "data" / "historical_dataset.csv"
    hist_1x2_path = ROOT / "data" / "historical_1x2.csv"

    if hist_path.exists():
        try:
            df = pd.read_csv(hist_path)
            print(f"\n[INFO] historical_dataset.csv:")
            print(f"  - Totale righe: {len(df)}")
            print(f"  - Campionati: {df['league'].unique().tolist() if 'league' in df.columns else 'N/A'}")
            print(f"  - Date range: {df['date'].min()} → {df['date'].max()}" if 'date' in df.columns else "")

            # Check target OU
            if 'target_ou25' in df.columns:
                over_count = (df['target_ou25'] == 1).sum()
                under_count = (df['target_ou25'] == 0).sum()
                print(f"  - Over 2.5: {over_count} ({over_count / len(df) * 100:.1f}%)")
                print(f"  - Under 2.5: {under_count} ({under_count / len(df) * 100:.1f}%)")
        except Exception as e:
            print(f"[WARN] Errore lettura dataset: {e}")
    else:
        print(f"\n[WARN] {hist_path} non trovato")

    if hist_1x2_path.exists():
        try:
            df_1x2 = pd.read_csv(hist_1x2_path)
            print(f"\n[INFO] historical_1x2.csv:")
            print(f"  - Totale righe: {len(df_1x2)}")

            if 'target_1x2' in df_1x2.columns:
                home_wins = (df_1x2['target_1x2'] == '1').sum()
                draws = (df_1x2['target_1x2'] == 'X').sum()
                away_wins = (df_1x2['target_1x2'] == '2').sum()
                print(f"  - Home wins: {home_wins} ({home_wins / len(df_1x2) * 100:.1f}%)")
                print(f"  - Draws: {draws} ({draws / len(df_1x2) * 100:.1f}%)")
                print(f"  - Away wins: {away_wins} ({away_wins / len(df_1x2) * 100:.1f}%)")
        except Exception as e:
            print(f"[WARN] Errore lettura dataset 1X2: {e}")
    else:
        print(f"\n[INFO] {hist_1x2_path} sarà creato dal historical_dataset.csv se manca target_1x2")

    print(f"\n[NEXT STEP] Per training modelli ML, esegui:")
    print(f"  python3 model_pipeline.py --train-ou --algo lgbm")
    print(f"  python3 model_pipeline.py --train-1x2 --algo lgbm\n")

    return total_success, total_attempted

def main():
    parser = argparse.ArgumentParser(
        description="Espandi dataset storico per training ML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  # Scarica stagioni 2022-2025 per le top 5 leghe
  python3 expand_historical_dataset.py --start-year 2022 --end-year 2024 --comps "SA,PL,PD,BL1,FL1"

  # Solo Serie A e Premier League per ultime 2 stagioni
  python3 expand_historical_dataset.py --start-year 2023 --end-year 2024 --comps "SA,PL"
        """
    )

    parser.add_argument(
        "--start-year",
        type=int,
        default=2022,
        help="Anno inizio (default: 2022)"
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=2024,
        help="Anno fine (default: 2024)"
    )
    parser.add_argument(
        "--comps",
        type=str,
        default="SA,PL,PD,BL1,FL1",
        help="Competizioni separate da virgola (default: SA,PL,PD,BL1,FL1)"
    )
    parser.add_argument(
        "--n-recent",
        type=int,
        default=5,
        help="Numero partite recenti per xG (default: 5)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.6,
        help="Delay tra richieste scraping in secondi (default: 0.6)"
    )

    args = parser.parse_args()

    # Valida input
    if args.start_year < 2015 or args.start_year > datetime.now().year:
        print(f"[ERROR] start-year deve essere tra 2015 e {datetime.now().year}")
        sys.exit(1)

    if args.end_year < args.start_year or args.end_year > datetime.now().year:
        print(f"[ERROR] end-year deve essere >= start-year e <= {datetime.now().year}")
        sys.exit(1)

    comps_list = [c.strip().upper() for c in args.comps.split(",")]
    invalid_comps = [c for c in comps_list if c not in COMP_SEASONS]
    if invalid_comps:
        print(f"[ERROR] Competizioni non valide: {', '.join(invalid_comps)}")
        print(f"[INFO] Competizioni supportate: {', '.join(COMP_SEASONS.keys())}")
        sys.exit(1)

    # Info all'utente
    total_est = 300 * len(comps_list) * (args.end_year - args.start_year + 1)
    print(f"\n[STIMA] Verranno scaricate circa {total_est} partite")
    print(f"[TEMPO] Stima tempo: ~{total_est * args.delay / 60:.0f} minuti di scraping")
    print(f"\n[INFO] Avvio espansione dataset automatica...")

    # Esegui espansione
    success, attempted = expand_dataset(
        args.start_year,
        args.end_year,
        comps_list,
        args.n_recent,
        args.delay
    )

    if success == attempted:
        print(f"\n[SUCCESS] Tutte le {attempted} stagioni completate!")
        sys.exit(0)
    else:
        print(f"\n[WARNING] Solo {success}/{attempted} stagioni completate")
        sys.exit(1)

if __name__ == "__main__":
    main()
