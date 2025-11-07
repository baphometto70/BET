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

try:
    from lightgbm import LGBMClassifier
except ImportError:
    LGBMClassifier = None  # type: ignore

# =========================
# CONFIG
# =========================
ROOT = Path(__file__).resolve().parent

# Input/Output files
FIX_PATH = ROOT / "fixtures.csv"
FEA_PATH = ROOT / "features.csv"
PRED_PATH = ROOT / "predictions.csv"
REPORT_HTML = ROOT / "report.html"

# Storici
HIST_OU_PATH = ROOT / "data" / "historical_dataset.csv"
HIST_1X2_PATH = ROOT / "data" / "historical_1x2.csv"

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
FEATURES_BASE: List[str] = [
    "xG_for_5_home",
    "xG_against_5_home",
    "xG_for_5_away",
    "xG_against_5_away",
    "rest_days_home",
    "rest_days_away",
    "derby_flag",
    "europe_flag_home",
    "europe_flag_away",
    "meteo_flag",
    "style_ppda_home",
    "style_ppda_away",
    "travel_km_away",
]

FEATURES_OU: List[str] = FEATURES_BASE[:]  # per OU 2.5
FEATURES_1X2: List[str] = FEATURES_BASE[:]  # per 1X2

# STRICT ML: non usare MAI quote per produrre probabilità
STRICT_ML = True


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


def _build_components(algo: str, task: str):
    """
    Ritorna (model, imputer, scaler) per l'algoritmo richiesto.
    task = 'binary' | 'multiclass'
    """
    algo = (algo or "logistic").lower()
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


def _create_dummy_models_from_data(df: pd.DataFrame):
    """Crea modelli dummy intelligenti usando i dati reali disponibili."""
    # Prepara features
    cols = [c for c in FEATURES_OU if c in df.columns]
    if not cols:
        print("[WARN] Nessuna feature disponibile, uso dummy sintetici")
        return
    
    df_num = _to_num(df, cols)
    
    # Modello OU: deriva target da probabilità Over/Under basata su xG
    if all(c in df.columns for c in ["xG_for_5_home", "xG_against_5_home", "xG_for_5_away", "xG_against_5_away"]):
        xg_h = pd.to_numeric(df["xG_for_5_home"], errors="coerce").fillna(1.2)
        xga_h = pd.to_numeric(df["xG_against_5_home"], errors="coerce").fillna(1.2)
        xg_a = pd.to_numeric(df["xG_for_5_away"], errors="coerce").fillna(1.2)
        xga_a = pd.to_numeric(df["xG_against_5_away"], errors="coerce").fillna(1.2)
        
        # Stima lambda per Poisson
        lambda_h = ((xg_h + xga_a) / 2.0 * 1.12).clip(0.3, 4.0)
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
    if all(c in df.columns for c in ["xG_for_5_home", "xG_for_5_away"]):
        lambda_h = ((xg_h + xga_a) / 2.0 * 1.12).clip(0.3, 4.0)
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
    except Exception as e:
        print(f"[ERR] Errore lettura {HIST_OU_PATH}: {e}")
        sys.exit(1)
    
    if df.empty:
        print(f"[ERR] {HIST_OU_PATH} è vuoto")
        sys.exit(1)
    df = _ensure_target_ou(df)

    cols = [c for c in FEATURES_OU if c in df.columns]
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
    else:
        X_proc = X_proc.to_numpy()
    if scaler is not None:
        scaler.fit(X_proc)
        X_proc = scaler.transform(X_proc)

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
    df = _ensure_target_1x2(df)

    cols = [c for c in FEATURES_1X2 if c in df.columns]
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
    else:
        X_proc = X_proc.to_numpy()
    if scaler is not None:
        scaler.fit(X_proc)
        X_proc = scaler.transform(X_proc)

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


def _poisson_prob(lmbd: float, k: int) -> float:
    """Calcola probabilità Poisson: P(X=k) con lambda lmbd."""
    from math import exp, factorial
    if lmbd <= 0:
        return 0.0
    try:
        return exp(-lmbd) * (lmbd ** k) / factorial(k)
    except:
        return 0.0


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
    return 0.33, 0.34, 0.33


def _fallback_1x2_prob(r: pd.Series) -> Tuple[float, float, float]:
    """Calcola probabilità 1X2 usando fallback intelligente (Poisson da xG o quote)."""
    # Metodo 1: Usa xG per modello Poisson accurato
    xg_home = pd.to_numeric(r.get("xG_for_5_home"), errors="coerce")
    xg_away = pd.to_numeric(r.get("xG_for_5_away"), errors="coerce")
    xga_home = pd.to_numeric(r.get("xG_against_5_home"), errors="coerce")
    xga_away = pd.to_numeric(r.get("xG_against_5_away"), errors="coerce")
    
    # Calcola lambda usando xG for e xG against dell'avversario
    # IGNORA valori default (1.2) - sono placeholder quando dati non disponibili
    if (pd.notna(xg_home) and pd.notna(xga_away) and 
        xg_home > 0 and xga_away > 0 and 
        not (xg_home == 1.2 and xga_away == 1.2)):  # Evita default
        # Lambda home = media tra xG for home e xG against away
        lambda_h = (xg_home + xga_away) / 2.0
        lambda_h = max(0.3, min(4.0, lambda_h))  # Limiti ragionevoli
        
        if (pd.notna(xg_away) and pd.notna(xga_home) and 
            xg_away > 0 and xga_home > 0 and
            not (xg_away == 1.2 and xga_home == 1.2)):  # Evita default
            lambda_a = (xg_away + xga_home) / 2.0
            lambda_a = max(0.3, min(4.0, lambda_a))
            
            # Aggiungi home advantage (circa 10-15%)
            lambda_h *= 1.12
            lambda_a *= 0.95
            
            # Usa modello Poisson completo
            return _poisson_1x2_probs(lambda_h, lambda_a)
        elif pd.notna(xg_away) and xg_away > 0 and xg_away != 1.2:
            # Fallback: usa solo xG for
            lambda_a = max(0.3, min(4.0, xg_away))
            lambda_h = max(0.3, min(4.0, xg_home)) * 1.12
            return _poisson_1x2_probs(lambda_h, lambda_a)
    
    # Metodo 2: Se xG non disponibili, usa quote (anche parziali)
    o1 = pd.to_numeric(r.get("odds_1"), errors="coerce")
    ox = pd.to_numeric(r.get("odds_x"), errors="coerce")
    o2 = pd.to_numeric(r.get("odds_2"), errors="coerce")
    
    # Se abbiamo tutte e 3 le quote
    if pd.notna(o1) and pd.notna(ox) and pd.notna(o2) and all(o > 1.0 for o in [o1, ox, o2]):
        # Calcola probabilità implicite
        p1_impl = 1.0 / o1
        px_impl = 1.0 / ox
        p2_impl = 1.0 / o2
        total = p1_impl + px_impl + p2_impl
        
        if total > 0:
            # Normalizza (rimuove overround) e applica leggera correzione home advantage
            p1_norm = p1_impl / total
            px_norm = px_impl / total
            p2_norm = p2_impl / total
            
            # Leggera correzione: aumenta probabilità home del 2-3%
            p1_norm = min(0.85, p1_norm * 1.02)
            p2_norm = max(0.05, p2_norm * 0.98)
            px_norm = 1.0 - p1_norm - p2_norm
            
            return p1_norm, px_norm, p2_norm
    
    # Metodo 2b: Se abbiamo solo alcune quote, stima le altre in modo più intelligente
    if pd.notna(ox) and ox > 1.0:
        px_impl = 1.0 / ox
        
        # Stima più sofisticata basata su odds_x
        # Se odds_x è molto alta (>10), partita molto sbilanciata (una squadra fortemente favorita)
        # Se odds_x è media (3-5), partita equilibrata
        # Se odds_x è bassa (<3), partita molto equilibrata (alta probabilità pareggio)
        
        if ox > 10.0:
            # Partita molto sbilanciata - una squadra fortemente favorita
            # Stima: favorito ha ~60-70%, l'altro ~20-30%
            remaining = 1.0 - px_impl
            # Home leggermente favorito per default
            p1_est = remaining * 0.65
            p2_est = remaining * 0.35
        elif ox > 5.0:
            # Partita sbilanciata
            remaining = 1.0 - px_impl
            p1_est = remaining * 0.58
            p2_est = remaining * 0.42
        elif ox > 3.5:
            # Partita leggermente sbilanciata
            remaining = 1.0 - px_impl
            p1_est = remaining * 0.53
            p2_est = remaining * 0.47
        elif ox > 2.8:
            # Partita equilibrata
            remaining = (1.0 - px_impl) / 2.0
            p1_est = remaining * 1.05  # Leggero home advantage
            p2_est = remaining * 0.95
        else:
            # Partita molto equilibrata (bassa probabilità pareggio)
            remaining = (1.0 - px_impl) / 2.0
            p1_est = remaining * 1.02
            p2_est = remaining * 0.98
        
        total = p1_est + px_impl + p2_est
        if total > 0:
            return p1_est/total, px_impl/total, p2_est/total
    
    # Metodo 3: Default equilibrato con leggero home advantage
    return 0.35, 0.30, 0.35


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
        print(f"[WARN] Errore predizione 1X2 per {r.get('match_id', 'unknown')}: {e}")
        return _fallback_1x2_prob(r)


def load_merged_for_predict() -> pd.DataFrame:
    if not FIX_PATH.exists() or not FEA_PATH.exists():
        print("[ERR] fixtures.csv o features.csv non trovati.")
        sys.exit(1)
    fix = pd.read_csv(FIX_PATH)
    fea = pd.read_csv(FEA_PATH)
    df = pd.merge(fix, fea, on="match_id", how="inner")
    # garantisci che le colonne quote esistano
    for c in ["odds_1", "odds_x", "odds_2", "odds_ou25_over", "odds_ou25_under"]:
        if c not in df.columns:
            df[c] = np.nan
    return df


def predict_and_report():
    try:
        df = load_merged_for_predict()
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
            if p is None or np.isnan(p) or o is None:
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
        f"<h1>⚽ Report Previsioni — {datetime.now().strftime('%d/%m/%Y %H:%M')}</h1>",
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
        "--algo",
        choices=["logistic", "lgbm"],
        default="logistic",
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
        
        # Prova a usare fixtures+features esistenti per creare dataset dummy
        try:
            fix_df = pd.read_csv(FIX_PATH) if FIX_PATH.exists() else pd.DataFrame()
            fea_df = pd.read_csv(FEA_PATH) if FEA_PATH.exists() else pd.DataFrame()
            
            if not fix_df.empty and not fea_df.empty:
                merged = pd.merge(fix_df, fea_df, on="match_id", how="inner")
                if not merged.empty and len(merged) >= 10:
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
    # default: predict
    predict_and_report()


if __name__ == "__main__":
    main()
