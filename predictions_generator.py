#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
predictions_generator.py
Genera previsioni chiare dalle partite usando xG e quote.

Miglioramenti:
- Usa entrambi gli attacchi/difese (home vs away) invece di una sola squadra.
- Integra contesto: riposo, infortuni, viaggio, coppe europee, meteo, derby.
- Calcola probabilità 1X2 e Over/Under con Poisson coerente.
"""

import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
import warnings

from database import SessionLocal
from models import Fixture, Odds, Feature, Prediction
import random
from rapidfuzz import fuzz
import joblib
import json

# Neural Reasoning Engine - applies contextual intelligence as final layer
from neural_reasoning_engine import NeuralReasoningEngine

# Heuristica per fallback quando mancano dati xG
STRONG_TEAMS = {
    "SA": ["Inter", "Milan", "Juventus", "Napoli", "Roma", "Lazio", "Atalanta"],
    "PL": ["Manchester City", "Manchester United", "Liverpool", "Chelsea", "Arsenal", "Tottenham"],
    "PD": ["Real Madrid", "Barcelona", "Atletico Madrid", "Sevilla"],
    "BL1": ["Bayern München", "Borussia Dortmund", "RB Leipzig"],
    "FL1": ["Paris Saint-Germain", "Olympique Lyonnais", "Olympique Marseille"],
}

def _is_strong_team(team_name: str, league_code: str) -> bool:
    """Controlla se una squadra è in lista 'forti' per la lega."""
    if not league_code or league_code not in STRONG_TEAMS:
        return False
    strong_list = STRONG_TEAMS.get(league_code, [])
    # Usa una soglia di similarità per gestire variazioni di nome
    best_ratio = max([fuzz.ratio(team_name.upper(), s.upper()) for s in strong_list], default=0)
    return best_ratio >= 85

def _get_fallback_profile(is_strong: bool) -> Tuple[float, float]:
    """Restituisce un profilo (xG_fatti, xG_subiti) con variabilità per il fallback."""
    if is_strong:
        return (round(random.uniform(1.6, 2.0), 2), round(random.uniform(0.9, 1.3), 2))
    else:
        return (round(random.uniform(1.1, 1.5), 2), round(random.uniform(1.2, 1.6), 2))


ROOT = Path(__file__).resolve().parent

BLEND_HOME_EDGE_CAP = 0.55  # quanto le quote possono influenzare i lambda se dati scarsi

# Valori medi di goal per lega (usati come ancora quando i dati sono poveri)
LEAGUE_BASE_GOALS = {
    "SA": 2.55,
    "PL": 2.75,
    "PD": 2.55,
    "BL1": 3.05,
    "FL1": 2.55,
    "DED": 3.0,
    "PPL": 2.4,
    "ELC": 2.45,
    "CL": 2.9,
    "EL": 2.7,
}


def _hash_noise(seed: Optional[str]) -> float:
    """Piccola variazione deterministica per evitare simmetrie perfette (range ~[-0.125, 0.125])."""
    if not seed:
        return 0.0
    h = hash(seed)
    return ((h % 21) - 10) / 80.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _load_ml_artifact(model_path: Path, imputer_path: Path, scaler_path: Path, meta_path: Path):
    if not model_path.exists() or not meta_path.exists():
        return None
    try:
        model = joblib.load(model_path)
        imputer = joblib.load(imputer_path) if imputer_path.exists() else None
        scaler = joblib.load(scaler_path) if scaler_path.exists() else None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return {"model": model, "imputer": imputer, "scaler": scaler, "meta": meta}
    except Exception:
        return None


ML_CACHE = {"ou": None, "x2": None}
MODEL_DIR = ROOT / "models"
OU_MODEL_PATH = MODEL_DIR / "bet_ou25.joblib"
OU_IMPUTER_PATH = MODEL_DIR / "imputer_ou25.joblib"
OU_SCALER_PATH = MODEL_DIR / "scaler_ou25.joblib"
OU_META_PATH = MODEL_DIR / "meta_ou25.json"
X2_MODEL_PATH = MODEL_DIR / "bet_1x2.joblib"
X2_IMPUTER_PATH = MODEL_DIR / "imputer_1x2.joblib"
X2_SCALER_PATH = MODEL_DIR / "scaler_1x2.joblib"
X2_META_PATH = MODEL_DIR / "meta_1x2.json"


def _load_ml_models():
    if ML_CACHE["ou"] is None:
        ML_CACHE["ou"] = _load_ml_artifact(OU_MODEL_PATH, OU_IMPUTER_PATH, OU_SCALER_PATH, OU_META_PATH)
    if ML_CACHE["x2"] is None:
        ML_CACHE["x2"] = _load_ml_artifact(X2_MODEL_PATH, X2_IMPUTER_PATH, X2_SCALER_PATH, X2_META_PATH)


def _prepare_feature_vector(features: Dict[str, float], cols: List[str]) -> Tuple[Optional[pd.DataFrame], float]:
    if not cols:
        return None, 0.0
    row = {}
    coverage = 0
    for c in cols:
        val = features.get(c, None)
        if val is None or (isinstance(val, float) and math.isnan(val)):
            row[c] = math.nan
        else:
            row[c] = val
            coverage += 1
    cov_ratio = coverage / len(cols)
    if cov_ratio < 0.35:
        return None, cov_ratio
    df = pd.DataFrame([row], columns=cols)
    return df, cov_ratio


def _ml_predict(model_blob, df: Optional[pd.DataFrame]) -> Optional[List[float]]:
    if not model_blob or df is None or df.empty:
        return None
    model = model_blob.get("model")
    imputer = model_blob.get("imputer")
    scaler = model_blob.get("scaler")
    if model is None:
        return None
    arr_df = df.copy()
    col_names = list(arr_df.columns)
    try:
        if imputer is not None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=UserWarning)
                arr = imputer.transform(arr_df)
            col_names = getattr(imputer, "feature_names_in_", col_names)
            arr_df = pd.DataFrame(arr, columns=col_names)
        if scaler is not None:
            arr = scaler.transform(arr_df)
            arr_df = pd.DataFrame(arr, columns=col_names)
        proba = model.predict_proba(arr_df)
        return proba[0].tolist()
    except Exception:
        return None


def _apply_odds_shift(
    lambda_home: float,
    lambda_away: float,
    odds_probs: Optional[Tuple[float, float, float]],
    info_level: str,
    seed: Optional[str] = None,
) -> Tuple[float, float]:
    """Applica un'inclinazione sui lambda in base alle quote 1X2 per evitare pareggi piatti."""
    if not odds_probs:
        # Se non abbiamo quote e i dati sono poveri, aggiungi un piccolo skew deterministico pro-casa
        if info_level == "low":
            bias = 0.06 + abs(_hash_noise(seed)) * 0.4 if seed else 0.08
            lambda_home = _clamp(lambda_home * (1 + bias), 0.15, 5.0)
            lambda_away = _clamp(lambda_away * (1 - bias), 0.15, 5.0)
        return lambda_home, lambda_away
    cap = BLEND_HOME_EDGE_CAP * (1.15 if info_level == "low" else 1.0)
    delta = (odds_probs[0] - odds_probs[2]) * cap
    lambda_home = _clamp(lambda_home * (1 + delta), 0.15, 5.0)
    lambda_away = _clamp(lambda_away * (1 - delta), 0.15, 5.0)
    return lambda_home, lambda_away


def _intuition_adjust(
    lam_home: float,
    lam_away: float,
    info_level: str,
    seed: Optional[str],
    strong_home: Optional[bool],
    strong_away: Optional[bool],
    advantage_score: float,
) -> Tuple[float, float]:
    """Aggiunge rumore controllato e bonus/penalità intuitivi per rompere simmetrie."""
    if strong_home and not strong_away:
        lam_home *= 1.08
        lam_away *= 0.94
    elif strong_away and not strong_home:
        lam_away *= 1.08
        lam_home *= 0.94

    edge = _clamp(advantage_score, -0.8, 0.8)
    lam_home *= 1 + edge * 0.1
    lam_away *= 1 - edge * 0.1

    base_noise = 0.12 if info_level == "low" else 0.06 if info_level == "medium" else 0.03
    extra = _hash_noise(f"{seed}-intuition") if seed else 0.0
    if extra:
        lam_home *= _clamp(1 + extra * base_noise, 0.7, 1.3)
        lam_away *= _clamp(1 - extra * base_noise, 0.7, 1.3)

    return _clamp(lam_home, 0.15, 5.0), _clamp(lam_away, 0.15, 5.0)


def _target_total_goals(
    league_code: Optional[str],
    info_level: str,
    odds_ou_over: Optional[float],
    odds_ou_under: Optional[float],
    has_odds_hint: bool = False,
    odds_probs: Optional[Tuple[float, float, float]] = None,
) -> float:
    base = LEAGUE_BASE_GOALS.get(league_code, 2.55)
    has_total_market = bool(odds_ou_over and odds_ou_under and odds_ou_over > 1.0 and odds_ou_under > 1.0)
    try:
        if has_total_market:
            p_over = 1.0 / float(odds_ou_over)
            p_under = 1.0 / float(odds_ou_under)
            share = p_over / (p_over + p_under)
            base += (share - 0.5) * 0.9  # sposta la linea se il mercato è sbilanciato
        # Se abbiamo un chiaro favorito 1/2 dalle quote 1X2, alziamo leggermente il totale atteso
        if odds_probs:
            fav_bias = abs(odds_probs[0] - odds_probs[2])
            if fav_bias > 0.12:  # gap netto tra favorito e sfavorito
                base += min(0.35, fav_bias * 0.8)
    except Exception:
        pass

    if info_level == "low":
        base += 0.15  # spinge su per evitare bias UNDER sistematico
        base -= 0.18 if not has_total_market and not has_odds_hint else 0.08
    elif info_level == "medium":
        base += 0.05
        base -= 0.08 if not has_total_market and not has_odds_hint else 0.03

    return _clamp(base, 1.6, 3.4)


def _blend_totals(lambda_home: float, lambda_away: float, target_total: float, info_level: str) -> Tuple[float, float]:
    """Riscala i lambda verso un totale atteso per ridurre bias sistematici su Over/pareggi."""
    total = lambda_home + lambda_away
    if total <= 0:
        half = _clamp(target_total / 2.0, 0.2, 3.0)
        return half, half

    weights = {"high": 0.35, "medium": 0.55, "low": 0.7}
    blend = weights.get(info_level, 0.6)
    desired_total = total * (1 - blend) + target_total * blend
    scale = desired_total / total
    return _clamp(lambda_home * scale, 0.15, 5.0), _clamp(lambda_away * scale, 0.15, 5.0)


def _prob_from_lambda(lambda_home: float, lambda_away: float, max_goals: int = 8) -> Tuple[float, float, float, float, str]:
    """Ricalcola p1/px/p2, p_over25 e score più probabile da lambda."""
    p1 = px = p2 = over25 = 0.0
    best = (0, 0, 0.0)
    best_draw = None
    best_non_draw = None
    for hg in range(max_goals + 1):
        ph = _poisson_prob(lambda_home, hg)
        for ag in range(max_goals + 1):
            pa = _poisson_prob(lambda_away, ag)
            prob = ph * pa
            if hg > ag:
                p1 += prob
            elif hg == ag:
                px += prob
            else:
                p2 += prob
            if hg + ag > 2.5:
                over25 += prob
            if prob > best[2]:
                best = (hg, ag, prob)
            if hg == ag:
                if best_draw is None or prob > best_draw[2]:
                    best_draw = (hg, ag, prob)
            else:
                if best_non_draw is None or prob > best_non_draw[2]:
                    best_non_draw = (hg, ag, prob)
    tot = p1 + px + p2
    if tot > 0:
        p1, px, p2 = p1 / tot, px / tot, p2 / tot
    chosen = best
    if best_draw and best_non_draw and (best_draw[2] - best_non_draw[2]) < 0.025:
        chosen = best_non_draw
    top_score = f"{chosen[0]}-{chosen[1]} ({chosen[2]*100:.1f}%)"
    return p1, px, p2, over25, top_score


def _normalize_odds_probs(o1: Optional[float], ox: Optional[float], o2: Optional[float]) -> Optional[Tuple[float, float, float]]:
    if o1 and ox and o2 and o1 > 1.0 and ox > 1.0 and o2 > 1.0:
        p1 = 1.0 / o1
        px = 1.0 / ox
        p2 = 1.0 / o2
        tot = p1 + px + p2
        if tot > 0:
            return p1 / tot, px / tot, p2 / tot
    return None


def _poisson_prob(lam: float, k: int) -> float:
    if lam <= 0 or k < 0:
        return 0.0
    try:
        return (math.exp(-lam) * (lam ** k)) / math.factorial(k)
    except Exception:
        return 0.0


def _fatigue_factor(rest_days: Optional[int]) -> float:
    """Attenua/alza l'attacco in base ai giorni di riposo."""
    if rest_days is None:
        return 1.0
    if rest_days <= 2:
        return 0.88
    if rest_days == 3:
        return 0.93
    if rest_days == 4:
        return 0.97
    if rest_days >= 7:
        return 1.05
    return 1.0


def _injury_factor(n_key_players: Optional[int]) -> float:
    """Riduce l'attacco se mancano titolari, cap massimo ~30%."""
    if n_key_players is None:
        return 1.0
    return max(0.7, 1.0 - min(n_key_players, 6) * 0.05)


def _injury_boost_for_opponent(n_key_players: Optional[int]) -> float:
    """Incrementa il potenziale offensivo avversario se la difesa è decimata."""
    if n_key_players is None:
        return 1.0
    return 1.0 + min(n_key_players, 6) * 0.03


def _travel_penalty(km: Optional[float]) -> float:
    """
    Calcola un fattore di penalità basato sulla distanza di trasferta.
    Restituisce un moltiplicatore (<= 1.0) per ridurre l'efficacia offensiva.
    """
    if km is None:
        return 1.0
    try:
        km = float(km)
    except (ValueError, TypeError):
        return 1.0

    if km < 200:
        return 1.0  # Nessuna penalità per trasferte brevi
    elif km < 800:
        return 0.97 # Penalità leggera per trasferte medie
    else:
        return 0.94 # Penalità maggiore per trasferte lunghe


def _contextual_lambdas(
    xg_for_home: float,
    xg_against_home: float,
    xg_for_away: float,
    xg_against_away: float,
    rest_home: Optional[int],
    rest_away: Optional[int],
    inj_home: Optional[int],
    inj_away: Optional[int],
    travel_km_away: Optional[float],
    derby_flag: int,
    europe_home: int,
    europe_away: int,
    meteo_flag: int,
    seed: Optional[str] = None,
) -> Tuple[float, float]:
    """Costruisce lambda goal tenendo conto di attacco/difesa incrociati e contesto."""
    # Attacco vs difesa avversaria
    lam_home = max(0.2, (xg_for_home + xg_against_away) / 2.0)
    lam_away = max(0.2, (xg_for_away + xg_against_home) / 2.0)

    # Vantaggio casa
    home_adv = 1.12
    if derby_flag:
        home_adv += 0.02
    lam_home *= home_adv

    # Riposo / fatica
    lam_home *= _fatigue_factor(rest_home)
    lam_away *= _fatigue_factor(rest_away)

    # Effetto coppe europee (stanchezza extra)
    if europe_home:
        lam_home *= 0.95
    if europe_away:
        lam_away *= 0.95

    # Infortuni chiave: riducono l'attacco della squadra e aumentano il potenziale avversario
    home_injury_penalty = _injury_factor(inj_home)
    away_injury_penalty = _injury_factor(inj_away)
    lam_home *= home_injury_penalty
    lam_away *= away_injury_penalty
    lam_home *= _injury_boost_for_opponent(inj_away)
    lam_away *= _injury_boost_for_opponent(inj_home)

    # Viaggio per l'away team
    lam_away *= _travel_penalty(travel_km_away)

    # Meteo pesante = meno goal
    if meteo_flag:
        lam_home *= 0.96
        lam_away *= 0.96

    # Bordi sicuri + piccola variazione deterministica per evitare simmetrie
    lam_home = max(0.15, min(lam_home, 5.0))
    lam_away = max(0.15, min(lam_away, 5.0))
    noise = _hash_noise(seed)
    if noise:
        lam_home = max(0.15, min(5.0, lam_home * (1 + noise)))
        lam_away = max(0.15, min(5.0, lam_away * (1 - noise)))

    return lam_home, lam_away


def expected_goals_to_prob(
    *,
    xg_for_home: float,
    xg_against_home: float,
    xg_for_away: float,
    xg_against_away: float,
    rest_home: Optional[int],
    rest_away: Optional[int],
    inj_home: Optional[int],
    inj_away: Optional[int],
    travel_km_away: Optional[float],
    derby_flag: int,
    europe_home: int,
    europe_away: int,
    meteo_flag: int,
    seed: Optional[str] = None,
    league_code: Optional[str] = None,
    info_level: str = "medium",
    odds_probs: Optional[Tuple[float, float, float]] = None,
    odds_ou_over: Optional[float] = None,
    odds_ou_under: Optional[float] = None,
    strong_home: Optional[bool] = None,
    strong_away: Optional[bool] = None,
) -> Tuple[float, float, float, float, float, str, float]:
    """
    Calcola probabilità 1X2, lambda attesi, score più probabile e prob. Over 2.5.
    Ritorna: p1, px, p2, lambda_home, lambda_away, top_score, p_over25
    """
    lam_home, lam_away = _contextual_lambdas(
        xg_for_home,
        xg_against_home,
        xg_for_away,
        xg_against_away,
        rest_home,
        rest_away,
        inj_home,
        inj_away,
        travel_km_away,
        derby_flag,
        europe_home,
        europe_away,
        meteo_flag,
        seed=seed,
    )

    lam_home, lam_away = _apply_odds_shift(lam_home, lam_away, odds_probs, info_level, seed)
    target_total = _target_total_goals(league_code, info_level, odds_ou_over, odds_ou_under, bool(odds_probs), odds_probs)
    lam_home, lam_away = _blend_totals(lam_home, lam_away, target_total, info_level)
    advantage_score = (xg_for_home - xg_against_away) - (xg_for_away - xg_against_home)
    lam_home, lam_away = _intuition_adjust(lam_home, lam_away, info_level, seed, strong_home, strong_away, advantage_score)

    p1, px, p2, over25, top_score_txt = _prob_from_lambda(lam_home, lam_away)
    return p1, px, p2, lam_home, lam_away, top_score_txt, over25


def implied_prob_from_odds(odds: float) -> float:
    """Converte odds decimali in probabilità implicita."""
    if not odds or odds <= 0:
        return 0.0
    return 1.0 / odds


def generate_predictions(date_str: Optional[str] = None) -> List[Dict]:
    """
    Genera previsioni per partite di una data.
    
    Args:
        date_str: Data in formato YYYY-MM-DD. Se None, usa oggi.
    
    Returns:
        Lista di dict con previsioni
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    try:
        target_date = datetime.fromisoformat(str(date_str)[:10]).date()
    except Exception:
        target_date = None
    
    db = SessionLocal()

    # Load advanced features CSV if exists
    advanced_features_path = ROOT / "data" / "advanced_features.csv"
    advanced_features_df = None
    if advanced_features_path.exists():
        try:
            advanced_features_df = pd.read_csv(advanced_features_path)
            advanced_features_df.set_index('match_id', inplace=True)
        except Exception as e:
            print(f"[WARN] Could not load advanced features: {e}")

    try:
        _load_ml_models()
        # Fetch fixtures per la data
        if target_date:
            fixtures = db.query(Fixture).filter(Fixture.date == target_date).all()
        else:
            fixtures = db.query(Fixture).filter(Fixture.date == date_str).all()

        predictions = []

        for fixture in fixtures:
            mid = fixture.match_id
            
            # Skip matches that have already started or finished
            time_str = fixture.time_local or fixture.time
            if time_str:
                try:
                    kickoff_time = datetime.strptime(time_str, "%H:%M").time()
                    kickoff_datetime = datetime.combine(fixture.date, kickoff_time)
                    if kickoff_datetime <= datetime.now():
                        continue  # Skip past matches
                except Exception:
                    pass  # If time parsing fails, proceed anyway
            
            # Fetch odds
            odds_obj = db.query(Odds).filter(Odds.match_id == mid).first()
            
            # Fetch features (xG + contesto)
            feature_obj = db.query(Feature).filter(Feature.match_id == mid).first()
            
            # Logica di fallback per xG migliorata per evitare valori identici
            if feature_obj and feature_obj.xg_for_home is not None:
                xg_for_home = feature_obj.xg_for_home
                xg_against_home = feature_obj.xg_against_home
            else:
                xg_for_home, xg_against_home = _get_fallback_profile(_is_strong_team(fixture.home, fixture.league_code))

            if feature_obj and feature_obj.xg_for_away is not None:
                xg_for_away = feature_obj.xg_for_away
                xg_against_away = feature_obj.xg_against_away
            else:
                xg_for_away, xg_against_away = _get_fallback_profile(_is_strong_team(fixture.away, fixture.league_code))

            rest_home = feature_obj.rest_days_home if feature_obj else None
            rest_away = feature_obj.rest_days_away if feature_obj else None
            inj_home = feature_obj.injuries_key_home if feature_obj else None
            inj_away = feature_obj.injuries_key_away if feature_obj else None
            travel_km_away = feature_obj.travel_km_away if feature_obj else None
            derby_flag = feature_obj.derby_flag if feature_obj else 0
            europe_home = feature_obj.europe_flag_home if feature_obj else 0
            europe_away = feature_obj.europe_flag_away if feature_obj else 0
            meteo_flag = feature_obj.meteo_flag if feature_obj else 0
            xg_confidence = float(feature_obj.xg_confidence) if feature_obj and feature_obj.xg_confidence is not None else None
            xg_source_home = feature_obj.xg_source_home if feature_obj else None
            xg_source_away = feature_obj.xg_source_away if feature_obj else None
            info_level = "low" if feature_obj is None else "medium"
            if xg_confidence is not None:
                if xg_confidence >= 75:
                    info_level = "high"
                elif xg_confidence >= 50:
                    info_level = "medium"
                else:
                    info_level = "low"
            elif (xg_source_home == "fallback") or (xg_source_away == "fallback"):
                info_level = "low"
            elif (xg_source_home == "understat") or (xg_source_away == "understat"): # Dati da fonte primaria
                info_level = "high"
            
            odds_1 = float(odds_obj.odds_1) if odds_obj and odds_obj.odds_1 else None
            odds_x = float(odds_obj.odds_x) if odds_obj and odds_obj.odds_x else None
            odds_2 = float(odds_obj.odds_2) if odds_obj and odds_obj.odds_2 else None
            odds_probs = _normalize_odds_probs(odds_1, odds_x, odds_2)
            odds_ou_over = float(odds_obj.odds_ou25_over) if odds_obj and odds_obj.odds_ou25_over else None
            odds_ou_under = float(odds_obj.odds_ou25_under) if odds_obj and odds_obj.odds_ou25_under else None
            
            # Calcola probabilità da xG incrociati + contesto (seed=match_id per rumore deterministico)
            (
                prob_1_xg,
                prob_x_xg,
                prob_2_xg,
                lam_home,
                lam_away,
                top_score,
                p_over25,
            ) = expected_goals_to_prob(
                xg_for_home=xg_for_home,
                xg_against_home=xg_against_home,
                xg_for_away=xg_for_away,
                xg_against_away=xg_against_away,
                rest_home=rest_home,
                rest_away=rest_away,
                inj_home=inj_home,
                inj_away=inj_away,
                travel_km_away=travel_km_away,
                derby_flag=derby_flag,
                europe_home=europe_home,
                europe_away=europe_away,
                meteo_flag=meteo_flag,
                seed=mid,
                league_code=fixture.league_code,
                info_level=info_level,
                odds_probs=odds_probs,
                odds_ou_over=odds_ou_over,
                odds_ou_under=odds_ou_under,
                strong_home=_is_strong_team(fixture.home, fixture.league_code),
                strong_away=_is_strong_team(fixture.away, fixture.league_code),
            )

            # Blend con quote se dati poveri: più peso alle quote se xG di fallback
            weights = {"high": 0.75, "medium": 0.55, "low": 0.35}
            w_xg = weights.get(info_level, 0.6)
            prob_1_odds = prob_x_odds = prob_2_odds = None
            if odds_probs:
                prob_1_odds, prob_x_odds, prob_2_odds = odds_probs
                prob_1_xg = w_xg * prob_1_xg + (1 - w_xg) * prob_1_odds
                prob_x_xg = w_xg * prob_x_xg + (1 - w_xg) * prob_x_odds
                prob_2_xg = w_xg * prob_2_xg + (1 - w_xg) * prob_2_odds
                tot_blend = prob_1_xg + prob_x_xg + prob_2_xg
                if tot_blend > 0:
                    prob_1_xg, prob_x_xg, prob_2_xg = (
                        prob_1_xg / tot_blend,
                        prob_x_xg / tot_blend,
                        prob_2_xg / tot_blend,
                    )
            
            # ==========================================
            # 🧠 NEURAL REASONING - FINAL HEAVY LAYER
            # ==========================================
            # Apply contextual intelligence as last step before pick determination
            try:
                if not hasattr(generate_predictions, 'neural_engine'):
                    # Initialize neural engine once
                    generate_predictions.neural_engine = NeuralReasoningEngine(
                        db_path=str(Path(ROOT) / "bet.db")
                    )
                
                # Apply neural reasoning
                neural_prob_1, neural_prob_x, neural_prob_2, reasoning = \
                    generate_predictions.neural_engine.apply_reasoning(
                        match_id=mid,
                        home=fixture.home,
                        away=fixture.away,
                        league=fixture.league,
                        date=fixture.date,
                        ml_prob_1=prob_1_xg,
                        ml_prob_x=prob_x_xg,
                        ml_prob_2=prob_2_xg
                    )
                
                # Replace probabilities with neural-adjusted versions
                prob_1_xg = neural_prob_1
                prob_x_xg = neural_prob_x
                prob_2_xg = neural_prob_2
                
                neural_reasoning_summary = reasoning.get('reasoning_summary', '')
                neural_adjustments = f"1:{reasoning.get('home_change_pct', 0):+.1f}% 2:{reasoning.get('away_change_pct', 0):+.1f}%"
                
            except Exception as e:
                # If neural reasoning fails, continue with original probabilities
                print(f"[WARN] Neural reasoning failed for {mid}: {e}")
                neural_reasoning_summary = f"Neural reasoning unavailable: {e}"
                neural_adjustments = "N/A"
            
            
            # Determina il pick migliore (valore positivo)
            best_pick = None
            best_value = 0.0
            
            if odds_1 and prob_1_xg > 0:
                value_1 = prob_1_xg - (1.0 / odds_1)
                if value_1 > best_value:
                    best_value = value_1
                    best_pick = "1"
            
            if odds_x and prob_x_xg > 0:
                value_x = prob_x_xg - (1.0 / odds_x)
                if value_x > best_value:
                    best_value = value_x
                    best_pick = "X"
            
            if odds_2 and prob_2_xg > 0:
                value_2 = prob_2_xg - (1.0 / odds_2)
                if value_2 > best_value:
                    best_value = value_2
                    best_pick = "2"

            # Se non ci sono quote o il value è basso, usa la probabilità più alta per scegliere comunque un pick
            max_prob = max(prob_1_xg, prob_x_xg, prob_2_xg)
            if not best_pick:
                if prob_1_xg == max_prob:
                    best_pick = "1"
                elif prob_x_xg == max_prob:
                    best_pick = "X"
                else:
                    best_pick = "2"
            
            # --- LOGICA DOPPIA CHANCE (Safety First) ---
            prob_1x = prob_1_xg + prob_x_xg
            prob_x2 = prob_x_xg + prob_2_xg
            prob_12 = prob_1_xg + prob_2_xg
            
            # Se la probabilità del segno fisso è bassa (< 50%) ma la doppia è alta (> 70%), suggerisci la doppia
            if max_prob < 0.50:
                if best_pick == "1" and prob_1x >= 0.70:
                    best_pick = "1X"
                    max_prob = prob_1x # Aggiorna prob per confidence
                elif best_pick == "2" and prob_x2 >= 0.70:
                    best_pick = "X2"
                    max_prob = prob_x2
                elif best_pick == "X":
                    # Se è X, spesso meglio coprire con la favorita
                    if prob_1x > prob_x2:
                        best_pick = "1X"
                        max_prob = prob_1x
                    else:
                        best_pick = "X2"
                        max_prob = prob_x2

            # Determina confidence: considera sia value sia probabilità pura
            if best_value > 0.15 or max_prob >= 0.65: # Alzato un pelo soglia ALTA
                confidence = "ALTA"
            elif best_value > 0.08 or max_prob >= 0.55:
                confidence = "MEDIA"
            else:
                confidence = "BASSA"
            confidence_pct = int(max_prob * 100)
            
            # Over/Under 2.5: se abbiamo quote OU, usa anche la probabilità implicita del mercato
            if odds_ou_over and odds_ou_under and odds_ou_over > 1.0 and odds_ou_under > 1.0:
                p_over25_market = (1 / odds_ou_over) / ((1 / odds_ou_over) + (1 / odds_ou_under))
                p_over25 = 0.6 * p_over25 + 0.4 * p_over25_market
            ou_pred = "OVER 2.5" if p_over25 >= 0.52 else "UNDER 2.5"
            total_xg = lam_home + lam_away
            # ---- ML Inference (se modelli disponibili) ----
            features_map = {
                "xg_for_home": xg_for_home,
                "xg_against_home": xg_against_home,
                "xg_for_away": xg_for_away,
                "xg_against_away": xg_against_away,
                "rest_days_home": rest_home,
                "rest_days_away": rest_away,
                "derby_flag": derby_flag,
                "europe_flag_home": europe_home,
                "europe_flag_away": europe_away,
                "meteo_flag": meteo_flag,
                "style_ppda_home": feature_obj.style_ppda_home if feature_obj else None,
                "style_ppda_away": feature_obj.style_ppda_away if feature_obj else None,
                "travel_km_away": travel_km_away,
            }

            # Add advanced features from CSV if available
            if advanced_features_df is not None and mid in advanced_features_df.index:
                adv_row = advanced_features_df.loc[mid]
                # Add all advanced feature columns (excluding metadata)
                metadata_cols = ['date', 'league', 'home_team', 'away_team']
                for col in adv_row.index:
                    if col not in metadata_cols and col not in features_map:
                        features_map[col] = adv_row[col] if pd.notna(adv_row[col]) else None

            ml_ou_prob = None
            ml_1x2_prob = None
            ou_cov = x2_cov = 0.0
            if ML_CACHE["ou"]:
                cols_ou = ML_CACHE["ou"]["meta"].get("features", list(features_map.keys()))
                df_vec, ou_cov = _prepare_feature_vector(features_map, cols_ou)
                if df_vec is not None:
                    ml_ou_prob = _ml_predict(ML_CACHE["ou"], df_vec)
            if ML_CACHE["x2"]:
                cols_x2 = ML_CACHE["x2"]["meta"].get("features", list(features_map.keys()))
                df_vec, x2_cov = _prepare_feature_vector(features_map, cols_x2)
                if df_vec is not None:
                    ml_1x2_prob = _ml_predict(ML_CACHE["x2"], df_vec)

            # Merge Poisson + ML + Odds per affidabilità
            reliability_score = 0.3  # base
            coverage = sum(1 for v in features_map.values() if v is not None) / max(1, len(features_map))
            if coverage >= 0.7:
                reliability_score += 0.2
            if odds_probs:
                reliability_score += 0.2
            if ml_1x2_prob:
                reliability_score += 0.2
                # accordo ML/Poisson
                delta_ml = abs(ml_1x2_prob[0] - prob_1_xg) + abs(ml_1x2_prob[1] - prob_x_xg) + abs(ml_1x2_prob[2] - prob_2_xg)
                if delta_ml < 0.6:
                    reliability_score += 0.1
                if x2_cov >= 0.6:
                    reliability_score += 0.05
            if ml_ou_prob:
                reliability_score += 0.1
                if ou_cov >= 0.6:
                    reliability_score += 0.05

            if reliability_score >= 0.8:
                reliability = "high"
            elif reliability_score >= 0.55:
                reliability = "medium"
            else:
                reliability = "low"
            
            # ==========================================
            # NUOVE LOGICHE: Data Quality & Consensus
            # ==========================================
            
            # 1. Data Quality Score
            data_quality_score = 0
            if info_level == "high":
                data_quality_score = 100
            elif info_level == "medium":
                data_quality_score = 75
            else:
                data_quality_score = 40
            
            if not feature_obj:
                data_quality_score = 30
            
            data_quality_label = "Low"
            if data_quality_score >= 85: 
                data_quality_label = "High"
            elif data_quality_score >= 60:
                data_quality_label = "Medium"

            # 2. BTTS (Goal / NoGoal) Calculation from Poisson
            p_goal_home = 1 - math.exp(-lam_home)
            p_goal_away = 1 - math.exp(-lam_away)
            prob_btts_yes = p_goal_home * p_goal_away
            prob_btts_no = 1 - prob_btts_yes
            
            btts_pred = "GOAL" if prob_btts_yes >= 0.55 else "NOGOAL"
            
            # 3. Multigol Calculation
            p_goals_exact = {}
            for g in range(9): # 0-8 goals
                p_g = 0.0
                for h in range(g + 1):
                    a = g - h
                    p_g += _poisson_prob(lam_home, h) * _poisson_prob(lam_away, a)
                p_goals_exact[g] = p_g
            
            prob_mg_1_3 = sum(p_goals_exact.get(g, 0) for g in range(1, 4))
            prob_mg_2_4 = sum(p_goals_exact.get(g, 0) for g in range(2, 5))
            
            # 4. Combo Bets Calculation - Ricalcolo preciso da matrice Poisson
            p_1_over15 = 0.0
            p_1x_over15 = 0.0
            p_x2_under35 = 0.0
            
            for h in range(9):
                ph = _poisson_prob(lam_home, h)
                for a in range(9):
                    pa = _poisson_prob(lam_away, a)
                    p_joint = ph * pa
                    tot = h + a
                    
                    # 1 + Over 1.5
                    if h > a and tot > 1.5:
                        p_1_over15 += p_joint
                    
                    # 1X + Over 1.5
                    if h >= a and tot > 1.5:
                        p_1x_over15 += p_joint
                        
                    # X2 + Under 3.5
                    if a >= h and tot < 3.5:
                        p_x2_under35 += p_joint

            # 5. Consensus Score
            consensus_points = 0
            consensus_max = 0
            
            # Check 1X2 direction
            poisson_pick = "1" if prob_1_xg > prob_x_xg and prob_1_xg > prob_2_xg else ("2" if prob_2_xg > prob_1_xg and prob_2_xg > prob_x_xg else "X")
            
            if ml_1x2_prob:
                ml_pick = "1" if ml_1x2_prob[0] > ml_1x2_prob[1] and ml_1x2_prob[0] > ml_1x2_prob[2] else ("2" if ml_1x2_prob[2] > ml_1x2_prob[0] and ml_1x2_prob[2] > ml_1x2_prob[1] else "X")
                if ml_pick == poisson_pick:
                    consensus_points += 30
                consensus_max += 30
            
            if odds_probs:
                odds_pick = "1" if odds_probs[0] > odds_probs[1] and odds_probs[0] > odds_probs[2] else ("2" if odds_probs[2] > odds_probs[0] and odds_probs[2] > odds_probs[1] else "X")
                if odds_pick == poisson_pick:
                    consensus_points += 20
                consensus_max += 20
                
            if ml_ou_prob:
                ml_ou = "Over" if ml_ou_prob[1] > 0.5 else "Under"
                poisson_ou = "Over" if p_over25 > 0.5 else "Under"
                if ml_ou == poisson_ou:
                    consensus_points += 20
                consensus_max += 20
            
            if confidence == "ALTA":
                consensus_points += 10
            consensus_max += 10

            consensus_score = int((consensus_points / consensus_max) * 100) if consensus_max > 0 else 50
            
            # Top 3 Correct Scores
            scores_with_prob = []
            for h in range(7):
                for a in range(7):
                    p = _poisson_prob(lam_home, h) * _poisson_prob(lam_away, a)
                    scores_with_prob.append((f"{h}-{a}", p))
            scores_with_prob.sort(key=lambda x: x[1], reverse=True)
            top_3_scores = [f"{s[0]} ({s[1]*100:.1f}%)" for s in scores_with_prob[:3]]

            prediction = {
                'match_id': mid,
                'date': fixture.date.isoformat() if fixture.date else '',
                'time': fixture.time_local or '-',
                'league': fixture.league_code,
                'home': fixture.home,
                'away': fixture.away,
                'xg_home': round(xg_for_home, 2),
                'xga_home': round(xg_against_home, 2),
                'xg_away': round(xg_for_away, 2),
                'xga_away': round(xg_against_away, 2),
                'odds_1': round(odds_1, 2) if odds_1 else '-',
                'odds_x': round(odds_x, 2) if odds_x else '-',
                'odds_2': round(odds_2, 2) if odds_2 else '-',
                'prob_1_xg': round(prob_1_xg * 100, 1),
                'prob_x_xg': round(prob_x_xg * 100, 1),
                'prob_2_xg': round(prob_2_xg * 100, 1),
                'prob_1_odds': round(prob_1_odds * 100, 1) if prob_1_odds else '-',
                'prob_x_odds': round(prob_x_odds * 100, 1) if prob_x_odds else '-',
                'prob_2_odds': round(prob_2_odds * 100, 1) if prob_2_odds else '-',
                'pick': best_pick or '-',
                'confidence': confidence,
                'confidence_pct': confidence_pct,
                'value': round(best_value, 3),
                'ou_pred': ou_pred,
                'total_xg': round(total_xg, 2),
                'top_score': top_score,
                'ml_prob_ou_over': round(ml_ou_prob[1] * 100, 1) if ml_ou_prob else '-',
                'ml_prob_1': round(ml_1x2_prob[0] * 100, 1) if ml_1x2_prob else '-',
                'ml_prob_x': round(ml_1x2_prob[1] * 100, 1) if ml_1x2_prob else '-',
                'ml_prob_2': round(ml_1x2_prob[2] * 100, 1) if ml_1x2_prob else '-',
                'data_reliability': reliability,
                # New Fields
                'data_quality': data_quality_label,
                'consensus_score': consensus_score,
                'btts_pred': btts_pred,
                'prob_btts_yes': round(prob_btts_yes * 100, 1),
                'prob_mg_1_3': round(prob_mg_1_3 * 100, 1),
                'prob_mg_2_4': round(prob_mg_2_4 * 100, 1),
                'prob_1x_over15': round(p_1x_over15 * 100, 1),
                'prob_x2_under35': round(p_x2_under35 * 100, 1),
                'prob_1_over15': round(p_1_over15 * 100, 1),
                'top_3_correct_scores': " | ".join(top_3_scores)
            }
            
            # ==========================================
            # PERSISTENCE: Save to Database
            # ==========================================
            try:
                # Upsert prediction
                pred_obj = db.query(Prediction).filter(
                    Prediction.match_id == fixture.match_id,
                    Prediction.prediction_date == datetime.now().date()
                ).first()
                
                if not pred_obj:
                    pred_obj = Prediction(
                        match_id=fixture.match_id,
                        prediction_date=datetime.now().date()
                    )
                
                pred_obj.pick_1x2 = best_pick
                pred_obj.confidence_1x2 = confidence
                pred_obj.prob_1 = float(prob_1_xg)
                pred_obj.prob_x = float(prob_x_xg)
                pred_obj.prob_2 = float(prob_2_xg)
                
                pred_obj.pick_ou = ou_pred
                pred_obj.prob_over = float(p_over25)
                pred_obj.prob_under = float(1 - p_over25)
                
                pred_obj.pick_btts = btts_pred
                pred_obj.prob_btts_yes = float(prob_btts_yes)
                
                pred_obj.data_quality = data_quality_label
                pred_obj.consensus_score = int(consensus_score)
                
                pred_obj.prob_mg_1_3 = float(prob_mg_1_3)
                pred_obj.prob_mg_2_4 = float(prob_mg_2_4)
                pred_obj.prob_combo_1_over = float(p_1_over15)
                pred_obj.prob_combo_1x_over = float(p_1x_over15)
                
                # Save neural reasoning data
                pred_obj.neural_reasoning = neural_reasoning_summary
                pred_obj.neural_adjustments = neural_adjustments
                
                db.add(pred_obj)
                db.commit()
            except Exception as e:
                print(f"Error saving prediction for {fixture.match_id}: {e}")
                db.rollback()

            predictions.append(prediction)
        
        return predictions
    
    finally:
        db.close()


if __name__ == "__main__":
    import json
    
    # Parse --date argument
    date = None
    if len(sys.argv) > 1:
        if '--date' in sys.argv:
            idx = sys.argv.index('--date')
            if idx + 1 < len(sys.argv):
                date = sys.argv[idx + 1]
        else:
            date = sys.argv[1]
    
    preds = generate_predictions(date)
    
    # Mostra in terminal
    if preds:
        print(f"\n{'='*120}")
        print(f"PREVISIONI - {preds[0]['date']}")
        print(f"{'='*120}\n")
        
        for p in preds:
            print(f"[{p['league']}] {p['home']} vs {p['away']}")
            print(f"  xG: {p['xg_home']:.1f}-{p['xg_away']:.1f} | xGA: {p['xga_home']:.1f}-{p['xga_away']:.1f}")
            print(f"  Prob xG: {p['prob_1_xg']}% - {p['prob_x_xg']}% - {p['prob_2_xg']}%")
            if p['prob_1_odds'] != '-':
                print(f"  Prob Odds: {p['prob_1_odds']}% - {p['prob_x_odds']}% - {p['prob_2_odds']}%")
                print(f"  Odds: {p['odds_1']} - {p['odds_x']} - {p['odds_2']}")
            print(f"  🎯 PICK: {p['pick']} ({p['confidence']} - {p['confidence_pct']}%)")
            print(f"  O/U: {p['ou_pred']} (tot xG: {p['total_xg']})")
            print(f"  BTTS: {p['btts_pred']} ({p['prob_btts_yes']}%)")
            print(f"  DATA QUALITY: {p['data_quality']} | CONSENSUS: {p['consensus_score']}/100")
            print(f"  MULTIGOL: 1-3 ({p['prob_mg_1_3']}%) | 2-4 ({p['prob_mg_2_4']}%)")
            print(f"  COMBO: 1+Over1.5 ({p['prob_1_over15']}%) | 1X+Over1.5 ({p['prob_1x_over15']}%)")
            print(f"  TOP SCORES: {p['top_3_correct_scores']}")
            print()
    else:
        print(f"Nessuna partita trovata per {date or 'oggi'}")
