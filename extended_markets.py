#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extended_markets.py

Calcola mercati estesi per aumentare le opportunità di scommessa:
- Doppia Chance (1X, X2, 12)
- Multigol (1-2, 1-3, 2-3, 2-4, 2-5, 3-4, 3-5, etc.)
- Goal/No Goal (GG/NG)
- Over/Under altre linee (1.5, 3.5, 4.5)
- Combo markets (DC + GG, DC + OU, etc.)
"""

import math
from typing import Dict, List, Tuple, Optional
import numpy as np


def poisson_prob(lam: float, k: int) -> float:
    """Probabilità Poisson di k goal con media lambda."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (math.exp(-lam) * (lam ** k)) / math.factorial(k)


def calculate_score_matrix(lambda_home: float, lambda_away: float, max_goals: int = 8) -> np.ndarray:
    """
    Calcola matrice di probabilità per ogni possibile score.
    Returns: matrix[home_goals][away_goals] = probability
    """
    matrix = np.zeros((max_goals + 1, max_goals + 1))
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            matrix[h][a] = poisson_prob(lambda_home, h) * poisson_prob(lambda_away, a)
    return matrix


def calculate_extended_markets(
    lambda_home: float,
    lambda_away: float,
    p1_ml: Optional[float] = None,
    px_ml: Optional[float] = None,
    p2_ml: Optional[float] = None,
    max_goals: int = 8
) -> Dict[str, float]:
    """
    Calcola tutti i mercati estesi.

    Args:
        lambda_home: Expected goals home (Poisson lambda)
        lambda_away: Expected goals away (Poisson lambda)
        p1_ml: Probabilità ML Home Win (opzionale, altrimenti usa Poisson)
        px_ml: Probabilità ML Draw (opzionale)
        p2_ml: Probabilità ML Away Win (opzionale)
        max_goals: Massimo numero di gol da considerare

    Returns:
        Dict con tutte le probabilità dei mercati
    """
    # Score matrix
    score_matrix = calculate_score_matrix(lambda_home, lambda_away, max_goals)

    # Basic 1X2 from Poisson
    p1_poisson = p2_poisson = px_poisson = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            prob = score_matrix[h][a]
            if h > a:
                p1_poisson += prob
            elif h == a:
                px_poisson += prob
            else:
                p2_poisson += prob

    # Normalize
    total = p1_poisson + px_poisson + p2_poisson
    if total > 0:
        p1_poisson /= total
        px_poisson /= total
        p2_poisson /= total

    # Use ML probabilities if available, otherwise Poisson
    p1 = p1_ml if p1_ml is not None else p1_poisson
    px = px_ml if px_ml is not None else px_poisson
    p2 = p2_ml if p2_ml is not None else p2_poisson

    markets = {}

    # ========== DOPPIA CHANCE (DC) ==========
    markets['dc_1x'] = p1 + px  # Home or Draw
    markets['dc_12'] = p1 + p2  # Home or Away (No Draw)
    markets['dc_x2'] = px + p2  # Draw or Away

    # ========== GOAL / NO GOAL (GG/NG) ==========
    # GG = entrambe segnano almeno 1 gol
    # NG = almeno una squadra non segna
    p_home_scores = 1 - poisson_prob(lambda_home, 0)
    p_away_scores = 1 - poisson_prob(lambda_away, 0)

    markets['gg'] = p_home_scores * p_away_scores  # Both score
    markets['ng'] = 1 - markets['gg']  # At least one doesn't score

    # ========== OVER / UNDER ALTRE LINEE ==========
    # SOLO linee utili: 1.5, 2.5, 3.5 (elimino 0.5, 4.5, 5.5 troppo ovvie)
    for line in [1.5, 2.5, 3.5]:
        over_prob = 0.0
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                if h + a > line:
                    over_prob += score_matrix[h][a]

        markets[f'over_{line}'] = over_prob
        markets[f'under_{line}'] = 1 - over_prob

    # ========== MULTIGOL ==========
    # Multigol indica il totale di gol nella partita
    # Es: MG_1-2 = tra 1 e 2 gol totali, MG_2-3 = tra 2 e 3 gol, etc.

    multigol_ranges = [
        ('0-1', 0, 1),
        ('1-2', 1, 2),
        ('1-3', 1, 3),
        ('2-3', 2, 3),
        ('2-4', 2, 4),
        ('2-5', 2, 5),
        ('3-4', 3, 4),
        ('3-5', 3, 5),
        ('3-6', 3, 6),
        ('4-5', 4, 5),
        ('4-6', 4, 6),
        ('5-6', 5, 6),
    ]

    for label, min_goals, max_goals_range in multigol_ranges:
        prob = 0.0
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                total_goals = h + a
                if min_goals <= total_goals <= max_goals_range:
                    prob += score_matrix[h][a]
        markets[f'mg_{label}'] = prob

    # ========== COMBO MARKETS ==========
    # SOLO combo essenziali: DC + GG/NG
    markets['combo_1x_gg'] = markets['dc_1x'] * markets['gg']
    markets['combo_1x_ng'] = markets['dc_1x'] * markets['ng']
    markets['combo_12_gg'] = markets['dc_12'] * markets['gg']
    markets['combo_12_ng'] = markets['dc_12'] * markets['ng']
    markets['combo_x2_gg'] = markets['dc_x2'] * markets['gg']
    markets['combo_x2_ng'] = markets['dc_x2'] * markets['ng']

    return markets


def find_best_bets(
    markets: Dict[str, float],
    odds_map: Optional[Dict[str, float]] = None,
    min_probability: float = 0.50,
    min_value: float = 0.00,  # CAMBIATO: più permissivo
    kelly_fraction: float = 0.25,
    diversify: bool = True  # NUOVO: forza diversificazione
) -> List[Dict]:
    """
    Trova le migliori scommesse basate su probabilità e value.

    Args:
        markets: Dict con probabilità di tutti i mercati
        odds_map: Dict con quote disponibili (opzionale)
        min_probability: Probabilità minima per considerare una scommessa
        min_value: Value minimo (expected value - 1) per scommettere
        kelly_fraction: Frazione del Kelly criterion da usare
        diversify: Se True, garantisce diversificazione tra categorie

    Returns:
        Lista di dict con le migliori scommesse ordinate per value
    """
    best_bets = []

    # Market categories per ordinamento
    market_categories = {
        'dc_': 'Doppia Chance',
        'gg': 'Goal/No Goal',
        'ng': 'Goal/No Goal',
        'over_': 'Over/Under',
        'under_': 'Over/Under',
        'mg_': 'Multigol',
        'combo_': 'Combo',
        'exact_goals_': 'Exact Goals',
        'home_over_': 'Team Totals',
        'home_under_': 'Team Totals',
        'away_over_': 'Team Totals',
        'away_under_': 'Team Totals',
        'home_win_by_': 'Winning Margin',
        'away_win_by_': 'Winning Margin',
    }

    for market_key, prob in markets.items():
        # Skip se probabilità troppo bassa
        if prob < min_probability:
            continue

        # Determina categoria
        category = 'Other'
        for prefix, cat_name in market_categories.items():
            if market_key.startswith(prefix):
                category = cat_name
                break

        # Calcola value se abbiamo le quote
        value = None
        kelly = 0.0
        odds = None

        if odds_map and market_key in odds_map:
            odds = odds_map[market_key]
            if odds and odds > 1.01:
                implied_prob = 1 / odds
                value = (prob * odds) - 1  # Expected value - 1

                # Kelly criterion: f = (bp - q) / b
                # dove b = odds - 1, p = prob, q = 1 - prob
                if value > 0:
                    b = odds - 1
                    kelly = ((b * prob) - (1 - prob)) / b
                    kelly = max(0, kelly) * kelly_fraction  # Fractional Kelly

        # Se non abbiamo quote, consideriamo probabilità
        if value is None:
            # CAMBIATO: più permissivo per diversificare
            value = prob - min_probability  # Value basato sulla probabilità

        # Skip se value troppo basso SOLO se non stiamo diversificando
        if not diversify and value < min_value:
            continue

        bet = {
            'market': market_key,
            'category': category,
            'probability': prob,
            'odds': odds,
            'value': value,
            'kelly': kelly,
            'confidence': 'high' if prob >= 0.70 else 'medium' if prob >= 0.60 else 'low'
        }

        best_bets.append(bet)

    # Se diversificazione attiva, bilancia tra categorie
    if diversify:
        from collections import defaultdict

        # Organizza per categoria
        by_category = defaultdict(list)
        for bet in best_bets:
            by_category[bet['category']].append(bet)

        # Ordina ogni categoria per value
        for cat in by_category:
            by_category[cat].sort(key=lambda x: x['value'], reverse=True)

        # Prendi top N da ogni categoria in modo bilanciato
        balanced_bets = []
        categories = list(by_category.keys())
        max_rounds = 10  # Max 10 iterazioni per categoria

        for round_num in range(max_rounds):
            for cat in categories:
                if round_num < len(by_category[cat]):
                    balanced_bets.append(by_category[cat][round_num])

        return balanced_bets
    else:
        # Ordina per value decrescente
        best_bets.sort(key=lambda x: x['value'], reverse=True)
        return best_bets


def format_market_name(market_key: str) -> str:
    """Formatta il nome del mercato in modo leggibile."""
    # Doppia Chance
    if market_key == 'dc_1x':
        return '1X (Home or Draw)'
    elif market_key == 'dc_12':
        return '12 (Home or Away)'
    elif market_key == 'dc_x2':
        return 'X2 (Draw or Away)'

    # Goal/No Goal
    elif market_key == 'gg':
        return 'Goal/Goal (Both Score)'
    elif market_key == 'ng':
        return 'No Goal (At least one clean sheet)'

    # Over/Under
    elif market_key.startswith('over_'):
        line = market_key.split('_')[1]
        return f'Over {line} goals'
    elif market_key.startswith('under_'):
        line = market_key.split('_')[1]
        return f'Under {line} goals'

    # Multigol
    elif market_key.startswith('mg_'):
        goals_range = market_key.replace('mg_', '')
        return f'Multigol {goals_range} goals'

    # Combo
    elif market_key.startswith('combo_'):
        combo = market_key.replace('combo_', '')
        return f'Combo: {combo.upper()}'

    return market_key


if __name__ == "__main__":
    # Test con esempio
    print("Testing Extended Markets Calculator\n")

    # Esempio: Match con lambda_home=1.6, lambda_away=1.2
    lambda_h = 1.6
    lambda_a = 1.2

    markets = calculate_extended_markets(lambda_h, lambda_a)

    # Trova best bets (senza quote, solo su probabilità)
    bets = find_best_bets(markets, min_probability=0.55, min_value=0.0)

    print(f"Match simulation: λ_home={lambda_h}, λ_away={lambda_a}")
    print("="*80)
    print(f"\nTop {min(10, len(bets))} Best Bets:\n")

    for i, bet in enumerate(bets[:10], 1):
        market_name = format_market_name(bet['market'])
        print(f"{i}. {market_name}")
        print(f"   Probability: {bet['probability']:.1%} | Confidence: {bet['confidence']}")
        if bet['odds']:
            print(f"   Odds: {bet['odds']:.2f} | Value: {bet['value']:.2%} | Kelly: {bet['kelly']:.2%}")
        print()
