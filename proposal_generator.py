#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
proposal_generator.py
Genera proposta calcolata: risultato più probabile per ogni partita
"""

import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from database import SessionLocal
from models import Fixture, Odds, Feature
from predictions_generator import (
    expected_goals_to_prob,
    _get_fallback_profile,
    _is_strong_team,
    _normalize_odds_probs,
)

def _poisson_prob(lam: float, k: int) -> float:
    if lam <= 0 or k < 0:
        return 0.0
    try:
        return (math.exp(-lam) * (lam ** k)) / math.factorial(k)
    except Exception:
        return 0.0


def _top_results(lh: float, la: float, top_n: int = 3) -> List[Tuple[str, float]]:
    """Top-N score da Poisson contestualizzato."""
    results = []
    best_draw = None
    best_non_draw = None
    for hg in range(0, 8):
        ph = _poisson_prob(lh, hg)
        for ag in range(0, 8):
            pa = _poisson_prob(la, ag)
            prob = ph * pa
            results.append((f"{hg}-{ag}", prob))
            if hg == ag:
                if best_draw is None or prob > best_draw[1]:
                    best_draw = (f"{hg}-{ag}", prob)
            else:
                if best_non_draw is None or prob > best_non_draw[1]:
                    best_non_draw = (f"{hg}-{ag}", prob)
    results.sort(key=lambda x: x[1], reverse=True)

    # MIGLIORAMENTO: Rendo la logica di sostituzione del pareggio più conservativa.
    # Sostituisco il pareggio solo se è il risultato più probabile E un altro risultato
    # (non pareggio) ha una probabilità quasi identica. Questo evita di scartare
    # pareggi legittimamente probabili, aumentando la coerenza delle previsioni.
    if results and best_draw and best_non_draw and results[0] == best_draw:
        if (best_draw[1] - best_non_draw[1]) < 0.01: # Soglia molto piccola
            # BUGFIX: La logica precedente eliminava il pareggio e duplicava il non-pareggio.
            # La logica corretta è scambiare le loro posizioni nella lista.
            try:
                idx_non_draw = results.index(best_non_draw)
                results[0], results[idx_non_draw] = results[idx_non_draw], results[0]
            except ValueError:
                pass # Salvaguardia nel caso in cui best_non_draw non sia nella lista

    unique = []
    seen = set()
    for r in results:
        if r[0] in seen:
            continue
        seen.add(r[0])
        unique.append(r)

    return unique[:top_n]


def generate_proposals(date_str: Optional[str] = None) -> List[Dict]:
    """
    Genera proposta calcolata per ogni partita.
    
    Args:
        date_str: Data in formato YYYY-MM-DD. Se None, usa oggi.
    
    Returns:
        Lista di dict con proposte
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    try:
        target_date = datetime.fromisoformat(str(date_str)[:10]).date()
    except Exception:
        target_date = None
    
    db = SessionLocal()
    
    try:
        if target_date:
            fixtures = db.query(Fixture).filter(Fixture.date == target_date).all()
        else:
            fixtures = db.query(Fixture).filter(Fixture.date == date_str).all()
        
        proposals = []
        
        for fixture in fixtures:
            mid = fixture.match_id
            
            odds_obj = db.query(Odds).filter(Odds.match_id == mid).first()
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
            
            odds_1 = float(odds_obj.odds_1) if odds_obj and odds_obj.odds_1 else None
            odds_x = float(odds_obj.odds_x) if odds_obj and odds_obj.odds_x else None
            odds_2 = float(odds_obj.odds_2) if odds_obj and odds_obj.odds_2 else None
            odds_ou_over = float(odds_obj.odds_ou25_over) if odds_obj and odds_obj.odds_ou25_over else None
            odds_ou_under = float(odds_obj.odds_ou25_under) if odds_obj and odds_obj.odds_ou25_under else None
            odds_probs = _normalize_odds_probs(odds_1, odds_x, odds_2)
            info_level = "low" if not feature_obj else "medium"
            if feature_obj and feature_obj.xg_confidence is not None:
                if feature_obj.xg_confidence >= 75:
                    info_level = "high"
                elif feature_obj.xg_confidence < 50:
                    info_level = "low"
            elif (feature_obj and feature_obj.xg_source_home == "fallback") or (feature_obj and feature_obj.xg_source_away == "fallback"):
                info_level = "low"
            elif (feature_obj and feature_obj.xg_source_home == "understat") or (feature_obj and feature_obj.xg_source_away == "understat"):
                info_level = "high"
            
            # Calcola probabilità contestualizzate (come predictions_xg) per evitare risultati piatti 1-1
            (
                p1,
                px,
                p2,
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

            top_results = _top_results(lam_home, lam_away, top_n=3)
            top_results_str = " | ".join([f"{r[0]} ({r[1]*100:.1f}%)" for r in top_results])
            top_results_list = [{"score": r[0], "pct": round(r[1]*100, 1)} for r in top_results]
            top3_confidence = round(sum(r[1] for r in top_results) * 100, 1)
            if top_results:
                most_prob_result, result_prob = top_results[0][0], top_results[0][1]
            else:
                most_prob_result, result_prob = "0-0", 0.0
            
            # Calcola risultato effettivo se disponibile
            actual_result = None
            actual_prob = 0.0
            if fixture.result_home_goals is not None and fixture.result_away_goals is not None:
                actual_result = f"{fixture.result_home_goals}-{fixture.result_away_goals}"
                # Calcola probabilità del risultato effettivo con lambda contestualizzati
                actual_prob = _poisson_prob(lam_home, fixture.result_home_goals) * _poisson_prob(lam_away, fixture.result_away_goals)
            
            # Determina esito previsione
            prediction_correct = False
            if actual_result and most_prob_result == actual_result:
                prediction_correct = True
            
            # Calcola affidabilità basata su xg_confidence numerico
            xg_confidence_val = None
            if feature_obj and feature_obj.xg_confidence is not None:
                xg_confidence_val = float(feature_obj.xg_confidence)
            
            # Determina livello affidabilità con soglie numeriche
            if xg_confidence_val is not None:
                if xg_confidence_val >= 75:
                    reliability = 'high'
                elif xg_confidence_val >= 50:
                    reliability = 'medium'
                else:
                    reliability = 'low'
            elif feature_obj:
                # Fallback basato su sorgente se xg_confidence non è disponibile
                if feature_obj.xg_source_home == 'understat' or feature_obj.xg_source_away == 'understat':
                    reliability = 'high'
                elif feature_obj.xg_source_home == 'odds' or feature_obj.xg_source_away == 'odds':
                    reliability = 'medium'
                else:
                    reliability = 'low'
            else:
                reliability = 'low'
            
            proposal = {
                'match_id': mid,
                'date': fixture.date.isoformat() if fixture.date else '',
                'time': fixture.time_local or '-',
                'league': fixture.league_code,
                'home': fixture.home,
                'away': fixture.away,
                'xg_for': round(xg_for_home, 2),
                'xga_for': round(xg_against_home, 2),
                'most_prob_result': most_prob_result,
                'most_prob_pct': round(result_prob * 100, 1),
                'top_results': top_results_str,
                'top_results_list': top_results_list,
                'top3_confidence': top3_confidence,
                'p1': round(p1, 3),
                'px': round(px, 3),
                'p2': round(p2, 3),
                'p_over25': round(p_over25, 3),
                'lambda_home': round(lam_home, 3),
                'lambda_away': round(lam_away, 3),
                # Provenienza dati xG (popolata da features_populator)
                'xg_source_home': feature_obj.xg_source_home if feature_obj else None,
                'xg_source_away': feature_obj.xg_source_away if feature_obj else None,
                # Confidenza numerica (0-90)
                'xg_confidence': xg_confidence_val,
                # Livello di affidabilità (high/medium/low)
                'data_reliability': reliability,
                'odds_1': round(odds_1, 2) if odds_1 else '-',
                'odds_x': round(odds_x, 2) if odds_x else '-',
                'odds_2': round(odds_2, 2) if odds_2 else '-',
                'actual_result': actual_result,
                'actual_prob': round(actual_prob * 100, 1) if actual_result else '-',
                'prediction_correct': prediction_correct,
                'is_finished': actual_result is not None,
            }
            
            proposals.append(proposal)
        
        return proposals
    
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    
    date = sys.argv[1] if len(sys.argv) > 1 else None
    
    props = generate_proposals(date)
    
    if props:
        print(f"\n{'='*100}")
        print(f"PROPOSTA CALCOLATA - {props[0]['date']}")
        print(f"{'='*100}\n")
        
        for p in props:
            print(f"[{p['league']}] {p['home']} vs {p['away']}")
            print(f"  xG: {p['xg_for']:.1f} | xGA: {p['xga_for']:.1f}")
            print(f"  Risultato più probabile: {p['most_prob_result']} ({p['most_prob_pct']}%)")
            print(f"  Top 3 risultati: {p['top_results']}")
            if p['is_finished']:
                print(f"  Risultato effettivo: {p['actual_result']} ({p['actual_prob']}%)")
                if p['prediction_correct']:
                    print(f"  ✅ PREDIZIONE CORRETTA")
                else:
                    print(f"  ❌ Previsione sbagliata")
            print()
    else:
        print(f"Nessuna partita trovata per {date or 'oggi'}")
