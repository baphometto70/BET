#!/usr/bin/env python3
"""
Neural Reasoning Engine V2 - PESANTE MA INTELLIGENTE

Aggiustamenti fino a ±30% basati su DATI REALI:
- Form ultimi 5 match (REALE dal DB)
- Head-to-head ultimi 3 anni (REALE)
- Fatigue e rest days (REALE)
- Momentum ultimi 10 match (REALE)

NIENTE STIME, SOLO FATTI.
"""
from typing import Dict, Tuple
from datetime import datetime
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))

from context_analyzer_v2_csv import ContextAnalyzerV2CSV


class NeuralReasoningEngineV2:
    """
    Neural Reasoning Engine V2 - PESANTE E INTELLIGENTE

    Applica fino a ±30% di aggiustamento basato su dati reali da CSV (1770 partite).
    """

    def __init__(self, db_path: str, weight_config: Dict = None):
        self.db_path = db_path
        self.context_analyzer = ContextAnalyzerV2CSV(db_path)

        # Pesi AGGRESSIVI ma BILANCIATI
        self.weights = weight_config or {
            'motivation': 0.25,      # Competizione
            'form': 0.30,            # Forma recente (REALE)
            'head_to_head': 0.20,    # Scontri diretti (REALE)
            'fatigue': 0.15,         # Rest days (REALE)
            'momentum': 0.10,        # Trend (REALE)
        }

        # AGGIUSTAMENTO MASSIMO: ±30% (pesante ma non folle)
        self.max_adjustment = 0.30

        # SOGLIE per applicare aggiustamenti forti
        self.thresholds = {
            'strong_boost': 0.70,    # Se factor > 0.70 → boost forte
            'moderate_boost': 0.40,  # Se factor > 0.40 → boost moderato
            'weak_boost': 0.20,      # Se factor > 0.20 → boost leggero
        }

        self.debug = True

    def apply_reasoning(self, match_id: str, home: str, away: str,
                       league: str, date: datetime,
                       ml_prob_1: float, ml_prob_x: float, ml_prob_2: float
                       ) -> Tuple[float, float, float, Dict]:
        """
        Applica Neural Reasoning PESANTE ma INTELLIGENTE.

        Args:
            match_id: Match ID
            home, away: Team names
            league: League code
            date: Match date
            ml_prob_1, ml_prob_x, ml_prob_2: ML probabilities

        Returns:
            (neural_prob_1, neural_prob_x, neural_prob_2, reasoning_dict)
        """
        # Step 1: Analizza contesto con DATI REALI
        context = self.context_analyzer.analyze_match(
            match_id, home, away, league, date
        )

        # Step 2: Calcola adjustment factors
        home_factor = self._calculate_adjustment_factor(context, is_home=True)
        away_factor = self._calculate_adjustment_factor(context, is_home=False)

        if self.debug:
            print(f"\n🧠 NEURAL REASONING FACTORS:")
            print(f"   Home factor: {home_factor:+.3f}")
            print(f"   Away factor: {away_factor:+.3f}")

        # Step 3: Calcola probability shifts
        # Net home boost = quanto home è favorito rispetto away
        net_home_boost = (home_factor - away_factor) * self.max_adjustment
        net_away_boost = (away_factor - home_factor) * self.max_adjustment

        if self.debug:
            print(f"   Net adjustments: Home={net_home_boost:+.1%} Away={net_away_boost:+.1%}")

        # Step 4: Applica shifts
        neural_prob_1 = ml_prob_1 + net_home_boost
        neural_prob_2 = ml_prob_2 + net_away_boost

        # Step 5: Aggiusta pareggio per mantenere sum = 1.0
        neural_prob_x = 1.0 - neural_prob_1 - neural_prob_2

        # Step 6: Clamp a range valido [0.05, 0.90]
        neural_prob_1 = max(0.05, min(0.90, neural_prob_1))
        neural_prob_2 = max(0.05, min(0.90, neural_prob_2))
        neural_prob_x = max(0.05, min(0.90, neural_prob_x))

        # Step 7: Normalizza
        total = neural_prob_1 + neural_prob_x + neural_prob_2
        neural_prob_1 /= total
        neural_prob_x /= total
        neural_prob_2 /= total

        # Step 8: Genera reasoning dettagliato
        reasoning = self._generate_reasoning(
            context, home, away, home_factor, away_factor,
            ml_prob_1, ml_prob_x, ml_prob_2,
            neural_prob_1, neural_prob_x, neural_prob_2
        )

        if self.debug:
            print(f"\n📊 FINAL PROBABILITIES:")
            print(f"   ML:     1={ml_prob_1:.1%} X={ml_prob_x:.1%} 2={ml_prob_2:.1%}")
            print(f"   NEURAL: 1={neural_prob_1:.1%} X={neural_prob_x:.1%} 2={neural_prob_2:.1%}")
            print(f"   Change: 1={reasoning['home_change_pct']:+.1f}% X={reasoning['draw_change_pct']:+.1f}% 2={reasoning['away_change_pct']:+.1f}%")

        return neural_prob_1, neural_prob_x, neural_prob_2, reasoning

    def _calculate_adjustment_factor(self, context: Dict, is_home: bool) -> float:
        """
        Calcola weighted adjustment factor da context REALE.

        Returns: -1.0 to +1.0
        """
        prefix = 'home' if is_home else 'away'

        # Normalizza ogni componente
        motivation = context[f'motivation_{prefix}'] / 100.0     # 0-100 → 0-1.0

        form = context[f'form_{prefix}'] / 50.0                  # -50/+50 → -1.0/+1.0

        # Head-to-head (solo per home, è già relativo)
        if is_home:
            h2h = context['head_to_head'] / 30.0                 # -30/+30 → -1.0/+1.0
        else:
            h2h = -context['head_to_head'] / 30.0                # Inverti per away

        fatigue = context[f'fatigue_{prefix}'] / 30.0            # -30/0 → -1.0/0

        momentum = context[f'momentum_{prefix}'] / 20.0          # -20/+20 → -1.0/+1.0

        # Weighted sum
        factor = (
            motivation * self.weights['motivation'] +
            form * self.weights['form'] +
            h2h * self.weights['head_to_head'] +
            fatigue * self.weights['fatigue'] +
            momentum * self.weights['momentum']
        )

        # Clamp
        return max(-1.0, min(1.0, factor))

    def _generate_reasoning(self, context: Dict, home: str, away: str,
                           home_factor: float, away_factor: float,
                           ml_prob_1: float, ml_prob_x: float, ml_prob_2: float,
                           neural_prob_1: float, neural_prob_x: float, neural_prob_2: float
                           ) -> Dict:
        """
        Genera reasoning dettagliato e TRASPARENTE.
        """
        # Calcola changes
        home_change = (neural_prob_1 - ml_prob_1) * 100
        draw_change = (neural_prob_x - ml_prob_x) * 100
        away_change = (neural_prob_2 - ml_prob_2) * 100

        # Identifica key factors (REALI)
        key_factors_home = []
        key_factors_away = []

        # HOME FACTORS
        if context['motivation_home'] > 80:
            key_factors_home.append(f"🔥 Alta motivazione ({context['motivation_home']}/100)")

        if context['form_home'] > 25:
            key_factors_home.append(f"📈 Forma eccellente (+{context['form_home']}/50)")
            if 'form_details' in context and context['form_details'].get('home_stats'):
                stats = context['form_details']['home_stats']
                key_factors_home.append(f"   └─ {stats['wins']}W-{stats['draws']}D-{stats['losses']}L, {stats['points']}pts")
        elif context['form_home'] < -25:
            key_factors_home.append(f"📉 Forma negativa ({context['form_home']}/50)")

        if context['head_to_head'] > 15:
            h2h_msg = context['h2h_details'].get('message', '')
            key_factors_home.append(f"🎯 Dominano scontri diretti (+{context['head_to_head']}/30)")
            if h2h_msg:
                key_factors_home.append(f"   └─ {h2h_msg}")
        elif context['head_to_head'] < -15:
            h2h_msg = context['h2h_details'].get('message', '')
            key_factors_home.append(f"⚠️ Soffrono scontri diretti ({context['head_to_head']}/30)")
            if h2h_msg:
                key_factors_home.append(f"   └─ {h2h_msg}")

        if context['fatigue_home'] < -15:
            fat_det = context.get('fatigue_details', {})
            rest = fat_det.get('rest_home', '?')
            key_factors_home.append(f"😴 Stanchezza significativa ({context['fatigue_home']}/0)")
            key_factors_home.append(f"   └─ {rest} giorni di riposo")

        if context['momentum_home'] > 10:
            key_factors_home.append(f"🚀 Momentum positivo (+{context['momentum_home']}/20)")
        elif context['momentum_home'] < -10:
            key_factors_home.append(f"📉 Momentum negativo ({context['momentum_home']}/20)")

        # AWAY FACTORS
        if context['motivation_away'] > 80:
            key_factors_away.append(f"🔥 Alta motivazione ({context['motivation_away']}/100)")

        if context['form_away'] > 25:
            key_factors_away.append(f"📈 Forma eccellente (+{context['form_away']}/50)")
            if 'form_details' in context and context['form_details'].get('away_stats'):
                stats = context['form_details']['away_stats']
                key_factors_away.append(f"   └─ {stats['wins']}W-{stats['draws']}D-{stats['losses']}L, {stats['points']}pts")
        elif context['form_away'] < -25:
            key_factors_away.append(f"📉 Forma negativa ({context['form_away']}/50)")

        if context['fatigue_away'] < -15:
            fat_det = context.get('fatigue_details', {})
            rest = fat_det.get('rest_away', '?')
            key_factors_away.append(f"😴 Stanchezza significativa ({context['fatigue_away']}/0)")
            key_factors_away.append(f"   └─ {rest} giorni di riposo")

        if context['momentum_away'] > 10:
            key_factors_away.append(f"🚀 Momentum positivo (+{context['momentum_away']}/20)")
        elif context['momentum_away'] < -10:
            key_factors_away.append(f"📉 Momentum negativo ({context['momentum_away']}/20)")

        # Verdict
        if abs(home_change) < 3 and abs(away_change) < 3:
            verdict = "⚖️ Contesto bilanciato - ML confermato"
            impact = "LEGGERO"
        elif home_change > 10:
            verdict = f"💪 {home}: Neural Reasoning AUMENTA probabilità di {home_change:+.1f}%"
            impact = "FORTE"
        elif away_change > 10:
            verdict = f"💪 {away}: Neural Reasoning AUMENTA probabilità di {away_change:+.1f}%"
            impact = "FORTE"
        elif home_change > 5:
            verdict = f"↗️ {home}: Leggero vantaggio (+{home_change:.1f}%)"
            impact = "MODERATO"
        elif away_change > 5:
            verdict = f"↗️ {away}: Leggero vantaggio (+{away_change:.1f}%)"
            impact = "MODERATO"
        else:
            verdict = "→ Aggiustamenti minimi applicati"
            impact = "MINIMO"

        return {
            'context': context,
            'home_factor': home_factor,
            'away_factor': away_factor,
            'home_change_pct': home_change,
            'draw_change_pct': draw_change,
            'away_change_pct': away_change,
            'key_factors_home': key_factors_home,
            'key_factors_away': key_factors_away,
            'verdict': verdict,
            'impact': impact,
            'reasoning_summary': self._create_summary(
                home, away, key_factors_home, key_factors_away, verdict, impact
            )
        }

    def _create_summary(self, home: str, away: str,
                       factors_home: list, factors_away: list,
                       verdict: str, impact: str) -> str:
        """Crea summary conciso"""
        lines = [
            "=" * 80,
            "🧠 NEURAL REASONING V2 - PESANTE E INTELLIGENTE",
            "=" * 80,
            "",
            f"📊 IMPATTO: {impact}",
            f"🎯 VERDETTO: {verdict}",
            ""
        ]

        if factors_home:
            lines.append(f"✓ {home}:")
            for f in factors_home:
                lines.append(f"  {f}")
            lines.append("")

        if factors_away:
            lines.append(f"✓ {away}:")
            for f in factors_away:
                lines.append(f"  {f}")
            lines.append("")

        lines.append("=" * 80)

        return "\n".join(lines)


# Test standalone
if __name__ == "__main__":
    from datetime import datetime

    engine = NeuralReasoningEngineV2("/Users/gennaro.taurino/Develop/BET/BET/bet.db")

    # Test match
    neural_p1, neural_px, neural_p2, reasoning = engine.apply_reasoning(
        match_id="test_match",
        home="Liverpool FC",
        away="Manchester United FC",
        league="Premier League",
        date=datetime(2026, 1, 28),
        ml_prob_1=0.45,
        ml_prob_x=0.28,
        ml_prob_2=0.27
    )

    print(f"\n\n{reasoning['reasoning_summary']}")
    print(f"\n📌 ML:     1={0.45:.1%} X={0.28:.1%} 2={0.27:.1%}")
    print(f"📌 NEURAL: 1={neural_p1:.1%} X={neural_px:.1%} 2={neural_p2:.1%}")
