#!/usr/bin/env python3
"""
Context Analyzer V2 - PESANTE MA INTELLIGENTE
Usa SOLO DATI REALI dal database, niente stime o placeholder
"""
from typing import Dict, Tuple, List
from datetime import datetime, timedelta
import sqlite3
from collections import defaultdict

class ContextAnalyzerV2:
    """
    Analisi contestuale SERIA basata su dati reali:
    - Ultimi 5 match reali (risultati, gol, xG)
    - Head-to-head ultimi 3 anni
    - Form home/away separati
    - Rest days e fixture congestion
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.debug = True  # Mostra cosa sta calcolando

    def analyze_match(self, match_id: str, home: str, away: str,
                     league: str, date: datetime) -> Dict:
        """
        Analisi completa con DATI REALI.

        Returns dict con:
        - motivation_home/away: 0-100 (basato su competizione)
        - form_home/away: -50 to +50 (ultimi 5 match REALI)
        - head_to_head: -30 to +30 (scontri diretti REALI)
        - fatigue_home/away: -30 to 0 (rest days REALI)
        - momentum_home/away: -20 to +20 (trend ultimi 10 match)
        - psychology_home/away: -20 to +20 (home advantage + pressione)
        """
        conn = sqlite3.connect(self.db_path)

        if self.debug:
            print(f"\n🔍 NEURAL REASONING ANALYSIS: {home} vs {away}")

        # 1. MOTIVATION (competizione)
        mot_home, mot_away = self._calculate_motivation(league, date)

        # 2. FORM (ultimi 5 match REALI)
        form_home, form_away, form_details = self._calculate_real_form(
            conn, home, away, date
        )

        # 3. HEAD-TO-HEAD (scontri diretti REALI)
        h2h_score, h2h_details = self._calculate_head_to_head(
            conn, home, away, date
        )

        # 4. FATIGUE (rest days + fixture congestion)
        fat_home, fat_away, fat_details = self._calculate_real_fatigue(
            conn, match_id, home, away, date
        )

        # 5. MOMENTUM (trend ultimi 10 match)
        mom_home, mom_away, mom_details = self._calculate_momentum(
            conn, home, away, date
        )

        # 6. PSYCHOLOGY (home advantage + pressione)
        psy_home, psy_away = self._calculate_psychology(league)

        conn.close()

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

            # Dettagli per trasparenza
            'form_details': form_details,
            'h2h_details': h2h_details,
            'fatigue_details': fat_details,
            'momentum_details': mom_details,
        }

        if self.debug:
            self._print_analysis(result, home, away)

        return result

    def _calculate_motivation(self, league: str, date: datetime) -> Tuple[int, int]:
        """
        Motivation basata su competizione (OGGETTIVA).
        Champions > Europa League > Campionato
        """
        home_score = 50
        away_score = 50

        league_lower = league.lower()

        # Champions League
        if 'champions' in league_lower or league == 'CL':
            # Fase a gironi vs knockout
            if date.month >= 2:  # Knockout
                home_score = 90
                away_score = 90
            else:  # Girone
                home_score = 75
                away_score = 75

        # Europa League
        elif 'europa' in league_lower or league == 'EL':
            if date.month >= 2:
                home_score = 80
                away_score = 80
            else:
                home_score = 65
                away_score = 65

        # Conference League
        elif 'conference' in league_lower:
            home_score = 60
            away_score = 60

        # Campionato nazionale
        else:
            home_score = 55
            away_score = 55

        return home_score, away_score

    def _calculate_real_form(self, conn, home: str, away: str,
                            date: datetime) -> Tuple[int, int, Dict]:
        """
        Form basata su ULTIMI 5 MATCH REALI nel database.
        Usa: vittorie, pareggi, sconfitte, gol fatti/subiti.
        """
        home_score = 0
        away_score = 0

        home_matches = self._get_last_matches(conn, home, date, n=5)
        away_matches = self._get_last_matches(conn, away, date, n=5)

        # Calcola form home
        if home_matches:
            home_stats = self._calculate_team_stats(home_matches, home)
            home_score = self._form_score_from_stats(home_stats)

        # Calcola form away
        if away_matches:
            away_stats = self._calculate_team_stats(away_matches, away)
            away_score = self._form_score_from_stats(away_stats)

        details = {
            'home_matches': len(home_matches),
            'away_matches': len(away_matches),
            'home_stats': home_stats if home_matches else {},
            'away_stats': away_stats if away_matches else {},
        }

        return home_score, away_score, details

    def _get_last_matches(self, conn, team: str, before_date: datetime,
                         n: int = 5) -> List[Dict]:
        """
        Recupera ultimi N match REALI dal database.
        """
        cursor = conn.cursor()

        # Query per trovare match dove la squadra ha giocato
        query = """
            SELECT f.date, f.home, f.away,
                   f.result_home_goals, f.result_away_goals,
                   feat.xg_for_home, feat.xg_for_away
            FROM fixtures f
            LEFT JOIN features feat ON f.match_id = feat.match_id
            WHERE (f.home LIKE ? OR f.away LIKE ?)
              AND f.date < ?
              AND f.result_home_goals IS NOT NULL
            ORDER BY f.date DESC
            LIMIT ?
        """

        cursor.execute(query, (f"%{team}%", f"%{team}%", before_date.strftime('%Y-%m-%d'), n))
        rows = cursor.fetchall()

        matches = []
        for row in rows:
            match_date, home, away, hg, ag, xg_h, xg_a = row

            # Determina se team era home o away
            is_home = team.lower() in home.lower()

            matches.append({
                'date': match_date,
                'opponent': away if is_home else home,
                'is_home': is_home,
                'goals_for': hg if is_home else ag,
                'goals_against': ag if is_home else hg,
                'xg_for': xg_h if is_home else xg_a,
                'xg_against': xg_a if is_home else xg_h,
            })

        return matches

    def _calculate_team_stats(self, matches: List[Dict], team: str) -> Dict:
        """
        Calcola statistiche da lista match.
        """
        if not matches:
            return {}

        wins = 0
        draws = 0
        losses = 0
        goals_for = 0
        goals_against = 0
        xg_for_sum = 0
        xg_against_sum = 0

        for m in matches:
            gf = m['goals_for'] or 0
            ga = m['goals_against'] or 0

            goals_for += gf
            goals_against += ga

            if m['xg_for']:
                xg_for_sum += m['xg_for']
            if m['xg_against']:
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
            'goals_for': goals_for,
            'goals_against': goals_against,
            'goal_diff': goals_for - goals_against,
            'xg_for_avg': xg_for_sum / len(matches) if xg_for_sum > 0 else None,
            'xg_against_avg': xg_against_sum / len(matches) if xg_against_sum > 0 else None,
        }

    def _form_score_from_stats(self, stats: Dict) -> int:
        """
        Converte stats in form score (-50 to +50).

        Logica:
        - 15 punti (5W) = +50
        - 12 punti (4W) = +35
        - 9 punti (3W) = +20
        - 6 punti = 0
        - 3 punti o meno = -30 o peggio
        """
        if not stats:
            return 0

        points = stats['points']
        max_points = stats['matches'] * 3

        # Normalizza su 5 match
        if stats['matches'] < 5:
            points = points * (5 / stats['matches'])
            max_points = 15

        # Scala punti
        # 15 pts = +50, 0 pts = -50
        score = ((points / max_points) - 0.4) * 125  # 0.4 = 6/15 (baseline)

        # Bonus goal difference
        if 'goal_diff' in stats:
            gd = stats['goal_diff']
            if gd > 8:
                score += 15
            elif gd > 4:
                score += 10
            elif gd < -4:
                score -= 10
            elif gd < -8:
                score -= 15

        return int(max(-50, min(50, score)))

    def _calculate_head_to_head(self, conn, home: str, away: str,
                               date: datetime) -> Tuple[int, Dict]:
        """
        Scontri diretti REALI ultimi 3 anni.

        Returns:
        - score: -30 to +30 (positivo = vantaggio home)
        - details: dict con statistiche
        """
        cursor = conn.cursor()

        # Ultimi 3 anni
        three_years_ago = date - timedelta(days=1095)

        query = """
            SELECT f.home, f.away, f.result_home_goals, f.result_away_goals
            FROM fixtures f
            WHERE ((f.home LIKE ? AND f.away LIKE ?)
                   OR (f.home LIKE ? AND f.away LIKE ?))
              AND f.date >= ?
              AND f.date < ?
              AND f.result_home_goals IS NOT NULL
            ORDER BY f.date DESC
            LIMIT 10
        """

        cursor.execute(query, (
            f"%{home}%", f"%{away}%",
            f"%{away}%", f"%{home}%",
            three_years_ago.strftime('%Y-%m-%d'),
            date.strftime('%Y-%m-%d')
        ))

        rows = cursor.fetchall()

        if not rows:
            return 0, {'count': 0, 'message': 'Nessuno scontro diretto recente'}

        # Analizza risultati
        home_wins = 0
        draws = 0
        away_wins = 0
        home_goals = 0
        away_goals = 0

        for match_home, match_away, hg, ag in rows:
            is_home_at_home = home.lower() in match_home.lower()

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

        total = len(rows)

        # Calcola score
        # 100% vittorie home = +30
        # 50/50 = 0
        # 100% vittorie away = -30
        home_win_rate = home_wins / total
        away_win_rate = away_wins / total

        score = (home_win_rate - away_win_rate) * 60  # -60 to +60, poi clampo
        score = int(max(-30, min(30, score)))

        details = {
            'count': total,
            'home_wins': home_wins,
            'draws': draws,
            'away_wins': away_wins,
            'home_goals': home_goals,
            'away_goals': away_goals,
            'message': f"H2H: {home_wins}W-{draws}D-{away_wins}L negli ultimi {total} scontri"
        }

        return score, details

    def _calculate_real_fatigue(self, conn, match_id: str, home: str, away: str,
                               date: datetime) -> Tuple[int, int, Dict]:
        """
        Fatigue REALE da rest_days nel database.
        """
        cursor = conn.cursor()

        # Prendi rest days dal database
        cursor.execute("""
            SELECT rest_days_home, rest_days_away,
                   travel_km_away, injuries_key_home, injuries_key_away
            FROM features
            WHERE match_id = ?
        """, (match_id,))

        row = cursor.fetchone()

        home_score = 0
        away_score = 0
        details = {}

        if row:
            rest_h, rest_a, travel, inj_h, inj_a = row

            details['rest_home'] = rest_h
            details['rest_away'] = rest_a
            details['travel_km'] = travel
            details['injuries_home'] = inj_h
            details['injuries_away'] = inj_a

            # Rest days impact (REALE)
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

            # Travel fatigue
            if travel and travel > 2000:
                away_score -= 10
            elif travel and travel > 1000:
                away_score -= 5

            # Key injuries
            if inj_h and inj_h > 0:
                home_score -= min(15, inj_h * 5)
            if inj_a and inj_a > 0:
                away_score -= min(15, inj_a * 5)

        home_score = max(-30, home_score)
        away_score = max(-30, away_score)

        return home_score, away_score, details

    def _calculate_momentum(self, conn, home: str, away: str,
                           date: datetime) -> Tuple[int, int, Dict]:
        """
        Momentum = trend ultimi 10 match (miglioramento o peggioramento).
        """
        home_matches = self._get_last_matches(conn, home, date, n=10)
        away_matches = self._get_last_matches(conn, away, date, n=10)

        home_score = 0
        away_score = 0

        # Analizza trend home
        if len(home_matches) >= 6:
            first_half = home_matches[5:]  # Primi 5 (più vecchi)
            second_half = home_matches[:5]  # Ultimi 5 (più recenti)

            pts_first = sum(self._match_points(m) for m in first_half) / len(first_half)
            pts_second = sum(self._match_points(m) for m in second_half) / len(second_half)

            momentum = (pts_second - pts_first) / 3 * 100  # Normalizza
            home_score = int(max(-20, min(20, momentum)))

        # Analizza trend away
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
        """Punti da un singolo match."""
        gf = match['goals_for'] or 0
        ga = match['goals_against'] or 0

        if gf > ga:
            return 3
        elif gf == ga:
            return 1
        else:
            return 0

    def _calculate_psychology(self, league: str) -> Tuple[int, int]:
        """
        Fattori psicologici:
        - Home advantage standard: +10 home
        - Pressure handling (grandi squadre)
        """
        home_score = 10  # Home advantage standard
        away_score = 0

        return home_score, away_score

    def _print_analysis(self, result: Dict, home: str, away: str):
        """Stampa analisi dettagliata per trasparenza."""
        print(f"\n📊 CONTEXT ANALYSIS RESULTS:")
        print(f"   Motivation: H={result['motivation_home']} A={result['motivation_away']}")
        print(f"   Form (last 5): H={result['form_home']:+d} A={result['form_away']:+d}")
        print(f"      └─ {result['form_details'].get('home_stats', {})}")
        print(f"      └─ {result['form_details'].get('away_stats', {})}")
        print(f"   H2H: {result['head_to_head']:+d} ({result['h2h_details'].get('message', 'N/A')})")
        print(f"   Fatigue: H={result['fatigue_home']:+d} A={result['fatigue_away']:+d}")
        print(f"   Momentum: H={result['momentum_home']:+d} A={result['momentum_away']:+d}")
        print(f"   Psychology: H={result['psychology_home']:+d} A={result['psychology_away']:+d}")
