#!/usr/bin/env python3
"""
Context Analyzer - Calculate contextual scores for neural reasoning
"""
from typing import Dict, Tuple
from datetime import datetime, timedelta
import sqlite3

class ContextAnalyzer:
    """Analyze match context to generate reasoning scores"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def analyze_match(self, match_id: str, home: str, away: str, 
                     league: str, date: datetime) -> Dict:
        """
        Generate complete context analysis for a match.
        
        Returns dict with all context scores:
        - motivation_home/away: 0-100
        - form_home/away: -50 to +50
        - fatigue_home/away: -30 to 0
        - psychology_home/away: -20 to +20
        - external_home/away: -10 to +10
        """
        conn = sqlite3.connect(self.db_path)
        
        # Calculate each component
        mot_home, mot_away = self._calculate_motivation(conn, home, away, league, date)
        form_home, form_away = self._calculate_form(conn, home, away, date)
        fat_home, fat_away = self._calculate_fatigue(conn, match_id, home, away, date)
        psy_home, psy_away = self._calculate_psychology(conn, home, away, league)
        ext_home, ext_away = self._calculate_external(conn, match_id, home, away)
        
        conn.close()
        
        return {
            'motivation_home': mot_home,
            'motivation_away': mot_away,
            'form_home': form_home,
            'form_away': form_away,
            'fatigue_home': fat_home,
            'fatigue_away': fat_away,
            'psychology_home': psy_home,
            'psychology_away': psy_away,
            'external_home': ext_home,
            'external_away': ext_away
        }
    
    def _calculate_motivation(self, conn, home: str, away: str, 
                             league: str, date: datetime) -> Tuple[int, int]:
        """
        Calculate motivation score (0-100) based on:
        - League position context
        - Tournament stage
        - Historical rivalry
        """
        home_score = 50  # Base
        away_score = 50
        
        # Champions League gets automatic boost
        if 'champions' in league.lower() or 'CL' in league:
            if 'knockout' in league.lower() or date.month >= 2:
                home_score += 40
                away_score += 40
            else:
                home_score += 25
                away_score += 25
        
        # Derby detection (simple: same city or country code)
        if self._is_derby(home, away):
            home_score += 20
            away_score += 20
        
        # Cup finals
        if 'final' in league.lower() or 'cup' in league.lower():
            home_score += 30
            away_score += 30
        
        # League-specific context (would need standings data)
        # Placeholder: assume mid-table teams have base motivation
        # This should be enhanced with actual standings
        
        return min(100, home_score), min(100, away_score)
    
    def _calculate_form(self, conn, home: str, away: str, 
                       date: datetime) -> Tuple[int, int]:
        """
        Calculate form score (-50 to +50) based on:
        - Last 5 matches W/D/L
        - Points trend
        - Goals scored trend
        - Win streak bonus
        """
        home_score = 0
        away_score = 0
        
        # Query last 5 matches for each team (would need historical results)
        # Placeholder implementation with basic logic
        
        # For now, use feature table if available
        cursor = conn.cursor()
        cursor.execute("""
            SELECT xg_for_home, xg_for_away 
            FROM features 
            WHERE match_id LIKE ?
            LIMIT 1
        """, (f"%{home}%",))
        
        row = cursor.fetchone()
        if row:
            xg_home_avg = row[0] or 1.3
            xg_away_avg = row[1] or 1.3
            
            # High xG = good form
            if xg_home_avg > 1.8:
                home_score += 30
            elif xg_home_avg > 1.5:
                home_score += 15
            elif xg_home_avg < 1.0:
                home_score -= 20
            
            if xg_away_avg > 1.8:
                away_score += 30
            elif xg_away_avg > 1.5:
                away_score += 15
            elif xg_away_avg < 1.0:
                away_score -= 20
        
        return max(-50, min(50, home_score)), max(-50, min(50, away_score))
    
    def _calculate_fatigue(self, conn, match_id: str, home: str, away: str,
                          date: datetime) -> Tuple[int, int]:
        """
        Calculate fatigue score (-30 to 0) based on:
        - Days since last match
        - Fixture congestion
        - Travel distance
        - Key injuries
        """
        home_score = 0
        away_score = 0
        
        # Check rest_days from features table
        cursor = conn.cursor()
        cursor.execute("""
            SELECT rest_days_home, rest_days_away,
                   travel_km_away, injuries_key_home, injuries_key_away
            FROM features
            WHERE match_id = ?
        """, (match_id,))
        
        row = cursor.fetchone()
        if row:
            rest_home, rest_away, travel, inj_home, inj_away = row
            
            # Rest days impact
            if rest_home and rest_home < 3:
                home_score -= 20
            elif rest_home and rest_home < 5:
                home_score -= 10
            
            if rest_away and rest_away < 3:
                away_score -= 20
            elif rest_away and rest_away < 5:
                away_score -= 10
            
            # Travel fatigue
            if travel and travel > 1000:
                away_score -= 10
            
            # Injuries
            if inj_home:
                home_score -= min(15, inj_home * 5)
            if inj_away:
                away_score -= min(15, inj_away * 5)
        
        return max(-30, home_score), max(-30, away_score)
    
    def _calculate_psychology(self, conn, home: str, away: str, 
                             league: str) -> Tuple[int, int]:
        """
        Calculate psychological score (-20 to +20) based on:
        - Home advantage
        - Manager pressure
        - Recent upsets
        """
        home_score = 0
        away_score = 0
        
        # Home advantage (standard)
        home_score += 10
        
        # Top teams playing away in tough venues
        if self._is_top_team(away):
            away_score += 5  # Big teams handle pressure well
        
        return max(-20, min(20, home_score)), max(-20, min(20, away_score))
    
    def _calculate_external(self, conn, match_id: str, home: str, 
                           away: str) -> Tuple[int, int]:
        """
        Calculate external factors (-10 to +10) based on:
        - Weather
        - Time zone
        - Altitude
        """
        home_score = 0
        away_score = 0
        
        # Check weather from features (if column exists)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT weather_condition
                FROM features
                WHERE match_id = ?
            """, (match_id,))
            
            row = cursor.fetchone()
            if row and row[0]:
                weather = row[0].lower()
                if 'rain' in weather or 'snow' in weather:
                    # Technical teams suffer more in bad weather
                    if self._is_technical_team(home):
                        home_score -= 5
                    if self._is_technical_team(away):
                        away_score -= 5
        except Exception:
            # Weather column not available, skip
            pass
        
        return max(-10, min(10, home_score)), max(-10, min(10, away_score))
    
    # Helper methods
    def _is_derby(self, home: str, away: str) -> bool:
        """Detect if match is a derby"""
        # Simple city detection
        home_words = set(home.lower().split())
        away_words = set(away.lower().split())
        
        # Same city name appears in both
        cities = {'milan', 'london', 'manchester', 'madrid', 'barcelona', 
                 'liverpool', 'rome', 'paris', 'munich', 'amsterdam'}
        
        return len(home_words & away_words & cities) > 0
    
    def _is_top_team(self, team: str) -> bool:
        """Check if team is a top-tier club"""
        top_teams = {'real madrid', 'barcelona', 'bayern', 'manchester city',
                    'liverpool', 'psg', 'juventus', 'inter', 'milan'}
        return any(top in team.lower() for top in top_teams)
    
    def _is_technical_team(self, team: str) -> bool:
        """Check if team plays technical/possession style"""
        technical_teams = {'barcelona', 'manchester city', 'arsenal', 'bayern'}
        return any(tech in team.lower() for tech in technical_teams)
