#!/usr/bin/env python3
"""
Neural Reasoning Engine - Apply contextual intelligence to ML predictions

This is the FINAL HEAVY LAYER before predictions are output.
Adjusts ML probabilities based on context analysis.
"""
from typing import Dict, Tuple
from datetime import datetime
import sys
from pathlib import Path

# Add project to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))

from context_analyzer import ContextAnalyzer


class NeuralReasoningEngine:
    """
    Neural Reasoning Engine - applies heavy contextual adjustments.
    
    This runs AFTER ML predictions and applies ±20% probability shifts
    based on motivation, form, fatigue, psychology, and external factors.
    """
    
    def __init__(self, db_path: str, weight_config: Dict = None):
        self.db_path = db_path
        self.context_analyzer = ContextAnalyzer(db_path)
        
        # Heavy weights for significant impact
        self.weights = weight_config or {
            'motivation': 0.35,  # Increased from 0.30
            'form': 0.30,        # Increased from 0.25
            'fatigue': 0.20,     # Same
            'psychology': 0.10,  # Reduced from 0.15
            'external': 0.05     # Reduced from 0.10
        }
        
        # Maximum adjustment: ±20% instead of ±15%
        self.max_adjustment = 0.20
    
    def apply_reasoning(self, match_id: str, home: str, away: str,
                       league: str, date: datetime,
                       ml_prob_1: float, ml_prob_x: float, ml_prob_2: float
                       ) -> Tuple[float, float, float, Dict]:
        """
        Apply neural reasoning to adjust ML probabilities.
        
        Args:
            match_id: Match identifier
            home, away: Team names
            league: League/competition name
            date: Match date
            ml_prob_1, ml_prob_x, ml_prob_2: ML predicted probabilities
        
        Returns:
            (neural_prob_1, neural_prob_x, neural_prob_2, reasoning_dict)
        """
        # Step 1: Analyze context
        context = self.context_analyzer.analyze_match(
            match_id, home, away, league, date
        )
        
        # Step 2: Calculate adjustment factors
        home_factor = self._calculate_adjustment_factor(context, is_home=True)
        away_factor = self._calculate_adjustment_factor(context, is_home=False)
        
        # Step 3: Calculate probability shifts
        # Positive home_factor = boost home win prob
        # Positive away_factor = boost away win prob
        net_home_boost = (home_factor - away_factor) * self.max_adjustment
        net_away_boost = (away_factor - home_factor) * self.max_adjustment
        
        # Step 4: Apply shifts to ML probabilities
        neural_prob_1 = ml_prob_1 + net_home_boost
        neural_prob_2 = ml_prob_2 + net_away_boost
        
        # Step 5: Adjust draw probability to maintain sum = 1.0
        # If home/away boosted, draw suffers; if both weak, draw benefits
        neural_prob_x = 1.0 - neural_prob_1 - neural_prob_2
        
        # Step 6: Clamp probabilities to valid range [0.05, 0.90]
        neural_prob_1 = max(0.05, min(0.90, neural_prob_1))
        neural_prob_2 = max(0.05, min(0.90, neural_prob_2))
        neural_prob_x = max(0.05, min(0.90, neural_prob_x))
        
        # Step 7: Normalize to sum = 1.0
        total = neural_prob_1 + neural_prob_x + neural_prob_2
        neural_prob_1 /= total
        neural_prob_x /= total
        neural_prob_2 /= total
        
        # Step 8: Generate reasoning summary
        reasoning = self._generate_reasoning(
            context, home, away, home_factor, away_factor,
            ml_prob_1, ml_prob_2, neural_prob_1, neural_prob_2
        )
        
        return neural_prob_1, neural_prob_x, neural_prob_2, reasoning
    
    def _calculate_adjustment_factor(self, context: Dict, is_home: bool) -> float:
        """
        Calculate weighted adjustment factor from context scores.
        
        Returns value from -1.0 to +1.0
        Positive = team is favored, negative = team is disadvantaged
        """
        prefix = 'home' if is_home else 'away'
        
        # Normalize each component to -1.0 to +1.0
        motivation = context[f'motivation_{prefix}'] / 100.0  # 0-100 → 0-1
        form = context[f'form_{prefix}'] / 50.0               # -50 to +50 → -1 to +1
        fatigue = context[f'fatigue_{prefix}'] / 30.0         # -30 to 0 → -1 to 0
        psychology = context[f'psychology_{prefix}'] / 20.0   # -20 to +20 → -1 to +1
        external = context[f'external_{prefix}'] / 10.0       # -10 to +10 → -1 to +1
        
        # Weighted sum
        factor = (
            motivation * self.weights['motivation'] +
            form * self.weights['form'] +
            fatigue * self.weights['fatigue'] +
            psychology * self.weights['psychology'] +
            external * self.weights['external']
        )
        
        return max(-1.0, min(1.0, factor))
    
    def _generate_reasoning(self, context: Dict, home: str, away: str,
                           home_factor: float, away_factor: float,
                           ml_prob_1: float, ml_prob_2: float,
                           neural_prob_1: float, neural_prob_2: float) -> Dict:
        """
        Generate human-readable reasoning summary.
        """
        # Calculate changes
        home_change = (neural_prob_1 - ml_prob_1) * 100
        away_change = (neural_prob_2 - ml_prob_2) * 100
        
        # Identify key factors
        key_factors_home = []
        key_factors_away = []
        
        # Home factors
        if context['motivation_home'] > 70:
            key_factors_home.append(f"Alta motivazione ({context['motivation_home']})")
        if context['form_home'] > 20:
            key_factors_home.append(f"Forma eccellente (+{context['form_home']})")
        elif context['form_home'] < -20:
            key_factors_home.append(f"Forma negativa ({context['form_home']})")
        if context['fatigue_home'] < -15:
            key_factors_home.append(f"Stanchezza significativa ({context['fatigue_home']})")
        if context['psychology_home'] > 10:
            key_factors_home.append(f"Vantaggio psicologico (+{context['psychology_home']})")
        
        # Away factors
        if context['motivation_away'] > 70:
            key_factors_away.append(f"Alta motivazione ({context['motivation_away']})")
        if context['form_away'] > 20:
            key_factors_away.append(f"Forma eccellente (+{context['form_away']})")
        elif context['form_away'] < -20:
            key_factors_away.append(f"Forma negativa ({context['form_away']})")
        if context['fatigue_away'] < -15:
            key_factors_away.append(f"Stanchezza significativa ({context['fatigue_away']})")
        
        # Determine verdict
        if abs(home_change) < 3 and abs(away_change) < 3:
            verdict = "Contesto neutro - probabilita ML confermate"
        elif home_change > 5:
            verdict = f"{home}: Neural Reasoning aumenta probabilita di {home_change:+.1f}%"
        elif away_change > 5:
            verdict = f"{away}: Neural Reasoning aumenta probabilita di {away_change:+.1f}%"
        else:
            verdict = "Lievi aggiustamenti contestuali applicati"
        
        return {
            'context': context,
            'home_factor': home_factor,
            'away_factor': away_factor,
            'home_change_pct': home_change,
            'away_change_pct': away_change,
            'key_factors_home': key_factors_home,
            'key_factors_away': key_factors_away,
            'verdict': verdict,
            'reasoning_summary': self._create_summary(
                home, away, key_factors_home, key_factors_away, verdict
            )
        }
    
    def _create_summary(self, home: str, away: str,
                       factors_home: list, factors_away: list,
                       verdict: str) -> str:
        """Create concise reasoning summary"""
        lines = [f"🧠 NEURAL REASONING:", f"", verdict]
        
        if factors_home:
            lines.append(f"")
            lines.append(f"✓ {home}:")
            for f in factors_home:
                lines.append(f"  - {f}")
        
        if factors_away:
            lines.append(f"")
            lines.append(f"✓ {away}:")
            for f in factors_away:
                lines.append(f"  - {f}")
        
        return "\n".join(lines)


# Standalone test
if __name__ == "__main__":
    from datetime import datetime
    
    engine = NeuralReasoningEngine("/Users/gennaro.taurino/Develop/BET/BET/bet.db")
    
    # Test on a sample match
    neural_p1, neural_px, neural_p2, reasoning = engine.apply_reasoning(
        match_id="20260128_551950_CL",
        home="Liverpool FC",
        away="Qarabağ Ağdam FK",
        league="Champions League",
        date=datetime(2026, 1, 28),
        ml_prob_1=0.39,
        ml_prob_x=0.27,
        ml_prob_2=0.33
    )
    
    print(f"\nML Predictions: 1={0.39:.0%} X={0.27:.0%} 2={0.33:.0%}")
    print(f"Neural Adjusted: 1={neural_p1:.0%} X={neural_px:.0%} 2={neural_p2:.0%}")
    print(f"\nChanges: 1={reasoning['home_change_pct']:+.1f}% 2={reasoning['away_change_pct']:+.1f}%")
    print(f"\n{reasoning['reasoning_summary']}")
