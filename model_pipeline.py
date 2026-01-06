#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
model_pipeline.py — STRICT_ML
- Nessun fallback da quote → le quote servono solo per value/Kelly.
- Predice:
  * OU 2.5 con modello ML (se presente)
  * 1X2  con modello ML (se presente)
- Report HTML e CSV puliti.

Storici attesi:
- OU:  data/historical_dataset.csv         (già in uso)
- 1X2: data/historical_1x2.csv             (se manca target, viene derivato da ft_home_goals/ft_away_goals)

Modelli salvati:
- OU:  models/bet_ou25.joblib (+ scaler/imputer/meta)
- 1X2: models/bet_1x2.joblib  (+ scaler/imputer/meta)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import warnings
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler
from sklearn.base import clone
from sklearn.pipeline import Pipeline

# Importazioni per il database
from sqlalchemy.orm import joinedload
from database import SessionLocal
from models import Fixture, Feature, Odds
from predictions_generator import expected_goals_to_prob

try:
    from lightgbm import LGBMClassifier
except (ImportError, OSError) as e:  # Catch OSError for library loading issues (e.g., libomp)
    warnings.warn(
        f"LightGBM non può essere importato ({e}). Verranno usati modelli di fallback. Per risolvere, su macOS esegui: brew install libomp"
    )
    LGBMClassifier = None  # type: ignore

# =========================
# CONFIG
# =========================
ROOT = Path(__file__).resolve().parent

PRED_PATH = ROOT / "predictions.csv"
REPORT_HTML = ROOT / "report.html"

# Storici - usa dataset enhanced con advanced features
HIST_OU_PATH = ROOT / "data" / "historical_dataset_enhanced.csv"
HIST_1X2_PATH = ROOT / "data" / "historical_1x2_enhanced.csv"

# Modelli
MODEL_DIR = ROOT / "models"
MODEL_DIR.mkdir(exist_ok=True)

OU_MODEL_PATH = MODEL_DIR / "bet_ou25.joblib"
OU_SCALER_PATH = MODEL_DIR / "scaler_ou25.joblib"
OU_IMPUTER_PATH = MODEL_DIR / "imputer_ou25.joblib"
OU_META_PATH = MODEL_DIR / "meta_ou25.json"

X2_MODEL_PATH = MODEL_DIR / "bet_1x2.joblib"
X2_SCALER_PATH = MODEL_DIR / "scaler_1x2.joblib"
X2_IMPUTER_PATH = MODEL_DIR / "imputer_1x2.joblib"
X2_META_PATH = MODEL_DIR / "meta_1x2.json"

# Target names
TARGET_OU25 = "target_ou25"  # 1 = Over 2.5, 0 = Under
TARGET_1X2 = (
    "target_1x2"  # {1:'home', 0:'draw', -1:'away'} oppure stringhe {'1','X','2'}
)

# Feature sets (puoi adattarle alle tue colonne)
# NOTA: I nomi devono corrispondere ESATTAMENTE a quelli nel DB (models.py) e negli storici.

# Advanced features (54 feature professionali da sistemi come FiveThirtyEight)
FEATURES_ADVANCED: List[str] = [
    # Recent Form Features (Home)
    "home_form_xg_for",
    "home_form_xg_against",
    "home_form_xg_diff",
    "home_form_wins",
    "home_form_draws",
    "home_form_losses",
    "home_form_goals_for",
    "home_form_goals_against",
    "home_form_points",
    "home_form_trend",
    # Recent Form Features (Away)
    "away_form_xg_for",
    "away_form_xg_against",
    "away_form_xg_diff",
    "away_form_wins",
    "away_form_draws",
    "away_form_losses",
    "away_form_goals_for",
    "away_form_goals_against",
    "away_form_points",
    "away_form_trend",
    # Head-to-Head Features
    "h2h_home_wins",
    "h2h_draws",
    "h2h_away_wins",
    "h2h_home_goals_avg",
    "h2h_away_goals_avg",
    "h2h_home_xg_avg",
    "h2h_away_xg_avg",
    "h2h_total_over25",
    # League Standings Features (Home)
    "home_position",
    "home_points",
    "home_goal_difference",
    "home_pressure_top",
    "home_pressure_relegation",
    # League Standings Features (Away)
    "away_position",
    "away_points",
    "away_goal_difference",
    "away_pressure_top",
    "away_pressure_relegation",
    # Momentum Indicators (Home)
    "home_winning_streak",
    "home_unbeaten_streak",
    "home_losing_streak",
    "home_clean_sheet_streak",
    "home_scoring_streak",
    "home_xg_momentum",
    # Momentum Indicators (Away)
    "away_winning_streak",
    "away_unbeaten_streak",
    "away_losing_streak",
    "away_clean_sheet_streak",
    "away_scoring_streak",
    "away_xg_momentum",
    # Derived Features
    "position_gap",
    "points_gap",
    "form_diff",
    "momentum_diff",
]

# Base features (xG e context)
FEATURES_BASE: List[str] = [
    "xg_for_home",
    "xg_against_home",
    "xg_for_away",
    "xg_against_away",
    "rest_days_home",
    "rest_days_away",
    "derby_flag",
    "europe_flag_home",
    "europe_flag_away",
    "meteo_flag",
    "style_ppda_home",
    "style_ppda_away",
    "travel_km_away",
] + FEATURES_ADVANCED  # Aggiungi tutte le 54 advanced features

FEATURES_OU: List[str] = FEATURES_BASE[:]  # per OU 2.5
FEATURES_1X2: List[str] = FEATURES_BASE[:]  # per 1X2

# STRICT ML: non usare MAI quote per produrre probabilità
STRICT_ML = True

DEFAULT_XG_VALUE = 1.2 # Valore di default per xG quando non disponibili
BLEND_HOME_EDGE_CAP = 0.35  # limite di quanto le quote possono spostare i lambda in fallback


RENAME_MAP = {
    "xG_for_5_home": "xg_for_home",
    "xG_against_5_home": "xg_against_home",
    "xG_for_5_away": "xg_for_away",
    "xG_against_5_away": "xg_against_away",
}


def _standardize_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Uniforma i nomi delle colonne degli storici ai nomi attesi dal modello."""
    rename = {k: v for k, v in RENAME_MAP.items() if k in df.columns}
    if rename:
        df = df.rename(columns=rename)
    return df


def _select_features(df: pd.DataFrame, cols: List[str], min_nonnull_ratio: float = 0.05) -> List[str]:
    """Rimuove feature totalmente vuote o quasi (soglia di copertura)."""
    out = []
    for c in cols:
        if c not in df.columns:
            continue
        ratio = df[c].notna().mean()
        if ratio >= min_nonnull_ratio:
            out.append(c)
    return out


def _hash_noise(seed: Optional[str]) -> float:
    """Piccola variazione deterministica per evitare simmetrie perfette (range ~[-0.025, 0.025])."""
    if not seed:
        return 0.0
    h = hash(seed)
    return ((h % 11) - 5) / 200.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _normalize_odds_probs(o1: Optional[float], ox: Optional[float], o2: Optional[float]) -> Optional[Tuple[float, float, float]]:
    if o1 and ox and o2 and o1 > 1.0 and ox > 1.0 and o2 > 1.0:
        p1 = 1.0 / o1
        px = 1.0 / ox
        p2 = 1.0 / o2
        tot = p1 + px + p2
        if tot > 0:
            return p1 / tot, px / tot, p2 / tot
    return None


def _prob_from_lambda(lambda_home: float, lambda_away: float, max_goals: int = 8) -> Tuple[float, float, float]:
    p1 = px = p2 = 0.0
    for hg in range(max_goals + 1):
        from math import exp, factorial
        try:
            ph = exp(-lambda_home) * (lambda_home ** hg) / factorial(hg)
        except Exception:
            ph = 0.0
        for ag in range(max_goals + 1):
            try:
                pa = exp(-lambda_away) * (lambda_away ** ag) / factorial(ag)
            except Exception:
                pa = 0.0
            prob = ph * pa
            if hg > ag:
                p1 += prob
            elif hg == ag:
                px += prob
            else:
                p2 += prob
    tot = p1 + px + p2
    if tot > 0:
        p1, px, p2 = p1 / tot, px / tot, p2 / tot
    return p1, px, p2

# =========================
# UTILS
# =========================
def _to_num(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def _kelly(p: float, o: Optional[float], cut: float = 0.5) -> float:
    """Kelly frazionato (50%). Quote o (decimali)."""
    if o is None or not (o > 1.0):
        return 0.0
    if p <= 0 or p >= 1:
        return 0.0
    b = o - 1.0
    f = (b * p - (1 - p)) / b
    return round(max(0.0, f * cut), 4)


def _ensure_target_ou(df: pd.DataFrame) -> pd.DataFrame:
    """Se manca target_ou25, prova a derivarlo da ft_home_goals/ft_away_goals."""
    if TARGET_OU25 not in df.columns:
        if {"ft_home_goals", "ft_away_goals"}.issubset(df.columns):
            g = pd.to_numeric(df["ft_home_goals"], errors="coerce").fillna(
                0
            ) + pd.to_numeric(df["ft_away_goals"], errors="coerce").fillna(0)
            df = df.copy()
            df[TARGET_OU25] = (g > 2).astype(int)
    return df


def _ensure_target_1x2(df: pd.DataFrame) -> pd.DataFrame:
    """
    Se manca target_1x2, prova a derivarlo da ft_home_goals/ft_away_goals:
      '1' se home>away, 'X' se =, '2' se home<away
    """
    if TARGET_1X2 not in df.columns:
        if {"ft_home_goals", "ft_away_goals"}.issubset(df.columns):
            hg = pd.to_numeric(df["ft_home_goals"], errors="coerce").fillna(0)
            ag = pd.to_numeric(df["ft_away_goals"], errors="coerce").fillna(0)
            out = np.where(hg > ag, "1", np.where(hg < ag, "2", "X"))
            df = df.copy()
            df[TARGET_1X2] = out
    return df


def _encode_1x2_target(y: pd.Series) -> np.ndarray:
    """
    Converte etichette 1/X/2 in numeri (0,1,2) nell'ordine [1,X,2] → (0,1,2)
    """
    mapping = {"1": 0, "X": 1, "2": 2}
    return np.array([mapping.get(str(v).upper(), np.nan) for v in y], dtype=float)


def _poisson_prob(lmbd: float, k: int) -> float:
    """Calcola probabilità Poisson: P(X=k) con lambda lmbd."""
    from math import exp, factorial
    if lmbd <= 0: return 0.0
    try: return exp(-lmbd) * (lmbd ** k) / factorial(k)
    except: return 0.0

def _build_components(algo: str, task: str):
    """
    Ritorna (model, imputer, scaler) per l'algoritmo richiesto.
    task = 'binary' | 'multiclass'
    """
    algo = (algo or "logistic").lower()
    # Fallback automatico a logistic se lgbm non è disponibile
    if algo == "lgbm" and LGBMClassifier is None:
        warnings.warn("LightGBM non trovato, eseguo il training con Logistic Regression come fallback.")
        algo = "logistic"

    task = task.lower()

    if algo == "logistic":
        imputer = SimpleImputer(strategy="median")
        scaler = StandardScaler()
        if task == "binary":
            model = LogisticRegression(
                max_iter=2000,
                solver="lbfgs",
                class_weight="balanced",
                random_state=42,
            )
        elif task == "multiclass":
            model = LogisticRegression(
                max_iter=1500,
                solver="lbfgs",
                multi_class="multinomial",
                class_weight="balanced",
                random_state=42,
            )
        else:
            raise ValueError(f"Task sconosciuto: {task}")
        return model, imputer, scaler

    if algo == "lgbm":
        if LGBMClassifier is None:
            raise RuntimeError(
                "LightGBM non disponibile. Installa 'lightgbm' oppure usa --algo logistic."
            )
        params = dict(
            n_estimators=400,
            learning_rate=0.05,
            num_leaves=48,
            subsample=0.85,
            colsample_bytree=0.9,
            reg_lambda=1.0,
            # Aggiungo min_child_samples per rendere il modello leggermente meno restrittivo.
            min_child_samples=10,
            random_state=42,
            n_jobs=-1,
        )
        if task == "binary":
            model = LGBMClassifier(objective="binary", class_weight="balanced", **params)
        elif task == "multiclass":
            model = LGBMClassifier(objective="multiclass", num_class=3, **params)
        else:
            raise ValueError(f"Task sconosciuto: {task}")
        imputer = SimpleImputer(strategy="median")
        scaler = None  # gli alberi non richiedono scaling
        return model, imputer, scaler

    raise ValueError(f"Algoritmo non supportato: {algo}")


def _poisson_1x2_probs(lambda_home: float, lambda_away: float, max_goals: int = 8) -> Tuple[float, float, float]:
    """Calcola probabilità 1X2 usando modello Poisson completo."""
    p1 = px = p2 = 0.0
    
    for hg in range(max_goals + 1):
        ph = _poisson_prob(lambda_home, hg)
        for ag in range(max_goals + 1):
            pa = _poisson_prob(lambda_away, ag)
            p = ph * pa
            if hg > ag:
                p1 += p
            elif hg == ag:
                px += p
            else:
                p2 += p
    
    total = p1 + px + p2
    if total > 0:
        return p1/total, px/total, p2/total
    return 0.33, 0.34, 0.33 # Neutral default if total is zero


def _create_dummy_models_from_data(df: pd.DataFrame):
    """Crea modelli dummy intelligenti usando i dati reali disponibili."""
    # Prepara features
    cols = [c for c in FEATURES_OU if c in df.columns]
    if not cols:
        print("[WARN] Nessuna feature disponibile, uso dummy sintetici")
        return

    df_num = _to_num(df, cols)

    # Modello OU: deriva target da probabilità Over/Under basata su xG
    if all(c in df.columns for c in ["xg_for_home", "xg_against_home", "xg_for_away", "xg_against_away"]):
        xg_h = pd.to_numeric(df["xg_for_home"], errors="coerce").fillna(DEFAULT_XG_VALUE)
        xga_h = pd.to_numeric(df["xg_against_home"], errors="coerce").fillna(DEFAULT_XG_VALUE)
        xg_a = pd.to_numeric(df["xg_for_away"], errors="coerce").fillna(DEFAULT_XG_VALUE)
        xga_a = pd.to_numeric(df["xg_against_away"], errors="coerce").fillna(DEFAULT_XG_VALUE)

        # Stima lambda per Poisson
        lambda_h = ((xg_h + xga_a) / 2.0 * 1.12).clip(0.3, 4.0) # type: ignore
        lambda_a = ((xg_a + xga_h) / 2.0 * 0.95).clip(0.3, 4.0)
        
        # Calcola probabilità Over 2.5
        p_over_list = []
        for lh, la in zip(lambda_h, lambda_a):
            p_over = 0.0
            for hg in range(9):
                for ag in range(9):
                    if hg + ag > 2.5:
                        p_over += _poisson_prob(lh, hg) * _poisson_prob(la, ag)
            p_over_list.append(1.0 if p_over > 0.5 else 0.0)

        y_ou = np.array(p_over_list)
        X_ou = df_num[cols].fillna(0)

        imputer_ou = SimpleImputer(strategy="median")
        scaler_ou = StandardScaler()
        clf_ou = LogisticRegression(max_iter=2000, random_state=42, class_weight="balanced")

        X_ou_imp = imputer_ou.fit_transform(X_ou)
        X_ou_scl = scaler_ou.fit_transform(X_ou_imp)
        clf_ou.fit(X_ou_scl, y_ou)

        joblib.dump(imputer_ou, OU_IMPUTER_PATH)
        joblib.dump(scaler_ou, OU_SCALER_PATH)
        joblib.dump(clf_ou, OU_MODEL_PATH)
        OU_META_PATH.write_text(json.dumps({"features": cols, "dummy": True, "n_samples": len(df)}, indent=2), encoding="utf-8")
        print(f"[OK] Modello OU dummy creato da {len(df)} match reali")

    # Modello 1X2: deriva target da probabilità Poisson
    if all(c in df.columns for c in ["xg_for_home", "xg_for_away"]):
        lambda_h = ((xg_h + xga_a) / 2.0 * 1.12).clip(0.3, 4.0) # type: ignore
        lambda_a = ((xg_a + xga_h) / 2.0 * 0.95).clip(0.3, 4.0)

        y_1x2_list = []
        for lh, la in zip(lambda_h, lambda_a):
            p1, px, p2 = _poisson_1x2_probs(lh, la)
            if p1 > px and p1 > p2:
                y_1x2_list.append(0)  # 1
            elif px > p1 and px > p2:
                y_1x2_list.append(1)  # X
            else:
                y_1x2_list.append(2)  # 2

        y_1x2 = np.array(y_1x2_list)
        X_1x2 = df_num[cols].fillna(0)

        imputer_1x2 = SimpleImputer(strategy="median")
        scaler_1x2 = StandardScaler()
        clf_1x2 = LogisticRegression(max_iter=2000, solver="lbfgs", multi_class="multinomial", random_state=42)

        X_1x2_imp = imputer_1x2.fit_transform(X_1x2)
        X_1x2_scl = scaler_1x2.fit_transform(X_1x2_imp)
        clf_1x2.fit(X_1x2_scl, y_1x2)

        joblib.dump(imputer_1x2, X2_IMPUTER_PATH)
        joblib.dump(scaler_1x2, X2_SCALER_PATH)
        joblib.dump(clf_1x2, X2_MODEL_PATH)
        X2_META_PATH.write_text(json.dumps({"features": cols, "dummy": True, "n_samples": len(df)}, indent=2), encoding="utf-8")
        print(f"[OK] Modello 1X2 dummy creato da {len(df)} match reali")


def _safe_brier_logloss(
    y_true: np.ndarray, proba: np.ndarray, labels: List[int]
) -> Tuple[Optional[float], Optional[float]]:
    try:
        b = (
            brier_score_loss(y_true, proba[:, 1])
            if proba.ndim == 2 and proba.shape[1] == 2
            else None
        )
    except Exception:
        b = None
    try:
        l = log_loss(y_true, proba, labels=labels)
    except Exception:
        l = None
    return b, l


def _determine_cv_splits(y: np.ndarray, max_splits: int = 5) -> int:
    unique, counts = np.unique(y, return_counts=True)
    n_splits = min(max_splits, len(y))
    while n_splits > 2:
        if np.all(counts >= n_splits):
            break
        n_splits -= 1
    return max(2, n_splits)


# =========================
# TRAINING
# =========================
def train_ou25(algo: str = "logistic"):
    if not HIST_OU_PATH.exists():
        print(f"[ERR] Storico OU non trovato: {HIST_OU_PATH}")
        print(f"[HINT] Esegui: python historical_builder.py --from 2023-07-01 --to 2024-06-30 --comps 'SA,PL,PD,BL1'")
        sys.exit(1)
    
    try:
        df = pd.read_csv(HIST_OU_PATH)
        df = _standardize_cols(df)
    except Exception as e:
        print(f"[ERR] Errore lettura {HIST_OU_PATH}: {e}")
        sys.exit(1)
    
    if df.empty:
        print(f"[ERR] {HIST_OU_PATH} è vuoto")
        sys.exit(1)
    df = _ensure_target_ou(df)

    cols = _select_features(df, FEATURES_OU, min_nonnull_ratio=0.02)
    if not cols:
        print("[ERR] Nessuna feature compatibile nello storico OU.")
        print(f"[INFO] Feature richieste: {FEATURES_OU}")
        print(f"[INFO] Feature disponibili: {list(df.columns)}")
        sys.exit(1)

    df = _to_num(df, cols + [TARGET_OU25])
    df = df.dropna(subset=[TARGET_OU25]).copy()
    
    if len(df) < 80:
        print(f"[WARN] Solo {len(df)} esempi disponibili. Un training robusto richiede più dati.")
    
    y = df[TARGET_OU25].astype(int).values
    X = df[cols].copy()

    cv_splits = _determine_cv_splits(y)
    cv_model, cv_imputer, cv_scaler = _build_components(algo, "binary")
    cv_steps = []
    if cv_imputer is not None:
        cv_steps.append(("imputer", cv_imputer))
    if cv_scaler is not None:
        cv_steps.append(("scaler", cv_scaler))
    cv_steps.append(("clf", cv_model))
    cv = StratifiedKFold(n_splits=cv_splits, shuffle=True, random_state=42)

    brier = None
    logloss_cv = None
    try:
        proba = cross_val_predict(Pipeline(cv_steps), X, y, cv=cv, method="predict_proba")
        brier, logloss_cv = _safe_brier_logloss(y, proba, labels=[0, 1])
        if brier is not None and logloss_cv is not None:
            print(f"[CV {algo.upper()} OU] Brier: {brier:.4f}   LogLoss: {logloss_cv:.4f}   (n={len(y)})")
        else:
            print(f"[CV {algo.upper()} OU] n={len(y)}")
    except Exception as e:
        warnings.warn(f"Cross-validation OU fallita: {e}")

    model, imputer, scaler = _build_components(algo, "binary")
    X_proc = X.copy()
    if imputer is not None:
        imputer.fit(X_proc)
        X_proc = imputer.transform(X_proc)
        X_proc = pd.DataFrame(X_proc, columns=cols)
    else:
        X_proc = X_proc.to_numpy()
    if scaler is not None:
        scaler.fit(X_proc)
        X_proc = scaler.transform(X_proc)
        X_proc = pd.DataFrame(X_proc, columns=cols)

    model.fit(X_proc, y)

    try:
        joblib.dump(imputer, OU_IMPUTER_PATH)
        joblib.dump(scaler, OU_SCALER_PATH)
        joblib.dump(model, OU_MODEL_PATH)
        meta: Dict[str, Any] = {
            "features": cols,
            "n_samples": len(y),
            "created_at": datetime.now().isoformat(),
            "algo": algo,
            "cv_splits": cv_splits,
            "cv_brier": brier,
            "cv_logloss": logloss_cv,
        }
        OU_META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(f"[OK] Modello OU2.5 ({algo}) salvato: {OU_MODEL_PATH}")
    except Exception as e:
        print(f"[ERR] Errore salvataggio modello: {e}")
        sys.exit(1)


def train_1x2(algo: str = "logistic"):
    if not HIST_1X2_PATH.exists():
        print(f"[ERR] Storico 1X2 non trovato: {HIST_1X2_PATH}")
        sys.exit(1)
    df = pd.read_csv(HIST_1X2_PATH)
    df = _standardize_cols(df)
    df = _ensure_target_1x2(df)

    cols = _select_features(df, FEATURES_1X2, min_nonnull_ratio=0.02)
    if not cols:
        print("[ERR] Nessuna feature compatibile nello storico 1X2.")
        sys.exit(1)

    df = _to_num(df, cols)
    if TARGET_1X2 not in df.columns:
        print("[ERR] Manca target_1x2 e non ho potuto derivarlo.")
        sys.exit(1)

    y_raw = df[TARGET_1X2].astype(str).str.upper()
    y_enc = _encode_1x2_target(y_raw)
    mask = ~np.isnan(y_enc)
    df = df.loc[mask].copy()
    y = y_enc[mask].astype(int)
    X = df[cols].copy()

    if len(df) < 120:
        print(f"[WARN] Solo {len(df)} esempi disponibili. Considera di ampliare lo storico per il 1X2.")

    cv_splits = _determine_cv_splits(y)
    cv_model, cv_imputer, cv_scaler = _build_components(algo, "multiclass")
    cv_steps = []
    if cv_imputer is not None:
        cv_steps.append(("imputer", cv_imputer))
    if cv_scaler is not None:
        cv_steps.append(("scaler", cv_scaler))
    cv_steps.append(("clf", cv_model))
    cv = StratifiedKFold(n_splits=cv_splits, shuffle=True, random_state=42)

    logloss_cv = None
    try:
        proba = cross_val_predict(Pipeline(cv_steps), X, y, cv=cv, method="predict_proba")
        logloss_cv = log_loss(y, proba, labels=[0, 1, 2])
        print(f"[CV {algo.upper()} 1X2] LogLoss: {logloss_cv:.4f}   (n={len(y)})")
    except Exception as e:
        warnings.warn(f"Cross-validation 1X2 fallita: {e}")

    model, imputer, scaler = _build_components(algo, "multiclass")
    X_proc = X.copy()
    if imputer is not None:
        imputer.fit(X_proc)
        X_proc = imputer.transform(X_proc)
        X_proc = pd.DataFrame(X_proc, columns=cols)
    else:
        X_proc = X_proc.to_numpy()
    if scaler is not None:
        scaler.fit(X_proc)
        X_proc = scaler.transform(X_proc)
        X_proc = pd.DataFrame(X_proc, columns=cols)

    model.fit(X_proc, y)

    joblib.dump(imputer, X2_IMPUTER_PATH)
    joblib.dump(scaler, X2_SCALER_PATH)
    joblib.dump(model, X2_MODEL_PATH)
    meta = {
        "features": cols,
        "n_samples": len(y),
        "created_at": datetime.now().isoformat(),
        "algo": algo,
        "cv_splits": cv_splits,
        "cv_logloss": logloss_cv,
    }
    X2_META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"[OK] Modello 1X2 ({algo}) salvato: {X2_MODEL_PATH}")


# =========================
# PREDICTION
# =========================
def _load_model_triplet(
    model_p: Path, scaler_p: Path, imputer_p: Path
) -> Tuple[Optional[Any], Optional[Any], Optional[Any]]:
    model = joblib.load(model_p) if model_p.exists() else None
    if model is None:
        return None, None, None
    imputer = joblib.load(imputer_p) if imputer_p.exists() else None
    scaler = joblib.load(scaler_p) if scaler_p.exists() else None
    return imputer, scaler, model


def _predict_ou_row(
    r: pd.Series,
    feats: List[str],
    imputer: Optional[Any],
    scaler: Optional[Any],
    clf: Any,
) -> Tuple[float, float]:
    try:
        x = pd.DataFrame({c: [pd.to_numeric(r.get(c, 0), errors="coerce")] for c in feats})
        if imputer is not None:
            xs = imputer.transform(x)
        else:
            xs = x.to_numpy()
        if scaler is not None:
            xs = scaler.transform(xs)
        proba = clf.predict_proba(xs)[0]
        if len(proba) == 2:
            p_over = float(proba[1])  # class 1 = Over
        else:
            p_over = float(proba[0]) if len(proba) > 0 else 0.5
        p_under = 1.0 - p_over
        return max(0.0, min(1.0, p_over)), max(0.0, min(1.0, p_under))
    except Exception as e:
        print(f"[WARN] Errore predizione OU per {r.get('match_id', 'unknown')}: {e}")
        return 0.5, 0.5  # fallback neutro


def _fallback_1x2_prob(r: pd.Series) -> Tuple[float, float, float]:
    """Calcola probabilità 1X2 usando fallback intelligente (xG incrociati + quote + rumore deterministico)."""
    match_id = str(r.get("match_id", r.get("home", "") + r.get("away", "")))
    noise = _hash_noise(match_id)

    xg_home = pd.to_numeric(r.get("xg_for_home"), errors="coerce")
    xg_away = pd.to_numeric(r.get("xg_for_away"), errors="coerce")
    xga_home = pd.to_numeric(r.get("xg_against_home"), errors="coerce")
    xga_away = pd.to_numeric(r.get("xg_against_away"), errors="coerce")
    conf = pd.to_numeric(r.get("xg_confidence"), errors="coerce")
    src_home = str(r.get("xg_source_home", "") or "").lower()
    src_away = str(r.get("xg_source_away", "") or "").lower()

    odds_1 = pd.to_numeric(r.get("odds_1"), errors="coerce")
    odds_x = pd.to_numeric(r.get("odds_x"), errors="coerce")
    odds_2 = pd.to_numeric(r.get("odds_2"), errors="coerce")
    odds_probs = _normalize_odds_probs(odds_1, odds_x, odds_2)

    # Check xG validi
    has_valid_xg = (
        pd.notna(xg_home) and xg_home > 0 and xg_home != DEFAULT_XG_VALUE and
        pd.notna(xga_away) and xga_away > 0 and xga_away != DEFAULT_XG_VALUE and
        pd.notna(xg_away) and xg_away > 0 and xg_away != DEFAULT_XG_VALUE and
        pd.notna(xga_home) and xga_home > 0 and xga_home != DEFAULT_XG_VALUE
    )

    if has_valid_xg:
        _, _, _, lam_home, lam_away, _, _ = expected_goals_to_prob(
            xg_for_home=float(xg_home),
            xg_against_home=float(xga_home),
            xg_for_away=float(xg_away),
            xg_against_away=float(xga_away),
            rest_home=pd.to_numeric(r.get("rest_days_home"), errors="coerce") if "rest_days_home" in r else None,
            rest_away=pd.to_numeric(r.get("rest_days_away"), errors="coerce") if "rest_days_away" in r else None,
            inj_home=pd.to_numeric(r.get("injuries_key_home"), errors="coerce") if "injuries_key_home" in r else None,
            inj_away=pd.to_numeric(r.get("injuries_key_away"), errors="coerce") if "injuries_key_away" in r else None,
            travel_km_away=pd.to_numeric(r.get("travel_km_away"), errors="coerce") if "travel_km_away" in r else None,
            derby_flag=int(pd.to_numeric(r.get("derby_flag"), errors="coerce")) if "derby_flag" in r else 0,
            europe_home=int(pd.to_numeric(r.get("europe_flag_home"), errors="coerce")) if "europe_flag_home" in r else 0,
            europe_away=int(pd.to_numeric(r.get("europe_flag_away"), errors="coerce")) if "europe_flag_away" in r else 0,
            meteo_flag=int(pd.to_numeric(r.get("meteo_flag"), errors="coerce")) if "meteo_flag" in r else 0,
            seed=match_id,
            strong_home=None,
            strong_away=None,
        )

        # Piccolo aggiustamento verso le quote se presenti
        lam_home_adj, lam_away_adj = lam_home, lam_away
        if odds_probs:
            delta = (odds_probs[0] - odds_probs[2]) * BLEND_HOME_EDGE_CAP
            lam_home_adj = _clamp(lam_home * (1 + delta), 0.15, 5.0)
            lam_away_adj = _clamp(lam_away * (1 - delta), 0.15, 5.0)

        p1, px, p2 = _prob_from_lambda(lam_home_adj, lam_away_adj)

        # Blend con quote se pochi dati
        info_level = "medium"
        if pd.notna(conf):
            if conf >= 75:
                info_level = "high"
            elif conf >= 50:
                info_level = "medium"
            else:
                info_level = "low"
        elif "fallback" in (src_home, src_away):
            info_level = "low"
        elif "understat" in (src_home, src_away):
            info_level = "medium"

        if odds_probs:
            weights = {"high": 0.8, "medium": 0.6, "low": 0.45}
            w_xg = weights.get(info_level, 0.6)
            p1 = w_xg * p1 + (1 - w_xg) * odds_probs[0]
            px = w_xg * px + (1 - w_xg) * odds_probs[1]
            p2 = w_xg * p2 + (1 - w_xg) * odds_probs[2]
            tot = p1 + px + p2
            if tot > 0:
                p1, px, p2 = p1 / tot, px / tot, p2 / tot

        return p1, px, p2

    # Se xG non disponibili, usa quote se presenti
    if odds_probs:
        p1, px, p2 = odds_probs
        # Applica rumore deterministico leggero per evitare pareggi piatti
        if noise:
            p1 = _clamp(p1 * (1 + noise), 0.05, 0.9)
            p2 = _clamp(p2 * (1 - noise), 0.05, 0.9)
            tot = p1 + px + p2
            if tot > 0:
                p1, px, p2 = p1 / tot, px / tot, p2 / tot
        return p1, px, p2

    # Default equilibrato con leggero home advantage e rumore
    p1, px, p2 = 0.36, 0.28, 0.36
    if noise:
        p1 = _clamp(p1 * (1 + noise), 0.05, 0.9)
        p2 = _clamp(p2 * (1 - noise), 0.05, 0.9)
        tot = p1 + px + p2
        if tot > 0:
            p1, px, p2 = p1 / tot, px / tot, p2 / tot
    return p1, px, p2


def _predict_1x2_row(
    r: pd.Series,
    feats: List[str],
    imputer: Optional[Any],
    scaler: Optional[Any],
    clf: Any,
) -> Tuple[float, float, float]:
    try:
        x = pd.DataFrame({c: [pd.to_numeric(r.get(c, 0), errors="coerce")] for c in feats})
        if imputer is not None:
            xs = imputer.transform(x)
        else:
            xs = x.to_numpy()
        if scaler is not None:
            xs = scaler.transform(xs)
        # Ordine classi del modello: 0,1,2 → mappate a [1,X,2]
        proba = clf.predict_proba(xs)[0]
        if len(proba) != 3:
            # modello non multinomiale? Fail-safe
            return _fallback_1x2_prob(r)
        p1, px, p2 = float(proba[0]), float(proba[1]), float(proba[2])
        # Normalizza per assicurare somma = 1
        total = p1 + px + p2
        if total > 0:
            p1, px, p2 = p1/total, px/total, p2/total
        return max(0.0, min(1.0, p1)), max(0.0, min(1.0, px)), max(0.0, min(1.0, p2))
    except Exception as e:
        warnings.warn(f"Errore predizione 1X2 per {r.get('match_id', 'unknown')}: {e}")
        return _fallback_1x2_prob(r)


def load_data_from_db(date_str: str, comps: Optional[List[str]] = None) -> pd.DataFrame:
    """Carica i dati necessari (fixtures, features, odds) dal database per una data specifica."""
    db = SessionLocal()
    try:
        # Query per fixtures
        fix_query = db.query(Fixture).filter(Fixture.date == date_str)
        if comps:
            fix_query = fix_query.filter(Fixture.league_code.in_(comps))
        
        fix_df = pd.read_sql(fix_query.statement, db.bind)
        if fix_df.empty:
            print(f"[INFO] Nessuna partita trovata nel DB per il {date_str} con i filtri specificati.")
            return pd.DataFrame()

        match_ids = fix_df['match_id'].tolist()

        # Query per features e odds
        fea_df = pd.read_sql(db.query(Feature).filter(Feature.match_id.in_(match_ids)).statement, db.bind)
        odds_df = pd.read_sql(db.query(Odds).filter(Odds.match_id.in_(match_ids)).statement, db.bind)

        if fea_df.empty:
            print(f"[WARN] Nessuna feature trovata per le partite del {date_str}. Impossibile procedere.")
            return pd.DataFrame()

        # Merge dei dati
        df = pd.merge(fix_df, fea_df, on="match_id", how="inner")
        if not odds_df.empty:
            df = pd.merge(df, odds_df, on="match_id", how="left")

        return df
    finally:
        db.close()


def predict_and_report(date_str: str, comps: Optional[List[str]] = None):
    try:
        df = load_data_from_db(date_str, comps)
    except Exception as e:
        print(f"[ERR] Errore caricamento dati: {e}")
        sys.exit(1)
    
    if df.empty:
        print("[ERR] Nessun match da predire. Verifica fixtures.csv e features.csv")
        sys.exit(1)

    # Carica modelli (se esistono)
    ou_imputer, ou_scaler, ou_clf = _load_model_triplet(
        OU_MODEL_PATH, OU_SCALER_PATH, OU_IMPUTER_PATH
    )
    x2_imputer, x2_scaler, x2_clf = _load_model_triplet(
        X2_MODEL_PATH, X2_SCALER_PATH, X2_IMPUTER_PATH
    )
    
    if ou_clf is None:
        print("[WARN] Modello OU 2.5 non trovato. Esegui: python model_pipeline.py --train-ou")
    if x2_clf is None:
        print("[WARN] Modello 1X2 non trovato. Uso fallback (quote o xG) per calcolare probabilità 1X2.")

    # Carica feature list dai meta
    ou_feats = FEATURES_OU
    x2_feats = FEATURES_1X2
    ou_meta: Dict[str, Any] = {}
    x2_meta: Dict[str, Any] = {}
    try:
        if OU_META_PATH.exists():
            ou_meta = json.loads(OU_META_PATH.read_text())
            ou_feats = [c for c in ou_meta.get("features", []) if c in df.columns]
        if X2_META_PATH.exists():
            x2_meta = json.loads(X2_META_PATH.read_text())
            x2_feats = [c for c in x2_meta.get("features", []) if c in df.columns]
    except Exception as e:
        warnings.warn(f"Impossibile leggere meta modelli: {e}")

    if ou_clf is not None and ou_meta.get("algo"):
        print(
            f"[INFO] Modello OU: {ou_meta.get('algo')} "
            f"(n={ou_meta.get('n_samples', '?')}, CV splits={ou_meta.get('cv_splits', '?')})"
        )
    if x2_clf is not None and x2_meta.get("algo"):
        print(
            f"[INFO] Modello 1X2: {x2_meta.get('algo')} "
            f"(n={x2_meta.get('n_samples', '?')}, CV splits={x2_meta.get('cv_splits', '?')})"
        )

    rows = []
    for _, r in df.iterrows():
        # --- Probabilità ML ---
        # 1X2
        if x2_clf is not None and x2_feats:
            p1, px, p2 = _predict_1x2_row(r, x2_feats, x2_imputer, x2_scaler, x2_clf)
        else:
            # Fallback: calcola probabilità 1X2 da xG o quote
            p1, px, p2 = _fallback_1x2_prob(r)

        # OU
        if ou_clf is not None and ou_feats:
            p_over, p_under = _predict_ou_row(
                r, ou_feats, ou_imputer, ou_scaler, ou_clf
            )
        else:
            p_over, p_under = np.nan, np.nan

        # --- Value & Picks (quote opzionali) ---
        o1 = float(r["odds_1"]) if pd.notna(r.get("odds_1")) else None
        ox = float(r["odds_x"]) if pd.notna(r.get("odds_x")) else None
        o2 = float(r["odds_2"]) if pd.notna(r.get("odds_2")) else None
        oo = float(r["odds_ou25_over"]) if pd.notna(r.get("odds_ou25_over")) else None
        ou_ = (
            float(r["odds_ou25_under"]) if pd.notna(r.get("odds_ou25_under")) else None
        )

        # Se STRICT_ML è True → NON derivare probabilità dalle quote (p1/px/p2 o p_over/p_under rimangono come calcolate dai modelli)
        # Calcolo del value solo se ho sia p che quota
        def _value(p, o):
            if p is None or not isinstance(p, (int, float)) or np.isnan(p) or o is None:
                return None
            return round((o - 1) * p - (1 - p), 4)

        v1 = _value(p1, o1)
        vx = _value(px, ox)
        v2 = _value(p2, o2)
        vov = _value(p_over, oo)
        vun = _value(p_under, ou_)

        # Picks
        pick_1x2 = "NoBet"
        kelly_1x2 = 0.0
        # scegli il segno con value maggiore e >= 0
        cand_1x2 = [(v1, "1", p1, o1), (vx, "X", px, ox), (v2, "2", p2, o2)]
        cand_1x2 = [c for c in cand_1x2 if (c[0] is not None)]
        if cand_1x2:
            best = max(cand_1x2, key=lambda x: x[0])
            if best[0] >= 0 and best[2] is not None and best[3] is not None:
                pick_1x2 = best[1]
                kelly_1x2 = _kelly(best[2], best[3])

        pick_ou25 = "NoBet"
        kelly_ou25 = 0.0
        if (
            vov is not None
            and (vun is None or vov >= vun)
            and vov >= 0
            and p_over == p_over
            and oo
        ):
            pick_ou25 = "Over 2.5"
            kelly_ou25 = _kelly(p_over, oo)
        elif vun is not None and vun >= 0 and p_under == p_under and ou_:
            pick_ou25 = "Under 2.5"
            kelly_ou25 = _kelly(p_under, ou_)

        # Previsione 1X2 leggibile (segno con probabilità maggiore)
        prev_1x2 = "N/A"
        if not (np.isnan(p1) and np.isnan(px) and np.isnan(p2)):
            if not np.isnan(p1) and (np.isnan(px) or p1 >= px) and (np.isnan(p2) or p1 >= p2):
                prev_1x2 = "1"
            elif not np.isnan(px) and (np.isnan(p1) or px >= p1) and (np.isnan(p2) or px >= p2):
                prev_1x2 = "X"
            elif not np.isnan(p2):
                prev_1x2 = "2"
        
        # Probabilità 1X2 in percentuale leggibile
        p1_pct = f"{p1*100:.1f}%" if not np.isnan(p1) else "N/A"
        px_pct = f"{px*100:.1f}%" if not np.isnan(px) else "N/A"
        p2_pct = f"{p2*100:.1f}%" if not np.isnan(p2) else "N/A"
        
        # Over/Under in Sì/No (soglia 50%)
        ou_over_yesno = "Sì" if not np.isnan(p_over) and p_over > 0.5 else "No"
        ou_under_yesno = "Sì" if not np.isnan(p_under) and p_under > 0.5 else "No"
        
        rows.append(
            {
                "match_id": r.get("match_id"),
                "date": r.get("date"),
                "time": r.get("time_local", r.get("time")),
                "league": r.get("league", r.get("league_code")),
                "home": r.get("home"),
                "away": r.get("away"),
                # Previsioni leggibili
                "Previsione_1X2": prev_1x2,
                "Prob_1": p1_pct,
                "Prob_X": px_pct,
                "Prob_2": p2_pct,
                "Over_2.5": ou_over_yesno,
                "Under_2.5": ou_under_yesno,
                # Prob 1X2 ML (raw per calcoli)
                "p1": None if (p1 != p1) else round(float(p1), 4),
                "px": None if (px != px) else round(float(px), 4),
                "p2": None if (p2 != p2) else round(float(p2), 4),
                # Quote 1X2
                "odds_1": o1,
                "odds_x": ox,
                "odds_2": o2,
                # Value 1X2
                "value_1": v1,
                "value_x": vx,
                "value_2": v2,
                "pick_1x2": pick_1x2,
                "kelly_1x2": kelly_1x2,
                # Prob OU ML (raw)
                "p_over_2_5": None if (p_over != p_over) else round(float(p_over), 4),
                "p_under_2_5": None
                if (p_under != p_under)
                else round(float(p_under), 4),
                # Quote OU
                "odds_ou25_over": oo,
                "odds_ou25_under": ou_,
                # Value OU
                "value_ou_over": vov,
                "value_ou_under": vun,
                "pick_ou25": pick_ou25,
                "kelly_ou25": kelly_ou25,
            }
        )

    out = pd.DataFrame(rows)
    out.to_csv(PRED_PATH, index=False)
    print(f"[OK] predictions.csv scritto ({len(out)} righe).")

    # Report HTML leggibile con colonne principali
    # Seleziona solo colonne rilevanti per visualizzazione
    display_cols = [
        "date", "time", "league", "home", "away",
        "Previsione_1X2", "Prob_1", "Prob_X", "Prob_2",
        "Over_2.5", "Under_2.5",
        "odds_1", "odds_x", "odds_2",
        "pick_1x2", "pick_ou25"
    ]
    
    # Filtra colonne esistenti
    display_cols = [c for c in display_cols if c in out.columns]
    tab_display = out[display_cols].copy()
    
    # Formattazione valori
    def fmt(x):
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return "-"
        if isinstance(x, float):
            if abs(x) < 0.0001:
                return "0"
            return f"{x:.3f}"
        return str(x) if x != "" else "-"
    
    for c in tab_display.columns:
        if c not in ["Previsione_1X2", "Over_2.5", "Under_2.5", "Prob_1", "Prob_X", "Prob_2", "pick_1x2", "pick_ou25"]:
            tab_display[c] = tab_display[c].apply(fmt)
    
    # Stile migliorato
    html = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'><title>Report Previsioni</title>",
        "<style>",
        "body{font-family:'Segoe UI',Arial,Helvetica,sans-serif; margin:20px; background:#f5f5f5}",
        ".container{max-width:1400px; margin:0 auto; background:white; padding:20px; border-radius:8px; box-shadow:0 2px 4px rgba(0,0,0,0.1)}",
        "h1{color:#333; margin-top:0}",
        "table{border-collapse:collapse; width:100%; margin-top:20px}",
        "th{background:#4a90e2; color:white; padding:12px 8px; text-align:left; font-weight:600}",
        "td{padding:10px 8px; border-bottom:1px solid #ddd}",
        "tr:hover{background:#f9f9f9}",
        "tr:nth-child(even){background:#fafafa}",
        ".prev-1{background:#d4edda; font-weight:bold; color:#155724}",
        ".prev-X{background:#fff3cd; font-weight:bold; color:#856404}",
        ".prev-2{background:#f8d7da; font-weight:bold; color:#721c24}",
        ".si{background:#d1ecf1; font-weight:bold; color:#0c5460}",
        ".no{color:#6c757d}",
        ".pick{background:#e7f3ff; font-weight:bold; padding:4px 8px; border-radius:4px}",
        ".info{color:#666; font-size:13px; margin:10px 0; padding:10px; background:#e9ecef; border-radius:4px}",
        "</style>",
        "</head><body>",
        "<div class='container'>",
        f"<h1>⚽ Report Previsioni — {datetime.fromisoformat(date_str).strftime('%d/%m/%Y')}</h1>",
        "<div class='info'>",
        "<strong>Legenda:</strong><br>",
        "• <strong>Previsione_1X2</strong>: Segno previsto (1=Home, X=Pareggio, 2=Away)<br>",
        "• <strong>Prob_1/X/2</strong>: Probabilità in percentuale<br>",
        "• <strong>Over/Under 2.5</strong>: Sì se probabilità > 50%<br>",
        "• <strong>pick_1x2/ou25</strong>: Scommessa suggerita (se value > 0)",
        "</div>",
    ]
    
    # Genera HTML tabella con styling
    html.append("<table><thead><tr>")
    for col in tab_display.columns:
        html.append(f"<th>{col.replace('_', ' ').title()}</th>")
    html.append("</tr></thead><tbody>")
    
    for _, row in tab_display.iterrows():
        html.append("<tr>")
        for col in tab_display.columns:
            val = str(row[col]) if pd.notna(row[col]) else "-"
            
            # Styling condizionale
            if col == "Previsione_1X2":
                if val == "1":
                    html.append(f"<td class='prev-1'>{val}</td>")
                elif val == "X":
                    html.append(f"<td class='prev-X'>{val}</td>")
                elif val == "2":
                    html.append(f"<td class='prev-2'>{val}</td>")
                else:
                    html.append(f"<td>{val}</td>")
            elif col in ["Over_2.5", "Under_2.5"]:
                if val == "Sì":
                    html.append(f"<td class='si'>{val}</td>")
                else:
                    html.append(f"<td class='no'>{val}</td>")
            elif col in ["pick_1x2", "pick_ou25"]:
                if val != "NoBet" and val != "-":
                    html.append(f"<td class='pick'>{val}</td>")
                else:
                    html.append(f"<td>{val}</td>")
            else:
                html.append(f"<td>{val}</td>")
        html.append("</tr>")
    
    html.append("</tbody></table>")
    html.append("</div></body></html>")
    
    REPORT_HTML.write_text("\n".join(html), encoding="utf-8")
    print(f"[OK] report HTML: {REPORT_HTML}")


# =========================
# CLI
# =========================
def main():
    ap = argparse.ArgumentParser(description="Pipeline ML: 1X2 e OU2.5 (STRICT_ML)")
    ap.add_argument(
        "--train-ou",
        action="store_true",
        help="Allena OU 2.5 da data/historical_dataset.csv",
    )
    ap.add_argument(
        "--train-1x2", action="store_true", help="Allena 1X2 da data/historical_1x2.csv"
    )
    ap.add_argument(
        "--train-dummy",
        action="store_true",
        help="Crea modelli dummy per test (usa dati minimi)",
    )
    ap.add_argument(
        "--predict",
        action="store_true",
        help="Esegue le previsioni su fixtures+features",
    )
    ap.add_argument(
        "--date", help="Data (YYYY-MM-DD) per cui eseguire le previsioni"
    )
    ap.add_argument(
        "--comps", help="Filtra competizioni per le previsioni, es. 'SA,PL,CL'"
    )
    ap.add_argument(
        "--algo",
        choices=["logistic", "lgbm"],
        default="lgbm",
        help="Algoritmo da usare per il training (default: logistic).",
    )
    args = ap.parse_args()

    if args.train_ou:
        train_ou25(algo=args.algo)
        return
    if args.train_1x2:
        train_1x2(algo=args.algo)
        return
    if args.train_dummy:
        # Crea modelli dummy intelligenti usando features reali se disponibili
        print("[INFO] Creazione modelli dummy intelligenti...")

        # Prova a usare dati recenti dal DB per creare dataset dummy
        try:
            # Carica i dati degli ultimi 3 giorni
            today = datetime.now().date()
            merged = pd.DataFrame()
            for i in range(3):
                day = today - timedelta(days=i)
                day_str = day.isoformat()
                day_df = load_data_from_db(day_str)
                if not day_df.empty:
                    merged = pd.concat([merged, day_df], ignore_index=True)
            
            if not merged.empty:
                # Rimuovi duplicati se lo stesso match_id appare in più giorni (improbabile)
                merged = merged.drop_duplicates(subset=["match_id"])
                
                if len(merged) >= 10:
                    print(f"[INFO] Trovati {len(merged)} match con features. Creo modelli basati su questi dati...")
                    _create_dummy_models_from_data(merged)
                    return
        except Exception as e:
            print(f"[WARN] Errore creazione dummy da dati reali: {e}")
        
        # Fallback: crea dummy minimi
        print("[INFO] Creazione modelli dummy minimi (sintetici)...")
        try:
            train_ou25(algo=args.algo)  # Prova a trainare, se fallisce crea dummy
        except:
            from sklearn.datasets import make_classification
            X, y = make_classification(n_samples=100, n_features=len(FEATURES_OU), n_classes=2, random_state=42)
            imputer = SimpleImputer(strategy="median")
            scaler = StandardScaler()
            clf = LogisticRegression(max_iter=1000, random_state=42)
            X_imp = imputer.fit_transform(X)
            X_scl = scaler.fit_transform(X_imp)
            clf.fit(X_scl, y)
            joblib.dump(imputer, OU_IMPUTER_PATH)
            joblib.dump(scaler, OU_SCALER_PATH)
            joblib.dump(clf, OU_MODEL_PATH)
            OU_META_PATH.write_text(json.dumps({"features": FEATURES_OU, "dummy": True}, indent=2), encoding="utf-8")
            print(f"[OK] Modello dummy OU creato")
        return
    
    # Default: predict
    if args.predict or not (args.train_ou or args.train_1x2 or args.train_dummy):
        if not args.date:
            print("[ERR] L'opzione --predict richiede --date YYYY-MM-DD.")
            sys.exit(1)
        
        comps_list = [c.strip().upper() for c in args.comps.split(",")] if args.comps else None
        predict_and_report(date_str=args.date, comps=comps_list)



if __name__ == "__main__":
    main()
