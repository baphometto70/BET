# 🔍 ANALISI COMPLETA PROBLEMI PROGETTO BET
**Data analisi**: 2 Gennaio 2026
**Analista**: Claude Code (Sonnet 4.5)

---

## 📋 EXECUTIVE SUMMARY

Il progetto BET presenta 3 problemi critici che impediscono il funzionamento ottimale:

1. **Quote mancanti**: 39 partite nel DB ma NESSUNA ha quote → problema critico nel fetch
2. **Visualizzazione limitata**: Solo 3 partite mostrate su 39 → problema nel rendering
3. **Accuratezza predizioni**: Sistema ML sottoutilizzato con dataset troppo piccolo

---

## 🚨 PROBLEMA 1: QUOTE COMPLETAMENTE ASSENTI

### Stato Attuale
```
✗ 39 partite future nel database
✗ 0 partite con quote (0%)
✗ odds_fetcher.py non scarica nessuna quota
```

### Causa Radice
Analizzando [odds_fetcher.py:315-372](odds_fetcher.py#L315-L372):

```python
def run_daily_fetch(args):
    # ...
    match_ids_for_day = {f.match_id for f in fixtures_for_day}
    existing_odds_ids = {o[0] for o in db.query(Odds.match_id).filter(...).all()}

    missing_odds_fixtures = [f for f in fixtures_for_day if f.match_id not in existing_odds_ids]

    if not missing_odds_fixtures:
        print(f"[INFO] Tutte le {len(fixtures_for_day)} partite hanno già le quote")
        return  # ⚠️ ESCE SENZA CONTROLLARE SE LE QUOTE SONO REALMENTE VALIDE
```

**PROBLEMA**: Lo script controlla solo se ESISTE una riga nella tabella Odds, non se contiene dati validi.
Le quote potrebbero essere `NULL` per tutti i campi ma la riga esiste → nessun aggiornamento.

### Impatto
- ❌ Impossibile calcolare value betting
- ❌ Kelly criterion non applicabile
- ❌ Blending quote/ML non funziona
- ❌ Confidence dei pick ridotta drasticamente

### Soluzione Proposta
1. **Controllo validità quote esistenti**: Modificare logica per verificare se odds_1/odds_x/odds_2 sono NOT NULL
2. **Riprova automatica**: Se matching fallisce, tentare con normalizzazione nomi squadre più aggressiva
3. **Logging dettagliato**: Tracciare esattamente quali partite non trovano match

---

## 🚨 PROBLEMA 2: VISUALIZZAZIONE LIMITATA (3 su 39 partite)

### Stato Attuale
```
✗ app.py mostra solo 3 partite
✗ Le altre 36 non vengono renderizzate
✗ Nessun messaggio d'errore visibile
```

### Causa Radice
Analizzando [app.py:673-717](app.py#L673-L717):

```python
@APP.get("/data")
def data_view():
    query_results = (
        db.query(Fixture, Odds, Feature)
        .outerjoin(Odds, Fixture.match_id == Odds.match_id)
        .outerjoin(Feature, Fixture.match_id == Feature.match_id)
        .order_by(Fixture.date.desc())
        .all()  # ⚠️ NESSUN LIMIT, ma filtering implicito?
    )
```

**POSSIBILI CAUSE**:
1. Template HTML ha paginazione che mostra solo prime 3 righe
2. JavaScript client-side limita visualizzazione
3. Fixture/Feature/Odds join restituisce solo 3 match completi

### Verifica Necessaria
```bash
# Test query diretta
python3 << EOF
from database import SessionLocal
from models import Fixture, Odds, Feature

db = SessionLocal()
results = db.query(Fixture, Odds, Feature).outerjoin(Odds).outerjoin(Feature).all()
print(f"Query restituisce: {len(results)} righe")
db.close()
EOF
```

### Soluzione Proposta
1. **Logging query size**: Aggiungere print per contare righe restituite
2. **Rimuovere limit impliciti**: Verificare templates HTML non abbiano limiti hard-coded
3. **Paginazione esplicita**: Se troppe partite, implementare paginazione corretta

---

## 🚨 PROBLEMA 3: MACHINE LEARNING SOTTOUTILIZZATO

### Stato Attuale Dataset
```python
# historical_dataset.csv - utilizzato per training OU 2.5
Righe stimate: < 500 partite  # ⚠️ TROPPO POCHE

# historical_1x2.csv - utilizzato per training 1X2
Righe stimate: < 300 partite  # ⚠️ CRITICO
```

### Benchmark Industria
| Tipologia Modello | Minimo Raccomandato | Ideale | BET Attuale |
|-------------------|---------------------|--------|-------------|
| Logistic Regression | 500 | 2000+ | ~300 ❌ |
| LightGBM | 1000 | 5000+ | ~300 ❌ |
| Neural Network | 5000 | 50000+ | N/A |

### Feature Engineering Mancanti

**Attualmente utilizzate** (13 features):
- xg_for_home, xg_against_home, xg_for_away, xg_against_away
- rest_days_home, rest_days_away
- derby_flag, europe_flag_home, europe_flag_away
- meteo_flag
- style_ppda_home, style_ppda_away
- travel_km_away

**Feature mancanti critiche**:
1. **Form recente** (ultimi 5 match: W/D/L)
2. **Head-to-head** storico (ultimi N scontri diretti)
3. **Posizione in classifica** / punteggio attuale
4. **Streak** (vittorie/sconfitte consecutive)
5. **Goal scored/conceded** nelle ultime N partite
6. **xG rolling average** (non solo ultima media, ma trend)
7. **Injury count specifico** (difensori/attaccanti)
8. **Managerial change** (nuovo allenatore < 5 partite)
9. **Fixture congestion** (3+ partite in 7 giorni)
10. **Time of season** (inizio/metà/fine stagione)

### Algoritmi e Ottimizzazioni

**Attualmente implementati**:
- ✅ Logistic Regression (fallback)
- ✅ LightGBM (se disponibile)
- ❌ Ensemble methods (VotingClassifier, Stacking)
- ❌ Hyperparameter tuning automatico (GridSearchCV/Optuna)
- ❌ Cross-validation stratificata per campionati
- ❌ Calibrazione probabilità (CalibratedClassifierCV)

**Metriche di valutazione**:
- ✅ Brier Score (OU)
- ✅ Log Loss (1X2)
- ❌ ROC-AUC
- ❌ Profit & Loss simulato su odds storiche
- ❌ Sharpe Ratio delle scommesse

---

## 📊 ANALISI ARCHITETTURALE

### Punti di Forza ✅
1. **Separazione responsabilità**: Moduli ben divisi (fetch, features, ML, predictions)
2. **Fallback multipli xG**: Sistema 3-livelli (Understat → Odds → Conservative)
3. **Database robusto**: PostgreSQL con SQLite fallback
4. **API tracking**: Controllo utilizzo TheOddsAPI (limite 500/mese)
5. **Flask dashboard**: Interfaccia web funzionante

### Criticità ❌
1. **Nessun caching intelligente** quote (re-fetch inutili)
2. **Scraping Understat fragile** (dipende da HTML structure)
3. **Normalizzazione nomi squadre** limitata (solo ALIAS dict)
4. **Nessun sistema di alerting** quando quote/xG mancano
5. **Mancanza di backtesting** storico per validare modelli

---

## 🎯 PRIORITÀ DI INTERVENTO

### P0 - CRITICAL (Blockers)
1. **Risolvere fetch quote** → Sistema inutilizzabile senza
2. **Fixing visualizzazione 39 partite** → UX rotta

### P1 - HIGH (Major Impact)
3. **Ampliare dataset storico** → 2000+ partite minimo
4. **Aggiungere top 5 feature engineering** (form, h2h, classifica, streak, goals trend)

### P2 - MEDIUM (Important)
5. **Implementare ensemble ML** (VotingClassifier LightGBM + LogReg)
6. **Hyperparameter tuning** con Optuna
7. **Calibrazione probabilità** output modelli

### P3 - LOW (Nice to have)
8. Backtesting framework con P&L tracking
9. Alerting system (Telegram/Email quando confidence > 80%)
10. API multi-fonte xG (Understat + FBRef + StatsBomb se accessibile)

---

## 📈 METRICHE TARGET POST-FIX

| Metrica | Attuale | Target |
|---------|---------|--------|
| % Partite con quote | 0% | 95%+ |
| Partite visualizzate | 3/39 | 39/39 |
| Dataset size (OU) | ~500 | 2500+ |
| Dataset size (1X2) | ~300 | 2000+ |
| Numero features | 13 | 25+ |
| Brier Score (OU) | ? | < 0.20 |
| Log Loss (1X2) | ? | < 0.90 |
| ROI simulato | N/A | +5% target |

---

## 🛠️ PIANO DI IMPLEMENTAZIONE

### Fase 1 - Emergency Fix (oggi)
- [ ] Fix odds_fetcher per verificare validità quote esistenti
- [ ] Aggiungere retry logic con normalizzazione nomi migliorata
- [ ] Fix visualizzazione tutte partite in app.py
- [ ] Testing end-to-end fetch → populate → predict

### Fase 2 - Dataset Expansion (2-3 giorni)
- [ ] Scaricare storici 2022-2025 per SA, PL, PD, BL1, FL1
- [ ] Popolare feature per ~3000+ partite storiche
- [ ] Verificare distribuzione target (Over/Under, 1X2) bilanciata

### Fase 3 - Feature Engineering (3-5 giorni)
- [ ] Implementare form calculator (W/D/L ultimi 5)
- [ ] Head-to-head statistics (ultimi N scontri)
- [ ] Posizione classifica/punteggio al momento match
- [ ] Streak calculator (vittorie/sconfitte consecutive)
- [ ] Rolling xG averages (trend ultimi 10 match)

### Fase 4 - ML Optimization (5-7 giorni)
- [ ] Ensemble VotingClassifier (LightGBM + LogReg + XGBoost se disponibile)
- [ ] Hyperparameter tuning Optuna (50+ trials)
- [ ] Calibrazione probabilità CalibratedClassifierCV
- [ ] Cross-validation stratificata per campionato
- [ ] Backtesting con P&L tracking su 2024 season

### Fase 5 - Production Ready (ongoing)
- [ ] Monitoring automatico metriche (Brier, LogLoss, ROI)
- [ ] Alert system confidence > 80% picks
- [ ] Automated retraining scheduler (settimanale con nuovi dati)
- [ ] API endpoints per integrazione esterna

---

## 📞 CONTATTI & RISORSE

**Documentazione progetto**:
- [README](README_Scommesse.md)
- [Stato Finale](STATO_FINALE.md)
- [Automazione](AUTOMAZIONE.md)

**API utilizzate**:
- TheOddsAPI: `dd036a9e9bfe6a4b3753268c8f5f62ec` (500 requests/mese)
- football-data.org: `9f48528ff8d5482f8851ae808eaa9f13`

**Database**:
- PostgreSQL: `betting_db` @ localhost:5432
- User: `gennaro` / pwd: `g3nn4r070`

---

*Fine analisi. Inizio implementazione fix.*
