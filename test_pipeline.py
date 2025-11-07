#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script di test rapido per verificare che la pipeline funzioni.
Esegue tutti gli step principali e verifica i risultati.
"""

import sys
from pathlib import Path
import subprocess
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parent

def test_step(name, cmd, required=True):
    """Esegue un comando e verifica il risultato."""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"Comando: {cmd}")
    print('='*60)
    
    try:
        result = subprocess.run(
            cmd.split(),
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        if result.returncode != 0:
            if required:
                print(f"❌ FALLITO (exit code {result.returncode})")
                return False
            else:
                print(f"⚠️  AVVISI (exit code {result.returncode}, continuo)")
                return True
        else:
            print(f"✅ COMPLETATO")
            return True
            
    except subprocess.TimeoutExpired:
        print(f"❌ TIMEOUT dopo 300s")
        return False
    except Exception as e:
        print(f"❌ ERRORE: {e}")
        return False

def main():
    print("="*60)
    print("TEST PIPELINE COMPLETA")
    print("="*60)
    
    # Data di test (oggi o domani)
    test_date = date.today().isoformat()
    comps = "SA,PL"  # Solo Serie A e Premier League per test rapido
    
    results = []
    
    # Step 1: Fixtures
    results.append((
        "Fetch Fixtures",
        test_step(
            "Recupero partite",
            f"python fixtures_fetcher.py --date {test_date} --comps {comps}",
            required=True
        )
    ))
    
    # Verifica fixtures.csv
    fix_path = ROOT / "fixtures.csv"
    if fix_path.exists():
        import pandas as pd
        try:
            df = pd.read_csv(fix_path)
            print(f"\n✅ fixtures.csv: {len(df)} partite trovate")
            if len(df) > 0:
                print(f"   Esempio: {df.iloc[0]['home']} vs {df.iloc[0]['away']}")
        except Exception as e:
            print(f"⚠️  Errore lettura fixtures.csv: {e}")
    else:
        print("❌ fixtures.csv non creato")
        results[-1] = (results[-1][0], False)
    
    # Step 2: Odds (opzionale)
    results.append((
        "Fetch Odds",
        test_step(
            "Recupero quote",
            f"python odds_fetcher.py --date {test_date} --comps {comps} --delay 0.3",
            required=False
        )
    ))
    
    # Step 3: Features (opzionale, può essere lento)
    results.append((
        "Populate Features",
        test_step(
            "Popolamento features",
            f"python features_populator.py --date {test_date} --comps {comps} --n_recent 5 --delay 0.6 --cache 1",
            required=False
        )
    ))
    
    # Verifica features.csv
    fea_path = ROOT / "features.csv"
    if fea_path.exists():
        import pandas as pd
        try:
            df = pd.read_csv(fea_path)
            print(f"\n✅ features.csv: {len(df)} righe")
            if len(df) > 0:
                filled = df.select_dtypes(include=['object', 'float', 'int']).notna().sum().sum()
                total = df.select_dtypes(include=['object', 'float', 'int']).size
                pct = (filled / total * 100) if total > 0 else 0
                print(f"   Dati compilati: {pct:.1f}%")
        except Exception as e:
            print(f"⚠️  Errore lettura features.csv: {e}")
    
    # Step 4: Creazione modello dummy (se non esiste)
    model_path = ROOT / "models" / "bet_ou25.joblib"
    if not model_path.exists():
        print("\n" + "="*60)
        print("Creazione modello dummy per test...")
        print("="*60)
        results.append((
            "Train Dummy Model",
            test_step(
                "Training modello dummy",
                "python model_pipeline.py --train-dummy",
                required=False
            )
        ))
    
    # Step 5: Predictions
    results.append((
        "Generate Predictions",
        test_step(
            "Generazione previsioni",
            "python model_pipeline.py --predict",
            required=True
        )
    ))
    
    # Verifica predictions.csv
    pred_path = ROOT / "predictions.csv"
    if pred_path.exists():
        import pandas as pd
        try:
            df = pd.read_csv(pred_path)
            print(f"\n✅ predictions.csv: {len(df)} previsioni")
            if len(df) > 0:
                print("\n📊 Prime 3 previsioni:")
                for idx, row in df.head(3).iterrows():
                    match = f"{row.get('home', '?')} vs {row.get('away', '?')}"
                    p_over = row.get('p_over_2_5', 'N/A')
                    p1 = row.get('p1', 'N/A')
                    print(f"   {match}: OU2.5 Over={p_over}, 1X2 1={p1}")
        except Exception as e:
            print(f"⚠️  Errore lettura predictions.csv: {e}")
    else:
        print("❌ predictions.csv non creato")
        results[-1] = (results[-1][0], False)
    
    # Riepilogo
    print("\n" + "="*60)
    print("RIEPILOGO TEST")
    print("="*60)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(s for _, s in results if "Predictions" in _ or "Fixtures" in _)
    
    if all_passed:
        print("\n🎉 Pipeline funzionante! Puoi usare:")
        print(f"   python app.py  (dashboard web)")
        print(f"   make daily DATE={test_date} COMPS={comps}  (CLI)")
        return 0
    else:
        print("\n⚠️  Alcuni step hanno fallito. Controlla i log sopra.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

