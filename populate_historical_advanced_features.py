#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
populate_historical_advanced_features.py

Popola advanced features per dataset storico CSV (non DB).
Calcola features basandosi solo sui dati già presenti nel CSV.

Strategy:
- Load historical CSV
- For each match, calculate advanced features using rolling windows on CSV data
- Save enhanced CSV with all features
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parent

# Input/Output paths
HIST_OU_PATH = ROOT / "data" / "historical_dataset.csv"
HIST_1X2_PATH = ROOT / "data" / "historical_1x2.csv"
HIST_OU_ENHANCED = ROOT / "data" / "historical_dataset_enhanced.csv"
HIST_1X2_ENHANCED = ROOT / "data" / "historical_1x2_enhanced.csv"


def calculate_team_form(df, team, league, before_date, n_recent=5):
    """
    Calcola forma recente di una squadra usando dati CSV.
    """
    # Filter matches before this date for this team
    team_matches = df[
        (df['date'] < before_date) &
        (df['league'] == league) &
        ((df['home'] == team) | (df['away'] == team))
    ].tail(n_recent)

    if len(team_matches) == 0:
        return {
            'form_xg_for': 1.3,  # Default xG
            'form_xg_against': 1.3,
            'form_xg_diff': 0.0,
            'form_wins': 0,
            'form_draws': 0,
            'form_losses': 0,
            'form_goals_for': 1.0,
            'form_goals_against': 1.0,
            'form_points': 0,
            'form_trend': 0.0,
        }

    # Calculate stats
    xg_for_list = []
    xg_against_list = []
    goals_for_list = []
    goals_against_list = []
    wins = draws = losses = 0
    points = 0

    for _, match in team_matches.iterrows():
        is_home = match['home'] == team

        if is_home:
            xg_for = match.get('xg_for_home', 1.3)
            xg_against = match.get('xg_against_home', 1.3)
            goals_for = match.get('ft_home_goals', 1)
            goals_against = match.get('ft_away_goals', 1)
        else:
            xg_for = match.get('xg_for_away', 1.3)
            xg_against = match.get('xg_against_away', 1.3)
            goals_for = match.get('ft_away_goals', 1)
            goals_against = match.get('ft_home_goals', 1)

        xg_for_list.append(xg_for if pd.notna(xg_for) else 1.3)
        xg_against_list.append(xg_against if pd.notna(xg_against) else 1.3)
        goals_for_list.append(goals_for if pd.notna(goals_for) else 1)
        goals_against_list.append(goals_against if pd.notna(goals_against) else 1)

        # Count result
        if pd.notna(goals_for) and pd.notna(goals_against):
            if goals_for > goals_against:
                wins += 1
                points += 3
            elif goals_for == goals_against:
                draws += 1
                points += 1
            else:
                losses += 1

    # Trend: more weight to recent matches
    if len(xg_for_list) >= 2:
        trend = np.mean(xg_for_list[-2:]) - np.mean(xg_for_list[:2]) if len(xg_for_list) >= 4 else 0.0
    else:
        trend = 0.0

    return {
        'form_xg_for': np.mean(xg_for_list),
        'form_xg_against': np.mean(xg_against_list),
        'form_xg_diff': np.mean(xg_for_list) - np.mean(xg_against_list),
        'form_wins': wins,
        'form_draws': draws,
        'form_losses': losses,
        'form_goals_for': np.mean(goals_for_list),
        'form_goals_against': np.mean(goals_against_list),
        'form_points': points,
        'form_trend': trend,
    }


def calculate_h2h(df, home_team, away_team, league, before_date, n_recent=5):
    """
    Calcola statistiche H2H tra due squadre.
    """
    h2h_matches = df[
        (df['date'] < before_date) &
        (df['league'] == league) &
        (
            ((df['home'] == home_team) & (df['away'] == away_team)) |
            ((df['home'] == away_team) & (df['away'] == home_team))
        )
    ].tail(n_recent)

    if len(h2h_matches) == 0:
        return {
            'h2h_home_wins': 0,
            'h2h_draws': 0,
            'h2h_away_wins': 0,
            'h2h_home_goals_avg': 1.0,
            'h2h_away_goals_avg': 1.0,
            'h2h_home_xg_avg': 1.3,
            'h2h_away_xg_avg': 1.3,
            'h2h_total_over25': 0,
        }

    home_wins = draws = away_wins = 0
    home_goals = []
    away_goals = []
    home_xg = []
    away_xg = []
    over25_count = 0

    for _, match in h2h_matches.iterrows():
        is_regular = match['home'] == home_team  # True if home_team was actually home

        h_goals = match.get('ft_home_goals', 1)
        a_goals = match.get('ft_away_goals', 1)
        h_xg = match.get('xg_for_home', 1.3)
        a_xg = match.get('xg_for_away', 1.3)

        if is_regular:
            home_goals.append(h_goals if pd.notna(h_goals) else 1)
            away_goals.append(a_goals if pd.notna(a_goals) else 1)
            home_xg.append(h_xg if pd.notna(h_xg) else 1.3)
            away_xg.append(a_xg if pd.notna(a_xg) else 1.3)

            if pd.notna(h_goals) and pd.notna(a_goals):
                total_goals = h_goals + a_goals
                if total_goals > 2.5:
                    over25_count += 1

                if h_goals > a_goals:
                    home_wins += 1
                elif h_goals == a_goals:
                    draws += 1
                else:
                    away_wins += 1
        else:
            # Inverted (away_team was home)
            home_goals.append(a_goals if pd.notna(a_goals) else 1)
            away_goals.append(h_goals if pd.notna(h_goals) else 1)
            home_xg.append(a_xg if pd.notna(a_xg) else 1.3)
            away_xg.append(h_xg if pd.notna(h_xg) else 1.3)

            if pd.notna(h_goals) and pd.notna(a_goals):
                total_goals = h_goals + a_goals
                if total_goals > 2.5:
                    over25_count += 1

                if a_goals > h_goals:
                    home_wins += 1
                elif h_goals == a_goals:
                    draws += 1
                else:
                    away_wins += 1

    return {
        'h2h_home_wins': home_wins,
        'h2h_draws': draws,
        'h2h_away_wins': away_wins,
        'h2h_home_goals_avg': np.mean(home_goals),
        'h2h_away_goals_avg': np.mean(away_goals),
        'h2h_home_xg_avg': np.mean(home_xg),
        'h2h_away_xg_avg': np.mean(away_xg),
        'h2h_total_over25': over25_count,
    }


def calculate_standings(df, team, league, at_date):
    """
    Calcola posizione in classifica approssimativa.
    (Semplificato: usa solo goal difference)
    """
    # Get all matches up to this date for this league
    league_matches = df[
        (df['date'] < at_date) &
        (df['league'] == league)
    ]

    # Calculate team stats
    team_matches = league_matches[
        (league_matches['home'] == team) | (league_matches['away'] == team)
    ]

    if len(team_matches) == 0:
        return {
            'position': 10,
            'points': 0,
            'goal_difference': 0,
            'pressure_top': 0.0,
            'pressure_relegation': 0.0,
        }

    points = 0
    gf = 0
    ga = 0

    for _, match in team_matches.iterrows():
        is_home = match['home'] == team
        h_goals = match.get('ft_home_goals', 0)
        a_goals = match.get('ft_away_goals', 0)

        if pd.notna(h_goals) and pd.notna(a_goals):
            if is_home:
                gf += h_goals
                ga += a_goals
                if h_goals > a_goals:
                    points += 3
                elif h_goals == a_goals:
                    points += 1
            else:
                gf += a_goals
                ga += h_goals
                if a_goals > h_goals:
                    points += 3
                elif h_goals == a_goals:
                    points += 1

    gd = gf - ga

    # Approximate position (simplified)
    # In reality would need full standings calculation
    position = 10  # Middle position default

    # Pressure indicators (simplified)
    pressure_top = max(0, (25 - points) / 25) if points < 25 else 0.0
    pressure_relegation = max(0, (15 - points) / 15) if points < 15 else 0.0

    return {
        'position': position,
        'points': points,
        'goal_difference': gd,
        'pressure_top': pressure_top,
        'pressure_relegation': pressure_relegation,
    }


def calculate_momentum(df, team, league, before_date, n_recent=10):
    """
    Calcola momentum e streaks.
    """
    team_matches = df[
        (df['date'] < before_date) &
        (df['league'] == league) &
        ((df['home'] == team) | (df['away'] == team))
    ].tail(n_recent).sort_values('date')

    if len(team_matches) == 0:
        return {
            'winning_streak': 0,
            'unbeaten_streak': 0,
            'losing_streak': 0,
            'clean_sheet_streak': 0,
            'scoring_streak': 0,
            'xg_momentum': 0.0,
        }

    # Calculate streaks from most recent backwards
    win_streak = unbeaten_streak = lose_streak = 0
    clean_sheet_streak = scoring_streak = 0
    xg_diffs = []

    for _, match in team_matches.iloc[::-1].iterrows():  # Reverse to go from most recent
        is_home = match['home'] == team
        h_goals = match.get('ft_home_goals', 0)
        a_goals = match.get('ft_away_goals', 0)

        if pd.notna(h_goals) and pd.notna(a_goals):
            if is_home:
                result_goals_for = h_goals
                result_goals_against = a_goals
                xg_diff = match.get('xg_for_home', 1.3) - match.get('xg_against_home', 1.3)
            else:
                result_goals_for = a_goals
                result_goals_against = h_goals
                xg_diff = match.get('xg_for_away', 1.3) - match.get('xg_against_away', 1.3)

            xg_diffs.append(xg_diff if pd.notna(xg_diff) else 0)

            # Win streak
            if result_goals_for > result_goals_against:
                if win_streak >= 0:  # Continue counting
                    win_streak += 1
                    unbeaten_streak += 1
            elif result_goals_for == result_goals_against:
                if win_streak == 0:  # Only if not already broken
                    unbeaten_streak += 1
                win_streak = -999  # Break win streak
            else:
                win_streak = -999
                unbeaten_streak = -999
                if lose_streak >= 0:
                    lose_streak += 1

            # Clean sheet streak
            if result_goals_against == 0:
                if clean_sheet_streak >= 0:
                    clean_sheet_streak += 1
            else:
                clean_sheet_streak = -999

            # Scoring streak
            if result_goals_for > 0:
                if scoring_streak >= 0:
                    scoring_streak += 1
            else:
                scoring_streak = -999

    # Clean up negative markers
    win_streak = max(0, win_streak)
    unbeaten_streak = max(0, unbeaten_streak)
    lose_streak = max(0, lose_streak)
    clean_sheet_streak = max(0, clean_sheet_streak)
    scoring_streak = max(0, scoring_streak)

    # xG momentum: weighted recent xG difference
    xg_momentum = np.mean(xg_diffs) if len(xg_diffs) > 0 else 0.0

    return {
        'winning_streak': win_streak,
        'unbeaten_streak': unbeaten_streak,
        'losing_streak': lose_streak,
        'clean_sheet_streak': clean_sheet_streak,
        'scoring_streak': scoring_streak,
        'xg_momentum': xg_momentum,
    }


def populate_enhanced_features(input_csv, output_csv):
    """
    Main function: populate advanced features for historical CSV.
    """
    print(f"\n{'='*80}")
    print(f"POPULATING ADVANCED FEATURES")
    print(f"Input: {input_csv}")
    print(f"Output: {output_csv}")
    print(f"{'='*80}\n")

    # Load historical data
    df = pd.read_csv(input_csv)
    df['date'] = pd.to_datetime(df['date']).dt.date

    print(f"Loaded {len(df)} historical matches")
    print(f"Date range: {df['date'].min()} → {df['date'].max()}")
    print(f"Leagues: {df['league'].unique().tolist()}\n")

    # Initialize new columns
    advanced_feature_cols = [
        'home_form_xg_for', 'home_form_xg_against', 'home_form_xg_diff',
        'home_form_wins', 'home_form_draws', 'home_form_losses',
        'home_form_goals_for', 'home_form_goals_against', 'home_form_points', 'home_form_trend',
        'away_form_xg_for', 'away_form_xg_against', 'away_form_xg_diff',
        'away_form_wins', 'away_form_draws', 'away_form_losses',
        'away_form_goals_for', 'away_form_goals_against', 'away_form_points', 'away_form_trend',
        'h2h_home_wins', 'h2h_draws', 'h2h_away_wins',
        'h2h_home_goals_avg', 'h2h_away_goals_avg', 'h2h_home_xg_avg', 'h2h_away_xg_avg',
        'h2h_total_over25',
        'home_position', 'home_points', 'home_goal_difference', 'home_pressure_top', 'home_pressure_relegation',
        'away_position', 'away_points', 'away_goal_difference', 'away_pressure_top', 'away_pressure_relegation',
        'home_winning_streak', 'home_unbeaten_streak', 'home_losing_streak',
        'home_clean_sheet_streak', 'home_scoring_streak', 'home_xg_momentum',
        'away_winning_streak', 'away_unbeaten_streak', 'away_losing_streak',
        'away_clean_sheet_streak', 'away_scoring_streak', 'away_xg_momentum',
        'position_gap', 'points_gap', 'form_diff', 'momentum_diff',
    ]

    for col in advanced_feature_cols:
        df[col] = np.nan

    # Process each match
    print("Calculating advanced features...")
    total = len(df)
    for i, (idx, row) in enumerate(df.iterrows(), 1):
        if i % 100 == 0 or i == total:
            print(f"  Progress: {i}/{total} ({i/total*100:.1f}%)")
        try:
            home = row['home']
            away = row['away']
            league = row['league']
            date = row['date']

            # Home team form
            home_form = calculate_team_form(df, home, league, date, n_recent=5)
            for key, val in home_form.items():
                df.at[idx, f'home_{key}'] = val

            # Away team form
            away_form = calculate_team_form(df, away, league, date, n_recent=5)
            for key, val in away_form.items():
                df.at[idx, f'away_{key}'] = val

            # H2H
            h2h = calculate_h2h(df, home, away, league, date, n_recent=5)
            for key, val in h2h.items():
                df.at[idx, key] = val

            # Standings
            home_standings = calculate_standings(df, home, league, date)
            for key, val in home_standings.items():
                df.at[idx, f'home_{key}'] = val

            away_standings = calculate_standings(df, away, league, date)
            for key, val in away_standings.items():
                df.at[idx, f'away_{key}'] = val

            # Momentum
            home_momentum = calculate_momentum(df, home, league, date, n_recent=10)
            for key, val in home_momentum.items():
                df.at[idx, f'home_{key}'] = val

            away_momentum = calculate_momentum(df, away, league, date, n_recent=10)
            for key, val in away_momentum.items():
                df.at[idx, f'away_{key}'] = val

            # Derived features
            df.at[idx, 'position_gap'] = home_standings['position'] - away_standings['position']
            df.at[idx, 'points_gap'] = home_standings['points'] - away_standings['points']
            df.at[idx, 'form_diff'] = home_form['form_xg_diff'] - away_form['form_xg_diff']
            df.at[idx, 'momentum_diff'] = home_momentum['xg_momentum'] - away_momentum['xg_momentum']

        except Exception as e:
            print(f"\n[ERROR] Row {idx}: {e}")
            continue

    # Save enhanced dataset
    df.to_csv(output_csv, index=False)

    print(f"\n{'='*80}")
    print(f"[SUCCESS] Enhanced dataset saved: {output_csv}")
    print(f"Total rows: {len(df)}")
    print(f"Total columns: {len(df.columns)}")

    # Check coverage
    sample_features = ['home_form_xg_for', 'away_form_xg_for', 'h2h_home_wins', 'home_position']
    print(f"\nFeature coverage:")
    for col in sample_features:
        coverage = df[col].notna().mean() * 100
        print(f"  {col}: {coverage:.1f}%")
    print(f"{'='*80}\n")


def main():
    # Process OU dataset
    if HIST_OU_PATH.exists():
        populate_enhanced_features(HIST_OU_PATH, HIST_OU_ENHANCED)
    else:
        print(f"[WARN] {HIST_OU_PATH} not found")

    # Process 1X2 dataset
    if HIST_1X2_PATH.exists():
        populate_enhanced_features(HIST_1X2_PATH, HIST_1X2_ENHANCED)
    else:
        print(f"[WARN] {HIST_1X2_PATH} not found")


if __name__ == "__main__":
    main()
