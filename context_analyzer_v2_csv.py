#!/usr/bin/env python3
"""
Context Analyzer V2 CSV - MASSIME PERFORMANCE
Usa CSV storico (1770 partite) + Database per dati REALI
"""
from typing import Dict, Tuple, List
from datetime import datetime, timedelta
import sqlite3
import pandas as pd
from pathlib import Path
from collections import defaultdict

class ContextAnalyzerV2CSV:
    """
    Analisi contestuale con CSV storico per MASSIME PERFORMANCE.

    Usa:
    - CSV historical_dataset_enhanced.csv (1770 partite)
    - Database per features aggiuntive
    """

    def __init__(self, db_path: str, csv_path: str = None):
        self.db_path = db_path
        self.debug = True

        # Carica CSV storico
        if csv_path is None:
            csv_path = Path(db_path).parent / "data" / "historical_dataset_enhanced.csv"

        self.csv_path = csv_path
        self.df = None
        self.team_cache = {}  # Cache per performance

        self._load_historical_data()

    def _load_historical_data(self):
        """Carica CSV storico in memoria."""
        try:
            self.df = pd.read_csv(self.csv_path)
            self.df['date'] = pd.to_datetime(self.df['date'])

            if self.debug:
                print(f"✅ CSV storico caricato: {len(self.df)} partite")
                print(f"   Date range: {self.df['date'].min()} → {self.df['date'].max()}")
        except Exception as e:
            print(f"⚠️  CSV non trovato, uso solo DB: {e}")
            self.df = None

    def analyze_match(self, match_id: str, home: str, away: str,
                     league: str, date: datetime) -> Dict:
        """Analisi completa con CSV + DB."""

        if self.debug:
            print(f"\n🔍 NEURAL REASONING ANALYSIS: {home} vs {away}")

        # 1. MOTIVATION (competizione)
        mot_home, mot_away = self._calculate_motivation(league, date)

        # 2. FORM (ultimi 5 match REALI da CSV)
        form_home, form_away, form_details = self._calculate_real_form_csv(
            home, away, date
        )

        # 3. HEAD-TO-HEAD (scontri diretti REALI da CSV)
        h2h_score, h2h_details = self._calculate_head_to_head_csv(
            home, away, date
        )

        # 4. FATIGUE (rest days REALI da DB)
        fat_home, fat_away, fat_details = self._calculate_real_fatigue(
            match_id
        )

        # 5. MOMENTUM (trend ultimi 10 match da CSV)
        mom_home, mom_away, mom_details = self._calculate_momentum_csv(
            home, away, date
        )

        # 6. PSYCHOLOGY (home advantage)
        psy_home, psy_away = self._calculate_psychology(league)

        result = {
            'motivation_home': mot_home,
            'motivation_away': mot_away,
            'form_home': form_home,
            'form_away': form_away,
            'head_to_head': h2h_score,
            'fatigue_home': fat_home,
            'fatigue_away': fat_away,
            'momentum_home': mom_home,
            'momentum_away': mom_away,
            'psychology_home': psy_home,
            'psychology_away': psy_away,
            'form_details': form_details,
            'h2h_details': h2h_details,
            'fatigue_details': fat_details,
            'momentum_details': mom_details,
        }

        if self.debug:
            self._print_analysis(result, home, away)

        return result

    def _calculate_motivation(self, league: str, date: datetime) -> Tuple[int, int]:
        """Motivation basata su competizione."""
        home_score = 50
        away_score = 50

        league_lower = league.lower()

        if 'champions' in league_lower or league == 'CL':
            if date.month >= 2:  # Knockout
                home_score = 90
                away_score = 90
            else:
                home_score = 75
                away_score = 75
        elif 'europa' in league_lower or league == 'EL':
            if date.month >= 2:
                home_score = 80
                away_score = 80
            else:
                home_score = 65
                away_score = 65
        elif 'conference' in league_lower:
            home_score = 60
            away_score = 60
        else:
            home_score = 55
            away_score = 55

        return home_score, away_score

    def _calculate_real_form_csv(self, home: str, away: str,
                                 date: datetime) -> Tuple[int, int, Dict]:
        """Form da CSV storico."""
        if self.df is None:
            return 0, 0, {'message': 'CSV non disponibile'}

        home_matches = self._get_last_matches_csv(home, date, n=5)
        away_matches = self._get_last_matches_csv(away, date, n=5)

        home_score = 0
        away_score = 0
        home_stats = {}
        away_stats = {}

        if home_matches:
            home_stats = self._calculate_team_stats(home_matches, home)
            home_score = self._form_score_from_stats(home_stats)

        if away_matches:
            away_stats = self._calculate_team_stats(away_matches, away)
            away_score = self._form_score_from_stats(away_stats)

        details = {
            'home_matches': len(home_matches),
            'away_matches': len(away_matches),
            'home_stats': home_stats,
            'away_stats': away_stats,
        }

        return home_score, away_score, details

    def _get_last_matches_csv(self, team: str, before_date: datetime, n: int = 5) -> List[Dict]:
        """Recupera ultimi N match da CSV."""
        if self.df is None:
            return []

        # Converti before_date in Timestamp per confronto con pandas
        before_date_ts = pd.Timestamp(before_date)

        # Normalizza nome team per matching
        team_norm = team.lower().strip()

        # Filtra match dove team ha giocato
        mask_home = self.df['home'].str.lower().str.contains(team_norm[:10], na=False)
        mask_away = self.df['away'].str.lower().str.contains(team_norm[:10], na=False)
        mask_date = self.df['date'] < before_date_ts

        df_team = self.df[(mask_home | mask_away) & mask_date].copy()
        df_team = df_team.sort_values('date', ascending=False).head(n)

        matches = []
        for _, row in df_team.iterrows():
            is_home = team_norm[:10] in str(row['home']).lower()

            matches.append({
                'date': row['date'],
                'opponent': row['away'] if is_home else row['home'],
                'is_home': is_home,
                'goals_for': row['ft_home_goals'] if is_home else row['ft_away_goals'],
                'goals_against': row['ft_away_goals'] if is_home else row['ft_home_goals'],
                'xg_for': row.get('xg_for_home' if is_home else 'xg_for_away'),
                'xg_against': row.get('xg_against_home' if is_home else 'xg_against_away'),
            })

        return matches

    def _calculate_team_stats(self, matches: List[Dict], team: str) -> Dict:
        """Calcola statistiche da lista match."""
        if not matches:
            return {}

        wins = 0
        draws = 0
        losses = 0
        goals_for = 0
        goals_against = 0
        xg_for_sum = 0
        xg_against_sum = 0
        xg_count = 0

        for m in matches:
            gf = m['goals_for'] if pd.notna(m['goals_for']) else 0
            ga = m['goals_against'] if pd.notna(m['goals_against']) else 0

            goals_for += gf
            goals_against += ga

            if pd.notna(m.get('xg_for')) and m['xg_for'] is not None:
                xg_for_sum += m['xg_for']
                xg_count += 1
            if pd.notna(m.get('xg_against')) and m['xg_against'] is not None:
                xg_against_sum += m['xg_against']

            if gf > ga:
                wins += 1
            elif gf == ga:
                draws += 1
            else:
                losses += 1

        points = wins * 3 + draws

        return {
            'matches': len(matches),
            'wins': wins,
            'draws': draws,
            'losses': losses,
            'points': points,
            'goals_for': int(goals_for),
            'goals_against': int(goals_against),
            'goal_diff': int(goals_for - goals_against),
            'xg_for_avg': xg_for_sum / xg_count if xg_count > 0 else None,
            'xg_against_avg': xg_against_sum / xg_count if xg_count > 0 else None,
        }

    def _form_score_from_stats(self, stats: Dict) -> int:
        """Converte stats in form score (-50 to +50)."""
        if not stats or stats.get('matches', 0) == 0:
            return 0

        points = stats['points']
        matches = stats['matches']
        max_points = matches * 3

        # Normalizza su 5 match
        if matches < 5:
            points = points * (5 / matches)
            max_points = 15

        # Scala: 15 pts = +50, 6 pts = 0, 0 pts = -50
        score = ((points / max_points) - 0.4) * 125

        # Bonus goal difference
        gd = stats.get('goal_diff', 0)
        if gd > 8:
            score += 15
        elif gd > 4:
            score += 10
        elif gd < -4:
            score -= 10
        elif gd < -8:
            score -= 15

        return int(max(-50, min(50, score)))

    def _calculate_head_to_head_csv(self, home: str, away: str,
                                    date: datetime) -> Tuple[int, Dict]:
        """Scontri diretti da CSV."""
        if self.df is None:
            return 0, {'count': 0, 'message': 'CSV non disponibile'}

        # Converti date in Timestamp
        date_ts = pd.Timestamp(date)
        three_years_ago = date_ts - timedelta(days=1095)

        home_norm = home.lower().strip()[:10]
        away_norm = away.lower().strip()[:10]

        # Filtra h2h
        mask_h2h1 = (self.df['home'].str.lower().str.contains(home_norm, na=False) &
                     self.df['away'].str.lower().str.contains(away_norm, na=False))
        mask_h2h2 = (self.df['home'].str.lower().str.contains(away_norm, na=False) &
                     self.df['away'].str.lower().str.contains(home_norm, na=False))
        mask_date = (self.df['date'] >= three_years_ago) & (self.df['date'] < date_ts)

        df_h2h = self.df[(mask_h2h1 | mask_h2h2) & mask_date].copy()

        if len(df_h2h) == 0:
            return 0, {'count': 0, 'message': 'Nessuno scontro diretto recente'}

        home_wins = 0
        draws = 0
        away_wins = 0
        home_goals = 0
        away_goals = 0

        for _, row in df_h2h.iterrows():
            is_home_at_home = home_norm in str(row['home']).lower()
            hg = row['ft_home_goals'] if pd.notna(row['ft_home_goals']) else 0
            ag = row['ft_away_goals'] if pd.notna(row['ft_away_goals']) else 0

            if is_home_at_home:
                home_goals += hg
                away_goals += ag
                if hg > ag:
                    home_wins += 1
                elif hg == ag:
                    draws += 1
                else:
                    away_wins += 1
            else:
                home_goals += ag
                away_goals += hg
                if ag > hg:
                    home_wins += 1
                elif ag == hg:
                    draws += 1
                else:
                    away_wins += 1

        total = len(df_h2h)
        home_win_rate = home_wins / total
        away_win_rate = away_wins / total

        score = (home_win_rate - away_win_rate) * 60
        score = int(max(-30, min(30, score)))

        details = {
            'count': total,
            'home_wins': home_wins,
            'draws': draws,
            'away_wins': away_wins,
            'home_goals': int(home_goals),
            'away_goals': int(away_goals),
            'message': f"H2H: {home_wins}W-{draws}D-{away_wins}L negli ultimi {total} scontri"
        }

        return score, details

    def _calculate_real_fatigue(self, match_id: str) -> Tuple[int, int, Dict]:
        """Fatigue da DB."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT rest_days_home, rest_days_away,
                   travel_km_away, injuries_key_home, injuries_key_away
            FROM features
            WHERE match_id = ?
        """, (match_id,))

        row = cursor.fetchone()
        conn.close()

        home_score = 0
        away_score = 0
        details = {}

        if row:
            rest_h, rest_a, travel, inj_h, inj_a = row

            details = {
                'rest_home': rest_h,
                'rest_away': rest_a,
                'travel_km': travel,
                'injuries_home': inj_h,
                'injuries_away': inj_a
            }

            if rest_h is not None:
                if rest_h < 3:
                    home_score = -25
                elif rest_h < 4:
                    home_score = -15
                elif rest_h < 5:
                    home_score = -5

            if rest_a is not None:
                if rest_a < 3:
                    away_score = -25
                elif rest_a < 4:
                    away_score = -15
                elif rest_a < 5:
                    away_score = -5

            if travel and travel > 2000:
                away_score -= 10
            elif travel and travel > 1000:
                away_score -= 5

            if inj_h and inj_h > 0:
                home_score -= min(15, inj_h * 5)
            if inj_a and inj_a > 0:
                away_score -= min(15, inj_a * 5)

        return max(-30, home_score), max(-30, away_score), details

    def _calculate_momentum_csv(self, home: str, away: str,
                                date: datetime) -> Tuple[int, int, Dict]:
        """Momentum da CSV."""
        if self.df is None:
            return 0, 0, {'message': 'CSV non disponibile'}

        # get_last_matches_csv già gestisce la conversione Timestamp
        home_matches = self._get_last_matches_csv(home, date, n=10)
        away_matches = self._get_last_matches_csv(away, date, n=10)

        home_score = 0
        away_score = 0

        if len(home_matches) >= 6:
            first_half = home_matches[5:]
            second_half = home_matches[:5]

            pts_first = sum(self._match_points(m) for m in first_half) / len(first_half)
            pts_second = sum(self._match_points(m) for m in second_half) / len(second_half)

            momentum = (pts_second - pts_first) / 3 * 100
            home_score = int(max(-20, min(20, momentum)))

        if len(away_matches) >= 6:
            first_half = away_matches[5:]
            second_half = away_matches[:5]

            pts_first = sum(self._match_points(m) for m in first_half) / len(first_half)
            pts_second = sum(self._match_points(m) for m in second_half) / len(second_half)

            momentum = (pts_second - pts_first) / 3 * 100
            away_score = int(max(-20, min(20, momentum)))

        details = {
            'home_momentum': 'positivo' if home_score > 5 else 'negativo' if home_score < -5 else 'stabile',
            'away_momentum': 'positivo' if away_score > 5 else 'negativo' if away_score < -5 else 'stabile',
        }

        return home_score, away_score, details

    def _match_points(self, match: Dict) -> int:
        """Punti da singolo match."""
        gf = match['goals_for'] if pd.notna(match['goals_for']) else 0
        ga = match['goals_against'] if pd.notna(match['goals_against']) else 0

        if gf > ga:
            return 3
        elif gf == ga:
            return 1
        else:
            return 0

    def _calculate_psychology(self, league: str) -> Tuple[int, int]:
        """Psicologia: home advantage."""
        return 10, 0

    def _print_analysis(self, result: Dict, home: str, away: str):
        """Stampa analisi dettagliata."""
        print(f"\n📊 CONTEXT ANALYSIS RESULTS:")
        print(f"   Motivation: H={result['motivation_home']} A={result['motivation_away']}")
        print(f"   Form (last 5): H={result['form_home']:+d} A={result['form_away']:+d}")

        h_stats = result['form_details'].get('home_stats', {})
        if h_stats:
            print(f"      └─ Home: {h_stats.get('wins',0)}W-{h_stats.get('draws',0)}D-{h_stats.get('losses',0)}L, {h_stats.get('points',0)}pts, GD:{h_stats.get('goal_diff',0):+d}")

        a_stats = result['form_details'].get('away_stats', {})
        if a_stats:
            print(f"      └─ Away: {a_stats.get('wins',0)}W-{a_stats.get('draws',0)}D-{a_stats.get('losses',0)}L, {a_stats.get('points',0)}pts, GD:{a_stats.get('goal_diff',0):+d}")

        print(f"   H2H: {result['head_to_head']:+d} ({result['h2h_details'].get('message', 'N/A')})")
        print(f"   Fatigue: H={result['fatigue_home']:+d} A={result['fatigue_away']:+d}")
        print(f"   Momentum: H={result['momentum_home']:+d} A={result['momentum_away']:+d}")
        print(f"   Psychology: H={result['psychology_home']:+d} A={result['psychology_away']:+d}")
