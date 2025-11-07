#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parent
FIX_PATH = ROOT / "fixtures.csv"
FEA_PATH = ROOT / "features.csv"
HIST_PATH = ROOT / "data" / "historical_dataset.csv"
PRED_PATH = ROOT / "predictions.csv"
MODEL_DIR = ROOT / "models"
MODEL_DIR.mkdir(exist_ok=True)
MODEL_PATH = MODEL_DIR / "bet_ou25.joblib"
SCALER_PATH = MODEL_DIR / "scaler_ou25.joblib"
IMPUTER_PATH = MODEL_DIR / "imputer_ou25.joblib"
META_PATH = MODEL_DIR / "meta_ou25.json"
REPORT_HTML = ROOT / "report.html"

FEATURE_COLS = [
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
TARGET_OU25 = "target_ou25"


def _to_num(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _clip01(p, lo=1e-6, hi=1 - 1e-6):
    return float(np.clip(p, lo, hi))


def _ensure_target(df: pd.DataFrame) -> pd.DataFrame:
    if TARGET_OU25 not in df.columns:
        if {"ft_home_goals", "ft_away_goals"}.issubset(df.columns):
            g = pd.to_numeric(df["ft_home_goals"], errors="coerce").fillna(
                0
            ) + pd.to_numeric(df["ft_away_goals"], errors="coerce").fillna(0)
            df[TARGET_OU25] = (g > 2).astype(int)
    return df


def _kelly(p: float, o: float, cut: float = 0.5) -> float:
    if not (o and o > 1):
        return 0.0
    if p <= 0 or p >= 1:
        return 0.0
    b = o - 1.0
    f = (b * p - (1 - p)) / b
    return round(max(0.0, f * cut), 4)


# ---------- TRAIN OU2.5 ----------
def load_training_df() -> pd.DataFrame:
    if HIST_PATH.exists():
        df = pd.read_csv(HIST_PATH)
        return _ensure_target(df)
    print("[ERR] data/historical_dataset.csv mancante.")
    sys.exit(1)


def train_real_ou25():
    df = load_training_df()
    cols = [c for c in FEATURE_COLS if c in df.columns]
    if not cols:
        print("[ERR] Nessuna FEATURE_COLS nello storico.")
        sys.exit(1)

    _to_num(df, cols)
    y = pd.to_numeric(df[TARGET_OU25], errors="coerce").astype("Int64").dropna()
    df = df.loc[y.index]
    y = y.astype(int)
    X = df[cols].copy()

    imputer = SimpleImputer(strategy="constant", fill_value=0.0)
    scaler = StandardScaler()
    clf = LogisticRegression(solver="lbfgs", max_iter=1000, random_state=42)

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    X_imp = imputer.fit_transform(X)
    X_scl = scaler.fit_transform(X_imp)
    proba = cross_val_predict(clf, X_scl, y, cv=cv, method="predict_proba")[:, 1]
    proba = np.clip(proba, 1e-6, 1 - 1e-6)
    print(
        f"[CV] Brier: {brier_score_loss(y, proba):.4f}   LogLoss: {log_loss(y, proba, labels=[0, 1]):.4f}   (n={len(y)})"
    )

    clf.fit(X_scl, y)
    joblib.dump(imputer, IMPUTER_PATH)
    joblib.dump(scaler, SCALER_PATH)
    joblib.dump(clf, MODEL_PATH)
    META_PATH.write_text(json.dumps({"features": cols}, indent=2))
    print(f"[OK] Modello OU2.5 salvato: {MODEL_PATH}")


# ---------- POISSON (da xG) ----------
def _lambda_from_xg(row: pd.Series) -> tuple[float, float, bool]:
    hxgf = pd.to_numeric(row.get("xG_for_5_home"), errors="coerce")
    hxga = pd.to_numeric(row.get("xG_against_5_home"), errors="coerce")
    axgf = pd.to_numeric(row.get("xG_for_5_away"), errors="coerce")
    axga = pd.to_numeric(row.get("xG_against_5_away"), errors="coerce")
    have_xg = (
        np.isfinite(hxgf)
        and np.isfinite(hxga)
        and np.isfinite(axgf)
        and np.isfinite(axga)
    )
    if not have_xg:
        # ritorno numeri placeholder + flag di mancanza
        return (1.35, 1.35, False)
    lam_h = max(0.05, 0.6 * float(hxgf) + 0.4 * float(axga))
    lam_a = max(0.05, 0.6 * float(axgf) + 0.4 * float(hxga))
    try:
        rest_diff = float(row.get("rest_days_home", 0)) - float(
            row.get("rest_days_away", 0)
        )
    except:
        rest_diff = 0.0
    try:
        meteo = float(row.get("meteo_flag", 0))
    except:
        meteo = 0.0
    try:
        travel = float(row.get("travel_km_away", 0))
    except:
        travel = 0.0
    lam_h *= (1.0 + 0.02 * np.tanh(rest_diff / 5.0)) * (1.0 - 0.03 * meteo)
    lam_a *= (
        (1.0 - 0.02 * np.tanh(rest_diff / 5.0))
        * (1.0 - 0.03 * meteo)
        * (1.0 - min(0.05, travel / 3000.0))
    )
    return (float(max(lam_h, 0.05)), float(max(lam_a, 0.05)), True)


def _poisson_probs(lh: float, la: float, gmax: int = 6):
    i = np.arange(0, gmax + 1)
    fx = np.vectorize(math.factorial)
    px = np.exp(-lh) * np.power(lh, i) / fx(i)
    py = np.exp(-la) * np.power(la, i) / fx(i)
    M = np.outer(px, py)
    M = M / M.sum()
    p1 = float(np.triu(M, k=1).sum())
    px = float(np.trace(M))
    p2 = float(np.tril(M, k=-1).sum())
    p_btts = float(1.0 - M[0, :].sum() - M[:, 0].sum() + M[0, 0])
    pu = float(M[0:3, 0:3].sum())
    po = float(1.0 - pu)
    idx = np.unravel_index(np.argmax(M), M.shape)
    return {
        "p1": _clip01(p1),
        "px": _clip01(px),
        "p2": _clip01(p2),
        "p_btts": _clip01(p_btts),
        "p_over_2_5": _clip01(po),
        "p_under_2_5": _clip01(pu),
        "score_mode": f"{idx[0]}-{idx[1]}",
        "p_score_mode": float(M[idx]),
    }


# ---------- FALLBACK DA QUOTE ----------
def _prob_from_odds(o1, ox, o2):
    """Converte quote in probabilità rimuovendo l'overround."""
    if not all(pd.notna([o1, ox, o2])):
        return (np.nan, np.nan, np.nan)
    inv = np.array([1 / float(o1), 1 / float(ox), 1 / float(o2)], dtype=float)
    s = inv.sum()
    if s <= 0:
        return (np.nan, np.nan, np.nan)
    p = inv / s
    return (float(p[0]), float(p[1]), float(p[2]))


def _ou_from_totals(oo, ou):
    if pd.notna(oo) and pd.notna(ou) and float(oo) > 1 and float(ou) > 1:
        p_over = 1 / float(oo)
        p_under = 1 / float(ou)
        s = p_over + p_under
        if s > 0:
            return (_clip01(p_over / s), _clip01(p_under / s))
    return (np.nan, np.nan)


# ---------- PREDICT + REPORT ----------
def _load_ou25_model():
    if MODEL_PATH.exists() and SCALER_PATH.exists() and IMPUTER_PATH.exists():
        return (
            joblib.load(IMPUTER_PATH),
            joblib.load(SCALER_PATH),
            joblib.load(MODEL_PATH),
        )
    return (None, None, None)


def load_merged_for_predict() -> pd.DataFrame:
    if not FIX_PATH.exists() or not FEA_PATH.exists():
        print("[ERR] fixtures.csv o features.csv non trovati.")
        sys.exit(1)
    fix = pd.read_csv(FIX_PATH)
    fea = pd.read_csv(FEA_PATH)
    return pd.merge(fix, fea, on="match_id", how="inner")


def predict_and_report():
    df = load_merged_for_predict()
    for c in ["odds_1", "odds_x", "odds_2", "odds_ou25_over", "odds_ou25_under"]:
        if c not in df.columns:
            df[c] = np.nan

    imputer, scaler, clf = _load_ou25_model()
    used_feats = []
    if clf is not None:
        try:
            meta = json.loads(META_PATH.read_text())
            used_feats = [
                c for c in meta.get("features", FEATURE_COLS) if c in df.columns
            ]
        except Exception:
            used_feats = [c for c in FEATURE_COLS if c in df.columns]

    rows = []
    for _, r in df.iterrows():
        o1, ox, o2 = (
            r.get("odds_1", np.nan),
            r.get("odds_x", np.nan),
            r.get("odds_2", np.nan),
        )
        oo, ou = r.get("odds_ou25_over", np.nan), r.get("odds_ou25_under", np.nan)

        # 1) prova Poisson da xG
        lam_h, lam_a, have_xg = _lambda_from_xg(r)
        if have_xg:
            pois = _poisson_probs(lam_h, lam_a, gmax=6)
            p1, px, p2 = pois["p1"], pois["px"], pois["p2"]
            p_btts = pois["p_btts"]
            p_over, p_under = pois["p_over_2_5"], pois["p_under_2_5"]
        else:
            # 2) fallback da quote per 1X2
            p1, px, p2 = _prob_from_odds(o1, ox, o2)
            # fallback BTTS non disponibile dalle quote -> stima neutra
            p_btts = (
                0.52
                if any(pd.isna([p1, px, p2]))
                else max(0.40, min(0.65, p1 + p2 - 0.35))
            )
            # OU: se ho quote totals uso quelle, altrimenti stima neutra
            p_over, p_under = _ou_from_totals(oo, ou)
            if pd.isna(p_over) or pd.isna(p_under):
                p_over, p_under = 0.5, 0.5

        # OU dal modello (se c’è) sovrascrive
        if clf is not None and used_feats:
            x = pd.DataFrame(
                {c: [pd.to_numeric(r.get(c), errors="coerce")] for c in used_feats}
            )
            x = imputer.transform(x)
            x = scaler.transform(x)
            p_over = _clip01(float(clf.predict_proba(x)[0, 1]))
            p_under = 1.0 - p_over

        # value & picks
        v1 = ((float(o1) - 1) * p1 - (1 - p1)) if pd.notna(o1) else np.nan
        vx = ((float(ox) - 1) * px - (1 - px)) if pd.notna(ox) else np.nan
        v2 = ((float(o2) - 1) * p2 - (1 - p2)) if pd.notna(o2) else np.nan
        pick_1x2 = "NoBet"
        k1x2 = 0.0
        cand = [(v1, "1", o1, p1), (vx, "X", ox, px), (v2, "2", o2, p2)]
        cand = [c for c in cand if not pd.isna(c[0])]
        if cand:
            best = max(cand, key=lambda x: x[0])
            if best[0] >= 0:
                pick_1x2 = best[1]
                k1x2 = _kelly(best[3], float(best[2]))

        vov = ((float(oo) - 1) * p_over - (1 - p_over)) if pd.notna(oo) else np.nan
        vun = ((float(ou) - 1) * p_under - (1 - p_under)) if pd.notna(ou) else np.nan
        pick_ou = "NoBet"
        k_ou = 0.0
        if not pd.isna(vov) and (pd.isna(vun) or vov >= vun) and vov >= 0:
            pick_ou = "Over 2.5"
            k_ou = _kelly(p_over, float(oo))
        elif not pd.isna(vun) and vun >= 0:
            pick_ou = "Under 2.5"
            k_ou = _kelly(p_under, float(ou))

        rows.append(
            {
                "match_id": r["match_id"],
                "date": r.get("date", pd.NA),
                "time": r.get("time_local", r.get("time", pd.NA)),
                "league": r.get("league", pd.NA),
                "home": r.get("home", pd.NA),
                "away": r.get("away", pd.NA),
                "p1": float(p1) if not pd.isna(p1) else np.nan,
                "px": float(px) if not pd.isna(px) else np.nan,
                "p2": float(p2) if not pd.isna(p2) else np.nan,
                "odds_1": o1,
                "odds_x": ox,
                "odds_2": o2,
                "value_1": None if pd.isna(v1) else round(float(v1), 4),
                "value_x": None if pd.isna(vx) else round(float(vx), 4),
                "value_2": None if pd.isna(v2) else round(float(v2), 4),
                "pick_1x2": pick_1x2,
                "kelly_1x2": k1x2,
                "p_over_2_5": float(p_over),
                "p_under_2_5": float(p_under),
                "odds_ou25_over": oo,
                "odds_ou25_under": ou,
                "pick_ou25": pick_ou,
                "kelly_ou25": k_ou,
                "p_btts": float(p_btts),
                "score_mode": "",  # il correct score ha senso solo con xG affidabili; lo lasciamo vuoto in fallback
            }
        )

    out = pd.DataFrame(rows)
    out.to_csv(PRED_PATH, index=False)
    print(f"[OK] predictions.csv scritto ({len(out)} righe).")

    # report essenziale e chiaro
    tab = out.copy()
    for c in [
        "p1",
        "px",
        "p2",
        "p_over_2_5",
        "p_under_2_5",
        "p_btts",
        "kelly_1x2",
        "kelly_ou25",
        "value_1",
        "value_x",
        "value_2",
    ]:
        if c in tab.columns:
            tab[c] = tab[c].apply(lambda x: "" if pd.isna(x) else f"{float(x):.3f}")
    html = [
        "<html><head><meta charset='utf-8'><title>Report</title>",
        "<style>body{font-family:Arial} table{border-collapse:collapse} th,td{border:1px solid #ddd;padding:6px 8px}</style>",
        "</head><body>",
        f"<h2>Report — {datetime.utcnow().isoformat()}Z</h2>",
        "<p>Se mancano xG: p1/px/p2 e OU derivati dalle <b>quote</b> (overround-corrected). Se xG presenti: Poisson + modello OU.</p>",
        tab.to_html(index=False, escape=False),
        "</body></html>",
    ]
    REPORT_HTML.write_text("\n".join(html), encoding="utf-8")
    print(f"[OK] report HTML: {REPORT_HTML}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--train-dummy", action="store_true")
    ap.add_argument("--predict", action="store_true")
    args = ap.parse_args()
    if args.train:
        train_real_ou25()
    elif args.train_dummy:
        # piccolo dummy per creare il modello
        rows = [
            {
                "xG_for_5_home": 1.8,
                "xG_against_5_home": 0.9,
                "xG_for_5_away": 1.1,
                "xG_against_5_away": 1.5,
                "rest_days_home": 6,
                "rest_days_away": 6,
                "derby_flag": 0,
                "europe_flag_home": 0,
                "europe_flag_away": 0,
                "meteo_flag": 0,
                "style_ppda_home": 10,
                "style_ppda_away": 12,
                "travel_km_away": 300,
                "target_ou25": 1,
            },
            {
                "xG_for_5_home": 0.9,
                "xG_against_5_home": 1.3,
                "xG_for_5_away": 1.6,
                "xG_against_5_away": 0.8,
                "rest_days_home": 5,
                "rest_days_away": 7,
                "derby_flag": 0,
                "europe_flag_home": 0,
                "europe_flag_away": 0,
                "meteo_flag": 1,
                "style_ppda_home": 12,
                "style_ppda_away": 9,
                "travel_km_away": 120,
                "target_ou25": 0,
            },
        ]
        df = pd.DataFrame(rows)
        imputer = SimpleImputer(strategy="constant", fill_value=0.0)
        scaler = StandardScaler()
        clf = LogisticRegression(max_iter=1000, solver="lbfgs", random_state=42)
        X = df[FEATURE_COLS]
        y = df["target_ou25"].astype(int)
        X = imputer.fit_transform(X)
        X = scaler.fit_transform(X)
        clf.fit(X, y)
        joblib.dump(imputer, IMPUTER_PATH)
        joblib.dump(scaler, SCALER_PATH)
        joblib.dump(clf, MODEL_PATH)
        META_PATH.write_text(
            json.dumps({"features": FEATURE_COLS, "dummy": True}, indent=2)
        )
        print(f"[OK] Modello dummy OU2.5 salvato: {MODEL_PATH}")
    else:
        predict_and_report()


if __name__ == "__main__":
    main()
