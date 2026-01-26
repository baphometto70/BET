#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
advanced_features.py

Modulo per calcolare feature avanzate che migliorano predizioni ML:
1. Recent Form (ultimi 5 match)
2. Head-to-Head (ultimi 5 scontri diretti)
3. League Standings (posizione classifica, pressione)
4. Momentum Indicators (streaks, trend xG)
5. Home/Away Split (performance casa vs trasferta)

Basato su analisi sistemi professionali (FiveThirtyEight, BetClan, etc.)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from models import Fixture, Feature


class AdvancedFeatureCalculator:
    """Calcola feature avanzate per migliorare predizioni ML."""

    def __init__(self, db_session: Session):
        self.db = db_session

    def get_recent_form(
        self,
        team: str,
        league: str,
        before_date: datetime.date,
        n_matches: int = 5
    ) -> Dict[str, float]:
        """
        Calcola forma recente di una squadra (ultimi N match).

        Returns:
            {
                'form_xg_for': float,      # Media xG segnati ultimi N
                'form_xg_against': float,  # Media xG subiti ultimi N
                'form_xg_diff': float,     # Differenza xG
                'form_wins': int,          # Vittorie ultimi N
                'form_draws': int,         # Pareggi ultimi N
                'form_losses': int,        # Sconfitte ultimi N
                'form_goals_for': float,   # Media gol segnati
                'form_goals_against': float, # Media gol subiti
                'form_points': int,        # Punti ultimi N (3*W + 1*D)
                'form_trend': float        # Trend xG (recente vs precedente)
            }
        """
        # Query ultimi N match della squadra nella stessa lega
        recent_matches = (
            self.db.query(Fixture, Feature)
            .join(Feature, Fixture.match_id == Feature.match_id)
            .filter(
                Fixture.league == league,
                Fixture.date < before_date,
                ((Fixture.home == team) | (Fixture.away == team))
            )
            .order_by(Fixture.date.desc())
            .limit(n_matches)
            .all()
        )

        if len(recent_matches) < 2:
            # Dati insufficienti, return defaults
            return {
                'form_xg_for': 1.3,
                'form_xg_against': 1.3,
                'form_xg_diff': 0.0,
                'form_wins': 0,
                'form_draws': 0,
                'form_losses': 0,
                'form_goals_for': 1.0,
                'form_goals_against': 1.0,
                'form_points': 0,
                'form_trend': 0.0
            }

        xg_for_list = []
        xg_against_list = []
        goals_for_list = []
        goals_against_list = []
        wins = 0
        draws = 0
        losses = 0

        for fixture, feature in recent_matches:
            is_home = (fixture.home == team)

            # xG
            if is_home:
                xg_for = feature.xg_for_home or 1.3
                xg_against = feature.xg_for_away or 1.3
            else:
                xg_for = feature.xg_for_away or 1.3
                xg_against = feature.xg_for_home or 1.3

            xg_for_list.append(xg_for)
            xg_against_list.append(xg_against)

            # Risultati effettivi (se disponibili)
            if fixture.result_home_goals is not None and fixture.result_away_goals is not None:
                if is_home:
                    gf = fixture.result_home_goals
                    ga = fixture.result_away_goals
                else:
                    gf = fixture.result_away_goals
                    ga = fixture.result_home_goals

                goals_for_list.append(gf)
                goals_against_list.append(ga)

                if gf > ga:
                    wins += 1
                elif gf == ga:
                    draws += 1
                else:
                    losses += 1

        # Calcola medie
        avg_xg_for = np.mean(xg_for_list)
        avg_xg_against = np.mean(xg_against_list)
        avg_goals_for = np.mean(goals_for_list) if goals_for_list else avg_xg_for
        avg_goals_against = np.mean(goals_against_list) if goals_against_list else avg_xg_against

        # Trend: differenza xG ultimi 2 vs precedenti 3
        if len(xg_for_list) >= 5:
            recent_2_xg = np.mean(xg_for_list[:2]) - np.mean(xg_against_list[:2])
            previous_3_xg = np.mean(xg_for_list[2:5]) - np.mean(xg_against_list[2:5])
            trend = recent_2_xg - previous_3_xg
        else:
            trend = 0.0

        return {
            'form_xg_for': round(avg_xg_for, 2),
            'form_xg_against': round(avg_xg_against, 2),
            'form_xg_diff': round(avg_xg_for - avg_xg_against, 2),
            'form_wins': wins,
            'form_draws': draws,
            'form_losses': losses,
            'form_goals_for': round(avg_goals_for, 2),
            'form_goals_against': round(avg_goals_against, 2),
            'form_points': wins * 3 + draws,
            'form_trend': round(trend, 2)
        }

    def get_head_to_head(
        self,
        home_team: str,
        away_team: str,
        league: str,
        before_date: datetime.date,
        n_matches: int = 5
    ) -> Dict[str, float]:
        """
        Calcola statistiche head-to-head tra due squadre.

        Returns:
            {
                'h2h_home_wins': int,       # Vittorie home negli ultimi N H2H
                'h2h_draws': int,           # Pareggi
                'h2h_away_wins': int,       # Vittorie away
                'h2h_home_goals_avg': float, # Media gol home in H2H
                'h2h_away_goals_avg': float, # Media gol away in H2H
                'h2h_home_xg_avg': float,   # Media xG home in H2H
                'h2h_away_xg_avg': float,   # Media xG away in H2H
                'h2h_total_over25': int     # Quanti Over 2.5 negli ultimi N H2H
            }
        """
        # Query ultimi N scontri diretti
        h2h_matches = (
            self.db.query(Fixture, Feature)
            .outerjoin(Feature, Fixture.match_id == Feature.match_id)
            .filter(
                Fixture.league == league,
                Fixture.date < before_date,
                (
                    ((Fixture.home == home_team) & (Fixture.away == away_team)) |
                    ((Fixture.home == away_team) & (Fixture.away == home_team))
                )
            )
            .order_by(Fixture.date.desc())
            .limit(n_matches)
            .all()
        )

        if len(h2h_matches) == 0:
            # Nessun precedente, return neutral
            return {
                'h2h_home_wins': 0,
                'h2h_draws': 0,
                'h2h_away_wins': 0,
                'h2h_home_goals_avg': 1.0,
                'h2h_away_goals_avg': 1.0,
                'h2h_home_xg_avg': 1.3,
                'h2h_away_xg_avg': 1.3,
                'h2h_total_over25': 0
            }

        home_wins = 0
        draws = 0
        away_wins = 0
        home_goals = []
        away_goals = []
        home_xg = []
        away_xg = []
        over25_count = 0

        for fixture, feature in h2h_matches:
            # Determina se home_team era in casa o trasferta in quel match
            was_home = (fixture.home == home_team)

            # xG
            if feature:
                if was_home:
                    home_xg.append(feature.xg_for_home or 1.3)
                    away_xg.append(feature.xg_for_away or 1.3)
                else:
                    home_xg.append(feature.xg_for_away or 1.3)
                    away_xg.append(feature.xg_for_home or 1.3)

            # Risultati
            if fixture.result_home_goals is not None and fixture.result_away_goals is not None:
                if was_home:
                    hg = fixture.result_home_goals
                    ag = fixture.result_away_goals
                else:
                    hg = fixture.result_away_goals
                    ag = fixture.result_home_goals

                home_goals.append(hg)
                away_goals.append(ag)

                if hg > ag:
                    home_wins += 1
                elif hg == ag:
                    draws += 1
                else:
                    away_wins += 1

                if (fixture.result_home_goals + fixture.result_away_goals) > 2.5:
                    over25_count += 1

        return {
            'h2h_home_wins': home_wins,
            'h2h_draws': draws,
            'h2h_away_wins': away_wins,
            'h2h_home_goals_avg': round(np.mean(home_goals), 2) if home_goals else 1.0,
            'h2h_away_goals_avg': round(np.mean(away_goals), 2) if away_goals else 1.0,
            'h2h_home_xg_avg': round(np.mean(home_xg), 2) if home_xg else 1.3,
            'h2h_away_xg_avg': round(np.mean(away_xg), 2) if away_xg else 1.3,
            'h2h_total_over25': over25_count
        }

    def get_league_standings(
        self,
        team: str,
        league: str,
        at_date: datetime.date
    ) -> Dict[str, float]:
        """
        Calcola posizione in classifica e contesto competitivo.

        Returns:
            {
                'position': int,           # Posizione stimata (1-20)
                'points': int,             # Punti stimati
                'goal_difference': int,    # Differenza reti
                'pressure_top': float,     # Pressione lotta alta (0-1)
                'pressure_relegation': float  # Pressione salvezza (0-1)
            }
        """
        # Calcola punti stimati basandosi su risultati
        season_matches = (
            self.db.query(Fixture)
            .filter(
                Fixture.league == league,
                Fixture.date < at_date,
                Fixture.date >= datetime(at_date.year if at_date.month >= 8 else at_date.year - 1, 8, 1).date(),
                ((Fixture.home == team) | (Fixture.away == team)),
                Fixture.result_home_goals.isnot(None)
            )
            .all()
        )

        if len(season_matches) == 0:
            # Inizio stagione, return neutral
            return {
                'position': 10,
                'points': 0,
                'goal_difference': 0,
                'pressure_top': 0.0,
                'pressure_relegation': 0.0
            }

        points = 0
        goals_for = 0
        goals_against = 0

        for match in season_matches:
            is_home = (match.home == team)

            if is_home:
                gf = match.result_home_goals
                ga = match.result_away_goals
            else:
                gf = match.result_away_goals
                ga = match.result_home_goals

            goals_for += gf
            goals_against += ga

            if gf > ga:
                points += 3
            elif gf == ga:
                points += 1

        # Stima posizione (media 1 punto/partita = 10° posto)
        matches_played = len(season_matches)
        if matches_played > 0:
            ppg = points / matches_played
            # ppg 2.5+ -> top 4, ppg 2.0+ -> top 6, ppg 1.0- -> bottom
            if ppg >= 2.3:
                estimated_position = np.random.randint(1, 5)
            elif ppg >= 1.8:
                estimated_position = np.random.randint(4, 8)
            elif ppg >= 1.3:
                estimated_position = np.random.randint(7, 13)
            elif ppg >= 0.8:
                estimated_position = np.random.randint(12, 17)
            else:
                estimated_position = np.random.randint(16, 21)
        else:
            estimated_position = 10

        # Pressione competitiva
        pressure_top = max(0, min(1, (2.5 - (estimated_position / 10)) ** 2))  # Alta se top 5
        pressure_relegation = max(0, min(1, ((estimated_position - 13) / 7) ** 2))  # Alta se bottom 5

        return {
            'position': estimated_position,
            'points': points,
            'goal_difference': goals_for - goals_against,
            'pressure_top': round(pressure_top, 2),
            'pressure_relegation': round(pressure_relegation, 2)
        }

    def get_momentum_indicators(
        self,
        team: str,
        league: str,
        before_date: datetime.date,
        n_recent: int = 10
    ) -> Dict[str, float]:
        """
        Calcola indicatori di momentum (streaks, trend).

        Returns:
            {
                'winning_streak': int,      # Vittorie consecutive
                'unbeaten_streak': int,     # Partite senza sconfitte
                'losing_streak': int,       # Sconfitte consecutive
                'clean_sheet_streak': int,  # Clean sheet consecutivi
                'scoring_streak': int,      # Partite consecutive con gol
                'xg_momentum': float        # Trend xG recente (+/-)
            }
        """
        recent_matches = (
            self.db.query(Fixture, Feature)
            .outerjoin(Feature, Fixture.match_id == Feature.match_id)
            .filter(
                Fixture.league == league,
                Fixture.date < before_date,
                ((Fixture.home == team) | (Fixture.away == team)),
                Fixture.result_home_goals.isnot(None)
            )
            .order_by(Fixture.date.desc())
            .limit(n_recent)
            .all()
        )

        if len(recent_matches) < 3:
            return {
                'winning_streak': 0,
                'unbeaten_streak': 0,
                'losing_streak': 0,
                'clean_sheet_streak': 0,
                'scoring_streak': 0,
                'xg_momentum': 0.0
            }

        winning_streak = 0
        unbeaten_streak = 0
        losing_streak = 0
        clean_sheet_streak = 0
        scoring_streak = 0
        xg_diffs = []

        for fixture, feature in recent_matches:
            is_home = (fixture.home == team)

            # Risultato
            if is_home:
                gf = fixture.result_home_goals
                ga = fixture.result_away_goals
            else:
                gf = fixture.result_away_goals
                ga = fixture.result_home_goals

            # Streaks (solo primi match consecutivi)
            if gf > ga:
                if winning_streak == len([m for m in recent_matches[:recent_matches.index((fixture, feature))]]):
                    winning_streak += 1
                if losing_streak == 0:
                    unbeaten_streak += 1
            elif gf == ga:
                if losing_streak == 0:
                    unbeaten_streak += 1
                winning_streak = 0
            else:
                if losing_streak == len([m for m in recent_matches[:recent_matches.index((fixture, feature))]]):
                    losing_streak += 1
                winning_streak = 0
                unbeaten_streak = 0

            # Clean sheets
            if ga == 0:
                if clean_sheet_streak == len([m for m in recent_matches[:recent_matches.index((fixture, feature))]]):
                    clean_sheet_streak += 1
            else:
                if clean_sheet_streak > 0:
                    break

            # Scoring streak
            if gf > 0:
                scoring_streak += 1
            else:
                break

            # xG trend
            if feature:
                if is_home:
                    xg_diff = (feature.xg_for_home or 1.3) - (feature.xg_for_away or 1.3)
                else:
                    xg_diff = (feature.xg_for_away or 1.3) - (feature.xg_for_home or 1.3)
                xg_diffs.append(xg_diff)

        # xG momentum: recenti 3 vs precedenti 3
        if len(xg_diffs) >= 6:
            xg_momentum = np.mean(xg_diffs[:3]) - np.mean(xg_diffs[3:6])
        else:
            xg_momentum = 0.0

        return {
            'winning_streak': winning_streak,
            'unbeaten_streak': unbeaten_streak,
            'losing_streak': losing_streak,
            'clean_sheet_streak': clean_sheet_streak,
            'scoring_streak': scoring_streak,
            'xg_momentum': round(xg_momentum, 2)
        }

    def calculate_all_advanced_features(
        self,
        match_id: str,
        home_team: str,
        away_team: str,
        league: str,
        match_date: datetime.date
    ) -> Dict[str, float]:
        """
        Calcola TUTTE le feature avanzate per un match.

        Returns dizionario completo con tutte le features.
        """
        # Recent Form
        home_form = self.get_recent_form(home_team, league, match_date, n_matches=5)
        away_form = self.get_recent_form(away_team, league, match_date, n_matches=5)

        # Head-to-Head
        h2h = self.get_head_to_head(home_team, away_team, league, match_date, n_matches=5)

        # League Standings
        home_standings = self.get_league_standings(home_team, league, match_date)
        away_standings = self.get_league_standings(away_team, league, match_date)

        # Momentum
        home_momentum = self.get_momentum_indicators(home_team, league, match_date, n_recent=10)
        away_momentum = self.get_momentum_indicators(away_team, league, match_date, n_recent=10)

        # Combina tutto con prefissi home/away
        features = {}

        for key, val in home_form.items():
            features[f'home_{key}'] = val
        for key, val in away_form.items():
            features[f'away_{key}'] = val

        for key, val in h2h.items():
            features[key] = val

        for key, val in home_standings.items():
            features[f'home_{key}'] = val
        for key, val in away_standings.items():
            features[f'away_{key}'] = val

        for key, val in home_momentum.items():
            features[f'home_{key}'] = val
        for key, val in away_momentum.items():
            features[f'away_{key}'] = val

        # Aggiungi features derivate
        features['position_gap'] = abs(home_standings['position'] - away_standings['position'])
        features['points_gap'] = abs(home_standings['points'] - away_standings['points'])
        features['form_diff'] = home_form['form_xg_diff'] - away_form['form_xg_diff']
        features['momentum_diff'] = home_momentum['xg_momentum'] - away_momentum['xg_momentum']

        return features


if __name__ == "__main__":
    # Test
    from database import SessionLocal

    db = SessionLocal()
    calc = AdvancedFeatureCalculator(db)

    # Test su una partita futura
    test_match = db.query(Fixture).filter(
        Fixture.date >= datetime.now().date()
    ).first()

    if test_match:
        print(f"\n[TEST] Match: {test_match.home} vs {test_match.away}")
        print(f"[TEST] League: {test_match.league}, Date: {test_match.date}\n")

        features = calc.calculate_all_advanced_features(
            test_match.match_id,
            test_match.home,
            test_match.away,
            test_match.league,
            test_match.date
        )

        print("[FEATURES CALCOLATE]")
        for key, val in sorted(features.items()):
            print(f"  {key:30s} = {val}")

    db.close()
