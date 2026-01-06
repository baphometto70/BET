#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
optimize_models.py - Ottimizzazione iperparametri con Optuna

Ottimizza i modelli LightGBM per OU 2.5 e 1X2 usando Optuna.
Salva i modelli ottimizzati in models/bet_ou25_optimized.joblib e models/bet_1x2_optimized.joblib.

Usage:
    python optimize_models.py --model ou25 --trials 50
    python optimize_models.py --model 1x2 --trials 100
    python optimize_models.py --model both --trials 50
"""

import argparse
import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import joblib
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import log_loss, brier_score_loss

try:
    import optuna
    from optuna.samplers import TPESampler
except ImportError:
    print("ERROR: Optuna non installato. Esegui: pip install optuna")
    exit(1)

try:
    from lightgbm import LGBMClassifier
except ImportError:
    print("ERROR: LightGBM non installato. Esegui: pip install lightgbm")
    exit(1)

# Paths
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
MODEL_DIR = ROOT / "models"

HIST_OU_PATH = DATA_DIR / "historical_dataset_enhanced.csv"
HIST_1X2_PATH = DATA_DIR / "historical_1x2_enhanced.csv"

# Features (dalle colonne disponibili negli storici)
FEATURES_BASE = [
    "xg_for_home", "xg_against_home", "xg_for_away", "xg_against_away",
    "derby_flag", "europe_flag_home", "europe_flag_away", "meteo_flag",
]

FEATURES_ADVANCED = [
    # Recent Form Features (Home)
    "home_form_xg_for", "home_form_xg_against", "home_form_xg_diff",
    "home_form_wins", "home_form_draws", "home_form_losses",
    "home_form_goals_for", "home_form_goals_against", "home_form_points", "home_form_trend",
    # Recent Form Features (Away)
    "away_form_xg_for", "away_form_xg_against", "away_form_xg_diff",
    "away_form_wins", "away_form_draws", "away_form_losses",
    "away_form_goals_for", "away_form_goals_against", "away_form_points", "away_form_trend",
    # Head-to-Head
    "h2h_home_wins", "h2h_draws", "h2h_away_wins",
    "h2h_home_goals_avg", "h2h_away_goals_avg", "h2h_home_xg_avg", "h2h_away_xg_avg",
    "h2h_total_over25",
    # League Standings (Home)
    "home_position", "home_points", "home_goal_difference",
    "home_pressure_top", "home_pressure_relegation",
    # League Standings (Away)
    "away_position", "away_points", "away_goal_difference",
    "away_pressure_top", "away_pressure_relegation",
    # Momentum (Home)
    "home_winning_streak", "home_unbeaten_streak", "home_losing_streak",
    "home_clean_sheet_streak", "home_scoring_streak", "home_xg_momentum",
    # Momentum (Away)
    "away_winning_streak", "away_unbeaten_streak", "away_losing_streak",
    "away_clean_sheet_streak", "away_scoring_streak", "away_xg_momentum",
    # Derived
    "position_gap", "points_gap", "form_diff", "momentum_diff"
]

ALL_FEATURES = FEATURES_BASE + FEATURES_ADVANCED


def load_data(path: Path, target_col: str, is_multiclass: bool = False):
    """Carica e prepara i dati per il training."""
    if not path.exists():
        raise FileNotFoundError(f"File non trovato: {path}")

    df = pd.read_csv(path)

    # Seleziona solo le features disponibili
    available_features = [f for f in ALL_FEATURES if f in df.columns]

    if not available_features:
        raise ValueError(f"Nessuna feature disponibile in {path}")

    # Prepara X e y
    if target_col not in df.columns:
        raise ValueError(f"Target {target_col} non trovato in {path}")

    # Converti features in numerico
    X = df[available_features].copy()
    for col in X.columns:
        X[col] = pd.to_numeric(X[col], errors='coerce')

    # Prepara target
    if is_multiclass:
        # Per 1X2: converti '1', 'X', '2' in 0, 1, 2
        y = df[target_col].astype(str).str.upper()
        mapping = {'1': 0, 'X': 1, '2': 2}
        y = y.map(mapping)
        # Rimuovi NaN
        mask = y.notna()
        X = X[mask]
        y = y[mask].astype(int)
    else:
        # Per OU: binario (0/1)
        y = pd.to_numeric(df[target_col], errors='coerce')
        mask = y.notna()
        X = X[mask]
        y = y[mask].astype(int)

    print(f"✓ Dataset caricato: {len(X)} samples, {len(available_features)} features")
    print(f"  Distribuzione target: {dict(pd.Series(y).value_counts().sort_index())}")

    return X, y, available_features


def objective_ou(trial, X, y, features):
    """Funzione obiettivo per Optuna - OU 2.5"""
    # Hyperparameters da ottimizzare
    params = {
        'objective': 'binary',
        'metric': 'binary_logloss',
        'verbosity': -1,
        'random_state': 42,
        'n_jobs': -1,

        # Parametri da ottimizzare
        'n_estimators': trial.suggest_int('n_estimators', 100, 1000, step=50),
        'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
        'num_leaves': trial.suggest_int('num_leaves', 20, 100),
        'max_depth': trial.suggest_int('max_depth', 3, 12),
        'min_child_samples': trial.suggest_int('min_child_samples', 5, 50),
        'subsample': trial.suggest_float('subsample', 0.5, 1.0),
        'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
        'reg_alpha': trial.suggest_float('reg_alpha', 1e-8, 10.0, log=True),
        'reg_lambda': trial.suggest_float('reg_lambda', 1e-8, 10.0, log=True),
    }

    # Imputer e modello
    imputer = SimpleImputer(strategy='median')
    model = LGBMClassifier(**params)

    # Cross-validation
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    # Trasforma dati
    X_imp = imputer.fit_transform(X)

    # Calcola score (log loss negativo perché Optuna minimizza)
    scores = cross_val_score(model, X_imp, y, cv=cv, scoring='neg_log_loss', n_jobs=-1)

    return -scores.mean()  # Optuna minimizza, quindi ritorno log loss positivo


def objective_1x2(trial, X, y, features):
    """Funzione obiettivo per Optuna - 1X2"""
    # Hyperparameters da ottimizzare
    params = {
        'objective': 'multiclass',
        'num_class': 3,
        'metric': 'multi_logloss',
        'verbosity': -1,
        'random_state': 42,
        'n_jobs': -1,

        # Parametri da ottimizzare
        'n_estimators': trial.suggest_int('n_estimators', 100, 1000, step=50),
        'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
        'num_leaves': trial.suggest_int('num_leaves', 20, 100),
        'max_depth': trial.suggest_int('max_depth', 3, 12),
        'min_child_samples': trial.suggest_int('min_child_samples', 5, 50),
        'subsample': trial.suggest_float('subsample', 0.5, 1.0),
        'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
        'reg_alpha': trial.suggest_float('reg_alpha', 1e-8, 10.0, log=True),
        'reg_lambda': trial.suggest_float('reg_lambda', 1e-8, 10.0, log=True),
    }

    # Imputer e modello
    imputer = SimpleImputer(strategy='median')
    model = LGBMClassifier(**params)

    # Cross-validation
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    # Trasforma dati
    X_imp = imputer.fit_transform(X)

    # Calcola score (log loss negativo)
    scores = cross_val_score(model, X_imp, y, cv=cv, scoring='neg_log_loss', n_jobs=-1)

    return -scores.mean()


def optimize_ou(trials: int = 50):
    """Ottimizza modello OU 2.5"""
    print("\n" + "="*80)
    print("OTTIMIZZAZIONE MODELLO OU 2.5")
    print("="*80)

    # Carica dati
    X, y, features = load_data(HIST_OU_PATH, target_col='target_ou25', is_multiclass=False)

    # Crea studio Optuna
    study = optuna.create_study(
        direction='minimize',
        sampler=TPESampler(seed=42),
        study_name='ou25_optimization'
    )

    # Ottimizza
    print(f"\n🔍 Avvio ottimizzazione ({trials} trials)...")
    study.optimize(lambda trial: objective_ou(trial, X, y, features), n_trials=trials, show_progress_bar=True)

    # Best params
    print("\n✅ Ottimizzazione completata!")
    print(f"📊 Best LogLoss: {study.best_value:.4f}")
    print(f"🎯 Best params:\n{json.dumps(study.best_params, indent=2)}")

    # Training finale con best params
    print("\n🏋️ Training modello finale con best params...")
    best_params = study.best_params.copy()
    best_params.update({
        'objective': 'binary',
        'metric': 'binary_logloss',
        'verbosity': -1,
        'random_state': 42,
        'n_jobs': -1,
    })

    imputer = SimpleImputer(strategy='median')
    model = LGBMClassifier(**best_params)

    X_imp = imputer.fit_transform(X)
    model.fit(X_imp, y)

    # Salva modello ottimizzato
    ou_opt_model_path = MODEL_DIR / "bet_ou25_optimized.joblib"
    ou_opt_imputer_path = MODEL_DIR / "imputer_ou25_optimized.joblib"
    ou_opt_meta_path = MODEL_DIR / "meta_ou25_optimized.json"

    joblib.dump(model, ou_opt_model_path)
    joblib.dump(imputer, ou_opt_imputer_path)

    # Metadata
    meta = {
        'features': features,
        'n_samples': len(X),
        'created_at': datetime.now().isoformat(),
        'algo': 'lgbm_optimized',
        'best_params': study.best_params,
        'cv_logloss': study.best_value,
        'n_trials': trials,
    }
    ou_opt_meta_path.write_text(json.dumps(meta, indent=2), encoding='utf-8')

    print(f"✅ Modello salvato: {ou_opt_model_path}")
    print(f"   LogLoss CV: {study.best_value:.4f}")

    return study


def optimize_1x2(trials: int = 100):
    """Ottimizza modello 1X2"""
    print("\n" + "="*80)
    print("OTTIMIZZAZIONE MODELLO 1X2")
    print("="*80)

    # Carica dati
    X, y, features = load_data(HIST_1X2_PATH, target_col='target_1x2', is_multiclass=True)

    # Crea studio Optuna
    study = optuna.create_study(
        direction='minimize',
        sampler=TPESampler(seed=42),
        study_name='1x2_optimization'
    )

    # Ottimizza
    print(f"\n🔍 Avvio ottimizzazione ({trials} trials)...")
    study.optimize(lambda trial: objective_1x2(trial, X, y, features), n_trials=trials, show_progress_bar=True)

    # Best params
    print("\n✅ Ottimizzazione completata!")
    print(f"📊 Best LogLoss: {study.best_value:.4f}")
    print(f"🎯 Best params:\n{json.dumps(study.best_params, indent=2)}")

    # Training finale con best params
    print("\n🏋️ Training modello finale con best params...")
    best_params = study.best_params.copy()
    best_params.update({
        'objective': 'multiclass',
        'num_class': 3,
        'metric': 'multi_logloss',
        'verbosity': -1,
        'random_state': 42,
        'n_jobs': -1,
    })

    imputer = SimpleImputer(strategy='median')
    model = LGBMClassifier(**best_params)

    X_imp = imputer.fit_transform(X)
    model.fit(X_imp, y)

    # Salva modello ottimizzato
    x2_opt_model_path = MODEL_DIR / "bet_1x2_optimized.joblib"
    x2_opt_imputer_path = MODEL_DIR / "imputer_1x2_optimized.joblib"
    x2_opt_meta_path = MODEL_DIR / "meta_1x2_optimized.json"

    joblib.dump(model, x2_opt_model_path)
    joblib.dump(imputer, x2_opt_imputer_path)

    # Metadata
    meta = {
        'features': features,
        'n_samples': len(X),
        'created_at': datetime.now().isoformat(),
        'algo': 'lgbm_optimized',
        'best_params': study.best_params,
        'cv_logloss': study.best_value,
        'n_trials': trials,
    }
    x2_opt_meta_path.write_text(json.dumps(meta, indent=2), encoding='utf-8')

    print(f"✅ Modello salvato: {x2_opt_model_path}")
    print(f"   LogLoss CV: {study.best_value:.4f}")

    return study


def main():
    parser = argparse.ArgumentParser(description='Ottimizza modelli ML con Optuna')
    parser.add_argument('--model', choices=['ou25', '1x2', 'both'], default='both',
                        help='Quale modello ottimizzare')
    parser.add_argument('--trials', type=int, default=50,
                        help='Numero di trials Optuna (default: 50)')

    args = parser.parse_args()

    print(f"\n🚀 OTTIMIZZAZIONE MODELLI ML CON OPTUNA")
    print(f"   Modello: {args.model}")
    print(f"   Trials: {args.trials}\n")

    if args.model in ['ou25', 'both']:
        optimize_ou(trials=args.trials)

    if args.model in ['1x2', 'both']:
        optimize_1x2(trials=args.trials)

    print("\n" + "="*80)
    print("✅ OTTIMIZZAZIONE COMPLETATA!")
    print("="*80)
    print("\nPer usare i modelli ottimizzati, aggiorna model_pipeline.py per caricare:")
    print("  - models/bet_ou25_optimized.joblib")
    print("  - models/bet_1x2_optimized.joblib\n")


if __name__ == "__main__":
    main()
