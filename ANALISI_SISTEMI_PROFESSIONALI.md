# 🔬 ANALISI SISTEMI PREDIZIONE PROFESSIONALI

**Data Analisi**: 2 Gennaio 2026
**Sistemi Analizzati**: FiveThirtyEight, Understat, BetClan, PerformanceOdds, FootballWhispers

---

## 📊 EXECUTIVE SUMMARY

### Problema Attuale BET
- **Predizioni ripetitive**: Stesso pattern (43.8% / 56.2%) su molte partite
- **Features limitate**: Solo xG di base senza contesto temporale
- **Dataset piccolo**: ~500 partite vs 2500+ necessarie
- **Mancanza dinamismo**: Nessuna analisi forma recente, H2H, classifica, momentum

### Gap vs Sistemi Professionali
I nostri competitor usano **10-15+ features** contro le nostre **4-6 features attuali**.

---

## 🎯 FIVETHIRTYEIGHT - METODOLOGIA COMPLETA

### Soccer Power Index (SPI)
**Fonte**: [FiveThirtyEight Methodology](https://fivethirtyeight.com/methodology/how-our-club-soccer-predictions-work/)

#### Rating Sistema
- **Offensive Rating**: xG che una squadra segnerebbe contro team medio su campo neutro
- **Defensive Rating**: xG che una squadra concederebbe contro team medio
- **SPI complessivo**: Combinazione dei due rating (scala 0-100)

#### Dataset Storico
- **550,000+ partite** dal 1888 ad oggi
- Fonti: ESPN database, Engsoccerdata GitHub, Opta play-by-play (dal 2010)
- **Market value** da Transfermarkt per rating pre-stagione

#### Metriche Chiave

**1. Adjusted Goals**
```
- Riduce valore gol con uomo in più
- Sconta gol tardivi quando già in vantaggio
- Pondera contesto situazionale
```

**2. Shot-based xG**
```python
xG_shot = f(
    distance,           # Distanza dalla porta
    angle,              # Angolo di tiro
    body_part,          # Testa/piede
    player_skill        # Conversion rate storica giocatore
)
```

**3. Non-shot xG**
```
- Qualità gioco costruttivo oltre i tiri
- Controllo possesso
- Progressione palla
```

#### Aggiornamento Dinamico
- **Rating cambiano dopo ogni partita**
- Non Elo puro: rating può diminuire anche dopo una vittoria se performance < aspettative
- Ponderazione forza avversario

---

## 🌐 FEATURES COMUNI SISTEMI PROFESSIONALI

### 1. **Recent Form (Forma Recente)**
**Fonte**: [Football Predictions Guide](https://www.performanceodds.com/how-to-guides/the-ultimate-guide-to-football-stats-how-to-read-analyze-predict-todays-matches-like-a-pro/)

```python
# Rolling xG-based form (non W-D-L)
form_last_5 = (xG_for - xG_against).rolling(5).mean()
form_trend = "momentum_UP" if form[-1] > form[-5] else "momentum_DOWN"
```

**Perché è importante**:
- Cattura dinamiche attuali oltre storia completa
- xG più predittivo di semplici risultati (1-0 fortunato ≠ dominanza)
- Identifica picchi: squadre con momentum spesso segnano entro 10-15 min

### 2. **Head-to-Head (H2H)**
**Fonte**: [Atalanta vs Roma Prediction](https://footballwhispers.com/blog/atalanta-vs-roma-prediction-03-01-2026/)

```python
h2h_features = {
    'wins_last_5': 4,        # Atalanta ha vinto 4/5 ultimi scontri
    'avg_goals_for': 2.4,
    'avg_goals_against': 0.8,
    'home_advantage_h2h': True  # Domini storici in casa/trasferta
}
```

**Perché è importante**:
- Matchup specifici > statistiche generali
- "Bestie nere": alcune squadre dominano sempre certe avversarie
- Fattore psicologico: fiducia/timore da scontri precedenti

### 3. **League Standings Context**
**Fonte**: [BetClan Predictions](https://www.betclan.com/todays-football-predictions/)

```python
standings_features = {
    'home_position': 3,      # Posizione classifica
    'away_position': 15,
    'gap_points': 12,        # Distacco punti
    'pressure_relegation': False,
    'pressure_champions': True  # Lotta CL/titolo
}
```

**Perché è importante**:
- Motivazione variabile: squadra in lotta salvezza ≠ metà classifica sicura
- Scontri diretti valgono 6 punti (3 vinti, 3 negati)
- Finale stagione: pressione > inizio stagione

### 4. **Momentum & Streaks**
**Fonte**: [Machine Learning Football](https://medium.com/@davidblum_6849/revolutionizing-football-predictions-how-machine-learning-is-changing-the-game-226b986babae)

```python
momentum_indicators = {
    'winning_streak': 5,           # 5 vittorie consecutive
    'unbeaten_streak': 10,
    'clean_sheets_streak': 3,
    'goals_trend': [1,2,2,3,4],    # Aumento produzione offensiva
    'xg_momentum': +0.4            # Delta xG ultimi 5 vs precedenti 5
}
```

**Perché è importante**:
- Fiducia squadra influenza performance
- Momentum offensivo: squadre in striscia gol spesso continuano
- Difesa solida: clean sheet breeds clean sheet

### 5. **Home/Away Split**
```python
venue_stats = {
    'home_xg_avg': 1.8,
    'away_xg_avg': 1.2,
    'home_advantage_factor': 1.5,  # xG moltiplicatore casa
    'travel_distance': 850         # km trasferta (stanchezza)
}
```

### 6. **Rest Days & Fixture Congestion**
```python
fatigue_features = {
    'rest_days_home': 3,
    'rest_days_away': 3,
    'games_last_7_days_home': 1,
    'games_next_7_days_home': 2,   # Gestione energie se big match successivo
    'competitions_active': ['League', 'Cup']  # Multi-front strain
}
```

### 7. **Player Availability & Injuries**
```python
squad_strength = {
    'injuries_key_players': 2,
    'suspensions': 1,
    'squad_value_available': 0.85,  # 85% rosa per infortuni
    'form_top_scorer': "HOT"        # Capocannoniere in forma
}
```

---

## ⚙️ MACHINE LEARNING - BEST PRACTICES

### Model Ensemble
**Fonte**: [ML Football Predictions](https://medium.com/@davidblum_6849/revolutionizing-football-predictions-how-machine-learning-is-changing-the-game-226b986babae)

```python
ensemble_models = {
    'lgbm': 0.35,           # Peso 35%
    'xgboost': 0.30,        # Peso 30%
    'random_forest': 0.20,  # Peso 20%
    'logistic': 0.15        # Peso 15%
}

final_prediction = weighted_average(ensemble_models)
```

**Perché**:
- Riduce overfitting di singolo modello
- Cattura pattern diversi (tree-based vs linear)
- Più robusto a outlier

### Probability Calibration
```python
from sklearn.calibration import CalibratedClassifierCV

# Post-training calibration
calibrated_model = CalibratedClassifierCV(
    base_model,
    method='isotonic',  # o 'sigmoid'
    cv=5
)
```

**Perché**:
- Probabilità grezze spesso male calibrate
- 60% predetto ≠ 60% vincite reali senza calibrazione
- Essenziale per value betting accurato

### Time-Series Cross-Validation
```python
from sklearn.model_selection import TimeSeriesSplit

tscv = TimeSeriesSplit(n_splits=5)
# Train solo su passato, test su futuro
# NO data leakage da match futuri
```

---

## 📈 FEATURE ENGINEERING AVANZATO

### Rolling Windows
```python
# Ultimi N match
for N in [3, 5, 10]:
    df[f'xg_for_last_{N}'] = df.groupby('team')['xg'].rolling(N).mean()
    df[f'xg_var_last_{N}'] = df.groupby('team')['xg'].rolling(N).std()
```

### Weighted Recent Form
```python
# Match recenti pesano di più
weights = [0.35, 0.25, 0.20, 0.12, 0.08]  # Ultimi 5 match
weighted_xg = sum(xg[i] * weights[i] for i in range(5))
```

### Interaction Features
```python
# Combinazioni feature
df['xg_form_x_home_adv'] = df['xg_form'] * df['home_factor']
df['rest_gap'] = df['rest_home'] - df['rest_away']
df['strength_diff'] = df['rating_home'] - df['rating_away']
```

---

## 🎯 PRIORITY FEATURES DA IMPLEMENTARE

### TIER 1 - CRITICHE (Implementare SUBITO)
1. **Recent Form (Last 5 matches)**
   - xG for/against rolling 5
   - W-D-L record
   - Goals trend

2. **Head-to-Head (Last 5 H2H)**
   - Wins/draws/losses
   - Avg goals for/against
   - Home/away H2H split

3. **League Standings**
   - Position
   - Points
   - Goal difference

4. **Expanded Dataset**
   - Minimo 2500+ partite
   - Usare `expand_historical_dataset.py`

### TIER 2 - IMPORTANTI (Prossime 2 settimane)
5. **Momentum Indicators**
   - Winning/unbeaten streaks
   - xG trend
   - Clean sheet streaks

6. **Home/Away Split Advanced**
   - xG home vs away separati
   - Win rate casa/trasferta

7. **Model Ensemble**
   - LightGBM + XGBoost + RandomForest
   - Weighted averaging

8. **Probability Calibration**
   - Isotonic regression
   - Platt scaling

### TIER 3 - NICE-TO-HAVE (Lungo termine)
9. **Fixture Congestion**
   - Games in last/next 7 days
   - Multiple competitions

10. **Player Data**
    - Key injuries/suspensions
    - Top scorer form

---

## 📊 BENCHMARK METRICS

### FiveThirtyEight Performance
- **Brier Score OU 2.5**: ~0.19-0.21 (vs nostro 0.26)
- **Log Loss 1X2**: ~0.85-0.95 (vs nostro 1.10+)
- **Calibration**: Eccellente (predicted 60% = actual 58-62%)

### Target Realistici BET (6 mesi)
- Brier Score OU: **< 0.22** (attuale 0.26)
- Log Loss 1X2: **< 1.00** (attuale 1.10+)
- Diversità predizioni: **80%+ match con probabilità uniche** (attuale ~40%)

---

## 🚀 ACTION PLAN

### Settimana 1-2
1. ✅ Risolto: Fetch quote bulk (26/39 quote)
2. ✅ Risolto: Features populate (39/39 xG)
3. ⏳ **TODO**: Espandere dataset a 2500+ partite
4. ⏳ **TODO**: Implementare recent form (5 match)
5. ⏳ **TODO**: Implementare H2H (5 scontri)

### Settimana 3-4
6. Implementare league standings
7. Implementare momentum indicators
8. Model ensemble (LGBM + XGB + RF)
9. Probability calibration

### Mese 2
10. Advanced feature engineering
11. Hyperparameter optimization
12. Backtesting completo su stagioni storiche

---

## 📚 FONTI E RISORSE

1. [How FiveThirtyEight Club Soccer Predictions Work](https://fivethirtyeight.com/methodology/how-our-club-soccer-predictions-work/)
2. [FiveThirtyEight Club Soccer Projections](https://fivethirtyeight.com/features/how-our-club-soccer-projections-work/)
3. [Ultimate Guide to Football Stats](https://www.performanceodds.com/how-to-guides/the-ultimate-guide-to-football-stats-how-to-read-analyze-predict-todays-matches-like-a-pro/)
4. [Machine Learning Football Predictions](https://medium.com/@davidblum_6849/revolutionizing-football-predictions-how-machine-learning-is-changing-the-game-226b986babae)
5. [Atalanta vs Roma Prediction Analysis](https://footballwhispers.com/blog/atalanta-vs-roma-prediction-03-01-2026/)
6. [BetClan Today's Football Predictions](https://www.betclan.com/todays-football-predictions/)

---

**Conclusione**: Per competere con sistemi professionali, BET deve implementare **almeno 10-12 features** (vs 4-6 attuali) e aumentare dataset a **2500+ partite** (vs ~500 attuali). Le predizioni ripetitive derivano da features insufficienti e dataset limitato che non cattura variabilità reale del calcio.
