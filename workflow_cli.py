#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
workflow_cli.py
---------------
Orchestratore interattivo per la pipeline giornaliera:
  1. Chiede data e campionati
  2. Esegue in ordine: fixtures → odds → sanitize → features → predict
  3. Opzionale: esegue scommesse_pipeline (--run/--update-metrics/--report)
  4. Al termine mostra un estratto di predictions.csv

Il comando stampa in tempo reale l'output di ogni step e verifica i file generati
prima di passare allo step successivo.
"""

from __future__ import annotations

import os
import sys
import shlex
import subprocess
from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent


def prompt(message: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default else ""
    ans = input(f"{message}{suffix}: ").strip()
    return ans or (default or "")


def run_step(name: str, cmd: List[str]) -> bool:
    print(f"\n=== {name} ===")
    print("$", " ".join(shlex.quote(c) for c in cmd))
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        print(line.rstrip())
    proc.wait()
    if proc.returncode != 0:
        print(f"[ERR] Step '{name}' terminato con codice {proc.returncode}.")
        return False
    print(f"[OK] Step '{name}' completato.")
    return True


def load_csv_rows(path: Path, match_date: str) -> int:
    if not path.exists():
        return 0
    try:
        df = pd.read_csv(path)
    except Exception:
        return 0
    if "date" in df.columns:
        return int((df["date"].astype(str) == match_date).sum())
    return len(df)


def confirm_continue(prompt_msg: str) -> bool:
    while True:
        ans = input(f"{prompt_msg} [y/n]: ").strip().lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False


def main():
    print("=== Orchestratore pipeline ===")
    default_date = date.today().isoformat()
    match_date = prompt("Data (YYYY-MM-DD)", default_date)
    print("\nCampionati disponibili:")
    leagues_hint = [
        "SA (Serie A)",
        "PL (Premier League)",
        "PD (Liga)",
        "BL1 (Bundesliga)",
        "FL1 (Ligue 1)",
        "DED (Eredivisie)",
        "PPL (Primeira Liga)",
        "ELC (Championship)",
    ]
    print("  " + ", ".join(leagues_hint))
    comps_default = "SA,PL,PD,BL1,FL1"
    comps_raw = prompt("Campionati da includere (es. SA,PL,...)", comps_default)
    comps = ",".join(sorted({c.strip().upper() for c in comps_raw.split(",") if c.strip()}))
    print("\nParametri suggeriti per features_populator:")
    print("  - N match recenti per xG: 5 (puoi salire a 7-10 per smoothing)")
    print("  - Delay scraping (s): 0.6 (ridocalo se hai fretta, ma rischi rate-limit)")
    n_recent = prompt("N match recenti per xG", "5")
    delay = prompt("Delay scraping features (s)", "0.6")

    steps = [
        ("Fetch fixtures", ["python", "fixtures_fetcher.py", "--date", match_date, "--comps", comps]),
        ("Fetch odds", ["python", "odds_fetcher.py", "--date", match_date, "--comps", comps, "--delay", "0.3"]),
        ("Sanitize fixtures", ["python", "sanitize_fixtures.py"]),
        (
            "Populate features",
            [
                "python",
                "features_populator.py",
                "--date",
                match_date,
                "--comps",
                comps,
                "--n_recent",
                n_recent,
                "--delay",
                delay,
                "--cache",
                "1",
            ],
        ),
        ("Predict (model_pipeline)", ["python", "model_pipeline.py", "--predict"]),
    ]

    for label, cmd in steps:
        if not run_step(label, cmd):
            if confirm_continue("Vuoi riprovare questo step?"):
                if not run_step(label, cmd):
                    print("[STOP] Interrompo la pipeline.")
                    return
            else:
                print("[STOP] Interrompo la pipeline.")
                return

        if label in ("Fetch fixtures", "Sanitize fixtures", "Populate features"):
            path = ROOT / ("fixtures.csv" if "fixture" in label.lower() else "features.csv")
            rows = load_csv_rows(path, match_date)
            if rows == 0:
                print(f"[WARN] {path.name} non contiene righe per {match_date}.")
                if not confirm_continue("Vuoi continuare comunque?"):
                    return

    if confirm_continue("Eseguire anche scommesse_pipeline (--run --update-metrics --report)?"):
        run_step(
            "Scommesse pipeline",
            ["python", "scommesse_pipeline.py", "--run", "--update-metrics", "--report"],
        )

    predictions_path = ROOT / "predictions.csv"
    if predictions_path.exists():
        if confirm_continue("Vuoi vedere un estratto di predictions.csv?"):
            try:
                df = pd.read_csv(predictions_path)
                cols = [
                    "date",
                    "time",
                    "league",
                    "home",
                    "away",
                    "Previsione_1X2",
                    "Prob_1",
                    "Prob_X",
                    "Prob_2",
                    "pick_1x2",
                    "pick_ou25",
                ]
                cols = [c for c in cols if c in df.columns]
                print(df[cols].head(10).to_string(index=False))
            except Exception as e:
                print(f"[WARN] Impossibile leggere predictions.csv: {e}")

        if confirm_continue("Aprire report.html (default browser)?"):
            subprocess.run(["open", str(ROOT / "report.html")])

    print("\n[TUTTO COMPLETATO]")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Uscita richiesta dall'utente.")
